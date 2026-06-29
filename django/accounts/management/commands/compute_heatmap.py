"""
Management command: compute_heatmap
Scores all active sites for tonight and upserts into site_daily_scores.
Designed to be run from cron at noon local time (17:00 UTC for CDT).

Usage:
  python manage.py compute_heatmap               # score all sites for today
  python manage.py compute_heatmap --only-missing # fill gaps only (skip already-scored)
  python manage.py compute_heatmap --force        # recompute even if already done today
"""
from django.core.management.base import BaseCommand
from django.db import connection

from django.core.cache import cache
from pages.views import _run_compute, _today_local, _COMPUTE_STATE_KEY


class Command(BaseCommand):
    help = "Compute tonight's forecast heatmap for all active sites"

    def add_arguments(self, parser):
        parser.add_argument("--only-missing", action="store_true",
                            help="Only score sites missing a score for today")
        parser.add_argument("--force", action="store_true",
                            help="Recompute all sites even if already scored today")

    def handle(self, *args, **options):
        # Check if already running
        state = cache.get(_COMPUTE_STATE_KEY)
        if state and state.get("running"):
            self.stderr.write(self.style.WARNING("Heatmap compute already running — skipping."))
            return

        today = _today_local()

        # Check if already done today (unless --force)
        if not options["force"] and not options["only_missing"]:
            with connection.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM site_daily_scores WHERE score_date = %s AND score IS NOT NULL",
                    [today]
                )
                already = cur.fetchone()[0]
            if already > 0:
                self.stdout.write(
                    f"Already have {already} scores for {today}. Use --force to recompute."
                )
                return

        from accounts.models import AppSetting
        tz = AppSetting.get("timezone", "America/Chicago")

        self.stdout.write(f"Computing heatmap for {today} (tz={tz})…")
        _run_compute(today, tz, only_missing=options["only_missing"])

        state = cache.get(_COMPUTE_STATE_KEY) or {}
        self.stdout.write(self.style.SUCCESS(
            f"Done. Scored {state.get('done', '?')} sites for {today}."
        ))
