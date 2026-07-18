"""ScrapeInsight — scrape a page, extract structured records with a local LLM,
analyze them with pandas, and narrate grounded insights.

Public-demo hardening: SSRF guard on every fetch hop, response size caps,
per-IP rate limits, a global daily LLM budget, and security headers.
"""
import contextlib
import json
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

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
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
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


@app.get("/api/presets")
async def presets():
    return {
        "presets": [
            {"id": pid, "label": p["label"], "hint": p["hint"], "sample": p["sample"]}
            for pid, p in schemas.PRESETS.items()
        ],
        "samples": [
            {"id": sid, "label": s["label"], "preset": s["preset"]}
            for sid, s in schemas.SAMPLES.items()
        ],
    }


class AnalyzeBody(BaseModel):
    url: str | None = Field(default=None, max_length=2000)
    sample: str | None = None
    preset: str

    @model_validator(mode="after")
    def one_source(self):
        if bool(self.url) == bool(self.sample):
            raise ValueError("Provide either a url or a sample, not both.")
        return self


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
    if body.preset not in schemas.PRESETS:
        raise HTTPException(400, "Unknown preset.")
    if body.sample and body.sample not in schemas.SAMPLES:
        raise HTTPException(400, "Unknown sample.")
    if not await ratelimit.spend_budget(2):  # one extract + one insight call
        raise HTTPException(429, "Demo budget for today is exhausted — come back tomorrow.")

    preset = schemas.PRESETS[body.preset]

    async def gen():
        # 1. Get page text
        try:
            if body.sample:
                sample = schemas.SAMPLES[body.sample]
                html = (config.SAMPLES_DIR / sample["file"]).read_text(encoding="utf-8")
                source = sample["label"]
            else:
                yield _sse("progress", {"stage": "fetching"})
                source, html = await scraper.fetch_html(body.url)
            text = scraper.clean_text(html)
            if not text.strip():
                yield _sse("error", "That page has no extractable text.")
                return
        except (ssrf.BlockedURL, scraper.ScrapeError) as exc:
            yield _sse("error", str(exc))
            return
        except httpx.HTTPError:
            yield _sse("error", "Could not fetch that page.")
            return

        # 2. LLM extraction (schema-constrained)
        yield _sse("progress", {"stage": "extracting"})
        try:
            raw = await llm.chat_json(
                EXTRACT_PROMPT.format(label=preset["label"], max_records=config.MAX_RECORDS),
                text,
                preset["schema"],
            )
        except (httpx.HTTPError, ValueError):
            yield _sse("error", "The model backend failed during extraction.")
            return
        records = [r for r in raw.get("items", []) if isinstance(r, dict)][: config.MAX_RECORDS]
        if not records:
            yield _sse("error", "No records matching this preset were found on the page.")
            return

        # 3. Deterministic analysis
        yield _sse("progress", {"stage": "analyzing"})
        stats = analyze.analyze(records, preset)

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
                "source": source,
                "preset": body.preset,
                "records": records,
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
