import json

from fastapi.testclient import TestClient

from app import ratelimit, scraper
from app.main import app
from app.scraper import clean_text


def _jsonld_page(n_products: int = 20) -> str:
    """Fixture page shaped like the live LEGO/IKEA pages: ItemList of
    ListItem-wrapped Products, mixed offers shapes."""
    items = []
    for i in range(n_products):
        offers = (
            {"@type": "Offer", "price": str(20 + i)}
            if i % 2 == 0
            else {"@type": "Offer", "priceSpecification": [{"price": 20 + i}]}
        )
        items.append(
            {
                "@type": "ListItem",
                "position": i + 1,
                "item": {
                    "@type": "Product",
                    "name": f"Set {i}",
                    "url": f"https://example.com/p/{i}",
                    "image": f"https://example.com/img/{i}.png",
                    "offers": offers,
                    "aggregateRating": {"@type": "AggregateRating", "ratingValue": 4.0 + (i % 10) / 10},
                },
            }
        )
    ld = {"@type": "ItemList", "itemListElement": items}
    return f'<html><head><script type="application/ld+json">{json.dumps(ld)}</script></head><body>x</body></html>'


def _patch_fetch(monkeypatch, html: str):
    async def fake_fetch(url):
        return url, html

    monkeypatch.setattr(scraper, "fetch_html", fake_fetch)


def test_live_target_flow_structured(fake_llm, monkeypatch):
    _patch_fetch(monkeypatch, _jsonld_page(20))
    with TestClient(app) as client:
        with client.stream(
            "POST", "/api/analyze", json={"target": "lego-star-wars"}
        ) as r:
            assert r.status_code == 200
            body = "".join(r.iter_text())
        assert "event: result" in body
        payload = json.loads(body.split("event: result\ndata: ")[1].split("\n")[0])
        assert payload["extraction"] == "structured"
        assert payload["total_found"] == 20
        assert payload["cap"] == 16
        assert len(payload["records"]) == 16          # display capped
        assert payload["stats"]["row_count"] == 20    # stats over everything
        assert payload["showcase"]["name"].startswith("Set")
        assert payload["showcase"]["url"].startswith("https://")
        assert payload["source"]["brand"] == "LEGO"
        assert payload["fetched_at"]


def test_llm_fallback_when_no_jsonld(fake_llm, monkeypatch):
    _patch_fetch(monkeypatch, "<html><body><p>Widget A $10. Widget B $20. Widget C $30.</p></body></html>")
    with TestClient(app) as client:
        with client.stream(
            "POST", "/api/analyze", json={"target": "ikea-desks"}
        ) as r:
            body = "".join(r.iter_text())
        assert "event: result" in body
        payload = json.loads(body.split("event: result\ndata: ")[1].split("\n")[0])
        assert payload["extraction"] == "llm"
        assert payload["records"][0]["category"] == "Desks"


def test_unknown_target_400(fake_llm):
    with TestClient(app) as client:
        r = client.post("/api/analyze", json={"target": "walmart-everything"})
        assert r.status_code == 400


def test_arbitrary_url_no_longer_accepted(fake_llm):
    with TestClient(app) as client:
        r = client.post("/api/analyze", json={"url": "https://example.com", "preset": "products"})
        assert r.status_code == 422  # target field required; free URLs are gone


def test_rate_limited(fake_llm, monkeypatch):
    _patch_fetch(monkeypatch, _jsonld_page(5))
    with TestClient(app) as client:
        old = ratelimit.analyze_window.limit
        ratelimit.analyze_window.limit = 1
        try:
            with client.stream("POST", "/api/analyze", json={"target": "lego-city"}) as r:
                "".join(r.iter_text())
            r2 = client.post("/api/analyze", json={"target": "lego-city"})
            assert r2.status_code == 429
        finally:
            ratelimit.analyze_window.limit = old


def test_budget_exhaustion(fake_llm, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "DAILY_LLM_BUDGET", 1)
    with TestClient(app) as client:
        r = client.post("/api/analyze", json={"target": "lego-city"})
        assert r.status_code == 429


def test_targets_endpoint(fake_llm):
    with TestClient(app) as client:
        j = client.get("/api/targets").json()
        assert j["cap"] == 16
        assert len(j["targets"]) == 6
        assert any(t["id"] == "ikea-sofas" for t in j["targets"])


def test_security_headers(fake_llm):
    with TestClient(app) as client:
        r = client.get("/")
        assert r.headers["X-Frame-Options"] == "DENY"
        assert "img-src 'self' data: https:" in r.headers["Content-Security-Policy"]


def test_clean_text_strips_scripts():
    html = "<html><head><title>t</title></head><body><script>evil()</script><p>keep me</p></body></html>"
    text = clean_text(html)
    assert "keep me" in text
    assert "evil" not in text
