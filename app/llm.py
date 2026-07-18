"""Thin async client for the Ollama HTTP API — structured-output chat."""
import json

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


async def chat_json(system: str, user: str, schema: dict) -> dict:
    """One-shot chat constrained to a JSON schema via Ollama's `format` parameter."""
    resp = await client().post(
        "/api/chat",
        json={
            "model": config.CHAT_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "format": schema,
            "options": {"num_ctx": config.NUM_CTX, "temperature": 0},
        },
    )
    resp.raise_for_status()
    return json.loads(resp.json()["message"]["content"])


async def healthy() -> dict:
    resp = await client().get("/api/tags")
    resp.raise_for_status()
    names = [m["name"] for m in resp.json().get("models", [])]
    return {"ok": True, "models": names}
