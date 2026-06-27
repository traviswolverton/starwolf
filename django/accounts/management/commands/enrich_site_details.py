"""
Management command: enrich_site_details
Populates the site_details table with Wikipedia summary, Wikimedia image,
elevation (already on sites table), Ollama narrative, and a Google Maps URL.

Usage:
  python manage.py enrich_site_details                     # skip already-enriched sites
  python manage.py enrich_site_details --force             # redo all
  python manage.py enrich_site_details --limit 20          # stop after N sites
  python manage.py enrich_site_details --site-id 42        # single site
  python manage.py enrich_site_details --near-houston      # 20 closest to Houston (test mode)
  python manage.py enrich_site_details --no-ollama         # skip narrative generation
  python manage.py enrich_site_details --model phi4        # different Ollama model
  python manage.py enrich_site_details --ollama http://host.docker.internal:11434
"""
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from django.db import connection

OLLAMA_DEFAULT = "http://host.docker.internal:11434"
MODEL_DEFAULT  = "llama3.1:8b"

NARRATIVE_PROMPT = """\
Write a 3–5 sentence description of this stargazing site for an amateur astronomer planning a visit.
Be evocative but factual. Mention the landscape/terrain, what makes the darkness special, \
what type of observer it suits best (visual, astrophotography, naked-eye), and any notable \
access or practical considerations. Do NOT mention the Bortle number directly — translate it \
into plain language (e.g. "Milky Way core is easily visible" for Bortle 3-4). \
Reply with only the description, no headings or bullet points.

Site: {name}
Type: {site_type}
Location: {location}
Bortle class: {bortle}
Elevation: {elevation}
Wikipedia background: {background}
"""

BORTLE_PLAIN = {
    1: "pristine skies with the faintest stars and nebulae visible to the naked eye",
    2: "truly dark with the Milky Way casting shadows on a good night",
    3: "dark rural skies where the Milky Way core is prominent and detailed",
    4: "good rural skies with a bright Milky Way clearly visible",
    5: "semi-rural skies with some light dome on the horizon",
    6: "suburban skies with a washed-out Milky Way",
    7: "suburban/urban fringe with limited naked-eye objects",
    8: "bright city-adjacent skies",
    9: "inner-city skies with very limited observing",
}

TYPE_LABELS = {
    "ida_certified":   "IDA Certified Dark Sky Place",
    "national_park":   "National Park",
    "national_forest": "National Forest",
    "state_park":      "State / Provincial Park",
    "community":       "Community Dark Sky Site",
    "observatory":     "Public Observatory",
}


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


_WIKI_HEADERS = {
    "User-Agent": "StarWolf/1.0 (https://starwolf.wolvertons.net; traviswolverton@gmail.com) python-urllib/3.12"
}


def _wiki_get(url):
    req = urllib.request.Request(url, headers=_WIKI_HEADERS)
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


def _wikipedia(name, state):
    """Return (summary, page_url) or ('', '')."""
    query = f"{name} {state or ''}".strip()
    search_url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={urllib.parse.quote(query)}&format=json&srlimit=1&utf8=1"
    )
    try:
        data = _wiki_get(search_url)
        results = data.get("query", {}).get("search", [])
        if not results:
            return "", ""
        title = results[0]["title"]
        slug = urllib.parse.quote(title.replace(" ", "_"))
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
        page = _wiki_get(summary_url)
        extract = page.get("extract", "")
        sentences = extract.replace("\n", " ").split(". ")
        summary = ". ".join(sentences[:3]).strip()
        if summary and not summary.endswith("."):
            summary += "."
        page_url = page.get("content_urls", {}).get("desktop", {}).get("page", "")
        return summary[:800], page_url
    except Exception:
        return "", ""


def _wikimedia_image(name, state):
    """Return (image_url, credit) via Wikipedia pageimages API, or ('', '')."""
    query = f"{name} {state or ''}".strip()
    search_url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=search"
        f"&srsearch={urllib.parse.quote(query)}&format=json&srlimit=1&utf8=1"
    )
    try:
        data = _wiki_get(search_url)
        results = data.get("query", {}).get("search", [])
        if not results:
            return "", ""
        title = results[0]["title"]
        img_url = (
            "https://en.wikipedia.org/w/api.php?action=query&titles="
            f"{urllib.parse.quote(title)}&prop=pageimages"
            "&pithumbsize=800&format=json"
        )
        img_data = _wiki_get(img_url)
        pages = img_data.get("query", {}).get("pages", {})
        for page in pages.values():
            src = page.get("thumbnail", {}).get("source", "")
            if src:
                credit = f"Via Wikipedia / Wikimedia Commons — {title} (CC BY-SA)"
                return src, credit
        return "", ""
    except Exception:
        return "", ""


def _ollama_narrative(site, model, base_url):
    bortle = site["bortle_class"]
    bortle_plain = BORTLE_PLAIN.get(int(bortle) if bortle else 0, "unknown darkness")
    elevation = f"{site['elevation_m']:.0f} m" if site["elevation_m"] else "unknown"
    location_parts = [p for p in [site["state_province"], site["country"]] if p]

    prompt = NARRATIVE_PROMPT.format(
        name=site["name"],
        site_type=TYPE_LABELS.get(site["site_type"], site["site_type"] or "Dark sky site"),
        location=", ".join(location_parts) or "Unknown",
        bortle=f"{bortle} — {bortle_plain}" if bortle else "unknown",
        elevation=elevation,
        background=site["_wiki_summary"] or "Not found on Wikipedia.",
    )

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 200},
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read())
    return data.get("response", "").strip().strip('"')


def _ensure_table():
    with connection.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS site_details (
                site_id         INTEGER PRIMARY KEY REFERENCES sites(id) ON DELETE CASCADE,
                wikipedia_url   TEXT,
                wikipedia_summary TEXT,
                image_url       TEXT,
                image_credit    TEXT,
                narrative       TEXT,
                maps_url        TEXT,
                enriched_at     TIMESTAMP WITH TIME ZONE
            )
        """)


class Command(BaseCommand):
    help = "Enrich sites with Wikipedia summary, image, and Ollama narrative"

    def add_arguments(self, parser):
        parser.add_argument("--force",       action="store_true", help="Re-enrich already-enriched sites")
        parser.add_argument("--limit",       type=int, default=0)
        parser.add_argument("--offset",      type=int, default=0)
        parser.add_argument("--site-id",     type=int, default=0, help="Enrich a single site by ID")
        parser.add_argument("--near-houston",action="store_true", help="Test mode: 20 closest sites to Houston")
        parser.add_argument("--no-ollama",   action="store_true", help="Skip Ollama narrative")
        parser.add_argument("--model",       default=MODEL_DEFAULT)
        parser.add_argument("--ollama",      default=OLLAMA_DEFAULT)

    def handle(self, *args, **options):
        _ensure_table()

        force        = options["force"]
        limit        = options["limit"]
        offset       = options["offset"]
        site_id      = options["site_id"]
        near_houston = options["near_houston"]
        no_ollama    = options["no_ollama"]
        model        = options["model"]
        ollama_url   = options["ollama"]

        # Check Ollama unless skipped
        if not no_ollama:
            try:
                with urllib.request.urlopen(f"{ollama_url}/api/tags", timeout=5):
                    pass
                self.stdout.write(f"Ollama OK at {ollama_url} using {model}")
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Cannot reach Ollama: {e}"))
                self.stderr.write("Run with --no-ollama to skip narrative generation.")
                return

        with connection.cursor() as cur:
            if site_id:
                cur.execute(
                    "SELECT id, name, site_type, bortle_class, elevation_m, lat, lon, state_province, country "
                    "FROM sites WHERE id=%s", [site_id]
                )
            elif near_houston:
                cur.execute(
                    "SELECT id, name, site_type, bortle_class, elevation_m, lat, lon, state_province, country "
                    "FROM sites ORDER BY ((lat-29.7604)*(lat-29.7604) + (lon+95.3698)*(lon+95.3698)) LIMIT 20"
                )
            elif force:
                cur.execute(
                    "SELECT id, name, site_type, bortle_class, elevation_m, lat, lon, state_province, country "
                    "FROM sites ORDER BY id"
                )
            else:
                cur.execute(
                    "SELECT s.id, s.name, s.site_type, s.bortle_class, s.elevation_m, s.lat, s.lon, s.state_province, s.country "
                    "FROM sites s "
                    "LEFT JOIN site_details sd ON sd.site_id = s.id "
                    "WHERE sd.site_id IS NULL ORDER BY s.id"
                )
            rows = cur.fetchall()

        cols = ["id", "name", "site_type", "bortle_class", "elevation_m", "lat", "lon", "state_province", "country"]
        sites = [dict(zip(cols, r)) for r in rows]

        if offset:
            sites = sites[offset:]
        if limit:
            sites = sites[:limit]

        total = len(sites)
        self.stdout.write(f"Sites to enrich: {total}")

        ok = skip = fail = 0
        for i, site in enumerate(sites, 1):
            name = site["name"]
            try:
                # Wikipedia summary + URL
                wiki_summary, wiki_url = _wikipedia(name, site["state_province"])
                time.sleep(0.4)

                # Wikimedia image
                image_url, image_credit = _wikimedia_image(name, site["state_province"])
                time.sleep(0.4)

                # Google Maps URL (no API key needed for a search link)
                maps_url = (
                    f"https://www.google.com/maps/search/?api=1&query="
                    f"{site['lat']},{site['lon']}"
                )

                # Ollama narrative
                narrative = None
                if not no_ollama:
                    site["_wiki_summary"] = wiki_summary
                    narrative = _ollama_narrative(site, model, ollama_url)

                now = datetime.now(timezone.utc)
                with connection.cursor() as cur:
                    cur.execute("""
                        INSERT INTO site_details
                            (site_id, wikipedia_url, wikipedia_summary, image_url, image_credit, narrative, maps_url, enriched_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (site_id) DO UPDATE SET
                            wikipedia_url     = EXCLUDED.wikipedia_url,
                            wikipedia_summary = EXCLUDED.wikipedia_summary,
                            image_url         = EXCLUDED.image_url,
                            image_credit      = EXCLUDED.image_credit,
                            narrative         = EXCLUDED.narrative,
                            maps_url          = EXCLUDED.maps_url,
                            enriched_at       = EXCLUDED.enriched_at
                    """, [
                        site["id"], wiki_url or None, wiki_summary or None,
                        image_url or None, image_credit or None,
                        narrative or None, maps_url, now,
                    ])

                ok += 1
                wiki_indicator  = "✓wiki" if wiki_summary else "✗wiki"
                image_indicator = "✓img"  if image_url    else "✗img"
                narr_indicator  = "✓narr" if narrative    else ("--" if no_ollama else "✗narr")
                self.stdout.write(
                    f"[{i}/{total}] {name[:45]:<45} {wiki_indicator} {image_indicator} {narr_indicator}"
                )

            except Exception as e:
                fail += 1
                self.stdout.write(self.style.WARNING(f"[{i}/{total}] {name[:45]:<45} ERROR: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. OK: {ok}  Failed: {fail}"))
