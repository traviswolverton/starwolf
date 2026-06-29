from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AppSetting, BortleModifier, NakedEyeWeight, Site, SiteDetail, SiteDailyScore, ScoringWeight, SkyObject, User, UserPreferences


@admin.register(ScoringWeight)
class ScoringWeightAdmin(ModelAdmin):
    list_display  = ("factor", "weight", "description")
    list_editable = ("weight",)


@admin.register(NakedEyeWeight)
class NakedEyeWeightAdmin(ModelAdmin):
    list_display  = ("factor", "weight", "description")
    list_editable = ("weight",)


@admin.register(BortleModifier)
class BortleModifierAdmin(ModelAdmin):
    list_display  = ("bortle_class", "composite_modifier", "naked_eye_modifier", "description")
    list_editable = ("composite_modifier", "naked_eye_modifier")
    ordering      = ("bortle_class",)


@admin.register(AppSetting)
class AppSettingAdmin(ModelAdmin):
    list_display  = ("key", "value", "description")
    search_fields = ("key", "description")


class SiteDetailInline(admin.StackedInline):
    model  = SiteDetail
    extra  = 0
    fields = ("wikipedia_url", "wikipedia_summary", "image_url", "image_credit", "narrative", "maps_url", "enriched_at")
    readonly_fields = ("enriched_at",)


@admin.register(Site)
class SiteAdmin(ModelAdmin):
    list_display   = ("name", "country", "state_province", "bortle_class", "site_type", "active")
    list_editable  = ("bortle_class", "active")
    list_filter    = ("active", "site_type", "country", "bortle_class")
    search_fields  = ("name", "country", "state_province", "notes")
    ordering       = ("name",)
    inlines        = [SiteDetailInline]


@admin.register(SiteDailyScore)
class SiteDailyScoreAdmin(ModelAdmin):
    list_display   = ("name", "score_date", "score", "computed_at")
    list_filter    = ("score_date",)
    search_fields  = ("name",)
    readonly_fields = ("computed_at",)


@admin.register(SiteDetail)
class SiteDetailAdmin(ModelAdmin):
    list_display   = ("site", "enriched_at")
    search_fields  = ("site__name",)
    readonly_fields = ("enriched_at",)


@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display  = ("username", "email", "role", "is_active", "date_joined")
    list_filter   = ("role", "is_active")
    search_fields = ("username", "email")


@admin.register(UserPreferences)
class UserPreferencesAdmin(ModelAdmin):
    list_display  = ("user", "location_display", "timezone", "equipment")
    search_fields = ("user__username", "location_display")


@admin.register(SkyObject)
class SkyObjectAdmin(ModelAdmin):
    list_display  = ("name", "common_name", "category", "obj_type", "magnitude", "source", "active", "sort_order")
    list_editable = ("active", "sort_order")
    list_filter   = ("category", "active", "source")
    search_fields = ("name", "common_name", "notes")
    ordering      = ("category", "sort_order", "name")
