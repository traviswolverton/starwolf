def prefs(request):
    """Expose request.prefs (set by middleware) to templates as `prefs`."""
    return {"prefs": getattr(request, "prefs", None)}
