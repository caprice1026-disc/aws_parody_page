import os
import sys
import json
import re
import time
import traceback
from typing import List

from flask import Flask, render_template, request, jsonify
from pydantic import BaseModel, Field, ValidationError
from dotenv import load_dotenv

# .env 読み込み
load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")

# OpenAI SDK（Responses API + Structured Outputs を使用）
from openai import OpenAI
from openai import (
    APIStatusError,        # ステータスコード付き例外（401/404/5xx など）
    APITimeoutError,       # タイムアウト
    APIConnectionError,    # 接続エラー
    RateLimitError,        # レート制限
    OpenAIError,           # 上記に該当しない SDK 例外の親
)

# =========================
#  ログ（sys 直書き・JSON Lines）
# =========================

def _log(level: str, event: str, **fields):
    '''関数の説明
    JSON-Lines で STDOUT/STDERR に出力するシンプルなロガー。
    '''
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "level": level,
        "event": event,
        **fields,
    }
    stream = sys.stderr if level == "error" else sys.stdout
    print(json.dumps(rec, ensure_ascii=False), file=stream, flush=True)


# =========================
#  Pydantic モデル（出力スキーマ）
# =========================

class FAQ(BaseModel):
    '''関数の説明
    FAQの1項目（Q/A）。
    '''
    q: str = Field(..., description="FAQの質問文。ユーザー視点の具体的な問い。")
    a: str = Field(..., description="FAQの回答文。簡潔で実用的な説明。")

class ServiceSpec(BaseModel):
    '''関数の説明
    パロディAWSサービスの構造化仕様。
    '''
    service_name: str = Field(..., description="サービス名。例: AWS Elastic <Term> / Amazon <Term> Service など、AWS風の命名。")
    tagline: str = Field(..., description="短いキャッチコピー。1行で価値を伝える。")
    summary: str = Field(..., description="冒頭の要約。AWS構文（完全マネージド/スケーラブル/セキュア/高可用/シームレス統合）。")
    highlights: List[str] = Field(default_factory=list, description="トップの箇条書きハイライト（3〜5個）。最も重要な便益を短文で。")
    features: List[str] = Field(default_factory=list, description="主な機能（5〜7個）。AWS構文で機能を列挙。")
    integrations: List[str] = Field(default_factory=list, description="統合サービスのリスト（IAM, VPC, CloudWatch, ALB, Lambda, S3, RDS, KMS, ECR 等の“っぽい”名前）。")
    getting_started: List[str] = Field(default_factory=list, description="導入手順（4〜7ステップ）。アカウント有効化から初回デプロイまで。")
    pricing: List[str] = Field(default_factory=list, description="料金の概要（3〜5項目）。無料枠の有無や課金単位も含む。")
    sample_cli: str = Field(..., description="CLI例。バッククォート無しの1つのテキスト。")
    faqs: List[FAQ] = Field(default_factory=list, description="FAQ配列。3〜5項目。")


# =========================
#  JSON Schema（Structured Outputs 用）
# =========================

def build_service_spec_json_schema(lang: str) -> dict:
    '''関数の説明
    Responses API の Structured Outputs で使用する JSON Schema（厳格）を構築する。
    '''
    object_desc = (
        "AWSの公式製品ページ風パロディの構造化出力。"
        "各フィールドはAWS構文（完全マネージド/スケーラブル/セキュア/高可用/シームレス統合）の文体で記述する。"
        f"出力言語: {'日本語' if lang == 'ja' else 'English'}。"
    )
    return {
        "name": "service_spec",
        "strict": True,  # スキーマ準拠を強制（Structured Outputs）
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "description": object_desc,
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "サービス名。例: AWS Elastic <Term> / Amazon <Term> Service。商標表記は避けて“風”の命名でも可。"
                },
                "tagline": {
                    "type": "string",
                    "description": "短いキャッチ。1文で価値を要約（誇張は控えめにリアル寄せ）。"
                },
                "summary": {
                    "type": "string",
                    "description": "冒頭概要。完全マネージド・スケーラブル・セキュア・高可用・統合を強調。"
                },
                "highlights": {
                    "type": "array",
                    "description": "トップの便益サマリ。3〜5項目。",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {"type": "string", "description": "便益を短く明快に述べた1行。"}
                },
                "features": {
                    "type": "array",
                    "description": "主な機能。5〜7項目。具体的・実務的な価値を示す。",
                    "minItems": 5,
                    "maxItems": 7,
                    "items": {"type": "string", "description": "個別の機能説明（AWS構文の語彙を適宜使用）。"}
                },
                "integrations": {
                    "type": "array",
                    "description": "統合可能な（AWS風の）サービス名。5〜10個。",
                    "minItems": 5,
                    "maxItems": 10,
                    "items": {"type": "string", "description": "例: IAM, VPC, CloudWatch, ALB, Lambda, S3, RDS, KMS, ECR 等。"}
                },
                "getting_started": {
                    "type": "array",
                    "description": "導入手順。4〜7ステップ。初期設定からデプロイ・監視まで。",
                    "minItems": 4,
                    "maxItems": 7,
                    "items": {"type": "string", "description": "操作手順を簡潔に1文で。"}
                },
                "pricing": {
                    "type": "array",
                    "description": "料金説明。3〜5項目。課金単位や無料枠・別料金（転送料など）を明記。",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {"type": "string", "description": "料金の観点（課金要素/無料枠/注意点）。"}
                },
                "sample_cli": {
                    "type": "string",
                    "description": "CLIの使用例。コードフェンス無しの平文1ブロック。"
                },
                "faqs": {
                    "type": "array",
                    "description": "FAQ配列。3〜5項目。",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "description": "FAQの1項目（QとA）。",
                        "properties": {
                            "q": {"type": "string", "description": "質問文。具体的で検索されやすい表現。"},
                            "a": {"type": "string", "description": "回答文。余計な免責や前置きは避け、端的に答える。"}
                        },
                        "required": ["q", "a"]
                    }
                }
            },
            "required": [
                "service_name", "tagline", "summary",
                "highlights", "features", "integrations",
                "getting_started", "pricing", "sample_cli", "faqs"
            ]
        }
    }


# =========================
#  プロンプト
# =========================

def build_prompt(term: str, lang: str, tone: str) -> str:
    '''関数の説明
    生成内容（意味論）だけを指示。形式・制約は JSON Schema に委譲する。
    '''
    if lang == "ja":
        lang_inst = "出力言語は日本語。"
        spice = "やや誇張して" if tone == "standard" else "強めに誇張して"
    else:
        lang_inst = "Output language is English."
        spice = "with a slightly grand tone" if tone == "standard" else "with an aggressively grand tone"

    return (
        "You are an expert AWS product marketer and solutions architect. "
        "Create a *parody* AWS-style product page description for the arbitrary term below, "
        "in the tone of official AWS docs (fully managed, scalable, secure, highly available, seamless integrations). "
        f"Arbitrary term: {term}\n"
        f"{lang_inst}\n"
        f"Tone: {spice}\n"
        "Do not include legal claims or real SLAs; keep it fictional but plausible.\n"
        "Fill every field in the provided JSON Schema faithfully."
    )


# =========================
#  OpenAI クライアント（Responses API + Structured Outputs）
# =========================

class OpenAIResponsesClient:
    '''関数の説明
    Responses API（Structured Outputs）で JSON 構造を厳密に取得するクライアント。
    '''
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def _extract_output_text(self, resp) -> str:
        '''関数の説明
        Responses API の戻りからテキスト出力を抽出する。
        output_text があればそれを、なければ output 配列を走査。
        '''
        text = getattr(resp, "output_text", None)
        if text:
            return text

        pieces = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                t = getattr(c, "text", None)
                if t:
                    pieces.append(t)
        if pieces:
            return "\n".join(pieces)

        # 取得できなければ JSON で返す（デバッグ用）
        return resp.model_dump_json()

    def generate(self, prompt: str, lang: str, temperature: float = 0.4, max_output_tokens: int = 1200) -> str:
        '''関数の説明
        Structured Outputs を使って生成し、厳格 JSON テキストを返す。
        '''
        schema = build_service_spec_json_schema(lang)

        t0 = time.perf_counter()
        _log("info", "openai.request",
             model=self.model, temperature=temperature, max_output_tokens=max_output_tokens)

        # ✅ instructions は“システム文”、input はプレーン文字列（messages ではない）
        resp = self.client.responses.create(
            model=self.model,
            instructions="You return only structured data defined by the provided JSON Schema. No prefaces.",
            input=prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": schema  # {"name","schema","strict"} を含む
            },
        )

        dt_ms = int((time.perf_counter() - t0) * 1000)
        usage = getattr(resp, "usage", None)
        usage_dict = None
        if usage:
            try:
                usage_dict = usage.model_dump() if hasattr(usage, "model_dump") else dict(usage)
            except Exception:
                usage_dict = None

        _log("info", "openai.response",
             response_id=getattr(resp, "id", None),
             model=self.model,
             latency_ms=dt_ms,
             usage=usage_dict)

        text = self._extract_output_text(resp)
        return text


# =========================
#  ルーティング
# =========================

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

    _log("info", "http.request", path="/api/generate", method="POST", lang=lang, tone=tone)

    # 最小バリデーション
    if not term:
        _log("error", "validation.error", reason="term missing")
        return jsonify({"error": "term は必須です"}), 400
    if lang not in ("ja", "en"):
        _log("error", "validation.error", reason="invalid lang", value=lang)
        return jsonify({"error": "lang は 'ja' または 'en' を指定してください"}), 400
    if tone not in ("standard", "overkill"):
        _log("error", "validation.error", reason="invalid tone", value=tone)
        return jsonify({"error": "tone は 'standard' または 'overkill' を指定してください"}), 400

    prompt = build_prompt(term=term, lang=lang, tone=tone)

    # OpenAI クライアント初期化
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        _log("error", "config.error", reason="OPENAI_API_KEY not set")
        return jsonify({"error": "サーバ設定エラー: OPENAI_API_KEY が未設定です"}), 500

    client = OpenAIResponsesClient(api_key=api_key, model=model)

    try:
        text = client.generate(prompt, lang=lang)
        obj = json.loads(text)  # Structured Outputs なので厳密 JSON のはず
        spec = ServiceSpec.model_validate(obj)  # 念のためPydanticでも検証
        _log("info", "generation.success", term=term, lang=lang, tone=tone)
        return jsonify(spec.model_dump())

    # ---------- OpenAI 由来のエラー ----------
    except RateLimitError as e:
        _log("error", "openai.error.rate_limit", message=str(e), trace=traceback.format_exc())
        return jsonify({"error": "LLM呼び出しがレート制限に達しました。時間を置いて再試行してください。"}), 502

    except APITimeoutError as e:
        _log("error", "openai.error.timeout", message=str(e), trace=traceback.format_exc())
        return jsonify({"error": "LLM応答がタイムアウトしました。"}), 502

    except APIConnectionError as e:
        _log("error", "openai.error.connection", message=str(e), trace=traceback.format_exc())
        return jsonify({"error": "LLM接続エラーが発生しました。ネットワーク/エンドポイントを確認してください。"}), 502

    except APIStatusError as e:
        status = getattr(e, "status_code", None)
        # ステータスコードに応じて人間可読メッセージを分岐
        if status == 401:
            _log("error", "openai.error.unauthorized", status_code=status, message=str(e), trace=traceback.format_exc())
            return jsonify({"error": "LLM認証に失敗しました。APIキー設定を確認してください。"}), 502
        elif status == 404:
            _log("error", "openai.error.not_found", status_code=status, message=str(e), trace=traceback.format_exc())
            return jsonify({"error": "指定のモデルやリソースが見つかりません。モデル名や設定を確認してください。"}), 502
        elif status == 400:
            _log("error", "openai.error.bad_request", status_code=status, message=str(e), trace=traceback.format_exc())
            return jsonify({"error": "LLMへの要求が不正です。プロンプト/パラメータを見直してください。"}), 502
        elif status == 422:
            _log("error", "openai.error.unprocessable", status_code=status, message=str(e), trace=traceback.format_exc())
            return jsonify({"error": "要求が処理できませんでした。JSON Schema の制約や複雑さを見直してください。"}), 502
        elif status == 409:
            _log("error", "openai.error.conflict", status_code=status, message=str(e), trace=traceback.format_exc())
            return jsonify({"error": "競合エラーが発生しました。再試行してください。"}), 502
        elif status and status >= 500:
            _log("error", "openai.error.internal", status_code=status, message=str(e), trace=traceback.format_exc())
            return jsonify({"error": "LLM側内部エラーが発生しました。"}), 502
        else:
            _log("error", "openai.error.status", status_code=status, message=str(e), trace=traceback.format_exc())
            return jsonify({"error": f"LLM呼び出しでHTTPエラーが発生しました（status={status}）。"}), 502

    except OpenAIError as e:
        _log("error", "openai.error.generic", message=str(e), trace=traceback.format_exc())
        return jsonify({"error": "LLM呼び出し中にエラーが発生しました。"}), 502

    # ---------- JSON/Pydantic/その他 ----------
    except ValidationError as e:
        _log("error", "validation.error.pydantic", message=str(e), errors=e.errors(), trace=traceback.format_exc())
        return jsonify({"error": "LLM出力の検証に失敗しました。"}), 502

    except json.JSONDecodeError as e:
        _log("error", "json.error.decode", message=str(e), trace=traceback.format_exc())
        return jsonify({"error": "LLM出力が不正なJSONでした。"}), 502

    except Exception as e:
        _log("error", "server.error.unexpected", message=str(e), trace=traceback.format_exc())
        return jsonify({"error": "不明なサーバエラーが発生しました。"}), 502


# =========================
#  エントリポイント
# =========================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    _log("info", "server.start", port=port, env="production" if not app.debug else "debug")
    app.run(host="0.0.0.0", port=port, debug=True)
