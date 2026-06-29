from urllib.parse import urlparse

from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse
from django.shortcuts import redirect, render


def _safe_next(request, param_source):
    """Return next URL only if it's a same-origin relative path."""
    next_url = param_source.get("next", "").strip()
    if not next_url:
        return "/"
    parsed = urlparse(next_url)
    # Reject anything with a scheme or netloc (external URLs)
    if parsed.scheme or parsed.netloc:
        return "/"
    return next_url


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request, request.GET))

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(_safe_next(request, request.POST))
        error = "Invalid username or password."

    return render(request, "accounts/login.html", {
        "next": _safe_next(request, request.GET),
        "error": error,
    })


def logout_view(request):
    logout(request)
    return redirect("/")
