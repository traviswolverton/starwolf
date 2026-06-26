# StarWolf Django Migration Plan

## Goal

Migrate from Streamlit to Django + HTMX to support proper user auth, RBAC,
per-user data, and a maintainable frontend architecture. The existing site
stays live throughout using a strangler fig pattern — the reverse proxy routes
migrated pages to Django and unmigrated pages to Streamlit until the
transition is complete.

## Current Stack

| Layer        | Technology                                          |
|--------------|-----------------------------------------------------|
| Frontend     | Streamlit (port 8501)                               |
| Public API   | FastAPI / uvicorn (port 8000)                       |
| Database     | Postgres 16                                         |
| Cache        | Redis 7                                             |
| Proxy        | Nginx Proxy Manager (NPM), host Docker container   |
| Tunnel       | cloudflared → Cloudflare (manages domain + SSL)    |
| Auth         | Single shared password in secrets.toml              |

## Target Stack

| Layer        | Technology                                          |
|--------------|-----------------------------------------------------|
| Frontend     | Django + HTMX + Alpine.js (port 8080)              |
| Public API   | FastAPI / uvicorn (port 8000) — kept as-is         |
| Database     | Postgres 16 — same instance                        |
| Cache        | Redis 7 — same instance                            |
| Proxy        | NPM — gains Django upstream, strangler fig routing |
| Tunnel       | cloudflared → Cloudflare — unchanged               |
| Auth         | Pluggable header-based auth (see Phase 0)          |

---

## Auth Provider Design — Portability First

Django does not care which system authenticated the user. It reads the
verified identity from a single HTTP header whose name is configurable:

```
AUTH_EMAIL_HEADER=Cf-Access-Authenticated-User-Email  # Cloudflare Access (owner's setup)
AUTH_EMAIL_HEADER=X-Auth-Request-Email                # oauth2-proxy
AUTH_EMAIL_HEADER=Remote-Email                        # Authelia, Authentik, etc.
AUTH_BYPASS=true                                      # local dev — skips header, uses test user
```

The Django middleware reads `AUTH_EMAIL_HEADER`, looks up or creates the user
record, and establishes a session. The rest of the app (views, RBAC, templates)
never touches auth-provider-specific logic.

**This means:** anyone cloning the repo can run their own auth proxy, set
`AUTH_EMAIL_HEADER` to match, and everything works. The Cloudflare setup is
not a requirement — it's one valid provider among several.

### Supported providers

| Provider           | How to run                              | Header to set                          |
|--------------------|-----------------------------------------|----------------------------------------|
| Cloudflare Access  | Cloudflare Zero Trust dashboard (free) | `Cf-Access-Authenticated-User-Email`  |
| oauth2-proxy       | Docker service in docker-compose        | `X-Auth-Request-Email`                |
| Authelia           | Self-hosted Docker service              | `Remote-Email`                        |
| Local dev          | `AUTH_BYPASS=true`                      | (header ignored)                       |

---

## Phase 0 — Auth Now, No App Code Changes

**Goal:** Real OAuth login protecting the existing Streamlit app. Two paths
depending on your infrastructure — pick one.

### Path A: Cloudflare Access (owner's setup — recommended)

No new Docker containers. Auth happens at Cloudflare's edge before traffic
reaches the machine.

1. [ ] Go to [Cloudflare Zero Trust](https://one.dash.cloudflare.com) →
       Settings → Authentication → Add Google as identity provider
2. [ ] Create an Access Application for the app domain
3. [ ] Set policy: allow specific emails or your whole domain
4. [ ] Verify: hitting the app now shows a Google login screen
5. [ ] Add `AUTH_EMAIL_HEADER=Cf-Access-Authenticated-User-Email` to `.env`
       (used by Django in Phase 1)

**New `.env` vars:**
```
AUTH_EMAIL_HEADER=Cf-Access-Authenticated-User-Email
```

### Path B: oauth2-proxy (self-hosted, no Cloudflare required)

For anyone cloning the repo without Cloudflare. Add to `docker-compose.yml`:

```yaml
oauth2-proxy:
  image: quay.io/oauth2-proxy/oauth2-proxy:latest
  command:
    - --provider=google
    - --http-address=0.0.0.0:4180
    - --reverse-proxy=true
    - --set-xauthrequest=true
    - --email-domain=*
    - --cookie-secret=${OAUTH2_COOKIE_SECRET}
    - --client-id=${GOOGLE_CLIENT_ID}
    - --client-secret=${GOOGLE_CLIENT_SECRET}
    - --cookie-secure=false   # set true once HTTPS is in place
  restart: unless-stopped
```

Configure your reverse proxy (NPM or nginx) to:
1. Check auth via oauth2-proxy before forwarding to the app
2. Forward `X-Auth-Request-Email` downstream

**New `.env` vars:**
```
OAUTH2_COOKIE_SECRET=   # openssl rand -base64 32
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
AUTH_EMAIL_HEADER=X-Auth-Request-Email
```

Both Google OAuth app credentials (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`)
carry forward unchanged into Phase 1 regardless of which path is used.

---

## Phase 1 — Django Scaffold + Auth (1 week)

**Goal:** Django running alongside Streamlit, no pages migrated yet. Auth,
user model, and RBAC fully working. Django reads the header from Phase 0
to auto-authenticate users — no second login prompt during migration.

### 1a — Project setup

- [ ] Create `requirements-django.txt`: `django`, `django-allauth`,
      `whitenoise`, `django-redis`, `gunicorn`
- [ ] `django-admin startproject starwolf_django` → commit scaffold
- [ ] `settings.py`: point at existing Postgres (Django manages only its own
      tables — see schema strategy below)
- [ ] Configure Redis as session and cache backend
- [ ] `whitenoise` for static file serving

### 1b — User model + RBAC

```python
# accounts/models.py
class User(AbstractUser):
    ROLES = [("guest", "Guest"), ("user", "User"), ("admin", "Admin")]
    role = models.CharField(max_length=16, choices=ROLES, default="user")
    # Phase 2+: default_lat, default_lon, default_radius_km, preferred_sites
```

- [ ] Custom user model (`AUTH_USER_MODEL = "accounts.User"`)
- [ ] Role-check decorator:

```python
def require_role(min_role="user"):
    def decorator(view_func):
        @login_required
        def wrapper(request, *args, **kwargs):
            if not has_role(request.user, min_role):
                return HttpResponseForbidden()
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

# Usage:
@require_role("admin")
def admin_view(request): ...
```

### 1c — Auth middleware (the portability layer)

This middleware runs on every request. It reads `AUTH_EMAIL_HEADER` from
settings (set via env), looks up or creates the user, and establishes a
Django session. Once a session exists the header is no longer needed.

```python
# accounts/middleware.py
class ProxyAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.header = settings.AUTH_EMAIL_HEADER  # from env
        self.bypass = settings.AUTH_BYPASS        # True in local dev

    def __call__(self, request):
        if self.bypass and not request.user.is_authenticated:
            request.user = User.objects.get_or_create(
                email="dev@localhost", defaults={"role": "admin"}
            )[0]
        elif self.header and not request.user.is_authenticated:
            email = request.headers.get(self.header)
            if email:
                user, _ = User.objects.get_or_create(
                    email=email,
                    defaults={"username": email, "role": "user"},
                )
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)
```

### 1d — Existing schema strategy

Django manages only its own tables. Existing tables (`sites`,
`scoring_weights`, `visitors`, etc.) are accessed via raw SQL or SQLAlchemy
exactly as they are today — the existing `db.py`, `scorer.py`, `forecast.py`
modules import cleanly into Django views with no changes.

New Django-managed tables get the `starwolf_` prefix to avoid any collision:
`starwolf_user`, `starwolf_session`, etc. Set in `settings.py`:

```python
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# All Django app tables use this prefix via AppConfig.default_auto_field
# Existing tables accessed via db.py / SQLAlchemy — Django does not migrate them
```

### 1e — Add Django to docker-compose

```yaml
django:
  build:
    context: .
    dockerfile: Dockerfile.django
  command: gunicorn starwolf_django.wsgi --bind 0.0.0.0:8080
  ports:
    - "8080:8080"
  environment:
    DATABASE_URL: postgresql://${POSTGRES_USER:-stargazing}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-stargazing}
    REDIS_URL: redis://redis:6379
    DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY}
    AUTH_EMAIL_HEADER: ${AUTH_EMAIL_HEADER}
    AUTH_BYPASS: ${AUTH_BYPASS:-false}
  depends_on:
    db:
      condition: service_healthy
  restart: unless-stopped
```

### 1f — NPM routing (strangler fig starts here)

Add a second proxy host in NPM for the same domain, path-based:

- `/` → Streamlit `:8501` (catch-all, unchanged)
- As pages migrate, add path rules above the catch-all pointing to Django `:8080`

NPM's "Advanced" tab accepts custom nginx location blocks for path routing.

**New `.env` vars:**
```
DJANGO_SECRET_KEY=    # python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
AUTH_BYPASS=false     # set true in local dev
```

---

## Phase 2 — Page Migration ✅ COMPLETE

**Goal:** Migrate pages one at a time in complexity order. Each migration is
a discrete PR: Django view + template + HTMX wiring, NPM route flipped,
Streamlit page left in place but no longer routed to.

The FastAPI public API (`/api/*`) is untouched throughout.

### Migration order

| Order | Page          | Streamlit file       | Complexity | Status |
|-------|---------------|----------------------|------------|--------|
| 1     | About         | `6_About.py`         | Low        | ✅ Done |
| 2     | API Guide     | `7_API.py`           | Low        | ✅ Done |
| 3     | Feedback      | `4_Feedback.py`      | Low        | ✅ Done |
| 4     | Bortle Scorer | `8_Bortle_Scorer.py` | Medium     | ✅ Done |
| 5     | Preferences   | `2_Preferences.py`   | Medium     | ✅ Done — now DB-backed per user |
| 6     | Location      | `0_Location.py`      | Medium     | ✅ Done |
| 7     | Admin         | `3_Admin.py`         | Medium     | ✅ Done — RBAC with require_role("admin") |
| 8     | Visitors      | `5_Visitors.py`      | Descoped   | 🚫 Removed from scope — visitor analytics not being migrated |
| 9     | Sites         | `1_Sites.py`         | High       | ✅ Done — filterable, distance-sorted, paginated |
| 10    | Heatmap       | `9_Heatmap.py`       | High       | ✅ Done — Leaflet map, admin-triggered background compute |
| 11    | Planner       | `Planner.py`         | Highest    | ✅ Done — background thread, per-user Redis cache, heatmap, AI summary |

### What was actually used (vs. plan)

| Feature               | Planned                    | Actual                                       |
|-----------------------|----------------------------|----------------------------------------------|
| Reactive UI           | htmx + django-htmx         | htmx 2.x + Alpine.js 3.x (no django-htmx)  |
| Data tables           | django-tables2             | Raw SQL + hand-rolled templates              |
| Forms                 | django-crispy-forms        | Plain Django forms + custom CSS              |
| Maps                  | pydeck embed               | Leaflet.js with CartoDB Dark tiles           |
| Rate limiting         | django-ratelimit           | Manual Redis counter (already in place)      |
| AI summary            | existing ai_summary.py     | ✅ Used unchanged                            |
| Bortle / scoring      | existing shared modules    | ✅ Used unchanged via PYTHONPATH=/app        |

---

---

## Management Commands

Run all commands from `/opt/stargazing-app` with `docker compose exec django python manage.py <command>`.

| Command | Purpose | Example |
|---------|---------|---------|
| `create_local_admin <email> <password>` | Create or update a local admin user with a password (bypasses Cloudflare — for local dev and emergency access) | `python manage.py create_local_admin travis Aggies83` |
| `offboard_user <email>` | Deactivate a user removed from Cloudflare Access. Sets `is_active=False`; preserves all preferences for re-activation. Blocked at both Cloudflare (can't get header) and middleware (`is_active` check). | `python manage.py offboard_user someone@example.com` |
| `offboard_user <email> --reactivate` | Re-activate a previously deactivated user. Their location, preferences, and settings are restored immediately. | `python manage.py offboard_user someone@example.com --reactivate` |

### User lifecycle

```
Cloudflare Access panel: add user
    → first request → ProxyAuthMiddleware auto-creates User + UserPreferences

Cloudflare Access panel: remove user
    → run: python manage.py offboard_user their@email.com
    → is_active=False; blocked at Cloudflare edge AND middleware

Re-add to Cloudflare panel
    → run: python manage.py offboard_user their@email.com --reactivate
    → all preferences restored
```

### app_settings keys (Admin → Settings)

| Key | Default | Description |
|-----|---------|-------------|
| `forecast_days` | 10 | Forecast horizon in days (1–16) |
| `timezone` | `America/Chicago` | Default timezone |
| `planner_max_sites` | 250 | Maximum sites scored per Planner run — closest sites scored first when cap is hit |
| `ollama_url` | `http://localhost:11434` | Ollama endpoint for AI summaries |
| `ollama_model` | `llama3` | Model used for AI narrative summaries |

---

## Phase 3 — Streamlit Retirement (1 day)

Once all 11 pages are migrated and stable:

- [ ] Remove `app` service from `docker-compose.yml`
- [ ] Remove Streamlit packages from `requirements.txt`
- [ ] Delete `pages/`, `Planner.py`, `visit_tracker.py`
- [ ] Delete `.streamlit/`
- [ ] Remove Streamlit catch-all from NPM — all traffic to Django
- [ ] If using Cloudflare Access: no changes needed, it stays
- [ ] If using oauth2-proxy: can retire it now if django-allauth is
      configured as a direct Google OAuth provider instead

---

## Strangler Fig: How Both Sites Stay Live

```
Internet
    ↓
Cloudflare (DNS + SSL + optional Access auth)
    ↓
cloudflared tunnel
    ↓
Nginx Proxy Manager
    ├── /about, /feedback, /api-guide → Django :8080   (migrated)
    ├── /static/                       → Django :8080
    ├── /api/                          → FastAPI :8000  (never changes)
    └── /  (catch-all)                 → Streamlit :8501 (until Phase 3)
```

Users see one domain throughout. NPM is the only component that knows
two backends exist. Each page migration is a new path rule in NPM — one
line, instantly reversible.

### Session continuity during migration

- Phase 0: auth proxy validates identity, injects email header
- Phase 1–2: Django middleware reads header → creates session cookie
  (`sessionid`). Coexists with any auth proxy cookie — different names,
  same domain, no conflict.
- Phase 3: auth proxy cookie retired (or kept if using Cloudflare Access
  long-term). Django session is authoritative.

### Data continuity

- Postgres is shared throughout — Django and Streamlit read the same tables
- Django migrations only add new tables; existing tables untouched
- Per-user preferences (new table) populated as users first log in to Django

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| pydeck embed complex outside Streamlit | Spike the Heatmap page before finalising migration order |
| Django migrations touch existing tables | `managed = False` on existing table models; Django only migrates its own |
| Session lost between Streamlit/Django | Preferences in DB by Phase 2; nothing load-bearing stays in `st.session_state` |
| Rollback needed mid-migration | Each NPM path rule is a one-click revert; Streamlit runs until Phase 3 |
| Repo cloners without Cloudflare | oauth2-proxy path in Phase 0 + `AUTH_EMAIL_HEADER` env var covers all cases |

---

## Full .env additions (all phases)

```
# Phase 0 — Path A (Cloudflare Access)
AUTH_EMAIL_HEADER=Cf-Access-Authenticated-User-Email

# Phase 0 — Path B (oauth2-proxy, for non-Cloudflare deployments)
OAUTH2_COOKIE_SECRET=   # openssl rand -base64 32
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
AUTH_EMAIL_HEADER=X-Auth-Request-Email

# Phase 1 (both paths)
DJANGO_SECRET_KEY=      # python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
AUTH_BYPASS=false       # set true for local dev (no proxy needed)
```
