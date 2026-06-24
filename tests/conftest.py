"""
Shared fixtures for all tests.

Playwright tests require the app to be running:
  docker-compose up -d
  (or: ./venv/bin/streamlit run Planner.py)

Run only unit tests (no app needed):
  ./venv/bin/pytest -m "not playwright"

Run only UI tests:
  ./venv/bin/pytest -m playwright
"""

import pytest
from playwright.sync_api import Page

APP_URL = "http://localhost:8501"

# Page URLs
URLS = {
    "planner":     APP_URL + "/",
    "location":    APP_URL + "/Location",
    "sites":       APP_URL + "/Sites",
    "preferences": APP_URL + "/Preferences",
    "feedback":    APP_URL + "/Feedback",
}


def wait_for_streamlit(page: Page, heading: str) -> None:
    """Wait for Streamlit to finish its initial render.
    Waits for the page's h1 heading, which appears after the app is ready.
    """
    page.wait_for_selector(f"h1", state="visible", timeout=15_000)
    # Brief pause for Streamlit's post-render state updates
    page.wait_for_timeout(300)


@pytest.fixture
def planner(page: Page):
    page.goto(URLS["planner"])
    wait_for_streamlit(page, "Stargazing Trip Planner")
    return page


@pytest.fixture
def location(page: Page):
    page.goto(URLS["location"])
    wait_for_streamlit(page, "Your Location")
    return page


@pytest.fixture
def sites(page: Page):
    page.goto(URLS["sites"])
    wait_for_streamlit(page, "Dark-Sky Sites")
    return page


@pytest.fixture
def preferences(page: Page):
    page.goto(URLS["preferences"])
    wait_for_streamlit(page, "Preferences")
    return page


@pytest.fixture
def feedback(page: Page):
    page.goto(URLS["feedback"])
    wait_for_streamlit(page, "Submit Feedback")
    return page
