from django.http import JsonResponse
from django.shortcuts import render
from django.urls import include, path

from pages import views as page_views


def health(request):
    return JsonResponse({"status": "ok"})


def home(request):
    return render(request, "home.html")


urlpatterns = [
    path("", home, name="home"),
    path("about", page_views.about, name="about"),
    path("sites", page_views.sites, name="sites"),
    path("location", page_views.location, name="location"),
    path("preferences", page_views.preferences, name="preferences"),
    path("preferences/reset", page_views.preferences_reset, name="preferences_reset"),
    path("planner", page_views.planner, name="planner"),
    path("planner/run", page_views.planner_run, name="planner_run"),
    path("planner/poll", page_views.planner_poll, name="planner_poll"),
    path("admin-panel", page_views.admin_panel, name="admin_panel"),
    path("admin-panel/weights", page_views.admin_save_weights, name="admin_save_weights"),
    path("admin-panel/settings", page_views.admin_save_settings, name="admin_save_settings"),
    path("admin-panel/bortle-fill", page_views.admin_bortle_fill, name="admin_bortle_fill"),
    path("heatmap", page_views.heatmap, name="heatmap"),
    path("heatmap/compute", page_views.heatmap_compute, name="heatmap_compute"),
    path("heatmap/status", page_views.heatmap_status, name="heatmap_status"),
    path("bortle", page_views.bortle_scorer, name="bortle_scorer"),
    path("api-guide", page_views.api_guide, name="api_guide"),
    path("feedback", page_views.feedback, name="feedback"),
    path("django-health", health),
    path("accounts/", include("allauth.urls")),
]
