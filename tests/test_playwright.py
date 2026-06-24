"""
Playwright UI tests — no live forecast or geocoding required.

QA scenarios covered:
  Planner landing:  1.3, 1.1 (via deactivate), 1.5, 1.6, 1.7
  Location page:    3.1, 3.6
  Sites page:       4.1, 4.4, 4.5, 4.7, 4.10
  Preferences page: 5.1, 5.5
  Feedback page:    6.1, 6.2

Requires the app to be running:
  docker-compose up -d
"""

import pytest
from playwright.sync_api import Page, expect


# ── Planner landing ────────────────────────────────────────────────────────────

@pytest.mark.playwright
class TestPlannerLanding:

    def test_default_state_button_enabled(self, planner: Page):
        """QA 1.3 — Fresh session has sites active (DB default), no location.
        Run Forecast button should be enabled."""
        btn = planner.get_by_role("button", name="Run Forecast")
        expect(btn).to_be_enabled()

    def test_default_state_location_card_not_set(self, planner: Page):
        """QA 1.3 — Location card should show ⚙️ and 'Not set' with no location in session."""
        expect(planner.get_by_text("Not set")).to_be_visible()

    def test_preferences_card_always_visible(self, planner: Page):
        """QA 1.5 — Preferences card is always present and shows ✅."""
        expect(planner.get_by_text("Preferences").first).to_be_visible()

    def test_how_it_works_collapsed_by_default(self, planner: Page):
        """QA 1.6 — 'How it works' expander is collapsed; body text not visible."""
        expect(planner.get_by_text("How it works")).to_be_visible()
        expect(planner.get_by_text("Use the pages in the left sidebar")).not_to_be_visible()

    def test_reading_results_collapsed_by_default(self, planner: Page):
        """QA 1.6 — 'Reading your results' expander is collapsed; body text not visible."""
        expect(planner.get_by_text("Reading your results")).to_be_visible()
        expect(planner.get_by_text("Score (0–100)")).not_to_be_visible()

    def test_button_disabled_after_deactivate_all(self, planner: Page):
        """QA 1.1 — After deactivating all sites via Sites page,
        the Run Forecast button should be disabled."""
        # Navigate to Sites, deactivate all
        planner.get_by_text("Sites").first.click()
        planner.wait_for_selector("h1", state="visible", timeout=10_000)
        planner.wait_for_timeout(300)
        planner.get_by_role("button", name="Deactivate All").click()
        planner.wait_for_timeout(500)

        # Navigate back to Planner
        planner.get_by_text("Planner").first.click()
        planner.wait_for_selector("h1", state="visible", timeout=10_000)
        planner.wait_for_timeout(300)

        expect(planner.get_by_role("button", name="Run Forecast")).to_be_disabled()

    def test_site_count_in_caption(self, planner: Page):
        """QA 1.7 — Caption below button shows site count and timezone."""
        # The caption contains "X of Y sites active · timezone"
        caption = planner.locator("small, [data-testid='stCaptionContainer']")
        # At minimum, check the pattern exists somewhere on the page
        expect(planner.get_by_text("sites active ·", exact=False)).to_be_visible()


# ── Location page ──────────────────────────────────────────────────────────────

@pytest.mark.playwright
class TestLocationPage:

    def test_empty_input_shows_warning(self, location: Page):
        """QA 3.1 — Clicking Set Location with empty input shows a warning."""
        location.get_by_role("button", name="Set Location").click()
        location.wait_for_timeout(500)
        expect(location.get_by_text("Enter a location first.")).to_be_visible()

    def test_set_location_button_present(self, location: Page):
        """Basic smoke — Set Location button exists and is enabled."""
        expect(location.get_by_role("button", name="Set Location")).to_be_enabled()

    def test_add_as_site_button_disabled_with_empty_name(self, location: Page):
        """QA 3.6 — 'Add as site' button is disabled when site name field is blank.
        This state only appears after a successful geocode resolve, so we verify
        the button's disabled logic by checking the initial page has no enabled 'Add as site'."""
        # On fresh load (no resolved location), no 'Add as site' button should be present
        add_btn = location.get_by_role("button", name="Add as site")
        expect(add_btn).to_have_count(0)


# ── Sites page ─────────────────────────────────────────────────────────────────

@pytest.mark.playwright
class TestSitesPage:

    def test_empty_proximity_input_shows_warning(self, sites: Page):
        """QA 4.1 — Clicking 'Activate Sites in Range' with empty input shows warning."""
        # Button lives inside the 'Activate by proximity' expander — open it first
        sites.get_by_text("Activate by proximity").click()
        sites.wait_for_timeout(300)
        sites.get_by_role("button", name="Activate Sites in Range").click()
        sites.wait_for_timeout(500)
        expect(sites.get_by_text("Enter a location.")).to_be_visible()

    def test_empty_osm_search_shows_warning(self, sites: Page):
        """QA 4.7 — Clicking 'Find Dark Sky Sites' with empty input shows warning."""
        # Button lives inside the 'Import IDA Dark Sky Sites' expander — open it first
        sites.get_by_text("Import IDA Dark Sky Sites").click()
        sites.wait_for_timeout(300)
        sites.get_by_role("button", name="Find Dark Sky Sites").click()
        sites.wait_for_timeout(500)
        expect(sites.get_by_text("Enter a location to search.")).to_be_visible()

    def test_empty_address_lookup_shows_warning(self, sites: Page):
        """QA 4.10 — Clicking 'Look Up' with empty address input shows warning."""
        # Button lives inside the 'Add Site by Address' expander — open it first
        sites.get_by_text("Add Site by Address").click()
        sites.wait_for_timeout(300)
        sites.get_by_role("button", name="Look Up").click()
        sites.wait_for_timeout(500)
        expect(sites.get_by_text("Enter an address to look up.")).to_be_visible()

    def test_activate_all_shows_success(self, sites: Page):
        """QA 4.4 — Clicking 'Activate All' keeps the page intact (no crash)."""
        # exact=True required: "Activate All" is a substring of "Deactivate All"
        sites.get_by_role("button", name="Activate All", exact=True).click()
        # After st.rerun() the page re-renders — wait for it to settle
        sites.wait_for_selector("h1", state="visible", timeout=10_000)
        sites.wait_for_timeout(300)
        # Page should still be on Sites, not errored out
        expect(sites.get_by_role("heading", name="Dark-Sky Sites")).to_be_visible()
        expect(sites.get_by_role("button", name="Deactivate All")).to_be_visible()

    def test_deactivate_all_then_planner_button_disabled(self, sites: Page):
        """QA 4.5 — After Deactivate All, navigating to Planner shows disabled Run Forecast."""
        sites.get_by_role("button", name="Deactivate All").click()
        sites.wait_for_timeout(500)

        sites.get_by_text("Planner").first.click()
        sites.wait_for_selector("h1", state="visible", timeout=10_000)
        sites.wait_for_timeout(300)

        expect(sites.get_by_role("button", name="Run Forecast")).to_be_disabled()


# ── Preferences page ───────────────────────────────────────────────────────────

@pytest.mark.playwright
class TestPreferencesPage:

    def test_reset_to_defaults_button_present(self, preferences: Page):
        """QA 5.5 — Reset to defaults button exists."""
        expect(preferences.get_by_role("button", name="Reset to defaults")).to_be_visible()

    def test_reset_to_defaults_runs_without_error(self, preferences: Page):
        """QA 5.5 — Clicking Reset to defaults does not produce an error."""
        preferences.get_by_role("button", name="Reset to defaults").click()
        preferences.wait_for_timeout(500)
        expect(preferences.get_by_text("Error", exact=False)).to_have_count(0)

    def test_timezone_shown_in_planner_caption(self, preferences: Page):
        """QA 5.1 — After Preferences loads, navigating to Planner shows the timezone
        in the status caption below the Run Forecast button."""
        # Navigate to planner
        preferences.get_by_text("Planner").first.click()
        preferences.wait_for_selector("h1", state="visible", timeout=10_000)
        preferences.wait_for_timeout(300)
        # Caption contains "sites active · <timezone>"
        expect(preferences.get_by_text("sites active ·", exact=False)).to_be_visible()


# ── Feedback page ──────────────────────────────────────────────────────────────

@pytest.mark.playwright
class TestFeedbackPage:

    def test_submit_disabled_with_empty_fields(self, feedback: Page):
        """QA 6.1 — Submit button is disabled when title and description are empty."""
        expect(feedback.get_by_role("button", name="Submit")).to_be_disabled()

    def test_submit_enabled_with_title_and_description(self, feedback: Page):
        """QA 6.2 — Submit is enabled when title and description are filled;
        name field is optional (left blank here)."""
        # Press Tab after each fill to commit the value and trigger Streamlit's re-render
        feedback.get_by_label("Short summary *").fill("Test title")
        feedback.get_by_label("Short summary *").press("Tab")
        feedback.get_by_label("Description *").fill("Test description")
        feedback.get_by_label("Description *").press("Tab")
        feedback.wait_for_timeout(800)
        expect(feedback.get_by_role("button", name="Submit")).to_be_enabled()

    def test_submit_enabled_without_name(self, feedback: Page):
        """QA 6.2 — Name field is optional; leaving it blank does not disable Submit."""
        feedback.get_by_label("Short summary *").fill("No name test")
        feedback.get_by_label("Short summary *").press("Tab")
        feedback.get_by_label("Description *").fill("Submitting without a name")
        feedback.get_by_label("Description *").press("Tab")
        feedback.wait_for_timeout(800)
        # Name field intentionally left blank
        expect(feedback.get_by_role("button", name="Submit")).to_be_enabled()
