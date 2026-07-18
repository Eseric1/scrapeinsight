from fastapi.testclient import TestClient

from app import ratelimit
from app.main import app
from app.scraper import clean_text


def _run(client, body):
    with client.stream("POST", "/api/analyze", json=body) as r:
        assert r.status_code == 200
        return "".join(r.iter_text())


def test_sample_analysis_flow(fake_llm):
    with TestClient(app) as client:
        body = _run(client, {"sample": "laptops", "preset": "products"})
        assert "event: result" in body
        assert '"row_count": 8' in body.replace('": ', '": ') or "row_count" in body
        assert "insights" in body
        assert "hist-price" in body


def test_posts_preset(fake_llm):
    with TestClient(app) as client:
        body = _run(client, {"sample": "forum", "preset": "posts"})
        assert "event: result" in body
        assert "hist-score" in body


def test_private_url_rejected_in_stream(fake_llm):
    with TestClient(app) as client:
        body = _run(client, {"url": "http://192.168.1.1/admin", "preset": "products"})
        assert "event: error" in body
        assert "private or reserved" in body
        assert "event: result" not in body


def test_unknown_preset_400(fake_llm):
    with TestClient(app) as client:
        r = client.post("/api/analyze", json={"sample": "laptops", "preset": "nope"})
        assert r.status_code == 400


def test_url_and_sample_together_rejected(fake_llm):
    with TestClient(app) as client:
        r = client.post(
            "/api/analyze",
            json={"url": "https://x.com", "sample": "laptops", "preset": "products"},
        )
        assert r.status_code == 422


def test_rate_limited(fake_llm):
    with TestClient(app) as client:
        old = ratelimit.analyze_window.limit
        ratelimit.analyze_window.limit = 1
        try:
            _run(client, {"sample": "laptops", "preset": "products"})
            r = client.post("/api/analyze", json={"sample": "laptops", "preset": "products"})
            assert r.status_code == 429
        finally:
            ratelimit.analyze_window.limit = old


def test_budget_exhaustion(fake_llm, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "DAILY_LLM_BUDGET", 1)
    with TestClient(app) as client:
        r = client.post("/api/analyze", json={"sample": "laptops", "preset": "products"})
        assert r.status_code == 429


def test_presets_endpoint(fake_llm):
    with TestClient(app) as client:
        j = client.get("/api/presets").json()
        assert {p["id"] for p in j["presets"]} == {"products", "posts"}
        assert {s["id"] for s in j["samples"]} == {"laptops", "forum"}


def test_security_headers(fake_llm):
    with TestClient(app) as client:
        r = client.get("/")
        assert r.headers["X-Frame-Options"] == "DENY"
        assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_clean_text_strips_scripts():
    html = "<html><head><title>t</title></head><body><script>evil()</script><p>keep me</p></body></html>"
    text = clean_text(html)
    assert "keep me" in text
    assert "evil" not in text
