"""Guarded page fetching + text cleanup."""
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


def clean_text(html: str) -> str:
    """Strip boilerplate markup down to readable text for the extractor."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "head"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text("\n").splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return text[: config.MAX_TEXT_CHARS]
