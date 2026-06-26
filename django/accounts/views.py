from django.contrib.auth import logout
from django.http import HttpResponse
from django.shortcuts import redirect


def login_view(request):
    """Placeholder — auth is handled by the upstream proxy, not a login form."""
    if request.user.is_authenticated:
        return redirect("/")
    return HttpResponse("Authentication is handled by the upstream proxy.", status=401)


def logout_view(request):
    logout(request)
    return redirect("/")
