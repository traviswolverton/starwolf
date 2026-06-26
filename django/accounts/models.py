from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"
    ROLES = [(GUEST, "Guest"), (USER, "User"), (ADMIN, "Admin")]

    role = models.CharField(max_length=16, choices=ROLES, default=USER)

    def is_admin(self):
        return self.role == self.ADMIN

    def has_min_role(self, min_role: str) -> bool:
        order = [self.GUEST, self.USER, self.ADMIN]
        return order.index(self.role) >= order.index(min_role)

    class Meta:
        db_table = "starwolf_user"


class UserPreferences(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preferences")

    # Location
    location_lat = models.FloatField(null=True, blank=True)
    location_lon = models.FloatField(null=True, blank=True)
    location_display = models.CharField(max_length=200, blank=True)
    location_text = models.CharField(max_length=200, blank=True)

    # Timezone
    timezone = models.CharField(max_length=50, default="America/Chicago")
    timezone_auto = models.BooleanField(default=False)

    # Units
    units = models.CharField(
        max_length=10, default="metric",
        choices=[("metric", "Metric (km, m)"), ("imperial", "Imperial (mi, ft)")],
    )

    # Planner filters
    min_score_threshold = models.IntegerField(default=40)
    disq_max_cloud_cover = models.IntegerField(default=85)
    disq_max_precip_prob = models.IntegerField(default=40)
    disq_min_visibility_km = models.IntegerField(default=10)

    class Meta:
        db_table = "starwolf_user_preferences"

    @property
    def has_location(self):
        return self.location_lat is not None and self.location_lon is not None
