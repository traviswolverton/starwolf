import hashlib
import logging
from urllib.parse import urlparse

import requests

import ai_config
from cache import cache_get, cache_set
from db import get_settings

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _assert_loopback(url: str) -> None:
    """Raise ValueError if the URL does not point to a loopback address."""
    host = urlparse(url).hostname or ""
    if host not in _LOOPBACK_HOSTS:
        raise ValueError(f"Ollama URL must point to localhost, got: {host!r}")

_TTL_SUMMARY = 3600  # match Open-Meteo TTL — summary is only as fresh as the forecast
_CONNECT_TIMEOUT = 3  # seconds — fast-fail if Ollama isn't reachable

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
    settings = get_settings()
    max_rows = int(settings.get("ollama_summary_max_rows", ai_config.OLLAMA_SUMMARY_MAX_ROWS))
    top = sorted(nights, key=lambda n: -n["composite"])[:max_rows]

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


def is_ollama_available() -> bool:
    """Return True if Ollama is reachable. Uses a 3-second connect timeout for fast-fail."""
    settings = get_settings()
    url = settings.get("ollama_url", ai_config.OLLAMA_URL)
    try:
        _assert_loopback(url)
        parsed = urlparse(url)
        ping_url = f"{parsed.scheme}://{parsed.netloc}/api/tags"
        requests.get(ping_url, timeout=(_CONNECT_TIMEOUT, 5))
        return True
    except Exception:
        return False


def generate_forecast_summary(context_table: str) -> str | None:
    """Call Ollama and return a plain-language summary, or None on any failure."""
    settings = get_settings()
    url     = settings.get("ollama_url",     ai_config.OLLAMA_URL)
    model   = settings.get("ollama_model",   ai_config.OLLAMA_MODEL)
    timeout = int(settings.get("ollama_timeout", ai_config.OLLAMA_TIMEOUT))

    try:
        _assert_loopback(url)
    except ValueError as e:
        _log.warning("Blocked Ollama request to non-loopback URL: %s", e)
        return None

    payload = {
        "model": model,
        "system": _SYSTEM_PROMPT,
        "prompt": _USER_PROMPT_TEMPLATE.format(context_table=context_table),
        "stream": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=(_CONNECT_TIMEOUT, timeout))
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        return text if text else None
    except requests.exceptions.ConnectionError:
        _log.debug("Ollama not reachable at %s", url)
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
