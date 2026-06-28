from django.contrib import admin

from .models import SkyObject, User, UserPreferences


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "role", "is_active", "date_joined")
    list_filter  = ("role", "is_active")
    search_fields = ("username", "email")


@admin.register(UserPreferences)
class UserPreferencesAdmin(admin.ModelAdmin):
    list_display = ("user", "location_display", "timezone", "equipment")
    search_fields = ("user__username", "location_display")


@admin.register(SkyObject)
class SkyObjectAdmin(admin.ModelAdmin):
    list_display  = ("name", "common_name", "category", "obj_type", "magnitude", "source", "active", "sort_order")
    list_editable = ("active", "sort_order")
    list_filter   = ("category", "active", "source")
    search_fields = ("name", "common_name", "notes")
    ordering      = ("category", "sort_order", "name")
