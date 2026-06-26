import logging

from django.conf import settings
from django.contrib.auth import login

from accounts.models import User, UserPreferences

_log = logging.getLogger(__name__)


class ProxyAuthMiddleware:
    """Authenticate users from the upstream auth proxy header.

    Reads AUTH_EMAIL_HEADER (set via env) to get the verified email injected
    by Cloudflare Access, oauth2-proxy, or any other header-based auth proxy.
    Once a Django session exists the header is no longer needed on subsequent
    requests.

    Set AUTH_BYPASS=true in .env to skip the header check in local dev.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            if settings.AUTH_BYPASS:
                user, _ = User.objects.get_or_create(
                    email="dev@localhost",
                    defaults={"username": "dev@localhost", "role": User.ADMIN},
                )
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            elif settings.AUTH_EMAIL_HEADER:
                email = request.headers.get(settings.AUTH_EMAIL_HEADER)
                if email:
                    user, created = User.objects.get_or_create(
                        email=email,
                        defaults={"username": email, "role": User.USER},
                    )
                    if created:
                        _log.info("New user created from proxy auth: %s", email)
                    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

        if request.user.is_authenticated:
            request.prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
        else:
            request.prefs = None

        return self.get_response(request)
