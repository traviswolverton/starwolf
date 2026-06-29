import os
from pathlib import Path

import dj_database_url
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"

# Cloudflare / NPM sit in front — all host validation happens there
ALLOWED_HOSTS = ["*"]

# Trust X-Forwarded-For from the reverse proxy
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.github",
    "allauth.socialaccount.providers.discord",
    "allauth.mfa",
    "accounts",
    "pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "accounts.middleware.ProxyAuthMiddleware",  # CF Access header fallback
    "accounts.middleware.SocialAuthStatusMiddleware",  # remap allauth 401 → 200
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
AUTH_USER_MODEL = "accounts.User"
SITE_ID = 1

# ── django-allauth ────────────────────────────────────────────────────────────
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",       # local password login
    "allauth.account.auth_backends.AuthenticationBackend",
]
ACCOUNT_ADAPTER = "accounts.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "accounts.adapters.SocialAccountAdapter"
SOCIALACCOUNT_LOGIN_ON_GET = True
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APPS": [{
            "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
            "secret":    os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        }],
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    },
    "github": {
        "APPS": [{
            "client_id": os.environ.get("GITHUB_CLIENT_ID", ""),
            "secret":    os.environ.get("GITHUB_CLIENT_SECRET", ""),
        }],
        "SCOPE": ["user:email"],
    },
    "discord": {
        "APPS": [{
            "client_id": os.environ.get("DISCORD_CLIENT_ID", ""),
            "secret":    os.environ.get("DISCORD_CLIENT_SECRET", ""),
        }],
        "SCOPE": ["identify", "email"],
    },
}

MFA_TOTP_ISSUER = "StarWolf"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.prefs",
            ],
        },
    },
]

# ── Database ──────────────────────────────────────────────────────────────────
# All application tables are managed via Django ORM (accounts/models.py).
DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL"),
        conn_max_age=600,
    )
}

# ── Cache + Sessions (Redis) ──────────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "django",
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 1 week

# ── Feedback / GitHub ─────────────────────────────────────────────────────────
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "traviswolverton/starwolf")
IP_HASH_SALT = os.environ.get("IP_HASH_SALT", "")

# ── Auth header config ────────────────────────────────────────────────────────
# Set by the upstream auth proxy (Cloudflare Access, oauth2-proxy, etc.)
# Set AUTH_BYPASS=true to skip header check in local dev.
AUTH_EMAIL_HEADER = os.environ.get("AUTH_EMAIL_HEADER", "")
AUTH_BYPASS = os.environ.get("AUTH_BYPASS", "false").lower() == "true"

# ── Static files ──────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

UNFOLD = {
    "SITE_TITLE": "Starwolf Admin",
    "SITE_HEADER": "Starwolf",
    "SITE_URL": "/",
    "SITE_SYMBOL": "star",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "COLORS": {
        "primary": {
            "50":  "240 249 255",
            "100": "224 242 254",
            "200": "186 230 253",
            "300": "125 211 252",
            "400": "56 189 248",
            "500": "14 165 233",
            "600": "2 132 199",
            "700": "3 105 161",
            "800": "7 89 133",
            "900": "12 74 110",
            "950": "8 47 73",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Sites",
                "items": [
                    {"title": "Sites", "icon": "location_on", "link": reverse_lazy("admin:accounts_site_changelist")},
                    {"title": "Site Details", "icon": "article", "link": reverse_lazy("admin:accounts_sitedetail_changelist")},
                    {"title": "Daily Scores", "icon": "bar_chart", "link": reverse_lazy("admin:accounts_sitedailyscore_changelist")},
                ],
            },
            {
                "title": "Sky Catalog",
                "items": [
                    {"title": "Sky Objects", "icon": "star", "link": reverse_lazy("admin:accounts_skyobject_changelist")},
                ],
            },
            {
                "title": "Configuration",
                "items": [
                    {"title": "App Settings",       "icon": "tune",        "link": reverse_lazy("admin:accounts_appsetting_changelist")},
                    {"title": "Scoring Weights",    "icon": "scale",       "link": reverse_lazy("admin:accounts_scoringweight_changelist")},
                    {"title": "Naked Eye Weights",  "icon": "visibility",  "link": reverse_lazy("admin:accounts_nakedeyeweight_changelist")},
                ],
            },
            {
                "title": "Users",
                "items": [
                    {"title": "Users", "icon": "person", "link": reverse_lazy("admin:accounts_user_changelist")},
                    {"title": "Preferences", "icon": "settings", "link": reverse_lazy("admin:accounts_userpreferences_changelist")},
                ],
            },
        ],
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING"},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "allauth": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}
