"""
Management command: enrich_notes
Rewrites the notes column for stargazing sites using Ollama + Wikipedia.

Usage:
  python manage.py enrich_notes                        # skip sites with notes > 200 chars
  python manage.py enrich_notes --force                # redo everything
  python manage.py enrich_notes --limit 200            # stop after 200 sites
  python manage.py enrich_notes --offset 200 --limit 200   # second batch of 200
  python manage.py enrich_notes --model phi4           # use a different Ollama model
  python manage.py enrich_notes --ollama http://host.docker.internal:11434

Parallel batches (no overlap):
  docker compose exec -d django python manage.py enrich_notes --offset 0   --limit 200
  docker compose exec -d django python manage.py enrich_notes --offset 200 --limit 200
  docker compose exec -d django python manage.py enrich_notes --offset 400 --limit 200
"""
import time
import json
import urllib.request
import urllib.parse
import urllib.error

from django.core.management.base import BaseCommand
from django.db import connection

OLLAMA_DEFAULT = "http://host.docker.internal:11434"
MODEL_DEFAULT = "llama3.1:8b"

COUNTRY_NAMES = {
    "US": "United States", "CA": "Canada", "AU": "Australia", "NZ": "New Zealand",
    "GB": "United Kingdom", "IE": "Ireland", "FR": "France", "DE": "Germany",
    "AT": "Austria", "CH": "Switzerland", "ES": "Spain", "PT": "Portugal",
    "IT": "Italy", "CZ": "Czech Republic", "SK": "Slovakia", "HU": "Hungary",
    "PL": "Poland", "NO": "Norway", "SE": "Sweden", "FI": "Finland",
    "IS": "Iceland", "CL": "Chile", "AR": "Argentina", "ZA": "South Africa",
    "NA": "Namibia", "KE": "Kenya", "MX": "Mexico",
}

TYPE_LABELS = {
    "ida_certified":  "IDA Certified Dark Sky Place",
    "national_park":  "National Park",
    "national_forest":"National Forest",
    "state_park":     "State / Provincial Park",
    "community":      "Community Dark Sky Site",
    "observatory":    "Public Observatory",
}

BORTLE_DESC = {
    1: "pristine dark sky", 2: "truly dark sky", 3: "rural sky",
    4: "rural/suburban transition", 5: "suburban sky", 6: "bright suburban",
    7: "suburban/urban", 8: "city sky", 9: "inner city",
}

PROMPT_TMPL = """\
Write a 1–2 sentence description for a stargazing site listing. \
Be concise (under 230 characters total), factual, and useful to an amateur astronomer planning a visit. \
Accurately reflect the Bortle class — do not describe a Bortle 4+ site as "darkest" or "pristine". \
Mention notable features, accessibility, or special astronomy facilities if relevant. \
Do not start with the site name. Reply with only the description text, nothing else.

Site: {name}
Type: {type_label}
Location: {location}
Bortle class: {bortle} ({bortle_desc})
Current description: {notes}
Background: {background}
"""


def _wikipedia(name, state):
    """Return a short Wikipedia extract for the site, or empty string."""
    query = f"{name} {state or ''}".strip()
    # Step 1: search
    search_url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={urllib.parse.quote(query)}&format=json&srlimit=1&utf8=1"
    )
    try:
        with urllib.request.urlopen(search_url, timeout=8) as r:
            data = json.loads(r.read())
        results = data.get("query", {}).get("search", [])
        if not results:
            return ""
        title = results[0]["title"]
        # Step 2: summary
        summary_url = (
            f"https://en.wikipedia.org/api/rest_v1/page/summary/"
            f"{urllib.parse.quote(title.replace(' ', '_'))}"
        )
        with urllib.request.urlopen(summary_url, timeout=8) as r:
            page = json.loads(r.read())
        extract = page.get("extract", "")
        # First two sentences only
        sentences = extract.replace("\n", " ").split(". ")
        return ". ".join(sentences[:2]).strip()[:600]
    except Exception:
        return ""


def _ollama(prompt, model, base_url):
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.4, "num_predict": 120},
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data.get("response", "").strip().strip('"')


class Command(BaseCommand):
    help = "Rewrite site notes using Ollama + Wikipedia"

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true",
                            help="Overwrite even sites that already have rich notes")
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--offset", type=int, default=0,
                            help="Skip the first N matching sites (for parallel batches)")
        parser.add_argument("--model", default=MODEL_DEFAULT)
        parser.add_argument("--ollama", default=OLLAMA_DEFAULT)

    def handle(self, *args, **options):
        force = options["force"]
        limit = options["limit"]
        offset = options["offset"]
        model = options["model"]
        ollama_url = options["ollama"]

        # Verify Ollama is reachable
        try:
            with urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=5):
                pass
            self.stdout.write(f"Ollama OK at {ollama_url} using model {model}")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Cannot reach Ollama at {ollama_url}: {e}"))
            return

        from accounts.models import Site
        from django.db.models import Q
        qs = Site.objects.order_by("id")
        if not force:
            qs = qs.filter(Q(notes__isnull=True) | Q(notes__regex=r'^.{0,199}$') | Q(notes__contains="— "))
        sites = list(qs.values_list("id", "name", "site_type", "bortle_class", "state_province", "country", "notes"))

        if offset:
            sites = sites[offset:]
        if limit:
            sites = sites[:limit]

        total = len(sites)
        self.stdout.write(f"Sites to enrich: {total} (offset={offset}, limit={limit or 'none'})")

        ok = skip = fail = 0
        for i, (sid, name, site_type, bortle, state, country, notes) in enumerate(sites, 1):
            try:
                country_name = COUNTRY_NAMES.get(country or "", country or "")
                location_parts = [p for p in [state, country_name] if p]
                location = ", ".join(location_parts) or "Unknown"
                type_label = TYPE_LABELS.get(site_type, site_type)
                bortle_int = int(bortle) if bortle else 0
                bortle_desc = BORTLE_DESC.get(bortle_int, "unknown darkness")

                background = _wikipedia(name, state)
                time.sleep(0.5)  # be polite to Wikipedia

                prompt = PROMPT_TMPL.format(
                    name=name,
                    type_label=type_label,
                    location=location,
                    bortle=bortle or "unknown",
                    bortle_desc=bortle_desc,
                    notes=notes or "None",
                    background=background or "Not found on Wikipedia.",
                )

                new_note = _ollama(prompt, model, ollama_url)
                if not new_note:
                    skip += 1
                    self.stdout.write(f"[{i}/{total}] {name[:45]:<45} → (empty response, skipped)")
                    continue

                from accounts.models import Site
                Site.objects.filter(id=sid).update(notes=new_note)

                ok += 1
                self.stdout.write(f"[{i}/{total}] {name[:45]:<45} → {new_note[:80]}")

            except Exception as e:
                fail += 1
                self.stdout.write(
                    self.style.WARNING(f"[{i}/{total}] {name[:45]:<45} → ERROR: {e}")
                )

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Enriched: {ok}  Skipped: {skip}  Failed: {fail}"
        ))
