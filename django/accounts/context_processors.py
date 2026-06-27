from datetime import date, timedelta
import json
from pathlib import Path

from astral.moon import phase as _moon_phase

_MOON_PHASES = [
    (0,   "🌑", "New Moon"),
    (1.5, "🌒", "Waxing Crescent"),
    (6,   "🌓", "First Quarter"),
    (8.5, "🌔", "Waxing Gibbous"),
    (13,  "🌕", "Full Moon"),
    (15.5,"🌖", "Waning Gibbous"),
    (20,  "🌗", "Last Quarter"),
    (22.5,"🌘", "Waning Crescent"),
    (27,  "🌑", "New Moon"),
]

def _moon_info():
    p = _moon_phase(date.today())  # 0–29.5
    emoji, label = "🌑", "New Moon"
    for threshold, e, l in reversed(_MOON_PHASES):
        if p >= threshold:
            emoji, label = e, l
            break
    return {"emoji": emoji, "label": label, "phase": round(p, 1)}

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
    """Expose request.prefs, has_new_notes, and moon_info to all templates."""
    return {
        "prefs": getattr(request, "prefs", None),
        "has_new_notes": _has_new_notes(request),
        "moon": _moon_info(),
    }
