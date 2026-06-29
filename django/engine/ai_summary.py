import hashlib
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import requests

from django.db import connection

from . import ai_config
from .cache import cache_get, cache_set


def _get_app_settings() -> dict:
    from accounts.models import AppSetting
    return AppSetting.all_as_dict()


_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),    # loopback
    ipaddress.ip_network("::1/128"),         # IPv6 loopback
    ipaddress.ip_network("10.0.0.0/8"),      # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),   # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918
    ipaddress.ip_network("fc00::/7"),        # IPv6 ULA
]


def _assert_private_url(url: str) -> None:
    """Raise ValueError if the URL resolves to a public internet address.

    Allows loopback and RFC 1918 private ranges so Ollama can run on the
    same host or anywhere on the local network. Blocks public IPs to
    prevent the admin-editable URL from being used to reach external servers.
    """
    host = urlparse(url).hostname or ""
    try:
        resolved = socket.getaddrinfo(host, None)[0][4][0]
        ip = ipaddress.ip_address(resolved)
    except Exception:
        raise ValueError(f"Cannot resolve Ollama URL host: {host!r}")
    if not any(ip in net for net in _PRIVATE_NETWORKS):
        raise ValueError(f"Ollama URL must resolve to a private/loopback address, got: {ip}")

_TTL_SUMMARY = 3600  # match Open-Meteo TTL — summary is only as fresh as the forecast
_CONNECT_TIMEOUT = 3  # seconds — fast-fail if Ollama isn't reachable

_log = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = (
    "You are a friendly stargazing advisor helping amateur astronomers in Texas plan their "
    "observing sessions. You speak casually and helpfully, like a knowledgeable friend — not "
    "a weather report. Keep responses to 3–5 sentences. Never mention numeric scores directly. "
    "Translate the data into plain language about what the sky will actually feel like."
)

_DEFAULT_USER_PROMPT_TEMPLATE = """\
Here are the best-scoring stargazing windows for the coming week:

{context_table}

In 3–5 sentences, tell me:
1. Which single night looks best overall and why (mention the site and date)
2. Which site has the strongest overall window across the week and what makes it worth the drive
If conditions are generally poor across the board, say so honestly but encouragingly."""


def build_context_table(nights: list) -> str:
    """Return a markdown table of the top-scored nights for use as LLM context."""
    settings = _get_app_settings()
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
    settings = _get_app_settings()
    url = settings.get("ollama_url", ai_config.OLLAMA_URL)
    try:
        _assert_private_url(url)
        parsed = urlparse(url)
        ping_url = f"{parsed.scheme}://{parsed.netloc}/api/tags"
        requests.get(ping_url, timeout=(_CONNECT_TIMEOUT, 5))
        return True
    except Exception:
        return False


def generate_forecast_summary(context_table: str) -> str | None:
    """Call Ollama and return a plain-language summary, or None on any failure."""
    settings = _get_app_settings()
    url     = settings.get("ollama_url",     ai_config.OLLAMA_URL)
    model   = settings.get("ollama_model",   ai_config.OLLAMA_MODEL)
    timeout = int(settings.get("ollama_timeout", ai_config.OLLAMA_TIMEOUT))

    try:
        _assert_private_url(url)
    except ValueError as e:
        _log.warning("Blocked Ollama request to non-private URL: %s", e)
        return None

    system_prompt = settings.get("ollama_system_prompt") or _DEFAULT_SYSTEM_PROMPT
    user_prompt   = (settings.get("ollama_user_prompt") or _DEFAULT_USER_PROMPT_TEMPLATE).format(
        context_table=context_table
    )

    payload = {
        "model": model,
        "system": system_prompt,
        "prompt": user_prompt,
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
