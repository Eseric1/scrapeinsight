"""Thin async client for the Ollama HTTP API — structured-output chat."""
import json
import re

import httpx

from . import config

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=config.OLLAMA_URL, timeout=config.LLM_TIMEOUT_S)
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


_BARE_WORD = re.compile(r':\s*([A-Za-z_][A-Za-z0-9_-]*)\s*([,}\]])')
_JSON_KEYWORDS = {"true", "false", "null"}


def _quote_bare_words(text: str) -> str:
    """Quote bare identifiers used as values — seen live: {"kind": line}."""

    def fix(m):
        word = m.group(1)
        if word in _JSON_KEYWORDS:
            return m.group(0)
        return f': "{word}"{m.group(2)}'

    return _BARE_WORD.sub(fix, text)


def parse_json_content(content: str) -> dict:
    """Parse model JSON output, tolerating markdown code fences and the
    bare-enum-value quirk observed live on qwen3.5 (Ollama 0.30.8)."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    try:
        return json.loads(text)
    except ValueError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        inner = text[start : end + 1]
        try:
            return json.loads(inner)
        except ValueError:
            return json.loads(_quote_bare_words(inner))
    raise ValueError("model returned no JSON object")


async def chat_json(system: str, user: str, schema: dict) -> dict:
    """One-shot JSON-mode chat with the schema stated in the prompt.

    `think: false` is required: thinking-default models (Qwen3.5, Gemma 4)
    otherwise return an empty response (verified live). And Ollama 0.30.8 +
    qwen3.5 silently ignores a `format: <json schema>` object, while
    `format: "json"` plus a schema in the prompt produces conformant output.
    """
    system_full = (
        f"{system}\n\nReply with ONLY one JSON object that validates against this JSON "
        f"Schema — correct types, no extra keys, no prose, all string values quoted:\n"
        f"{json.dumps(schema)}"
    )
    resp = await client().post(
        "/api/chat",
        json={
            "model": config.CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system_full},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": False,
            "format": "json",
            "options": {"num_ctx": config.NUM_CTX, "temperature": 0},
        },
    )
    resp.raise_for_status()
    return parse_json_content(resp.json()["message"]["content"])


async def loaded() -> bool:
    """True when the chat model is resident in VRAM (no cold-load pause)."""
    try:
        resp = await client().get("/api/ps")
        resp.raise_for_status()
        base = config.CHAT_MODEL.split(":")[0]
        return any(m["name"].split(":")[0] == base for m in resp.json().get("models", []))
    except Exception:
        return False


async def healthy() -> dict:
    resp = await client().get("/api/tags")
    resp.raise_for_status()
    names = [m["name"] for m in resp.json().get("models", [])]
    return {"ok": True, "models": names}
