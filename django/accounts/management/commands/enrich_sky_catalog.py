"""
Management command: enrich_sky_catalog
Populates sky_object_details with Wikipedia summary, Wikimedia CC image,
and structured facts (constellation, distance, angular size, discoverer).

Usage:
  python manage.py enrich_sky_catalog                  # skip already-enriched
  python manage.py enrich_sky_catalog --force          # redo all
  python manage.py enrich_sky_catalog --limit 10       # stop after N objects
  python manage.py enrich_sky_catalog --category dso   # only one category
  python manage.py enrich_sky_catalog --name M31       # single object
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

_HEADERS = {
    "User-Agent": (
        "StarWolf/1.0 (https://starwolf.wolvertons.net; traviswolverton@gmail.com)"
        " python-urllib/3.12"
    )
}

# Wikipedia search terms that work better than the raw catalog name
_WIKI_OVERRIDES = {
    "M1":  "Crab Nebula",
    "M2":  "Messier 2",
    "M3":  "Messier 3",
    "M4":  "Messier 4",
    "M5":  "Messier 5",
    "M9":  "Messier 9",
    "M10": "Messier 10",
    "M12": "Messier 12",
    "M14": "Messier 14",
    "M18": "Messier 18",
    "M19": "Messier 19",
    "M21": "Messier 21",
    "M23": "Messier 23",
    "M24": "Sagittarius Star Cloud",
    "M25": "Messier 25",
    "M26": "Messier 26",
    "M28": "Messier 28",
    "M29": "Messier 29",
    "M30": "Messier 30",
    "M34": "Messier 34",
    "M35": "Messier 35",
    "M39": "Messier 39",
    "M40": "Winnecke 4",
    "M46": "Messier 46",
    "M47": "Messier 47",
    "M48": "Messier 48",
    "M49": "Messier 49",
    "M53": "Messier 53",
    "M54": "Messier 54",
    "M55": "Messier 55",
    "M56": "Messier 56",
    "M58": "Messier 58",
    "M59": "Messier 59",
    "M60": "Messier 60",
    "M61": "Messier 61",
    "M62": "Messier 62",
    "M68": "Messier 68",
    "M69": "Messier 69",
    "M70": "Messier 70",
    "M72": "Messier 72",
    "M73": "Messier 73",
    "M75": "Messier 75",
    "M78": "Messier 78",
    "M79": "Messier 79",
    "M80": "Messier 80",
    "M84": "Messier 84",
    "M85": "Messier 85",
    "M86": "Messier 86",
    "M88": "Messier 88",
    "M89": "Messier 89",
    "M90": "Messier 90",
    "M91": "Messier 91",
    "M92": "Messier 92",
    "M93": "Messier 93",
    "M95": "Messier 95",
    "M96": "Messier 96",
    "M98": "Messier 98",
    "M99": "Messier 99",
    "M100": "Messier 100",
    "M102": "Messier 102",
    "M103": "Messier 103",
    "M105": "Messier 105",
    "M106": "Messier 106",
    "M107": "Messier 107",
    "M108": "Messier 108",
    "M109": "Messier 109",
    "M110": "Messier 110",
    "M8":  "Lagoon Nebula",
    "M13": "Hercules Cluster",
    "M16": "Eagle Nebula",
    "M17": "Omega Nebula",
    "M20": "Trifid Nebula",
    "M22": "Messier 22",
    "M27": "Dumbbell Nebula",
    "M31": "Andromeda Galaxy",
    "M32": "Messier 32",
    "M33": "Triangulum Galaxy",
    "M42": "Orion Nebula",
    "M44": "Beehive Cluster",
    "M45": "Pleiades",
    "M51": "Whirlpool Galaxy",
    "M57": "Ring Nebula",
    "M63": "Sunflower Galaxy",
    "M64": "Black Eye Galaxy",
    "M74": "Phantom Galaxy",
    "M76": "Little Dumbbell Nebula",
    "M77": "Messier 77",
    "M81": "Bode's Galaxy",
    "M82": "Cigar Galaxy",
    "M83": "Southern Pinwheel Galaxy",
    "M87": "Messier 87",
    "M97": "Owl Nebula",
    "M101": "Pinwheel Galaxy",
    "M104": "Sombrero Galaxy",
    # Meteor showers
    "Perseids":       "Perseid meteor shower",
    "Geminids":       "Geminid meteor shower",
    "Leonids":        "Leonid meteor shower",
    "Orionids":       "Orionid meteor shower",
    "Eta Aquariids":  "Eta Aquariid meteor shower",
    "Delta Aquariids": "Delta Aquariid meteor shower",
    "Quadrantids":    "Quadrantid meteor shower",
    "Lyrids":         "Lyrid meteor shower",
    "Taurids":        "Taurid meteor shower",
    "Ursids":         "Ursid meteor shower",
    # Constellations and asterisms
    "Orion":           "Orion (constellation)",
    "Ursa Major":      "Ursa Major",
    "Ursa Minor":      "Ursa Minor",
    "Cassiopeia":      "Cassiopeia (constellation)",
    "Leo":             "Leo (constellation)",
    "Scorpius":        "Scorpius (constellation)",
    "Sagittarius":     "Sagittarius (constellation)",
    "Gemini":          "Gemini (constellation)",
    "Taurus":          "Taurus (constellation)",
    "Boötes":          "Boötes",
    "Cygnus":          "Cygnus (constellation)",
    "Lyra":            "Lyra (constellation)",
    "Aquila":          "Aquila (constellation)",
    "Perseus":         "Perseus (constellation)",
    "Virgo":           "Virgo (constellation)",
    "Hercules":        "Hercules (constellation)",
    "Andromeda":       "Andromeda (constellation)",
    "Corona Borealis": "Corona Borealis",
    "Canis Major":     "Canis Major",
    "Big Dipper":      "Big Dipper",
    "Little Dipper":   "Little Dipper",
    "Orion's Belt":    "Orion's Belt",
    "Summer Triangle": "Summer Triangle",
    "Winter Hexagon":  "Winter Hexagon",
    # Stars that need disambiguation
    "Regulus":   "Regulus (star)",
    "Castor":    "Castor (star)",
    "Bellatrix": "Bellatrix (star)",
    "Adhara":    "Adhara",
    "Shaula":    "Shaula",
    # Planets and stars use their common name directly
    "Mercury": "Mercury (planet)",
    "Venus":   "Venus",
    "Mars":    "Mars",
    "Jupiter": "Jupiter",
    "Saturn":  "Saturn",
    "Uranus":  "Uranus",
    "Neptune": "Neptune",
}

# Known facts we embed rather than parse from Wikipedia
# (distance_ly, angular_size_arcmin, constellation, discovery_year, discoverer)
_KNOWN_FACTS = {
    "M1":  (6500,    7.0,   "Taurus",       1054, "Chinese astronomers"),
    "M2":  (37500,   12.9,  "Aquarius",     1746, "Jean-Dominique Maraldi"),
    "M3":  (33900,   18.0,  "Canes Venatici", 1764, "Charles Messier"),
    "M4":  (7200,    26.3,  "Scorpius",     1746, "Philippe Loys de Chéseaux"),
    "M5":  (24500,   17.4,  "Serpens",      1702, "Gottfried Kirch"),
    "M6":  (1600,    25.0,  "Scorpius",     1654, "Giovanni Battista Hodierna"),
    "M7":  (980,     80.0,  "Scorpius",     130,  "Claudius Ptolemy"),
    "M8":  (4070,   90.0,  "Sagittarius",  1747, "Guillaume Le Gentil"),
    "M11": (6120,    14.0,  "Scutum",       1681, "Gottfried Kirch"),
    "M13": (22200,   20.0,  "Hercules",     1714, "Edmond Halley"),
    "M15": (33600,   12.3,  "Pegasus",      1746, "Jean-Dominique Maraldi"),
    "M16": (7000,    7.0,   "Serpens",      1745, "Philippe Loys de Chéseaux"),
    "M17": (5500,    11.0,  "Sagittarius",  1745, "Philippe Loys de Chéseaux"),
    "M20": (4100,   28.0,  "Sagittarius",  1764, "Charles Messier"),
    "M22": (10400,  24.0,  "Sagittarius",  1665, "Abraham Ihle"),
    "M27": (1360,    8.0,   "Vulpecula",    1764, "Charles Messier"),
    "M31": (2537000, 190.0, "Andromeda",    964,  "Abd al-Rahman al-Sufi"),
    "M33": (2730000, 73.0,  "Triangulum",   1654, "Giovanni Battista Hodierna"),
    "M42": (1344,   65.0,  "Orion",        1610, "Nicolas-Claude Fabri de Peiresc"),
    "M44": (577,   95.0,  "Cancer",       250,  "Hipparchus"),
    "M45": (444,   110.0, "Taurus",       -1000, "Prehistoric"),
    "M51": (23000000, 11.2, "Canes Venatici", 1773, "Charles Messier"),
    "M57": (2300,    1.4,   "Lyra",         1779, "Antoine Darquier de Pellepoix"),
    "M63": (29000000, 12.6, "Canes Venatici", 1779, "Pierre Méchain"),
    "M64": (17000000, 9.3,  "Coma Berenices", 1779, "Edward Pigott"),
    "M74": (35000000, 10.5, "Pisces",       1780, "Pierre Méchain"),
    "M81": (11740000, 26.9, "Ursa Major",   1774, "Johann Elert Bode"),
    "M82": (11400000, 11.2, "Ursa Major",   1774, "Johann Elert Bode"),
    "M83": (15000000, 12.9, "Hydra",        1752, "Nicolas Louis de Lacaille"),
    "M87": (53490000, 7.2,  "Virgo",        1781, "Charles Messier"),
    "M97": (2030,    3.4,   "Ursa Major",   1781, "Pierre Méchain"),
    "M101": (20900000, 28.8, "Ursa Major",  1781, "Pierre Méchain"),
    "M104": (29350000, 8.7, "Virgo",        1781, "Pierre Méchain"),
    # Planets — distance is average AU converted to ly would be silly; use None
    "Mercury": (None, None, None, None, None),
    "Venus":   (None, None, None, None, None),
    "Mars":    (None, None, None, None, None),
    "Jupiter": (None, None, None, None, None),
    "Saturn":  (None, None, None, None, None),
    "Uranus":  (None, None, None, None, None),
    "Neptune": (None, None, None, None, None),
}


def _get(url):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _wiki_summary(search_term):
    """Return (extract, page_url, thumbnail_url, thumbnail_credit) via Wikipedia REST API."""
    slug = urllib.parse.quote(search_term.replace(" ", "_"))
    try:
        page = _get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}")
    except urllib.error.HTTPError:
        # Try search fallback
        try:
            data = _get(
                "https://en.wikipedia.org/w/api.php?action=query&list=search"
                f"&srsearch={urllib.parse.quote(search_term)}&format=json&srlimit=1"
            )
            results = data.get("query", {}).get("search", [])
            if not results:
                return "", "", "", ""
            slug = urllib.parse.quote(results[0]["title"].replace(" ", "_"))
            page = _get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}")
        except Exception:
            return "", "", "", ""

    extract = page.get("extract", "").replace("\n", " ").strip()
    # Trim to ~3 sentences
    sentences = re.split(r'(?<=[.!?])\s+', extract)
    summary = " ".join(sentences[:4]).strip()
    if len(summary) > 900:
        summary = summary[:900].rsplit(" ", 1)[0] + "…"

    page_url = page.get("content_urls", {}).get("desktop", {}).get("page", "")
    thumb = page.get("thumbnail", {})
    thumb_url = thumb.get("source", "")
    title = page.get("title", search_term)
    credit = f"Image: Wikipedia / Wikimedia Commons — {title} (CC BY-SA)" if thumb_url else ""

    # Fallback: search Wikimedia Commons directly if Wikipedia had no lead image
    if not thumb_url:
        thumb_url, credit = _commons_image(search_term, title)

    return summary, page_url, thumb_url, credit


def _commons_image(search_term, page_title):
    """Search Wikimedia Commons for a CC image when Wikipedia has no thumbnail."""
    try:
        data = _get(
            "https://commons.wikimedia.org/w/api.php?action=query&list=search"
            f"&srsearch={urllib.parse.quote(search_term)}&srnamespace=6"
            "&format=json&srlimit=3"
        )
        results = data.get("query", {}).get("search", [])
        for result in results:
            file_title = result["title"]  # e.g. "File:M92 globular cluster.jpg"
            # Get the image URL via imageinfo
            info = _get(
                "https://commons.wikimedia.org/w/api.php?action=query"
                f"&titles={urllib.parse.quote(file_title)}"
                "&prop=imageinfo&iiprop=url|mime&iiurlwidth=600&format=json"
            )
            pages = info.get("query", {}).get("pages", {})
            for p in pages.values():
                ii = p.get("imageinfo", [{}])[0]
                mime = ii.get("mime", "")
                if not mime.startswith("image/"):
                    continue
                url = ii.get("thumburl") or ii.get("url", "")
                if url:
                    credit = f"Image: Wikimedia Commons — {file_title[5:]} (CC BY-SA)"
                    return url, credit
    except Exception:
        pass
    return "", ""


class Command(BaseCommand):
    help = "Enrich sky catalog objects with Wikipedia data and structured facts"

    def add_arguments(self, parser):
        parser.add_argument("--force",    action="store_true", help="Re-enrich already-enriched objects")
        parser.add_argument("--limit",    type=int, default=0)
        parser.add_argument("--category", default="", help="Filter by category (dso, star, planet, ...)")
        parser.add_argument("--name",     default="", help="Single object by name (e.g. M31)")

    def handle(self, *args, **options):
        from accounts.models import SkyObject, SkyObjectDetail

        force    = options["force"]
        limit    = options["limit"]
        category = options["category"]
        name     = options["name"]

        qs = SkyObject.objects.filter(active=True)
        if name:
            qs = qs.filter(name=name)
        elif category:
            qs = qs.filter(category=category)

        if not force and not name:
            qs = qs.filter(detail__isnull=True)

        objects = list(qs.order_by("category", "sort_order", "name"))
        if limit:
            objects = objects[:limit]

        total = len(objects)
        self.stdout.write(f"Objects to enrich: {total}")

        ok = skip = fail = 0
        for i, obj in enumerate(objects, 1):
            label = obj.name + (f" ({obj.common_name})" if obj.common_name else "")
            try:
                # Determine Wikipedia search term
                search_term = _WIKI_OVERRIDES.get(obj.name) or obj.common_name or obj.name

                summary, page_url, thumb_url, credit = _wiki_summary(search_term)
                time.sleep(0.5)  # be polite to Wikipedia

                # Structured facts — use known table first, then leave None
                facts = _KNOWN_FACTS.get(obj.name, (None, None, None, None, None))
                dist_ly, ang_size, constellation, disc_year, discoverer = facts

                now = datetime.now(timezone.utc)
                SkyObjectDetail.objects.update_or_create(
                    sky_object=obj,
                    defaults={
                        "wikipedia_url":       page_url or None,
                        "wikipedia_summary":   summary or None,
                        "image_url":           thumb_url or None,
                        "image_credit":        credit or None,
                        "constellation":       constellation or "",
                        "distance_ly":         dist_ly,
                        "angular_size_arcmin": ang_size,
                        "discovery_year":      disc_year if disc_year and disc_year > 0 else None,
                        "discoverer":          discoverer or "",
                        "enriched_at":         now,
                    },
                )

                ok += 1
                wi = "✓wiki" if summary  else "✗wiki"
                ii = "✓img"  if thumb_url else "✗img"
                self.stdout.write(f"[{i}/{total}] {label[:50]:<50} {wi} {ii}")

            except Exception as e:
                fail += 1
                self.stdout.write(self.style.WARNING(f"[{i}/{total}] {label[:50]:<50} ERROR: {e}"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. OK={ok}  Failed={fail}"))
