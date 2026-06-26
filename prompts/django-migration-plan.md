# StarWolf Django Migration Plan

## Goal

Migrate from Streamlit to Django + HTMX to support proper user auth, RBAC,
per-user data, and a maintainable frontend architecture. The existing site
stays live throughout using a strangler fig pattern — nginx routes migrated
pages to Django and unmigrated pages to Streamlit until the transition is
complete.

## Current Stack

| Layer      | Technology                        |
|------------|-----------------------------------|
| Frontend   | Streamlit (port 8501)             |
| Public API | FastAPI / uvicorn (port 8000)     |
| Database   | Postgres 16                       |
| Cache      | Redis 7                           |
| Proxy      | nginx (implied, not in repo)      |
| Auth       | Single shared password in secrets |

## Target Stack

| Layer      | Technology                              |
|------------|-----------------------------------------|
| Frontend   | Django + HTMX + Alpine.js (port 8080)  |
| Public API | FastAPI / uvicorn (port 8000) — kept   |
| Database   | Postgres 16 — same instance            |
| Cache      | Redis 7 — same instance                |
| Proxy      | nginx — routes by URL path             |
| Auth       | Google OAuth via django-allauth         |

---

## Phase 0 — Auth Now, No Code Changes (1–2 days)

**Goal:** Real OAuth login without touching Streamlit or starting the migration.

Stand up `oauth2-proxy` as a new Docker service in front of nginx. Users
authenticate with Google; `oauth2-proxy` injects `X-Auth-Email` and
`X-Auth-User` headers upstream. Streamlit ignores these headers for now —
the value is that Phase 1 can read them immediately when Django arrives.

### Tasks

- [ ] Register a Google OAuth app (Google Cloud Console → Credentials)
- [ ] Add `oauth2-proxy` service to `docker-compose.yml`
- [ ] Configure nginx to run auth check via `oauth2-proxy` before proxying
      to Streamlit
- [ ] Set `OAUTH2_PROXY_EMAIL_DOMAINS` to restrict to your domain (or `*`
      for open)
- [ ] Verify login flow end-to-end

### Docker service sketch

```yaml
oauth2-proxy:
  image: quay.io/oauth2-proxy/oauth2-proxy:latest
  command:
    - --provider=google
    - --upstream=http://app:8501
    - --http-address=0.0.0.0:4180
    - --email-domain=*
    - --cookie-secret=${OAUTH2_COOKIE_SECRET}
    - --client-id=${GOOGLE_CLIENT_ID}
    - --client-secret=${GOOGLE_CLIENT_SECRET}
  ports:
    - "4180:4180"
  restart: unless-stopped
```

### New .env vars needed

```
OAUTH2_COOKIE_SECRET=   # 32-byte random: openssl rand -base64 32
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

---

## Phase 1 — Django Scaffold + Auth (1 week)

**Goal:** Django running alongside Streamlit, no pages migrated yet. Auth,
user model, and RBAC are fully working.

### 1a — Project setup

- [ ] Add `django`, `django-allauth`, `whitenoise`, `django-redis`,
      `psycopg2-binary` (already in requirements) to a new
      `requirements-django.txt`
- [ ] `django-admin startproject starwolf` → commit scaffold
- [ ] Point `settings.py` at the existing Postgres instance (separate
      `starwolf_django` schema or same DB, Django tables prefixed)
- [ ] Configure Redis as the session and cache backend
- [ ] `whitenoise` for static file serving (no separate nginx static config
      needed in dev)

### 1b — User model + RBAC

```python
# accounts/models.py
class User(AbstractUser):
    ROLES = [("guest", "Guest"), ("user", "User"), ("admin", "Admin")]
    role = models.CharField(max_length=16, choices=ROLES, default="user")
    # future: default_lat, default_lon, default_radius_km
```

- [ ] Custom user model (`AUTH_USER_MODEL = "accounts.User"`)
- [ ] `django-allauth` configured for Google provider
- [ ] Auth middleware: every request has `request.user`
- [ ] Role-check decorator:

```python
def require_role(min_role):
    def decorator(view_func):
        @login_required
        def wrapper(request, *args, **kwargs):
            if not has_role(request.user, min_role):
                return HttpResponseForbidden()
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
```

### 1c — Add Django to docker-compose

```yaml
django:
  build:
    context: .
    dockerfile: Dockerfile.django
  command: gunicorn starwolf.wsgi --bind 0.0.0.0:8080
  ports:
    - "8080:8080"
  environment:
    DATABASE_URL: postgresql://${POSTGRES_USER:-stargazing}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB:-stargazing}
    REDIS_URL: redis://redis:6379
    SECRET_KEY: ${DJANGO_SECRET_KEY}
    GOOGLE_CLIENT_ID: ${GOOGLE_CLIENT_ID}
    GOOGLE_CLIENT_SECRET: ${GOOGLE_CLIENT_SECRET}
  depends_on:
    db:
      condition: service_healthy
  restart: unless-stopped
```

### 1d — nginx routing (strangler fig starts here)

nginx gets a simple rule: requests for migrated paths go to Django (8080),
everything else goes to Streamlit (8501) — or to oauth2-proxy (4180) if
Phase 0 is in place.

```nginx
# Initially — all traffic to Streamlit
location / {
    proxy_pass http://app:8501;
}

# As pages migrate, add blocks above the catch-all:
# location /about { proxy_pass http://django:8080; }
# location /feedback { proxy_pass http://django:8080; }
# ...
```

---

## Phase 2 — Page Migration (3–4 weeks)

**Goal:** Migrate pages one at a time in complexity order. Each migration is
a discrete PR: Django view + template + HTMX wiring, nginx route flipped,
Streamlit page left in place but no longer routed to.

The FastAPI public API (`/api/*`) is untouched throughout — it stays as-is.

### Migration order

| Order | Page              | Streamlit file      | Complexity | Notes |
|-------|-------------------|---------------------|------------|-------|
| 1     | About             | `6_About.py`        | Low        | Static content, no data |
| 2     | API Guide         | `7_API.py`          | Low        | Renders `API_GUIDE.md` |
| 3     | Feedback          | `4_Feedback.py`     | Low        | Form → GitHub API, rate limiting already in Redis |
| 4     | Bortle Scorer     | `8_Bortle_Scorer.py`| Medium     | Form + map embed + FastAPI call |
| 5     | Preferences       | `2_Preferences.py`  | Medium     | Sliders → per-user DB row once auth exists |
| 6     | Location          | `0_Location.py`     | Medium     | Geocode form → store on user model |
| 7     | Admin             | `3_Admin.py`        | Medium     | Django admin or custom views with HTMX tables |
| 8     | Visitors          | `5_Visitors.py`     | High       | Plotly map embed, aggregate queries |
| 9     | Sites             | `1_Sites.py`        | High       | Filterable table, inline add/toggle, per-user lists |
| 10    | Heatmap           | `9_Heatmap.py`      | High       | pydeck embed, daily cache |
| 11    | Planner           | `Planner.py`        | Highest    | Core scoring view, site activation, AI summary |

### Per-page checklist

For each page:
- [ ] Django view (`views.py`)
- [ ] URL route (`urls.py`)
- [ ] Template (`templates/<page>.html`) extending `base.html`
- [ ] HTMX for any interactive elements (filtering, toggles, form submission)
- [ ] Tests (`tests/test_<page>.py`)
- [ ] nginx route flipped to Django
- [ ] Smoke-test against production data

### Key Django packages per feature

| Feature                    | Package                      |
|----------------------------|------------------------------|
| OAuth login                | `django-allauth`             |
| Plotly charts              | embed via `{{ plotly_json\|safe }}` in template |
| pydeck maps                | embed via script tag         |
| Reactive UI                | `htmx` + `django-htmx`      |
| Data tables                | `django-tables2`             |
| Forms                      | Django forms + crispy-forms  |
| Rate limiting (feedback)   | existing Redis logic → port to `django-ratelimit` |
| AI summary                 | call existing `ai_summary.py` directly |
| Bortle lookup              | call existing `bortle_lookup.py` directly |
| Scoring / forecast         | call existing `scorer.py`, `forecast.py` directly |

> The scoring, forecast, bortle, and AI modules are plain Python — they
> import cleanly into Django views with no changes needed.

---

## Phase 3 — Streamlit Retirement (1 day)

Once all 11 pages are migrated and stable:

- [ ] Remove `app` service from `docker-compose.yml`
- [ ] Remove `streamlit`, `extra-streamlit-components`, `streamlit-geolocation`
      from `requirements.txt`
- [ ] Delete `pages/`, `Planner.py`, `visit_tracker.py` (visitor logic moves
      to Django middleware)
- [ ] Remove Streamlit-specific config from `.streamlit/`
- [ ] Update nginx to drop the Streamlit fallback — all traffic to Django
- [ ] Update `Dockerfile` (or replace with `Dockerfile.django`)

---

## Keeping Both Sites Running (Strangler Fig Detail)

### How it works

```
Browser → nginx → oauth2-proxy (Phase 0+)
                       ↓
              ┌────────┴────────┐
         migrated?           not yet?
              ↓                  ↓
         Django :8080      Streamlit :8501
```

Users see one site at one domain throughout. nginx is the only thing that
knows two backends exist. A migrated page is indistinguishable from an
unmigrated one from the user's perspective.

### nginx routing strategy

Use a location block per migrated Django path, with a catch-all to Streamlit:

```nginx
server {
    listen 80;

    # Migrated pages (add each when ready)
    location /about       { proxy_pass http://django:8080; }
    location /feedback    { proxy_pass http://django:8080; }
    location /api-guide   { proxy_pass http://django:8080; }

    # Django static files
    location /static/     { proxy_pass http://django:8080; }

    # FastAPI public API — never changes
    location /api/        { proxy_pass http://api:8000; }

    # Everything else → Streamlit until migration is complete
    location / {
        proxy_pass http://app:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";  # required for Streamlit WebSocket
    }
}
```

### Session continuity

- **Phase 0–1:** oauth2-proxy handles session; both Streamlit and Django
  receive the same `X-Auth-Email` header
- **Phase 2:** Django session cookie (`sessionid`) coexists with the
  oauth2-proxy cookie — same domain, different cookie names, no conflict
- **Phase 3:** oauth2-proxy cookie retired; Django session is the only auth

### Data continuity

- Postgres is shared — Django reads the same `sites`, `scoring_weights`,
  `app_settings`, `visitors` tables throughout
- Django migrations add new tables (`auth_user`, `accounts_user`, etc.)
  without touching existing ones
- Per-user preference storage (new `user_preferences` table) added in
  Phase 1 and populated as users log in

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| pydeck embed is complex outside Streamlit | Prototype the heatmap page first as a spike before committing to the migration order |
| Django migrations conflict with existing schema | Use `managed = False` on models that map to existing tables; only let Django manage its own new tables |
| Session state lost between Streamlit and Django | Preferences move to DB in Phase 1; nothing meaningful lives only in `st.session_state` by the time pages migrate |
| Rollback needed | Every nginx route flip is a one-line revert; Streamlit stays running until Phase 3 |

---

## New .env vars summary

```
# Phase 0
OAUTH2_COOKIE_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Phase 1
DJANGO_SECRET_KEY=
```
