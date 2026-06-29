import logging

from django.conf import settings
from django.contrib.auth import login

from accounts.models import User, UserPreferences

_log = logging.getLogger(__name__)


class SocialAuthStatusMiddleware:
    """Remap allauth's hardcoded 401 on the social auth error page to 200.

    allauth always returns HTTP 401 for authentication_error.html, which causes
    reverse proxies (nginx, NPM) to intercept the response and show their own
    error page instead. Since this is a user-facing error page (not an API),
    200 is the right status code.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            response.status_code == 401
            and request.path.startswith("/accounts/")
        ):
            response.status_code = 200
        return response


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
                    if user.is_active:
                        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                    else:
                        _log.warning("Blocked inactive user from proxy auth: %s", email)

        if request.user.is_authenticated:
            request.prefs, _ = UserPreferences.objects.get_or_create(user=request.user)
        else:
            # Ensure guests have a session so guest_lat etc. can be stored
            if not request.session.session_key:
                request.session.create()
            request.prefs = None

        return self.get_response(request)
