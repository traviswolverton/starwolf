import json
import logging
from datetime import datetime
from pathlib import Path

_PATH = Path(__file__).parent / "release_notes.json"
_log = logging.getLogger(__name__)


def load_release_notes() -> dict:
    try:
        return json.loads(_PATH.read_text())
    except FileNotFoundError:
        _log.warning("release_notes.json not found at %s", _PATH)
        return {}
    except json.JSONDecodeError as e:
        _log.warning("release_notes.json is malformed: %s", e)
        return {}


def get_notes_since(since_date: datetime) -> list:
    since = since_date.date() if isinstance(since_date, datetime) else since_date
    releases = load_release_notes().get("releases", [])
    return [
        r for r in releases
        if datetime.strptime(r["date"], "%Y-%m-%d").date() > since
    ]


def get_notes_last_n_days(n: int) -> list:
    from datetime import date, timedelta
    cutoff = date.today() - timedelta(days=n)
    releases = load_release_notes().get("releases", [])
    return [
        r for r in releases
        if datetime.strptime(r["date"], "%Y-%m-%d").date() >= cutoff
    ]
