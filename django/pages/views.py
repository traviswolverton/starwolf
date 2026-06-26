import hashlib
import re
from pathlib import Path

import markdown as md
import requests as http
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

_FEEDBACK_LIMIT = 3
_FEEDBACK_TTL = 24 * 3600


def _ip_hash(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    if not ip or ip in ("127.0.0.1", "::1"):
        return None
    return hashlib.sha256((settings.IP_HASH_SALT + ip).encode()).hexdigest()


def about(request):
    return render(request, "pages/about.html")


@require_http_methods(["GET", "POST"])
def feedback(request):
    if request.method == "GET":
        return render(request, "pages/feedback.html")

    # ── POST: validate ────────────────────────────────────────────────────────
    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    submitter = request.POST.get("submitter", "").strip()
    feedback_type = request.POST.get("type", "feature")

    if not title or not description:
        return HttpResponse('<div class="alert error">Title and description are required.</div>')

    # ── Rate limit ────────────────────────────────────────────────────────────
    ip_hash = _ip_hash(request)
    if ip_hash and cache.get(f"feedback:{ip_hash}", 0) >= _FEEDBACK_LIMIT:
        return HttpResponse(
            f'<div class="alert warning">You\'ve submitted {_FEEDBACK_LIMIT} items in the '
            f'past 24 hours. Please check back tomorrow.</div>'
        )

    # ── GitHub API ────────────────────────────────────────────────────────────
    token = settings.GITHUB_TOKEN
    if not token:
        return HttpResponse('<div class="alert error">Feedback is not configured. Contact the site owner.</div>')

    prefix = "[Feature Request]" if feedback_type == "feature" else "[Bug Report]"
    body = (f"**Submitted by:** {submitter}\n\n" if submitter else "") + description

    try:
        resp = http.post(
            f"https://api.github.com/repos/{settings.GITHUB_REPO}/issues",
            json={"title": f"{prefix} {title}", "body": body},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10,
        )
    except http.exceptions.Timeout:
        return HttpResponse('<div class="alert error">Request timed out. Try again.</div>')
    except Exception as e:
        return HttpResponse(f'<div class="alert error">Submission failed: {e}</div>')

    if resp.status_code != 201:
        return HttpResponse(f'<div class="alert error">Submission failed (HTTP {resp.status_code}). Try again.</div>')

    issue = resp.json()
    if ip_hash:
        cache.set(f"feedback:{ip_hash}", cache.get(f"feedback:{ip_hash}", 0) + 1, _FEEDBACK_TTL)

    label = "feature request" if feedback_type == "feature" else "bug report"
    return HttpResponse(
        f'<div class="alert success">'
        f'Thanks! Your {label} was submitted as '
        f'<a href="{issue["html_url"]}" target="_blank">issue #{issue["number"]}</a>.'
        f'</div>'
    )


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
