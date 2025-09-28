import os
import json
import re
from typing import List, Optional

from flask import Flask, render_template, request, jsonify
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

# .env 読み込み（なければスキップ）
load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")

# OpenAI クライアントはオプション。未インストールでも動くように遅延 import。
OPENAI_AVAILABLE = True
try:
    from openai import OpenAI  # openai>=1.x の想定
except Exception:
    OPENAI_AVAILABLE = False


class FAQ(BaseModel):
    """FAQ の 1 項目を表現する Pydantic モデル"""
    q: str = Field(..., description="質問文")
    a: str = Field(..., description="回答文")


class ServiceSpec(BaseModel):
    """LLM から返ってくる（返させる）サービス仕様 JSON の形式"""
    service_name: str = Field(..., description="サービス名（例: AWS Elastic Coffee Pod）")
    tagline: str = Field(..., description="短いキャッチコピー")
    summary: str = Field(..., description="冒頭の要約（AWS構文）")
    highlights: List[str] = Field(default_factory=list, description="トップの箇条書きハイライト（3〜5個）")
    features: List[str] = Field(default_factory=list, description="主な機能（AWS構文）")
    integrations: List[str] = Field(default_factory=list, description="連携サービス名のリスト")
    getting_started: List[str] = Field(default_factory=list, description="導入手順のステップ")
    pricing: List[str] = Field(default_factory=list, description="価格体系の説明箇条書き")
    sample_cli: str = Field(..., description="CLI 例（コードブロックなし生テキスト）")
    faqs: List[FAQ] = Field(default_factory=list, description="FAQ の配列")


def build_prompt(term: str, lang: str, tone: str) -> str:
    '''関数の説明
    任意の単語 (term) から AWS 構文のパロディ説明 JSON を生成するためのプロンプト文字列を組み立てる。
    lang は "ja" または "en"。tone は文章の盛り具合（例: "standard" / "overkill"）。
    '''
    # 日本語・英語での出力条件を切り替える
    if lang == "ja":
        lang_inst = (
            "出力は必ず日本語。"
        )
        # 遊びを少しだけ
        spice = "やや誇張して" if tone == "standard" else "強めに誇張して"
    else:
        lang_inst = (
            "Output must be in English."
        )
        spice = "with a slightly grand tone" if tone == "standard" else "with an aggressively grand tone"

    # JSON 以外の文字を出さないように厳命
    prompt = f"""
You are an expert AWS product marketer and solutions architect.
Write a **parody** AWS-style service page description in strict JSON (no markdown, no commentary, no code fences).

Constraints:
- Style: official AWS documentation tone ("AWS構文"): fully managed, scalable, secure, integrated, high availability, reliability, seamless integration, etc.
- It is a parody for the arbitrary term: "{term}" (make it sound like a real AWS service).
- Create a plausible AWS-like name (e.g., "AWS Elastic <Term>" or "Amazon <Term> Service").
- DO NOT include real legal claims; keep it fictional but believable.
- {lang_inst}
- Return **ONLY** valid JSON per the schema below. No extra keys. No trailing commas. No markdown code fences.

Tone: {spice}

Schema (JSON keys only):
{{
  "service_name": string,
  "tagline": string,
  "summary": string,
  "highlights": [string, ...],
  "features": [string, ...],
  "integrations": [string, ...],
  "getting_started": [string, ...],
  "pricing": [string, ...],
  "sample_cli": string,
  "faqs": [{{"q": string, "a": string}}, ...]
}}

Quality bar:
- "highlights": 3-5 bullets
- "features": 5-7 bullets
- "integrations": 5-10 realistic AWS services (ALB, IAM, VPC, CloudWatch, Lambda, S3, RDS, etc.), or equivalents if language is Japanese
- "getting_started": 4-7 steps
- "pricing": 3-5 bullets with free tier-ish note
- "sample_cli": plausible CLI showing create/deploy using the service name; no backticks
- "faqs": 3-5 Q&A items

Again, respond with STRICT JSON ONLY.
"""
    return prompt.strip()


class LLMClient:
    '''関数の説明
    LLM へのインターフェースを抽象化するための基底クラス。
    '''

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 900) -> str:
        '''関数の説明
        実装クラスでプロンプトからテキストを生成する。戻り値は LLM の生テキスト。
        '''
        raise NotImplementedError


class OpenAILLMClient(LLMClient):
    '''関数の説明
    OpenAI API を用いた LLM クライアント。openai>=1.x を想定。
    '''

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        # 日本語コメント：OpenAI クライアントの初期化
        if not OPENAI_AVAILABLE:
            raise RuntimeError("openai ライブラリが利用できません。requirements を確認してください。")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 900) -> str:
        '''関数の説明
        OpenAI Chat Completions 互換 API を叩いてテキストを生成する。
        '''
        # 日本語コメント：モデル名は環境変数で差し替え可能にする
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content


class DummyLLMClient(LLMClient):
    '''関数の説明
    オフラインでも動作確認ができるダミー LLM クライアント。
    入力単語から決め打ちの JSON を返す。
    '''

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 900) -> str:
        '''関数の説明
        ダミー応答を JSON 文字列として返す。
        '''
        # 日本語コメント：プロンプトから term を雑に抽出（デモ用）
        m = re.search(r'term:\s*"([^"]+)"', prompt)
        term = m.group(1) if m else "サンプル"

        service_name = f"AWS Elastic {term}".strip()
        sample = {
            "service_name": service_name,
            "tagline": f"{term} を、クラウド級の可用性で。",
            "summary": f"{service_name} は、{term} のライフサイクルをフルマネージドで最適化し、スケーラブルでセキュアな運用を容易にします。AWS の信頼性と統合により、設計から運用、可観測性までを一貫して提供します。",
            "highlights": [
                "フルマネージドで運用負荷を大幅削減",
                "需要に応じた自動スケーリング",
                "IAM と統合したロールベースアクセス制御",
                "VPC 内でのセキュアな分離実行"
            ],
            "features": [
                "高可用なコントロールプレーンで {term} をオーケストレーション",
                "CloudWatch によるメトリクス/ログの一元監視",
                "ALB 連携でトラフィックをインテリジェントに分配",
                "Fargate/EC2 いずれのワークロードでも動作",
                "Well-Architected に準拠したリファレンス実装"
            ],
            "integrations": ["IAM", "VPC", "CloudWatch", "ALB", "Lambda", "S3", "RDS", "KMS", "ECR"],
            "getting_started": [
                "AWS アカウントで本サービスを有効化",
                f"必要な IAM ロールを作成し {term} 用ポリシーを適用",
                "VPC/サブネット/セキュリティグループを設定",
                f"{term} のワークロード定義を登録してデプロイ",
                "CloudWatch でメトリクスとログを確認"
            ],
            "pricing": [
                "コントロールプレーン課金 + 実行リソースの従量課金",
                "データ転送料金は別途適用",
                "無料利用枠: 月間 {term} ジョブ 100 回相当まで"
            ],
            "sample_cli": f"aws elastic-{term}-service create --name demo --replicas 3 --region ap-northeast-1",
            "faqs": [
                {"q": "オンプレミスでも動きますか？", "a": "はい。AWS Outposts やハイブリッド構成に対応します。"},
                {"q": "スケーリングの指標は？", "a": "CPU/メモリ/カスタムメトリクスに基づくポリシーを設定できます。"},
                {"q": "セキュリティは？", "a": "IAM/KMS/PrivateLink など標準機能と統合されています。"}
            ],
        }
        # 日本語コメント：{term} を実値で置換
        sample["features"][0] = sample["features"][0].format(term=term)
        return json.dumps(sample, ensure_ascii=False)


def get_llm_client() -> LLMClient:
    '''関数の説明
    環境変数から LLM の種別を判断し、適切なクライアントを返す。
    OPENAI_API_KEY があれば OpenAI を、なければ Dummy。
    '''
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if api_key and OPENAI_AVAILABLE:
        return OpenAILLMClient(api_key=api_key, model=model)
    return DummyLLMClient()


def coerce_json(text: str) -> dict:
    '''関数の説明
    LLM の出力から不要なバッククォートやプレフィックスを除去し、厳密に JSON として読み込む。
    '''
    # 日本語コメント：コードフェンスの除去
    text = text.strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```|\s*```$", "", text)
    # 日本語コメント：先頭に余計な説明文が混ざった場合に最初の { から末尾の } までを抽出
    m = re.search(r"{.*}", text, flags=re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)


@app.get("/")
def index():
    '''関数の説明
    トップページ（テンプレート）を返す。
    '''
    return render_template("index.html")


@app.post("/api/generate")
def api_generate():
    '''関数の説明
    任意の単語から AWS 構文パロディ JSON を生成して返す API。
    リクエスト JSON: {"term": str, "lang": "ja"|"en", "tone": "standard"|"overkill"}
    '''
    data = request.get_json(silent=True) or {}
    term = (data.get("term") or "").strip()
    lang = (data.get("lang") or "ja").strip().lower()
    tone = (data.get("tone") or "standard").strip().lower()

    # 日本語コメント：最小バリデーション
    if not term:
        return jsonify({"error": "term は必須です"}), 400
    if lang not in ("ja", "en"):
        return jsonify({"error": "lang は 'ja' または 'en' を指定してください"}), 400
    if tone not in ("standard", "overkill"):
        return jsonify({"error": "tone は 'standard' または 'overkill' を指定してください"}), 400

    # 日本語コメント：プロンプト作成 → 生成
    prompt = build_prompt(term=term, lang=lang, tone=tone)
    client = get_llm_client()
    try:
        raw = client.generate(prompt)
        obj = coerce_json(raw)
        spec = ServiceSpec.model_validate(obj)
    except ValidationError as ve:
        return jsonify({"error": "LLM 出力の検証に失敗しました", "detail": ve.errors()}), 500
    except Exception as e:
        # 日本語コメント：LLM 側の不具合や整形失敗時もダミー応答でフォールバック
        dummy = DummyLLMClient().generate(prompt)
        obj = coerce_json(dummy)
        spec = ServiceSpec.model_validate(obj)

    return jsonify(spec.model_dump())


if __name__ == "__main__":
    '''関数の説明
    ローカル開発用のエントリポイント。ポートは PORT 環境変数で上書き可。
    '''
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
