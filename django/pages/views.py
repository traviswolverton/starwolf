import re
from pathlib import Path

import markdown as md
from django.conf import settings
from django.shortcuts import render


def about(request):
    return render(request, "pages/about.html")


def api_guide(request):
    guide_path = Path(settings.BASE_DIR).parent / "API_GUIDE.md"
    raw = guide_path.read_text()

    parts = re.split(r"\n(?=### )", raw)

    overview_parts, endpoints = [], []
    for part in parts:
        m = re.match(r"### (.+?)\n", part)
        if m and "/" in m.group(1):
            label = m.group(1).replace("`", "")
            # Short label for the tab button: just METHOD /path
            short = re.search(r"(GET|POST|PUT|DELETE|PATCH)\s+(/\S+)", label)
            endpoints.append({
                "label": label,
                "tab": short.group(0) if short else label,
                "html": md.markdown(part, extensions=["tables", "fenced_code"]),
            })
        else:
            overview_parts.append(part)

    return render(request, "pages/api_guide.html", {
        "overview_html": md.markdown(
            "\n".join(overview_parts), extensions=["tables", "fenced_code"]
        ),
        "endpoints": endpoints,
    })
