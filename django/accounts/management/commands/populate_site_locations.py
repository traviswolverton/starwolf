import time

import requests
from django.core.management.base import BaseCommand

NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
HEADERS = {"User-Agent": "StarWolf-App/1.0 (stargazing site geocoder)"}


def _reverse(lat, lon):
    r = requests.get(
        NOMINATIM,
        params={"lat": lat, "lon": lon, "format": "json", "zoom": 5},
        headers=HEADERS,
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    addr = data.get("address", {})
    country = addr.get("country_code", "").upper() or None
    state = (
        addr.get("state")
        or addr.get("province")
        or addr.get("region")
        or addr.get("territory")
        or None
    )
    return country, state


class Command(BaseCommand):
    help = "Reverse-geocode lat/lon for each site to populate country and state_province"

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true",
                            help="Re-geocode even sites that already have country set")
        parser.add_argument("--limit", type=int, default=0,
                            help="Stop after N sites (0 = no limit)")

    def handle(self, *args, **options):
        redo = options["all"]
        limit = options["limit"]

        from accounts.models import Site
        qs = Site.objects.order_by("id")
        if not redo:
            qs = qs.filter(country__isnull=True)
        sites = list(qs.values_list("id", "name", "lat", "lon"))

        total = len(sites)
        if limit:
            sites = sites[:limit]

        self.stdout.write(f"Sites to geocode: {len(sites)} (of {total} pending)")

        ok = skip = fail = 0
        for i, (site_id, name, lat, lon) in enumerate(sites, 1):
            try:
                country, state = _reverse(lat, lon)
                Site.objects.filter(id=site_id).update(country=country, state_province=state)
                ok += 1
                self.stdout.write(
                    f"[{i}/{len(sites)}] {name[:40]:<40} → {country or '?'}, {state or '?'}"
                )
            except Exception as e:
                fail += 1
                self.stdout.write(self.style.WARNING(
                    f"[{i}/{len(sites)}] {name[:40]:<40} → ERROR: {e}"
                ))
            time.sleep(1.1)  # Nominatim ToS: max 1 req/sec

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. OK: {ok}  Skipped: {skip}  Failed: {fail}"
        ))
