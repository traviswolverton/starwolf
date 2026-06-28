import json
from datetime import date, timedelta
from pathlib import Path

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import include, path

from pages import api_views
from pages import views as page_views

_NOTES_PATH = Path(__file__).resolve().parent.parent.parent / "release_notes.json"


def _load_release_notes_since(since_date):
    """Return list of {date, bullets} merged by date, newest first."""
    try:
        data = json.loads(_NOTES_PATH.read_text())
    except Exception:
        return []
    merged = {}
    for entry in data.get("releases", []):
        try:
            entry_date = date.fromisoformat(entry["date"])
        except (KeyError, ValueError):
            continue
        if entry_date >= since_date:
            bullets = entry.get("features", []) + entry.get("fixes", []) + entry.get("notes", [])
            if bullets:
                merged.setdefault(entry["date"], []).extend(bullets)
    return [{"date": d, "bullets": b} for d, b in sorted(merged.items(), reverse=True)]


def health(request):
    return JsonResponse({"status": "ok"})


def home(request):
    # Determine what's "new" since last visit
    session_key = "last_home_visit"
    today = date.today()
    last_visit_str = request.session.get(session_key)
    if last_visit_str:
        try:
            since = date.fromisoformat(last_visit_str)
        except ValueError:
            since = today - timedelta(days=7)
    else:
        since = today - timedelta(days=7)

    new_notes = _load_release_notes_since(since)

    # Store yesterday so today's entries always appear on next same-day visit
    request.session[session_key] = (today - timedelta(days=1)).isoformat()

    return render(request, "home.html", {
        "new_notes": new_notes,
        "has_new_notes": bool(new_notes),
    })


urlpatterns = [
    path("", home, name="home"),
    path("about", page_views.about, name="about"),
    path("moon", page_views.moon_phase_page, name="moon_phase"),
    path("sites", page_views.sites, name="sites"),
    path("sites/<int:site_id>", page_views.site_detail, name="site_detail"),
    path("sites/<int:site_id>/sky", page_views.sky_objects, name="sky_objects"),
    path("tonight", page_views.tonight, name="tonight"),
    path("location", page_views.location, name="location"),
    path("preferences", page_views.preferences, name="preferences"),
    path("preferences/reset", page_views.preferences_reset, name="preferences_reset"),
    path("planner", page_views.planner, name="planner"),
    path("planner/run", page_views.planner_run, name="planner_run"),
    path("planner/poll", page_views.planner_poll, name="planner_poll"),
    path("planner/site-count", page_views.planner_site_count, name="planner_site_count"),
    path("admin-panel", page_views.admin_panel, name="admin_panel"),
    path("admin-panel/weights", page_views.admin_save_weights, name="admin_save_weights"),
    path("admin-panel/settings", page_views.admin_save_settings, name="admin_save_settings"),
    path("admin-panel/bortle-fill", page_views.admin_bortle_fill, name="admin_bortle_fill"),
    path("admin-panel/prompts", page_views.admin_save_prompts, name="admin_save_prompts"),
    path("admin-panel/users/<int:user_id>/role", page_views.admin_user_role, name="admin_user_role"),
    path("admin-panel/users/<int:user_id>/active", page_views.admin_user_active, name="admin_user_active"),
    path("heatmap", page_views.heatmap, name="heatmap"),
    path("heatmap/compute", page_views.heatmap_compute, name="heatmap_compute"),
    path("heatmap/status", page_views.heatmap_status, name="heatmap_status"),
    path("bortle", page_views.bortle_scorer, name="bortle_scorer"),
    path("api-guide", page_views.api_guide, name="api_guide"),
    path("feedback", page_views.feedback, name="feedback"),
    # Routes with /api/ prefix (direct access)
    path("api/v1/bortle", api_views.bortle, name="api_bortle"),
    path("api/v1/sites", api_views.sites, name="api_sites"),
    path("api/v1/forecast", api_views.forecast, name="api_forecast"),
    path("api/healthz", lambda r: JsonResponse({"status": "ok"}), name="api_health"),
    # Routes without prefix (proxy strips /api before forwarding)
    path("v1/bortle", api_views.bortle),
    path("v1/sites", api_views.sites),
    path("v1/forecast", api_views.forecast),
    path("healthz", lambda r: JsonResponse({"status": "ok"})),
    path("django-health", health),
    path("accounts/", include("allauth.urls")),
]
