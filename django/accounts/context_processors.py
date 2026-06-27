from datetime import date, timedelta
import json
from pathlib import Path

_NOTES_PATH = Path(__file__).resolve().parent.parent.parent / "release_notes.json"


def _has_new_notes(request):
    session_key = "last_home_visit"
    last_str = request.session.get(session_key)
    if not last_str:
        since = date.today() - timedelta(days=7)
    else:
        try:
            since = date.fromisoformat(last_str)
        except ValueError:
            since = date.today() - timedelta(days=7)
    try:
        data = json.loads(_NOTES_PATH.read_text())
    except Exception:
        return False
    for entry in data.get("releases", []):
        try:
            if date.fromisoformat(entry["date"]) >= since:
                return True
        except (KeyError, ValueError):
            pass
    return False


def prefs(request):
    """Expose request.prefs and has_new_notes to all templates."""
    return {
        "prefs": getattr(request, "prefs", None),
        "has_new_notes": _has_new_notes(request),
    }
