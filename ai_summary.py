import hashlib
import logging

import requests

from ai_config import OLLAMA_MODEL, OLLAMA_SUMMARY_MAX_ROWS, OLLAMA_TIMEOUT, OLLAMA_URL
from cache import cache_get, cache_set

_TTL_SUMMARY = 3600  # match Open-Meteo TTL — summary is only as fresh as the forecast

_log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a friendly stargazing advisor helping amateur astronomers in Texas plan their "
    "observing sessions. You speak casually and helpfully, like a knowledgeable friend — not "
    "a weather report. Keep responses to 3–5 sentences. Never mention numeric scores directly. "
    "Translate the data into plain language about what the sky will actually feel like."
)

_USER_PROMPT_TEMPLATE = """\
Here are the best-scoring stargazing windows for the coming week:

{context_table}

In 3–5 sentences, tell me:
1. Which single night looks best overall and why (mention the site and date)
2. Which site has the strongest overall window across the week and what makes it worth the drive
If conditions are generally poor across the board, say so honestly but encouragingly."""


def build_context_table(nights: list) -> str:
    """Return a markdown table of the top-scored nights for use as LLM context."""
    top = sorted(nights, key=lambda n: -n["composite"])[:OLLAMA_SUMMARY_MAX_ROWS]

    header = "| Site | Date | Telescope | Naked Eye | Cloud% | Moon | Humidity% | Seeing† | Transp.† | Bortle |"
    sep    = "|------|------|-----------|-----------|--------|------|-----------|---------|----------|--------|"

    def _fmt(val, suffix="", fallback="—"):
        return f"{val:.0f}{suffix}" if val is not None else fallback

    rows = []
    for n in top:
        s = n["stats"]
        f = n["factors"]
        rows.append(
            f"| {n['site']} | {n['date']} "
            f"| {_fmt(n['composite'])} "
            f"| {_fmt(n.get('naked_eye'))} "
            f"| {_fmt(s.get('avg_cloud_cover'), '%')} "
            f"| {_fmt(f.get('moon'))} "
            f"| {_fmt(s.get('avg_humidity'), '%')} "
            f"| {_fmt(s.get('seeing_7timer'))} "
            f"| {_fmt(s.get('transparency_7timer'))} "
            f"| {s.get('bortle_class') or '—'} |"
        )

    return "\n".join([header, sep] + rows)


def generate_forecast_summary(context_table: str) -> str | None:
    """Call Ollama and return a plain-language summary, or None on any failure."""
    payload = {
        "model": OLLAMA_MODEL,
        "system": _SYSTEM_PROMPT,
        "prompt": _USER_PROMPT_TEMPLATE.format(context_table=context_table),
        "stream": False,
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        return text if text else None
    except requests.exceptions.ConnectionError:
        _log.debug("Ollama not reachable at %s", OLLAMA_URL)
        return None
    except Exception as e:
        _log.debug("Ollama request failed: %s", e)
        return None


def get_cached_summary(nights: list) -> str | None:
    """Return a cached summary if available, otherwise generate and cache one."""
    context_table = build_context_table(nights)
    cache_key = "ai_summary:" + hashlib.md5(context_table.encode()).hexdigest()

    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    summary = generate_forecast_summary(context_table)
    if summary:
        cache_set(cache_key, summary, _TTL_SUMMARY)
    return summary
