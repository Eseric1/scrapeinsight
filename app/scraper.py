"""Guarded page fetching, JSON-LD product extraction, text cleanup."""
import json
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from . import config, ssrf

UA = "Mozilla/5.0 (compatible; ScrapeInsight-demo/1.0)"

REDIRECT_CODES = {301, 302, 303, 307, 308}


class ScrapeError(ValueError):
    pass


async def fetch_html(url: str) -> tuple[str, str]:
    """Fetch a page with SSRF validation on every hop and a hard size cap.

    Returns (final_url, html).
    """
    for _ in range(config.MAX_REDIRECTS + 1):
        ssrf.validate_public_url(url)
        async with httpx.AsyncClient(
            timeout=config.FETCH_TIMEOUT_S,
            follow_redirects=False,
            headers={"User-Agent": UA},
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code in REDIRECT_CODES:
                    loc = resp.headers.get("location")
                    if not loc:
                        raise ScrapeError("Redirect without a location.")
                    url = urljoin(url, loc)
                    continue
                if resp.status_code != 200:
                    raise ScrapeError(f"Page returned HTTP {resp.status_code}.")
                ctype = resp.headers.get("content-type", "")
                if not ctype.startswith(("text/", "application/xhtml")):
                    raise ScrapeError("Only HTML/text pages are supported.")
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    if size > config.FETCH_MAX_BYTES:
                        raise ScrapeError("Page is too large for the demo.")
                    chunks.append(chunk)
        return url, b"".join(chunks).decode(resp.encoding or "utf-8", errors="replace")
    raise ScrapeError("Too many redirects.")


def _price(offers):
    """Pull a numeric price out of the many shapes schema.org offers take."""
    if isinstance(offers, list):
        for o in offers:
            p = _price(o)
            if p is not None:
                return p
        return None
    if not isinstance(offers, dict):
        return None
    for key in ("price", "lowPrice"):
        v = offers.get(key)
        if v is not None:
            try:
                return float(str(v).replace(",", ""))
            except ValueError:
                pass
    spec = offers.get("priceSpecification")
    if spec:
        return _price(spec if isinstance(spec, list) else [spec])
    return None


def _walk_products(node, out: list):
    if isinstance(node, dict):
        if node.get("@type") == "Product":
            out.append(node)
        for v in node.values():
            _walk_products(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_products(v, out)


def _http_url(v) -> str | None:
    return v if isinstance(v, str) and v.startswith(("https://", "http://")) else None


def jsonld_products(html: str, category: str | None = None) -> list[dict]:
    """Deterministic extraction from schema.org JSON-LD blocks.

    Handles both shapes seen live: LEGO nests Products inside an ItemList's
    ListItems with offers.price; IKEA emits standalone Products with
    offers.priceSpecification[] and aggregateRating.
    """
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict] = []
    for s in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or "")
        except ValueError:
            continue
        _walk_products(data, found)

    records, seen = [], set()
    for p in found:
        name = str(p.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        rating = None
        agg = p.get("aggregateRating")
        if isinstance(agg, dict):
            try:
                rating = float(agg.get("ratingValue"))
            except (TypeError, ValueError):
                pass
        image = p.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if isinstance(image, dict):
            image = image.get("url")
        records.append(
            {
                "name": name[:160],
                "price": _price(p.get("offers")),
                "rating": rating,
                "category": category,
                "url": _http_url(p.get("url")) or _http_url(p.get("@id")),
                "image": _http_url(image),
            }
        )
    return records


def clean_text(html: str) -> str:
    """Strip boilerplate markup down to readable text for the extractor."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "head"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return text[: config.MAX_TEXT_CHARS]
