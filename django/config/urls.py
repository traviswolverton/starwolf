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
    path("django-health", health),
    path("accounts/login/", account_views.login_view, name="login"),
    path("accounts/logout/", account_views.logout_view, name="logout"),
]
