from django.http import JsonResponse
from django.urls import path

from accounts import views as account_views


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("django-health", health),
    path("accounts/login/", account_views.login_view, name="login"),
    path("accounts/logout/", account_views.logout_view, name="logout"),
    # Phase 2: page URLs added here as each page is migrated
]
