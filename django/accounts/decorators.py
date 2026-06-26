from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden


def require_role(min_role="user"):
    """Decorator that requires the user to be logged in with at least min_role."""
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not request.user.has_min_role(min_role):
                return HttpResponseForbidden("Access denied.")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
