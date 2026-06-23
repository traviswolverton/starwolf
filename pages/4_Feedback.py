import requests
import streamlit as st

from db import init_db
from utils import init_session_settings, render_sidebar

init_db()
init_session_settings()

st.set_page_config(page_title="Feedback — Stargazing Planner")
st.title("Submit Feedback")
st.caption("Feature ideas, bug reports, or anything else — it goes straight into our issue tracker.")

GITEA_API   = "https://gitea.wolvertons.net/api/v1"
GITEA_REPO  = "travis/stargazing-app"

def _get_token() -> str | None:
    return st.secrets.get("gitea_token") if hasattr(st.secrets, "get") else None


feedback_type = st.radio(
    "Type",
    options=["Feature Request", "Bug Report"],
    horizontal=True,
)

submitter = st.text_input("Your name (optional)", placeholder="e.g. Seth")

title = st.text_input(
    "Short summary *",
    placeholder="Feature Request: ..." if feedback_type == "Feature Request" else "Bug: ...",
)

if feedback_type == "Feature Request":
    description = st.text_area(
        "Description *",
        placeholder=(
            "What would you like the app to do?\n\n"
            "Why is it useful? (who benefits, in what situation)\n\n"
            "Which page or section? (Planner / Sites / Preferences / Location / other)\n\n"
            "Any ideas on how it might work? (optional)"
        ),
        height=220,
    )
else:
    description = st.text_area(
        "Description *",
        placeholder=(
            "What happened?\n\n"
            "What did you expect to happen?\n\n"
            "Steps to reproduce:\n1.\n2.\n3.\n\n"
            "Where in the app? (page and section)\n\n"
            "Browser / device (optional)"
        ),
        height=220,
    )

st.caption("\\* required")

if st.button("Submit", type="primary", disabled=not (title.strip() and description.strip())):
    token = _get_token()
    if not token:
        st.error("Feedback submission is not configured. Contact the site owner.")
    else:
        prefix = "[Feature Request]" if feedback_type == "Feature Request" else "[Bug Report]"
        full_title = f"{prefix} {title.strip()}"

        body_lines = []
        if submitter.strip():
            body_lines.append(f"**Submitted by:** {submitter.strip()}\n")
        body_lines.append(description.strip())

        payload = {
            "title": full_title,
            "body":  "\n".join(body_lines),
        }

        try:
            resp = requests.post(
                f"{GITEA_API}/repos/{GITEA_REPO}/issues",
                json=payload,
                headers={
                    "Authorization": f"token {token}",
                    "Content-Type":  "application/json",
                },
                timeout=10,
            )
            if resp.status_code == 201:
                issue = resp.json()
                st.success(
                    f"Thanks! Your {feedback_type.lower()} was submitted as "
                    f"[issue #{issue['number']}]({issue['html_url']})."
                )
                st.balloons()
            else:
                st.error(f"Submission failed (HTTP {resp.status_code}). Try again or contact the site owner.")
        except requests.exceptions.Timeout:
            st.error("Request timed out. Check your connection and try again.")
        except Exception as e:
            st.error(f"Submission failed: {e}")

render_sidebar()
