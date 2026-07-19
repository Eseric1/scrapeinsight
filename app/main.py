"""ScrapeInsight — scrape a page, extract structured records with a local LLM,
analyze them with pandas, and narrate grounded insights.

Public-demo hardening: SSRF guard on every fetch hop, response size caps,
per-IP rate limits, a global daily LLM budget, and security headers.
"""
import contextlib
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analyze, config, llm, ratelimit, scraper, schemas, ssrf

log = logging.getLogger("scrapeinsight")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await llm.close()


app = FastAPI(title="ScrapeInsight", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path == "/" or request.url.path.startswith("/static"):
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: https:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'",
        )
    return resp


def client_ip(request: Request) -> str:
    if config.TRUST_PROXY:
        cf = request.headers.get("cf-connecting-ip")
        if cf:
            return cf
    return request.client.host if request.client else "unknown"


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/targets")
async def targets():
    return {
        "targets": [{"id": tid, "label": t["label"]} for tid, t in schemas.TARGETS.items()],
        "cap": schemas.DISPLAY_CAP,
    }


class AnalyzeBody(BaseModel):
    target: str


EXTRACT_PROMPT = (
    "You extract structured records from web page text. Find every {label} on the page, "
    "up to {max_records} records. Use null for fields the page does not show. Prices, "
    "scores and ratings must be plain numbers with no currency symbols or thousands "
    "separators. Never invent records that are not in the text."
)

INSIGHT_PROMPT = (
    "You are a data analyst. You are given statistics computed from scraped records, as JSON. "
    "Write exactly 3 short, punchy insight bullets. Every bullet must quote at least one "
    "number that appears in the statistics. Do not speculate beyond the numbers."
)


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.post("/api/analyze")
async def analyze_page(request: Request, body: AnalyzeBody):
    ip = client_ip(request)
    if not ratelimit.analyze_window.allow(ip):
        raise HTTPException(429, "Analysis limit reached — try again in a few minutes.")
    if body.target not in schemas.TARGETS:
        raise HTTPException(400, "Unknown target.")
    if not await ratelimit.spend_budget(2):  # worst case: one extract + one insight call
        raise HTTPException(429, "Demo budget for today is exhausted — come back tomorrow.")

    target = schemas.TARGETS[body.target]
    preset = schemas.PRODUCTS_PRESET

    async def gen():
        # 1. Live fetch of the curated category page
        try:
            yield _sse("progress", {"stage": "fetching"})
            _final_url, html = await scraper.fetch_html(target["url"])
        except (ssrf.BlockedURL, scraper.ScrapeError) as exc:
            yield _sse("error", str(exc))
            return
        except httpx.HTTPError:
            yield _sse("error", f"{target['brand']} did not answer just now — try another target.")
            return

        # 2. Extraction: deterministic JSON-LD first, LLM fallback second
        yield _sse("progress", {"stage": "extracting"})
        records = scraper.jsonld_products(html, category=target["category"])
        extraction = "structured"
        if len(records) < 3:
            extraction = "llm"
            text = scraper.clean_text(html)
            try:
                raw = await llm.chat_json(
                    EXTRACT_PROMPT.format(label=preset["label"], max_records=config.MAX_RECORDS),
                    text,
                    preset["schema"],
                )
                records = [
                    {**r, "category": target["category"], "url": None, "image": None}
                    for r in raw.get("items", [])
                    if isinstance(r, dict)
                ]
            except (httpx.HTTPError, ValueError):
                yield _sse("error", "The model backend failed during extraction.")
                return
        records = records[: config.MAX_RECORDS]
        if not records:
            yield _sse("error", "No products could be extracted from that page right now.")
            return

        # 3. Deterministic analysis over EVERYTHING found; display gets capped
        yield _sse("progress", {"stage": "analyzing"})
        stats = analyze.analyze(records, preset)
        showcase = random.choice(records)

        # 4. Grounded insights
        try:
            insight_raw = await llm.chat_json(
                INSIGHT_PROMPT,
                json.dumps({k: v for k, v in stats.items() if k != "charts"}),
                schemas.INSIGHT_SCHEMA,
            )
            insights = [str(i) for i in insight_raw.get("insights", [])][:3]
        except (httpx.HTTPError, ValueError):
            insights = []  # charts + stats still ship without narration

        yield _sse(
            "result",
            {
                "source": {
                    "label": target["label"],
                    "brand": target["brand"],
                    "category": target["category"],
                    "url": target["url"],
                },
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "extraction": extraction,
                "total_found": len(records),
                "cap": schemas.DISPLAY_CAP,
                "records": records[: schemas.DISPLAY_CAP],
                "showcase": showcase,
                "stats": stats,
                "insights": insights,
                "model": config.CHAT_MODEL,
            },
        )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
async def health():
    try:
        info = await llm.healthy()
        ready = any(m.split(":")[0] == config.CHAT_MODEL.split(":")[0] for m in info["models"])
    except Exception:
        return {"ok": False, "chat_model": config.CHAT_MODEL}
    return {"ok": ready, "chat_model": config.CHAT_MODEL}


@app.get("/api/limits")
async def limits(request: Request):
    ip = client_ip(request)
    return {
        "analyses_left": ratelimit.analyze_window.remaining(ip),
        "daily_budget_left": ratelimit.budget_left(),
    }


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
