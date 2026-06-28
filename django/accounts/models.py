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

    # Planner scoring preference
    best_metric = models.CharField(
        max_length=16, default="combined",
        choices=[("telescope", "Telescope"), ("naked_eye", "Naked Eye"), ("combined", "Combined")],
    )

    # Equipment preference (for What's Up / Tonight's Sky)
    equipment = models.CharField(
        max_length=16, null=True, blank=True,
        choices=[
            ("naked_eye",   "Naked Eye"),
            ("binoculars",  "Binoculars (7×50)"),
            ("small_scope", "Small Telescope (4–6\")"),
            ("large_scope", "Large Telescope (10\"+)"),
        ],
    )

    class Meta:
        db_table = "starwolf_user_preferences"

    @property
    def has_location(self):
        return self.location_lat is not None and self.location_lon is not None


class SkyObject(models.Model):
    CATEGORY_PLANET   = "planet"
    CATEGORY_STAR     = "star"
    CATEGORY_DSO      = "dso"
    CATEGORY_SHOWER   = "meteor_shower"
    CATEGORY_SATELLITE = "satellite"
    CATEGORIES = [
        (CATEGORY_PLANET,    "Planet"),
        (CATEGORY_STAR,      "Star"),
        (CATEGORY_DSO,       "Deep Sky Object"),
        (CATEGORY_SHOWER,    "Meteor Shower"),
        (CATEGORY_SATELLITE, "Satellite"),
    ]

    name        = models.CharField(max_length=100)
    common_name = models.CharField(max_length=100, blank=True)
    category    = models.CharField(max_length=20, choices=CATEGORIES, db_index=True)
    obj_type    = models.CharField(max_length=50, blank=True)  # galaxy, nebula, planet, star…
    magnitude   = models.FloatField(null=True, blank=True)     # null → computed at runtime
    ra_h        = models.FloatField(null=True, blank=True)     # null → computed (planets, ISS, showers)
    dec_d       = models.FloatField(null=True, blank=True)
    source      = models.CharField(max_length=50, blank=True)  # messier_csv, yale_bsc, de421…
    active      = models.BooleanField(default=True, db_index=True)
    sort_order  = models.IntegerField(default=0)
    notes       = models.TextField(blank=True)
    extra_data  = models.JSONField(default=dict, blank=True)   # category-specific fields

    class Meta:
        db_table = "sky_catalog"
        ordering = ["category", "sort_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.category})"
