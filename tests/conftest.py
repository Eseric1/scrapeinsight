import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, ratelimit  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "BUDGET_FILE", tmp_path / "budget.json")
    ratelimit.analyze_window._hits.clear()
    yield


@pytest.fixture
def fake_llm(monkeypatch):
    """Schema-aware canned responses; no network."""
    from app import llm

    async def fake_chat_json(system, user, schema):
        props = schema.get("properties", {})
        if "insights" in props:
            return {"insights": ["Mean price is 145.0.", "Max rating is 4.5.", "8 records found."]}
        if "price" in json.dumps(schema):
            return {
                "items": [
                    {
                        "name": f"Item {i}",
                        "price": 100 + i * 10,
                        "rating": 3.5 + (i % 3) * 0.5,
                        "category": ["Budget", "Gaming"][i % 2],
                    }
                    for i in range(8)
                ]
            }
        return {
            "items": [
                {"title": f"Post {i}", "score": 10 * (i + 1), "comments": i, "author": f"u{i % 3}"}
                for i in range(8)
            ]
        }

    async def fake_healthy():
        return {"ok": True, "models": [config.CHAT_MODEL]}

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    async def fake_loaded():
        return True

    monkeypatch.setattr(llm, "healthy", fake_healthy)
    monkeypatch.setattr(llm, "loaded", fake_loaded)
    return llm
