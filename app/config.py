"""Environment-driven settings. Every knob a deployer needs lives here."""
import os
from pathlib import Path


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen3.5:9b")

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
BUDGET_FILE = DATA_DIR / "budget.json"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

# Fetch guards
FETCH_MAX_BYTES = _int("FETCH_MAX_BYTES", 2_000_000)
FETCH_TIMEOUT_S = _int("FETCH_TIMEOUT_S", 20)
MAX_REDIRECTS = _int("MAX_REDIRECTS", 3)

# How much cleaned page text goes to the extractor
MAX_TEXT_CHARS = _int("MAX_TEXT_CHARS", 12_000)
MAX_RECORDS = _int("MAX_RECORDS", 40)

# Abuse protection (public demo)
ANALYZE_LIMIT = _int("ANALYZE_LIMIT", 6)
ANALYZE_WINDOW_S = _int("ANALYZE_WINDOW_S", 600)
DAILY_LLM_BUDGET = _int("DAILY_LLM_BUDGET", 200)

# Set to 1 when running behind cloudflared
TRUST_PROXY = os.getenv("TRUST_PROXY", "0") == "1"

LLM_TIMEOUT_S = _int("LLM_TIMEOUT_S", 180)
NUM_CTX = _int("NUM_CTX", 8192)
