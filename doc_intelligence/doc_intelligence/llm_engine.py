import frappe
import time
import json
import re
import hashlib


def _strip_json_fences(text):
    """Many LLMs (especially smaller/free-tier fallback models) wrap JSON
    output in markdown code fences even when explicitly told not to.
    Strips those before json.loads(), same fix already applied to the
    entity/transaction/invoice extraction parsing in api/__init__.py."""
    return re.sub(r"```json\s*|\s*```", "", text or "").strip()

PROVIDERS = [
    {"id": "groq",       "base_url": "https://api.groq.com/openai/v1",                          "default_model": "llama-3.3-70b-versatile",                   "key_field": "groq_api_key",       "model_field": "groq_model",       "openai_compat": True},
    {"id": "gemini",     "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",  "default_model": "gemini-2.0-flash",                          "key_field": "gemini_api_key",     "model_field": "gemini_model",     "openai_compat": True},
    {"id": "cerebras",   "base_url": "https://api.cerebras.ai/v1",                               "default_model": "llama3.1-70b",                              "key_field": "cerebras_api_key",   "model_field": "cerebras_model",   "openai_compat": True},
    {"id": "openrouter", "base_url": "https://openrouter.ai/api/v1",                             "default_model": "meta-llama/llama-3.3-70b-instruct:free",    "key_field": "openrouter_api_key", "model_field": "openrouter_model", "openai_compat": True},
    {"id": "mistral",    "base_url": "https://api.mistral.ai/v1",                                "default_model": "mistral-small-latest",                      "key_field": "mistral_api_key",    "model_field": "mistral_model",    "openai_compat": True},
    {"id": "deepseek",   "base_url": "https://api.deepseek.com/v1",                          "default_model": "deepseek-chat",                             "key_field": "deepseek_api_key",   "model_field": "deepseek_model",   "openai_compat": True},
    {"id": "claude",     "base_url": None,                                                        "default_model": "claude-haiku-4-5-20251001",                 "key_field": "claude_api_key",     "model_field": "claude_model",     "openai_compat": False},
    {"id": "openai",     "base_url": "https://api.openai.com/v1",                                "default_model": "gpt-4o-mini",                               "key_field": "openai_api_key",     "model_field": "openai_model",     "openai_compat": True},
]


class _RateLimitError(Exception):
    pass


class _ProviderError(Exception):
    pass


def _get_settings():
    return frappe.get_single("Doc Intelligence Settings")


# Model names containing these tokens aren't chat/text models (audio
# transcription, TTS, moderation, prompt-guard, embeddings) so they're
# filtered out of the dropdown — selecting one would break extraction.
_NON_CHAT_MODEL_KEYWORDS = ("whisper", "guard", "orpheus", "tts", "embed", "moderation")


def list_provider_models(provider_id):
    """Fetch the live list of model IDs this provider's API key can access,
    straight from the provider's own /models endpoint — never hardcoded,
    so it can't go stale the way the old Select field options did."""
    settings = _get_settings()
    provider = next((p for p in PROVIDERS if p["id"] == provider_id), None)
    if not provider:
        frappe.throw(f"Unknown provider: {provider_id}")

    key = settings.get_password(provider["key_field"])
    if not key:
        return {"models": [], "error": "Add an API key for this provider first, then save, then refresh models."}

    cache_key = f"di_models:{provider_id}:{hashlib.md5(key.encode()).hexdigest()[:12]}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return {"models": json.loads(cached), "cached": True}

    try:
        if provider["openai_compat"]:
            from openai import OpenAI
            client = OpenAI(api_key=key, base_url=provider["base_url"], timeout=20.0, max_retries=0)
            resp = client.models.list()
            ids = [m.id for m in resp.data]
        else:
            import anthropic
            client = anthropic.Anthropic(api_key=key, timeout=20.0, max_retries=0)
            resp = client.models.list()
            ids = [m.id for m in resp.data]
    except Exception as e:
        return {"models": [], "error": str(e)[:200]}

    ids = sorted({m for m in ids if not any(k in m.lower() for k in _NON_CHAT_MODEL_KEYWORDS)})
    frappe.cache().set_value(cache_key, json.dumps(ids), expires_in_sec=3600)
    return {"models": ids}


def _get_provider_config(settings, tenant_name=None):
    # NOTE: tenant_name is accepted for call-signature compatibility but
    # unused — multi-tenant BYO-key routing was removed along with the
    # billing/tenant system.
    enabled = [p.strip() for p in (settings.enabled_providers or "groq,gemini,cerebras,openrouter,mistral,claude").split(",")]
    ordered = []
    for pid in enabled:
        p = next((x for x in PROVIDERS if x["id"] == pid), None)
        if not p:
            continue
        key = settings.get_password(p["key_field"]) if getattr(settings, p["key_field"], None) else None
        if key:
            ordered.append({**p, "_key": key})
    return ordered


def _log_provider_call(provider_id, success, tokens, error=None):
    try:
        frappe.get_doc({
            "doctype": "DI Provider Log",
            "provider": provider_id,
            "timestamp": frappe.utils.now_datetime(),
            "success": 1 if success else 0,
            "tokens": tokens,
            "error": str(error)[:140] if error else "",
        }).insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        pass


# UAE dirham is pegged at 3.6725 per US dollar. OpenRouter reports usage.cost in USD.
AED_PER_USD = 3.6725


def begin_usage():
    """Start summing tokens and provider cost for the current job."""
    frappe.local.di_usage = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "priced": False}


def take_usage():
    """Return the summed usage and stop recording."""
    bucket = getattr(frappe.local, "di_usage", None)
    frappe.local.di_usage = None
    if not isinstance(bucket, dict):
        return {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "priced": False}
    return bucket


def aed_per_usd():
    """Dirhams per dollar from settings, or the official peg when unset."""
    try:
        rate = float(_get_settings().get("aed_per_usd") or 0)
    except Exception:
        rate = 0
    return rate if rate > 0 else AED_PER_USD


def _note_usage(result):
    bucket = getattr(frappe.local, "di_usage", None)
    if not isinstance(bucket, dict) or not isinstance(result, dict):
        return
    bucket["tokens_in"] += int(result.get("tokens_in") or 0)
    bucket["tokens_out"] += int(result.get("tokens_out") or 0)
    if result.get("cost_usd") is not None:
        bucket["cost_usd"] += float(result["cost_usd"])
        bucket["priced"] = True


def _raw_response_json(raw):
    response = getattr(raw, "http_response", None)
    text = getattr(response, "text", None) if response is not None else None
    if text is None and response is not None:
        content = getattr(response, "content", b"") or b""
        if isinstance(content, bytes):
            text = content.decode("utf-8", errors="replace")
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _chat_create(client, provider, **kwargs):
    """Return (parsed response, raw JSON). OpenRouter's USD cost is only in the raw body."""
    if provider["id"] != "openrouter":
        return client.chat.completions.create(**kwargs), None
    raw = client.chat.completions.with_raw_response.create(**kwargs)
    return raw.parse(), _raw_response_json(raw)


def _usage_from(resp, body):
    usage = getattr(resp, "usage", None)
    raw_usage = {}
    if isinstance(body, dict) and isinstance(body.get("usage"), dict):
        raw_usage = body["usage"]
    tokens_in = int(getattr(usage, "prompt_tokens", 0) or raw_usage.get("prompt_tokens") or 0)
    tokens_out = int(getattr(usage, "completion_tokens", 0) or raw_usage.get("completion_tokens") or 0)
    cost = raw_usage.get("cost")
    if cost is None and usage is not None:
        cost = getattr(usage, "cost", None)
        extra = getattr(usage, "model_extra", None) or {}
        if cost is None and isinstance(extra, dict):
            cost = extra.get("cost")
    cost_usd = None
    if cost is not None:
        try:
            cost_usd = float(cost)
        except (TypeError, ValueError):
            cost_usd = None
    return tokens_in, tokens_out, cost_usd


def _completion_token_limit(provider, model, max_tokens):
    """gpt-5 and o-series reject max_tokens and return an empty completion."""
    if provider["id"] == "openai" and str(model or "").lower().startswith(("gpt-5", "o1", "o3", "o4")):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens}


def _call_openai_compat(provider, prompt, system, max_tokens, settings):
    from openai import OpenAI, RateLimitError, APIStatusError
    key = provider.get("_override_key") or provider.get("_key") or settings.get_password(provider["key_field"])
    model = getattr(settings, provider["model_field"], None) or provider["default_model"]
    extra_headers = {}
    if provider["id"] == "openrouter":
        extra_headers = {"HTTP-Referer": "https://github.com/roysbike/nexterp-doc-intelligence", "X-Title": "Doc Intelligence"}
    try:
        client = OpenAI(api_key=key, base_url=provider["base_url"], default_headers=extra_headers, timeout=90.0, max_retries=1)
        resp, body = _chat_create(
            client, provider,
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            **_completion_token_limit(provider, model, max_tokens),
        )
        text = resp.choices[0].message.content
        tokens_in, tokens_out, cost_usd = _usage_from(resp, body)
        return {"text": text, "provider": provider["id"], "model": model,
                "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost_usd}
    except RateLimitError as e:
        raise _RateLimitError(str(e))
    except APIStatusError as e:
        if e.status_code in (429, 502, 503):
            raise _RateLimitError(str(e))
        raise _ProviderError(str(e))
    except Exception as e:
        raise _ProviderError(str(e))


def _call_claude(provider, prompt, system, max_tokens, settings):
    import anthropic
    key = provider.get("_override_key") or provider.get("_key") or settings.get_password(provider["key_field"])
    model = getattr(settings, provider["model_field"], None) or provider["default_model"]
    try:
        client = anthropic.Anthropic(api_key=key, timeout=90.0, max_retries=1)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text
        tokens_in = resp.usage.input_tokens
        tokens_out = resp.usage.output_tokens
        return {"text": text, "provider": "claude", "model": model,
                "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": None}
    except anthropic.RateLimitError as e:
        raise _RateLimitError(str(e))
    except Exception as e:
        raise _ProviderError(str(e))


def llm_call(prompt, system="You are a helpful AI assistant.", max_tokens=2000, tenant_name=None, json_mode=False):
    settings = _get_settings()
    providers = _get_provider_config(settings, tenant_name)
    if not providers:
        frappe.throw("No LLM providers configured. Go to LLM Provider Settings and add at least one API key.")
    if json_mode:
        system = system + "\n\nYou MUST respond with valid JSON only. No preamble, no markdown, no backticks."
    tried = []
    fallback_used = False
    for i, p in enumerate(providers):
        try:
            if p["openai_compat"]:
                result = _call_openai_compat(p, prompt, system, max_tokens, settings)
            else:
                result = _call_claude(p, prompt, system, max_tokens, settings)
            _log_provider_call(p["id"], True, result.get("tokens_out", 0))
            result["fallback_used"] = i > 0
            result["attempts"] = i + 1
            _note_usage(result)
            return result
        except (_RateLimitError, _ProviderError) as e:
            _log_provider_call(p["id"], False, 0, e)
            detail = str(e).strip().replace("\n", " ")
            if len(detail) > 160:
                detail = detail[:160] + "…"
            tried.append(f"{p['id']} ({type(e).__name__}: {detail})" if detail else f"{p['id']} ({type(e).__name__})")
            fallback_used = True
            if isinstance(e, _RateLimitError):
                time.sleep(0.3)
            continue
    frappe.throw(f"All LLM providers exhausted. Tried: {', '.join(tried)}")


def analyse_document(raw_text, document_type, tenant_name=None, max_tokens=2000, source_format=None, output_language="en"):
    from doc_intelligence.doc_intelligence.prompts import get_analysis_prompt, language_instruction
    rules = get_analysis_prompt()
    source = source_format or "unknown"
    prompt = f"""{rules}

{language_instruction(output_language)}

Document category: {document_type}
Source format: {source}

Return a JSON object with these exact keys:
- "summary": string, 3-5 sentences in Russian: what the document is, who the parties are, and whether the mandatory tax-invoice fields are present
- "entities": string, bullet list of names, TRNs, dates, amounts, and currency actually printed
- "tables": array of objects, each with "headers" (array of strings) and "rows" (array of arrays). Empty array if no tables found. Include only real charged lines.
- "accounting": object with these keys, using null when the value is not printed:
  document_kind, supplier_name, supplier_address, supplier_trn,
  buyer_name, buyer_address, buyer_trn,
  invoice_number, invoice_date, supply_date, due_date, currency,
  lines (array of description, qty, rate, amount, vat_rate, vat_amount),
  taxable_amount, vat_amount, grand_total, vat_rate_stated,
  missing_mandatory (array of strings), warnings (array of strings)

Document text:
---
{raw_text[:12000]}
---"""
    system = "You are an expert document analyst for UAE bookkeeping. Extract only what is printed. Return valid JSON."
    result = llm_call(prompt, system, max_tokens, tenant_name, json_mode=True)
    try:
        parsed = json.loads(_strip_json_fences(result["text"]))
    except Exception:
        parsed = {"summary": result["text"], "entities": "", "tables": []}
    parsed["_meta"] = result
    return parsed


def ask_question(raw_text, title, document_type, question, tenant_name=None, max_tokens=2000, output_language="en"):
    from doc_intelligence.doc_intelligence.prompts import language_instruction
    prompt = f"""Document: "{title}" ({document_type})
---
{raw_text[:12000]}
---
Question: {question}

{language_instruction(output_language)}
Answer the question based solely on the document content. If the information is not present, say so explicitly."""
    system = "You are a precise document Q&A assistant. Only use information from the provided document."
    result = llm_call(prompt, system, max_tokens, tenant_name)
    return {"answer": result["text"], "_meta": result}


def compare_documents(text_a, title_a, text_b, title_b, aspect=None, tenant_name=None, max_tokens=2000, output_language="en"):
    from doc_intelligence.doc_intelligence.prompts import language_instruction
    aspect_str = f" Focus specifically on: {aspect}." if aspect else ""
    prompt = f"""Compare these two documents and return a JSON object with keys:
- "summary": string, 2-3 sentence overall comparison
- "similarities": array of strings
- "differences": array of objects with keys "aspect", "doc_a", "doc_b"
- "recommendation": string

Document A: "{title_a}"
---
{text_a[:6000]}
---

Document B: "{title_b}"
---
{text_b[:6000]}
---
{aspect_str}
{language_instruction(output_language)}"""
    system = "You are an expert document comparison analyst."
    result = llm_call(prompt, system, max_tokens, tenant_name, json_mode=True)
    try:
        parsed = json.loads(_strip_json_fences(result["text"]))
    except Exception:
        parsed = {"summary": result["text"], "similarities": [], "differences": [], "recommendation": ""}
    parsed["_meta"] = result
    return parsed


def get_provider_health():
    data = frappe.db.sql("""
        SELECT provider,
               COUNT(*) as total,
               SUM(success) as successes,
               SUM(tokens) as total_tokens,
               MAX(timestamp) as last_call
        FROM `tabDI Provider Log`
        WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        GROUP BY provider
    """, as_dict=True)
    for row in data:
        row["success_rate"] = round(row["successes"] / row["total"] * 100, 1) if row["total"] else 0
    return data
# =====================================================================
# VISION / IMAGE OCR  —  append to:
#   apps/doc_intelligence/doc_intelligence/doc_intelligence/llm_engine.py
#
# Adds vision_extract_text(image_path): sends an image to a
# vision-capable provider (Gemini via OpenAI-compat, or Claude) and
# returns the transcribed text. Reuses the same settings + provider
# ordering + fallback approach as llm_call.
# =====================================================================

import base64
import os

# Providers in PROVIDERS that can actually read images. OpenAI is included
# because the selected model may accept images; a text-only model still fails
# at request time and the next vision provider is tried.
_VISION_PROVIDER_IDS = {"gemini", "claude", "openrouter", "openai"}

_VISION_SYSTEM = (
    "You are an OCR and document-transcription engine. Transcribe ALL text "
    "visible in the image faithfully. Preserve line items, tables (as rows of "
    "values), numbers, dates, names, and totals exactly as shown. Output only "
    "the transcribed text — no commentary."
)

_VISION_PROMPT = (
    "Transcribe every piece of text in this document image. "
    "Keep tables readable as rows. Do not summarise; output the raw text."
)


def _mime_for(path):
    ext = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "image/jpeg")


def _vision_call_openai_compat(provider, image_b64, mime, max_tokens, settings):
    """Gemini / OpenRouter vision via OpenAI-compatible image_url content."""
    from openai import OpenAI, RateLimitError, APIStatusError
    key = provider.get("_override_key") or provider.get("_key") or settings.get_password(provider["key_field"])
    model = getattr(settings, provider["model_field"], None) or provider["default_model"]
    extra_headers = {}
    if provider["id"] == "openrouter":
        extra_headers = {"HTTP-Referer": "https://github.com/roysbike/nexterp-doc-intelligence", "X-Title": "Doc Intelligence"}
    try:
        client = OpenAI(api_key=key, base_url=provider["base_url"], default_headers=extra_headers, timeout=90.0, max_retries=1)
        resp, body = _chat_create(
            client, provider,
            model=model,
            messages=[
                {"role": "system", "content": _VISION_SYSTEM},
                {"role": "user", "content": [
                    {"type": "text", "text": _VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ]},
            ],
            **_completion_token_limit(provider, model, max_tokens),
        )
        text = resp.choices[0].message.content
        tokens_in, tokens_out, cost_usd = _usage_from(resp, body)
        return {"text": text, "provider": provider["id"], "model": model,
                "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost_usd}
    except RateLimitError as e:
        raise _RateLimitError(str(e))
    except APIStatusError as e:
        if e.status_code in (429, 502, 503):
            raise _RateLimitError(str(e))
        raise _ProviderError(str(e))
    except Exception as e:
        raise _ProviderError(str(e))


def _vision_call_claude(provider, image_b64, mime, max_tokens, settings):
    import anthropic
    key = provider.get("_override_key") or provider.get("_key") or settings.get_password(provider["key_field"])
    model = getattr(settings, provider["model_field"], None) or provider["default_model"]
    try:
        client = anthropic.Anthropic(api_key=key, timeout=90.0, max_retries=1)
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=_VISION_SYSTEM,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": _VISION_PROMPT},
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": image_b64}},
            ]}],
        )
        text = resp.content[0].text
        return {"text": text, "provider": "claude", "model": model,
                "tokens_in": resp.usage.input_tokens, "tokens_out": resp.usage.output_tokens,
                "cost_usd": None}
    except anthropic.RateLimitError as e:
        raise _RateLimitError(str(e))
    except Exception as e:
        raise _ProviderError(str(e))


def vision_extract_text(image_path, tenant_name=None, max_tokens=4000):
    """OCR an image to text using the first available vision-capable provider."""
    settings = _get_settings()
    all_providers = _get_provider_config(settings, tenant_name)
    providers = [p for p in all_providers if p["id"] in _VISION_PROVIDER_IDS]
    if not providers:
        frappe.throw(
        "No vision-capable LLM provider configured. Add an OpenRouter, Gemini, "
        "Claude, or OpenAI key in Doc Intelligence Settings to process images."
        )

    # image_path is not raw user input; it's constructed by extract_text()
    # via os.path.basename() joined against the site's own private/public
    # files directory, which already strips any path-traversal components
    # before this is called.
    with open(image_path, "rb") as f:  # nosemgrep: frappe-security-file-traversal
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    mime = _mime_for(image_path)

    tried = []
    for i, p in enumerate(providers):
        # up to 3 attempts per provider on rate-limit, with backoff
        for attempt in range(3):
            try:
                if p["id"] == "gemini":
                    result = _vision_call_gemini_native(p, image_b64, mime, max_tokens, settings)
                elif p["openai_compat"]:
                    result = _vision_call_openai_compat(p, image_b64, mime, max_tokens, settings)
                else:
                    result = _vision_call_claude(p, image_b64, mime, max_tokens, settings)
                _log_provider_call(p["id"], True, result.get("tokens_out", 0))
                _note_usage(result)
                return result.get("text", "")
            except _RateLimitError as e:
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))  # 2s, then 4s
                    continue
                _log_provider_call(p["id"], False, 0, e)
                tried.append(f"{p['id']} (RateLimit after retries)")
                break
            except _ProviderError as e:
                _log_provider_call(p["id"], False, 0, e)
                detail = str(e).strip().replace("\n", " ")
                if len(detail) > 160:
                    detail = detail[:160] + "…"
                tried.append(f"{p['id']} ({type(e).__name__}: {detail})" if detail else f"{p['id']} ({type(e).__name__})")
                break
    frappe.throw(f"All vision providers exhausted. Tried: {', '.join(tried)}. "
                 f"If this is a Gemini free-tier quota limit, wait a minute and retry, "
                 f"or add a Claude API key as a backup vision provider.")


def _vision_call_gemini_native(provider, image_b64, mime, max_tokens, settings):
    """Gemini vision via native generateContent endpoint (works with AQ.* keys)."""
    import requests
    key = provider.get("_override_key") or provider.get("_key") or settings.get_password(provider["key_field"])
    model = getattr(settings, provider["model_field"], None) or provider["default_model"]
    model = model.replace("models/", "")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{
            "parts": [
                {"text": _VISION_SYSTEM + "\n\n" + _VISION_PROMPT},
                {"inline_data": {"mime_type": mime, "data": image_b64}},
            ]
        }],
        "generationConfig": {"maxOutputTokens": max_tokens},
    }
    try:
        r = requests.post(url, headers={"x-goog-api-key": key}, json=payload, timeout=120)
        if r.status_code in (429, 502, 503):
            raise _RateLimitError(r.text[:200])
        if r.status_code != 200:
            raise _ProviderError(f"{r.status_code}: {r.text[:200]}")
        data = r.json()
        cand = (data.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        return {"text": text, "provider": "gemini", "model": model,
                "tokens_in": usage.get("promptTokenCount", 0),
                "tokens_out": usage.get("candidatesTokenCount", 0),
                "cost_usd": None}
    except (_RateLimitError, _ProviderError):
        raise
    except Exception as e:
        raise _ProviderError(str(e))

