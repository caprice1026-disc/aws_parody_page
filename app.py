# app.py (fixed)
import os
import sys
import json
import traceback
from datetime import datetime
from typing import Optional, List

from flask import Flask, request, jsonify, send_from_directory
from pydantic import BaseModel, Field, ValidationError

# ---- OpenAI SDK ----
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

# -------------- Logging helpers --------------
def jlog(level: str, event: str, **kwargs):
    payload = {"ts": datetime.now().isoformat(timespec="seconds"), "level": level, "event": event}
    payload.update(kwargs)
    stream = sys.stderr if level in ("warn", "error") else sys.stdout
    print(json.dumps(payload, ensure_ascii=False), file=stream, flush=True)

# -------------- Pydantic schemas for Structured Outputs --------------
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

# -------------- OpenAI client wrapper --------------
class LLMClient:
    def __init__(self, model: Optional[str] = None, temperature: float = 0.4, max_output_tokens: int = 1200):
        self.client = OpenAI()
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", temperature))
        self.max_output_tokens = int(os.getenv("OPENAI_MAX_TOKENS", max_output_tokens))

    def _build_messages(self, prompt: str, lang: str, tone: str):
        system = (
            "You are a senior technical writer trained on AWS product docs. "
            "Write STRICTLY in the requested language and tone. "
            "Return ONLY the structured data as requested by schema, without extra text."
        )
        # developer/system style messages (chat.completions)
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Generate an AWS-style parody product page content using the given keyword.",
                        "keyword": prompt,
                        "language": lang,
                        "tone": tone,
                        "constraints": [
                            "No real AWS trademark misuse; keep it parody.",
                            "Keep descriptions crisp and product-doc-ish.",
                            "Feature names feel cloud-native.",
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        return messages

    def generate(self, prompt: str, lang: str = "ja", tone: str = "standard") -> ServiceSpec:
        jlog("info", "openai.request", api="chat.completions", model=self.model, temperature=self.temperature, max_output_tokens=self.max_output_tokens)

        messages = self._build_messages(prompt, lang, tone)

        # ---- Path A: Pydantic-native Structured Outputs (parse) ----
        try:
            # Try the non-beta 'parse' first (newer SDKs). If missing, fall back to beta then to create().
            if hasattr(self.client.chat.completions, "parse"):
                comp = self.client.chat.completions.parse(  # type: ignore[attr-defined]
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_output_tokens=self.max_output_tokens,
                    response_format=ServiceSpec,  # Pydantic model
                )
                parsed: ServiceSpec = comp.choices[0].message.parsed  # type: ignore[assignment]
                jlog("info", "openai.response", path="chat.completions.parse", finish_reason=getattr(comp.choices[0], "finish_reason", None), usage=getattr(comp, "usage", None))
                return parsed
        except Exception as e:
            # Log and continue to Path B
            jlog("warn", "openai.parse.fallback", reason=str(e), tb=traceback.format_exc())

        # ---- Path B: JSON Schema via response_format (create) ----
        # Build strict JSON Schema from Pydantic model (OpenAI SDK will accept JSON schema dict)
        schema = {
            "name": "aws_parody_spec",
            "strict": True,
            "schema": ServiceSpec.model_json_schema(),  # includes field descriptions
        }

        try:
            cc = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_output_tokens=self.max_output_tokens,
                response_format={"type": "json_schema", "json_schema": schema},
            )
            raw = cc.choices[0].message.content
            jlog("info", "openai.response", path="chat.completions.create", finish_reason=cc.choices[0].finish_reason, usage=getattr(cc, "usage", None))
            data = json.loads(raw or "{}")
            # Validate with Pydantic for extra safety
            return ServiceSpec.model_validate(data)
        except (APIStatusError, BadRequestError, UnprocessableEntityError) as e:
            # LLMリクエストの構文・スキーマ不一致など
            jlog("error", "openai.error.request", kind=e.__class__.__name__, status=getattr(e, "status_code", None), message=str(e))
            raise
        except (RateLimitError, ConflictError) as e:
            jlog("error", "openai.error.limit", kind=e.__class__.__name__, message=str(e))
            raise
        except (APITimeoutError, APIConnectionError, InternalServerError, NotFoundError) as e:
            jlog("error", "openai.error.transport", kind=e.__class__.__name__, message=str(e))
            raise
        except OpenAIError as e:
            jlog("error", "openai.error.generic", kind=e.__class__.__name__, message=str(e))
            raise
        except Exception as e:
            jlog("error", "openai.error.unexpected", message=str(e), trace=traceback.format_exc())
            raise

# -------------- Flask app --------------
app = Flask(__name__, static_folder="static", static_url_path="/static")
llm = LLMClient()

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        body = request.get_json(force=True) or {}
        prompt = str(body.get("keyword") or body.get("prompt") or "").strip()
        lang = str(body.get("lang") or "ja")
        tone = str(body.get("tone") or "standard")
        if not prompt:
            return jsonify({"error": "keyword is required"}), 400

        jlog("info", "http.request", path=request.path, method=request.method, lang=lang, tone=tone)
        spec: ServiceSpec = llm.generate(prompt, lang=lang, tone=tone)
        return jsonify(spec.model_dump(mode="json"))
    except ValidationError as ve:
        jlog("error", "server.error.validation", errors=json.loads(ve.json()))
        return jsonify({"error": "ValidationError", "details": json.loads(ve.json())}), 422
    except (BadRequestError, UnprocessableEntityError) as e:
        return jsonify({"error": "OpenAIRequestError", "message": str(e)}), 400
    except RateLimitError as e:
        return jsonify({"error": "RateLimitError", "message": str(e)}), 429
    except (APITimeoutError, APIConnectionError, InternalServerError, NotFoundError, ConflictError) as e:
        return jsonify({"error": e.__class__.__name__, "message": str(e)}), 502
    except OpenAIError as e:
        return jsonify({"error": "OpenAIError", "message": str(e)}), 502
    except Exception as e:
        jlog("error", "server.error.unexpected", message=str(e), trace=traceback.format_exc())
        return jsonify({"error": "UnexpectedError", "message": str(e)}), 502

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    jlog("info", "server.start", port=port)
    app.run(host="0.0.0.0", port=port, debug=False)
