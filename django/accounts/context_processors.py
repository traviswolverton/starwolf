from accounts.models import UserPreferences


def prefs(request):
    """Make request.prefs and template var `prefs` available on every request."""
    if not request.user.is_authenticated:
        request.prefs = None
        return {"prefs": None}
    prefs_obj, _ = UserPreferences.objects.get_or_create(user=request.user)
    request.prefs = prefs_obj
    return {"prefs": prefs_obj}
