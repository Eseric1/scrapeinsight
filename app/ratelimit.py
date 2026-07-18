"""Per-IP sliding-window limits plus a persisted global daily LLM budget.

Fail-closed: if the budget file is unreadable the demo declines requests
rather than running unmetered.
"""
import asyncio
import json
import time
from collections import defaultdict, deque
from datetime import date

from . import config


class SlidingWindow:
    def __init__(self, limit: int, window_s: int):
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque] = defaultdict(deque)

    def _prune(self, key: str) -> deque:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        return q

    def allow(self, key: str) -> bool:
        q = self._prune(key)
        if len(q) >= self.limit:
            return False
        q.append(time.monotonic())
        return True

    def remaining(self, key: str) -> int:
        return max(0, self.limit - len(self._prune(key)))


analyze_window = SlidingWindow(config.ANALYZE_LIMIT, config.ANALYZE_WINDOW_S)

_lock = asyncio.Lock()


def _load() -> dict:
    try:
        return json.loads(config.BUDGET_FILE.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return {"error": True}


async def spend_budget(calls: int = 1) -> bool:
    """Consume from today's global LLM budget. False = exhausted or unreadable."""
    async with _lock:
        state = _load()
        if state.get("error"):
            return False
        today = date.today().isoformat()
        used = state.get(today, 0)
        if used + calls > config.DAILY_LLM_BUDGET:
            return False
        config.BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
        config.BUDGET_FILE.write_text(json.dumps({today: used + calls}))
        return True


def budget_left() -> int:
    state = _load()
    if state.get("error"):
        return 0
    return max(0, config.DAILY_LLM_BUDGET - state.get(date.today().isoformat(), 0))
