# Management Commands

All commands run inside the Django container:

```bash
docker compose exec django python manage.py <command> [options]
```

Use `-d` before `django` to run in the background (fire-and-forget):

```bash
docker compose exec -d django python manage.py <command>
```

---

## `create_local_admin`

Create or update a local admin account that can sign in with email/password — bypasses Cloudflare Access. Useful for initial setup and emergency access.

```bash
docker compose exec django python manage.py create_local_admin <email> <password>
```

**Example:**
```bash
docker compose exec django python manage.py create_local_admin admin@example.com s3cr3t
```

---

## `offboard_user`

Soft-deactivate a user by email. Preserves their preferences in case they are re-added later.

```bash
docker compose exec django python manage.py offboard_user <email> [--reactivate]
```

| Flag | Description |
|------|-------------|
| *(none)* | Deactivate the user |
| `--reactivate` | Re-activate a previously deactivated user |

**Examples:**
```bash
docker compose exec django python manage.py offboard_user someone@example.com
docker compose exec django python manage.py offboard_user someone@example.com --reactivate
```

---

## `compute_heatmap`

Score all active sites for tonight and upsert results into `site_daily_scores`. Skips automatically if scores already exist for today unless `--force` is passed.

**Runs automatically at noon CDT (17:00 UTC) via cron.** Can also be triggered manually or via the Admin UI.

```bash
docker compose exec django python manage.py compute_heatmap [--only-missing] [--force]
```

| Flag | Description |
|------|-------------|
| *(none)* | Score all sites; skip today if already done |
| `--only-missing` | Only score sites with no score for today (fill gaps) |
| `--force` | Recompute all sites even if already scored today |

**Cron entry** (host machine, `travis` user):
```
0 17 * * * docker compose exec -T django python manage.py compute_heatmap >> /var/log/starwolf-heatmap.log 2>&1
```

**Check the log:**
```bash
tail -f /var/log/starwolf-heatmap.log
```

---

## `populate_site_locations`

Reverse-geocode each site's lat/lon via Nominatim to populate `country` and `state_province` columns. Skips already-geocoded sites by default. Rate-limited to 1 request/second per Nominatim's usage policy.

```bash
docker compose exec -d django python manage.py populate_site_locations [--all] [--limit N]
```

| Flag | Description |
|------|-------------|
| *(none)* | Geocode only sites where `country IS NULL` |
| `--all` | Re-geocode all sites, including already-populated ones |
| `--limit N` | Stop after N sites |

**Check progress:**
```bash
docker compose exec django python manage.py shell -c "
from django.db import connection
with connection.cursor() as cur:
    cur.execute('SELECT COUNT(*) FROM sites WHERE country IS NOT NULL')
    done = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM sites')
    total = cur.fetchone()[0]
print(f'{done}/{total} geocoded')
"
```

> **Note:** A container rebuild kills this process mid-run. Re-run after rebuilding — already-geocoded sites are skipped automatically.

---

## `enrich_notes`

Rewrite site notes using a local Ollama model + Wikipedia summaries. Skips sites that already have rich notes (> 200 chars, non-admin-style) unless `--force` is passed.

Requires Ollama running on the host machine. The container reaches it via `host.docker.internal:11434`.

```bash
docker compose exec -d django python manage.py enrich_notes [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | none | Stop after N sites |
| `--offset N` | 0 | Skip the first N matching sites (for parallel batches) |
| `--force` | false | Rewrite all notes, including already-enriched ones |
| `--model NAME` | `llama3.1:8b` | Ollama model to use |
| `--ollama URL` | `http://host.docker.internal:11434` | Ollama base URL |

**Running parallel non-overlapping batches:**
```bash
docker compose exec -d django python manage.py enrich_notes --offset 0    --limit 400
docker compose exec -d django python manage.py enrich_notes --offset 400  --limit 400
docker compose exec -d django python manage.py enrich_notes --offset 800  --limit 400
docker compose exec -d django python manage.py enrich_notes --offset 1200 --limit 400
```

**Check progress:**
```bash
docker compose exec django python manage.py shell -c "
from django.db import connection
with connection.cursor() as cur:
    cur.execute(\"SELECT COUNT(*) FROM sites WHERE LENGTH(notes) > 200 AND notes NOT LIKE '%— %'\")
    print('Enriched:', cur.fetchone()[0])
"
```

> **Note:** A container rebuild kills this process mid-run. Re-run after rebuilding — already-enriched sites are skipped automatically.
