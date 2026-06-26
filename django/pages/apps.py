from django.apps import AppConfig


class PagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pages"

    def ready(self):
        # Clear any planner runs that were in-flight when the container last died.
        # Without this, users get a spinner that never resolves after a restart.
        try:
            from django.core.cache import cache
            cache.delete_pattern("*planner:status:*")
        except Exception:
            pass
