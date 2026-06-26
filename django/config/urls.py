from django.http import JsonResponse
from django.shortcuts import render
from django.urls import path

from accounts import views as account_views
from pages import views as page_views


def health(request):
    return JsonResponse({"status": "ok"})


def home(request):
    return render(request, "home.html")


urlpatterns = [
    path("", home, name="home"),
    path("about", page_views.about, name="about"),
    path("location", page_views.location, name="location"),
    path("preferences", page_views.preferences, name="preferences"),
    path("preferences/reset", page_views.preferences_reset, name="preferences_reset"),
    path("bortle", page_views.bortle_scorer, name="bortle_scorer"),
    path("api-guide", page_views.api_guide, name="api_guide"),
    path("feedback", page_views.feedback, name="feedback"),
    path("django-health", health),
    path("accounts/login/", account_views.login_view, name="login"),
    path("accounts/logout/", account_views.logout_view, name="logout"),
]
