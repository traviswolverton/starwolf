# Security Hardening Log

This document records the security audit performed on 2026-06-29 and all remediations applied. The audit covered three areas: general vulnerabilities, guest/customer data exposure, and DDoS exposure.

---

## Threat Model

- **App**: Django 5 stargazing planner, public-facing at starwolf.wolvertons.net
- **Auth**: Google OAuth + email via django-allauth; guests may use the app without logging in
- **Infra**: Cloudflare → Gunicorn → Django → Postgres + Redis
- **Data sensitivity**: User location (lat/lon), session data, feedback submissions. No financial data.
- **Attacker profile**: Automated abuse (scrapers, rate-limit bypass, DDoS), opportunistic web scanning

---

## Findings and Remediations

### CRITICAL

#### C1 — Open Redirect on Login
**File**: `django/accounts/views.py`  
**Risk**: The `next` parameter on the login redirect was passed to `redirect()` without validation. An attacker could craft `/?next=https://phishing.com` and redirect authenticated users to an external site after login.  
**Fix**: Added `_safe_next()` helper that rejects any URL containing a scheme or netloc (i.e., anything not a relative path). Applied to both GET and POST `next` handling.

#### C2 — Unauthenticated DDoS via Bortle Scorer
**File**: `django/pages/views.py` — `bortle_scorer` view  
**Risk**: The `POST /bortle` endpoint reads a GeoTIFF from disk on every request with no rate limiting at the view level. The API endpoint had a 60 req/min limit, but the browser-facing view had none.  
**Fix**: Added `_view_rate_limited()` helper (reuses `_ip_hash`) and applied a 15 req/min/IP limit to `bortle_scorer`.

#### C3 — X-Forwarded-For Spoofable
**Files**: `django/pages/views.py` — `_ip_hash()`, `django/pages/api_views.py` — `_ip()`  
**Risk**: Both IP extraction functions used `.split(",")[0]` — the first entry in `X-Forwarded-For`. The client controls this value; an attacker can rotate it to bypass all IP-based rate limiting.  
**Fix**: Changed both to `.split(",")[-1]` — the last entry, which is appended by Cloudflare and cannot be spoofed by the client.

#### C4 — Session Fixation on Guest Location
**File**: `django/pages/views.py` — `set_guest_location`  
**Risk**: When a guest set their location, the session key was not rotated. An attacker who planted a known session ID (e.g., via a shared device or a fixation attack) could track location changes on the same session.  
**Fix**: Added `request.session.cycle_key()` immediately before writing guest location data to the session.

#### C5 — Planner Thread Bomb
**File**: `django/pages/views.py` — `planner_run` and `_run_planner_thread`  
**Risk**: Each `POST /planner/run` spawned a new background thread with no global cap. An attacker hitting the endpoint repeatedly with different parameters could exhaust server threads.  
**Fix**: Added a Redis counter (`planner:global_active`) checked before spawning. Requests that would exceed 10 concurrent jobs receive a 429. The thread decrements the counter in a `finally` block on exit.

---

### HIGH

#### H1 — Missing Security Headers
**File**: `django/config/settings.py`  
**Risk**: Several security-critical HTTP headers and cookie flags were absent, leaving the app exposed to clickjacking, session theft over HTTP, and CSRF via cross-site requests.  
**Fix**: Added the following settings:
```python
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = "DENY"
```

#### H2 — Exception Details Leaked to Users
**File**: `django/pages/views.py`  
**Risk**: Four `except Exception as e` blocks rendered the raw exception string directly into HTML responses. Third-party API error messages (Nominatim, GitHub) could expose internal details.  
**Locations fixed**:
- Reverse geocode failure in `location` view (line ~284)
- Preferences save failure (line ~397)
- Bortle `ValueError` in `bortle_scorer` (line ~932)
- Feedback GitHub submission failure (line ~1414)

**Fix**: All four now log the exception via `_log.error()` and return a generic user-facing message.

#### H3 — Address Input Length Not Validated
**File**: `django/pages/views.py`  
**Risk**: User-supplied address strings were passed to Nominatim without a length cap. An attacker could send oversized payloads to exhaust outbound bandwidth or trigger Nominatim rate limits.  
**Fix**: Applied `.strip()[:200]` to address inputs in three places: authenticated `location` view, `set_guest_location`, and `bortle_scorer`.

#### H4 — IP_HASH_SALT Not Validated
**File**: `django/pages/views.py` — `_ip_hash()`  
**Risk**: If `IP_HASH_SALT` is missing from the environment, the HMAC-style hash degrades to a plain SHA256 of the IP, making rate limit keys predictable.  
**Fix**: Added a fallback string and a `_log.warning()` if the salt is unset, so the failure is visible in logs without crashing.

#### H5 — Admin Views Lacked Decorator-Level Protection
**File**: `django/pages/views.py`  
**Risk**: All seven admin views (`admin_panel`, `admin_save_weights`, `admin_save_settings`, `admin_bortle_fill`, `admin_save_prompts`, `admin_user_role`, `admin_user_active`) performed auth checks inline in the view body. A future exception or code change before the check could expose admin functionality.  
**Fix**: Added `@require_admin` decorator (already defined in `accounts/decorators.py`) to all seven views. Inline `is_admin()` checks removed.

#### H6 — No Audit Logging for Sensitive Admin Actions
**File**: `django/pages/views.py` — `admin_user_role`, `admin_user_active`  
**Risk**: Role changes and user deactivations left no audit trail.  
**Fix**: Added `_log.info("AUDIT ...")` entries to both views, recording admin user ID, target user ID, and the change made.

#### H7 — Sky Catalog API Returned All Objects Unbounded
**File**: `django/pages/api_views.py` — `sky_catalog`  
**Risk**: The `/api/v1/sky-catalog` endpoint serialized all matching objects into memory with no limit. At 179 objects this is fine; at scale it becomes a memory DoS vector.  
**Fix**: Hard cap of 1,000 objects per response. If the result is truncated, the response includes `"truncated": true` and `"total": <full count>`.

---

### MEDIUM

#### M1 — Unvalidated Timezone Strings
**File**: `django/engine/sky_objects.py` — `compute_sky()`  
**Risk**: User-supplied `tz_str` was passed directly to `ZoneInfo()`. Malformed values would raise `ZoneInfoNotFoundError`; repeated bad values waste CPU in exception handling.  
**Fix**: Added `if tz_name not in available_timezones(): tz_name = "UTC"` before constructing the `ZoneInfo` object.

#### M2 — Cache Stampede on Forecast Fetches
**File**: `django/engine/forecast.py` — `_fetch_open_meteo()`  
**Risk**: Under concurrent load, multiple threads could simultaneously miss the cache for the same lat/lon/date and all call Open-Meteo, multiplying external API load.  
**Fix**: Added a Redis lock using `cache.add()` (atomic, fails if key exists). Competing threads wait up to 5 seconds for the cache to populate before falling through. Lock is always released in a `finally` block.

---

### LOW

#### L1 — No Content-Type Validation on External API Responses
**File**: `django/pages/views.py`  
**Risk**: Nominatim responses were parsed with `resp.json()` without checking `Content-Type`. A 503 HTML error page would cause a `JSONDecodeError`, caught but producing a confusing log.  
**Fix**: Added `_safe_json(resp)` helper that checks `"json" in content-type` before parsing. Applied to all three Nominatim call sites (`_geocode`, auth `location`, `set_guest_location`).

#### L2 — API Guide File Load Could Expose Path in Errors
**File**: `django/pages/views.py` — `api_guide()`  
**Risk**: `guide_path.read_text()` with no error handling would raise an unhandled exception if the file was missing, potentially exposing the filesystem path in DEBUG mode.  
**Fix**: Wrapped in `try/except` with `_log.error()` and a graceful "documentation temporarily unavailable" response.

---

## Summary

| ID | Severity | Issue | Status |
|----|----------|-------|--------|
| C1 | Critical | Open redirect on login | ✅ Fixed |
| C2 | Critical | Bortle scorer unthrottled | ✅ Fixed |
| C3 | Critical | X-Forwarded-For spoofable | ✅ Fixed |
| C4 | Critical | Session fixation on guest location | ✅ Fixed |
| C5 | Critical | Planner thread bomb | ✅ Fixed |
| H1 | High | Missing security headers | ✅ Fixed |
| H2 | High | Exception details leaked to users | ✅ Fixed |
| H3 | High | Address input unbounded | ✅ Fixed |
| H4 | High | IP_HASH_SALT not validated | ✅ Fixed |
| H5 | High | Admin views no decorator | ✅ Fixed |
| H6 | High | No admin audit logging | ✅ Fixed |
| H7 | High | Sky catalog API unpaginated | ✅ Fixed |
| M1 | Medium | Timezone string unvalidated | ✅ Fixed |
| M2 | Medium | Forecast cache stampede | ✅ Fixed |
| L1 | Low | External API content-type not checked | ✅ Fixed |
| L2 | Low | API guide unsafe file load | ✅ Fixed |

**16 of 16 findings resolved.** No open items.

---

## Items Explicitly Not Addressed

- **Session timing side-channel** (theoretical, not exploitable over a network)
- **Heatmap status endpoint info leak** (protected behind admin auth, key is non-guessable in practice)

These were assessed as negligible risk given the app's threat model and user base.
