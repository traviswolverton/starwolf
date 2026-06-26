from functools import wraps

from django.http import HttpResponse
from django.shortcuts import redirect


def require_role(min_role="user"):
    """Require the user to have at least min_role. HTMX-aware."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if request.headers.get("HX-Request"):
                    return HttpResponse('<div class="alert error">Login required.</div>', status=401)
                return redirect(f"/accounts/login/?next={request.path}")
            if not request.user.has_min_role(min_role):
                if request.headers.get("HX-Request"):
                    return HttpResponse('<div class="alert error">Admin access required.</div>', status=403)
                return HttpResponse("Access denied.", status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_admin(view_func):
    return require_role("admin")(view_func)
