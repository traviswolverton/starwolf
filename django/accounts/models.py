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


class AppSetting(models.Model):
    key         = models.CharField(max_length=100, primary_key=True)
    value       = models.TextField()
    description = models.TextField(blank=True)

    class Meta:
        db_table = "app_settings"
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} = {self.value}"

    @classmethod
    def get(cls, key, default=None):
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def all_as_dict(cls):
        return {s.key: s.value for s in cls.objects.all()}


class Site(models.Model):
    SITE_TYPES = [
        ("public_land",    "Public Land"),
        ("state_park",     "State Park"),
        ("national_park",  "National Park"),
        ("ida_certified",  "IDA Certified"),
        ("private",        "Private"),
        ("other",          "Other"),
    ]

    name           = models.CharField(max_length=255)
    lat            = models.FloatField()
    lon            = models.FloatField()
    bortle_class   = models.IntegerField(null=True, blank=True)
    elevation_m    = models.FloatField(null=True, blank=True)
    notes          = models.TextField(blank=True)
    active         = models.IntegerField(default=1)  # 0/1 — keep as int to match existing schema
    site_type      = models.CharField(max_length=50, blank=True, choices=SITE_TYPES, null=True)
    country        = models.CharField(max_length=100, blank=True, null=True)
    state_province = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "sites"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SiteDetail(models.Model):
    site              = models.OneToOneField(Site, on_delete=models.CASCADE, primary_key=True, related_name="detail")
    wikipedia_url     = models.TextField(blank=True, null=True)
    wikipedia_summary = models.TextField(blank=True, null=True)
    image_url         = models.TextField(blank=True, null=True)
    image_credit      = models.TextField(blank=True, null=True)
    narrative         = models.TextField(blank=True, null=True)
    maps_url          = models.TextField(blank=True, null=True)
    enriched_at       = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "site_details"

    def __str__(self):
        return f"Details for {self.site_id}"


class SiteDailyScore(models.Model):
    site        = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="daily_scores")
    score_date  = models.DateField()
    name        = models.TextField()
    lat         = models.FloatField()
    lon         = models.FloatField()
    score       = models.FloatField(null=True, blank=True)
    computed_at = models.DateTimeField()

    class Meta:
        db_table = "site_daily_scores"
        unique_together = [("site", "score_date")]
        ordering = ["-score_date", "-score"]

    def __str__(self):
        return f"{self.name} {self.score_date} ({self.score})"


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
