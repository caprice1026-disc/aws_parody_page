import os
import sys
import json
import traceback
from datetime import datetime
from typing import Optional, List

from flask import Flask, request, jsonify, render_template
from pydantic import BaseModel, Field, ValidationError

from openai import OpenAI
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    OpenAIError,
    RateLimitError,
    UnprocessableEntityError,
    InternalServerError,
)

# =========================
# JSON-Lines logger (stdout: info, stderr: warn/error)
# =========================
def jlog(level: str, event: str, **kwargs) -> None:
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "level": level, "event": event}
    rec.update(kwargs)
    stream = sys.stderr if level in ("warn", "error") else sys.stdout
    print(json.dumps(rec, ensure_ascii=False), file=stream, flush=True)


# =========================
# Pydantic models (structured outputs schema)
# =========================
class HeroSection(BaseModel):
    title: str = Field(description="ページのヒーロー見出し。AWS構文っぽいが固有名詞はパロディ名に合わせる")
    subtitle: str = Field(description="短いサブキャッチ。誇張と安心感の両立を狙う")
    tagline: str = Field(description="一言スローガン。例: 'Scale from zero to overcaffeinated'")

class Feature(BaseModel):
    name: str = Field(description="機能名。例: 'Serverless Espresso Autoscaling'")
    description: str = Field(description="機能の要点説明")
    benefit: str = Field(description="この機能がもたらす具体的メリット")

class PricingTier(BaseModel):
    tier: str = Field(description="プラン名。例: 'On-Demand', 'Reserved Beans'")
    price_per_unit: str = Field(description="課金単位の価格。例: '$0.023 per cup'")
    unit: str = Field(description="課金単位。例: 'cup', 'pod', 'GB-hour'")
    notes: Optional[str] = Field(default=None, description="注意書きや無料枠情報など（任意）")

class ServiceSpec(BaseModel):
    service_name: str = Field(description="架空のAWS風サービス名。例: 'AWS Elastic コーヒーポッド (AECP)'")
    summary: str = Field(description="AWS公式ドキュメント風の要約（日本語または英語）")
    hero: HeroSection = Field(description="ヒーローセクションに表示するテキスト群")
    features: List[Feature] = Field(description="主な機能のリスト（3〜7件程度）")
    integrations: List[str] = Field(description="他AWS風サービスとの統合例。例: VPC/IAM/ALB 的な名前")
    pricing: List[PricingTier] = Field(description="料金体系の概要")
    faq: List[str] = Field(description="よくある質問と答えを交互に1要素ずつ。例: 'Q: ...', 'A: ...' の配列")
    disclaimers: List[str] = Field(description="注意書き・パロディである旨・非公式である旨")


# =========================
# Flask app
# =========================
app = Flask(__name__, static_folder="static", static_url_path="/static")


def get_openai_client() -> OpenAI:
    """Create OpenAI client with explicit API key check (no crash on import)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # ここで投げずに上位で整形メッセージを返す
        raise OpenAIError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)


def build_messages(keyword: str, lang: str, tone: str) -> list:
    """System+User messages. Keep it simple; schemaが拘束を担う。"""
    system = (
        "You are a senior AWS-style technical writer. "
        "Write STRICTLY in the requested language and tone. "
        "Return ONLY a JSON object matching the provided JSON Schema. No preface."
    )
    user_payload = {
        "task": "Generate an AWS-style parody product page content using the given keyword.",
        "keyword": keyword,
        "language": lang,
        "tone": tone,
        "constraints": [
            "No real AWS trademark misuse; keep it parody.",
            "Keep descriptions crisp and product-doc-ish.",
            "Feature names feel cloud-native."
        ],
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def make_json_schema() -> dict:
    """
    Build the JSON Schema used by Structured Outputs.
    Per official docs, use response_format={type:'json_schema', json_schema:{name, schema, strict:true}}
    """
    return {
        "name": "aws_parody_spec",
        "schema": ServiceSpec.model_json_schema(),  # 各フィールドのdescription付き
        "strict": True,  # スキーマ順守を強制
    }


@app.route("/")
def index():
    # 静的トップ (任意で templates に置き換え可)
    return render_template("index.html")


@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        body = request.get_json(force=True) or {}
        keyword = str(body.get("keyword") or body.get("term") or body.get("prompt") or "").strip()
        lang = str(body.get("lang") or "ja").strip().lower()
        tone = str(body.get("tone") or "standard").strip().lower()

        if not keyword:
            return jsonify({"error": "keyword is required"}), 400
        if lang not in ("ja", "en"):
            return jsonify({"error": "lang must be 'ja' or 'en'"}), 400
        if tone not in ("standard", "overkill"):
            return jsonify({"error": "tone must be 'standard' or 'overkill'"}), 400

        jlog("info", "http.request", path="/api/generate", method="POST", lang=lang, tone=tone)

        # OpenAI 呼び出し
        client = get_openai_client()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06")  # 公式でStructured Outputs対応が明確なモデルに設定
        temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.4"))
        max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "1200"))

        messages = build_messages(keyword, lang, tone)
        response_format = {"type": "json_schema", "json_schema": make_json_schema()}

        jlog("info", "openai.request", api="chat.completions", model=model,
             temperature=temperature, max_tokens=max_tokens)

        comp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,           # Chat Completions は max_tokens
            response_format=response_format, # Structured Outputs (json_schema + strict)
            # 参考：function callingと併用する場合は parallel_tool_calls: false も検討
        )

        choice = comp.choices[0]
        raw = choice.message.content or ""
        jlog("info", "openai.response",
             finish_reason=getattr(choice, "finish_reason", None),
             usage=getattr(comp, "usage", None))

        # 期待値は“素のJSON”。念のためフェンスを剥がす処理を入れる
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
        data = json.loads(text)

        # 追加バリデーション（安心の二段ロック）
        spec = ServiceSpec.model_validate(data)
        return jsonify(spec.model_dump(mode="json"))

    except OpenAIError as e:
        # APIキー未設定を含むSDKレベルの例外
        jlog("error", "openai.error", message=str(e), trace=traceback.format_exc())
        if "OPENAI_API_KEY" in str(e):
            return jsonify({"error": "OPENAI_API_KEY is not set. Please export it before running the server."}), 500
        return jsonify({"error": "OpenAIError", "message": str(e)}), 502

    except RateLimitError as e:
        # RateLimitError は APIStatusError のサブクラス。順序に注意。
        jlog("error", "openai.error.rate_limit", message=str(e))
        return jsonify({"error": "RateLimitError", "message": str(e)}), 429

    except (BadRequestError, UnprocessableEntityError) as e:
        # スキーマ不一致などで 400/422
        jlog("error", "openai.error.request", message=str(e))
        return jsonify({"error": "RequestError", "message": str(e)}), 400

    except (APITimeoutError, APIConnectionError, InternalServerError, NotFoundError, ConflictError) as e:
        jlog("error", "openai.error.transport", kind=e.__class__.__name__, message=str(e))
        return jsonify({"error": e.__class__.__name__, "message": str(e)}), 502

    except APIStatusError as e:
        # その他のHTTPステータス
        jlog("error", "openai.error.status", status_code=getattr(e, "status_code", None), message=str(e))
        return jsonify({"error": "APIStatusError", "message": str(e)}), 502

    except ValidationError as e:
        jlog("error", "server.error.validation", errors=json.loads(e.json()))
        return jsonify({"error": "ValidationError", "details": json.loads(e.json())}), 422

    except json.JSONDecodeError as e:
        jlog("error", "server.error.json_decode", message=str(e))
        return jsonify({"error": "JSONDecodeError", "message": str(e)}), 502

    except Exception as e:
        jlog("error", "server.error.unexpected", message=str(e), trace=traceback.format_exc())
        return jsonify({"error": "UnexpectedError", "message": str(e)}), 502


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    jlog("info", "server.start", port=port)
    app.run(host="0.0.0.0", port=port, debug=False)
