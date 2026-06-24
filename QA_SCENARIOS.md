# QA Scenarios — Stargazing Trip Planner

Format: Given / When / Then. Each scenario targets a specific edge case or user path.

## Automation key

| Badge | Meaning |
|---|---|
| 🟢 **pytest** | Already automated — run `./venv/bin/pytest tests/test_scorer.py -v` |
| 🟡 **Playwright** | Could be automated with browser testing (not yet written) |
| 🔴 **Manual** | Requires a real external API call, live network, or visual judgment |

Where a scenario has both a logic layer (scorer) and a UI layer (display), both badges appear.

---

## 1. Planner — Landing (pre-forecast)

### 1.1 No location, no active sites
> 🟡 **Playwright** — assert button disabled; assert Location card text = "Not set"; assert Sites card text = "No sites active"

- **Given** no location is set and all sites are deactivated
- **When** the Planner page loads
- **Then** the Run Forecast button is disabled; the Location card shows ⚙️ "Not set" with a "Set location →" link; the Sites card shows ⚙️ "No sites active"

### 1.2 Location set, no active sites
> 🟡 **Playwright** — assert button disabled; assert Location card shows ✅ and display name

- **Given** a location is set but all sites are deactivated
- **When** the Planner page loads
- **Then** the Run Forecast button is still disabled; the Location card shows ✅ with the display name; the Sites card shows ⚙️

### 1.3 Active sites, no location
> 🟡 **Playwright** — assert button enabled; assert Location card shows ⚙️; assert Sites card shows ✅

- **Given** one or more sites are active but no location is set
- **When** the Planner page loads
- **Then** the Run Forecast button is enabled; the Location card shows ⚙️; the Sites card shows ✅ with count

### 1.4 All systems go
> 🟡 **Playwright** — assert all three cards contain ✅; assert caption text matches pattern

- **Given** a location is set and at least one site is active
- **When** the Planner page loads
- **Then** all three status cards show ✅; the caption below the button reads "{active} of {total} sites active · {timezone}"

### 1.5 Preferences card always green
> 🟡 **Playwright** — assert Preferences card shows ✅ regardless of threshold/disqualifier values

- **Given** any state
- **When** the Planner page loads
- **Then** the Preferences card always shows ✅ regardless of threshold or disqualifier values

### 1.6 Expanders collapsed by default
> 🟡 **Playwright** — assert expander body elements not visible on fresh load

- **Given** a fresh page load
- **When** the pre-forecast view is displayed
- **Then** both "How it works" and "Reading your results" are collapsed; no markdown body is visible without interaction

### 1.7 Status card site count accuracy
> 🟡 **Playwright** — set 5 sites (3 active), assert card caption = "3 of 5 active"; assert button caption matches

- **Given** 5 total sites with 3 active
- **When** the Planner page loads
- **Then** the Sites card caption reads "3 of 5 active" and the button caption reads "3 of 5 sites active · {timezone}"

---

## 2. Planner — Results

### 2.1 Default sort is Telescope Score
> 🟡 **Playwright** — assert "🔭 Telescope Score" radio selected on first render; assert card order matches composite desc

- **Given** a forecast has been run
- **When** the results page first renders
- **Then** "🔭 Telescope Score" is selected and cards are ordered highest composite score first

### 2.2 Sort by Naked Eye Score
> 🟡 **Playwright** — click "👁 Naked Eye Score" radio; assert card order matches naked_eye desc

- **Given** forecast results are shown
- **When** the user selects "👁 Naked Eye Score"
- **Then** cards reorder by `naked_eye` descending; a site with Bortle 7+ should rank lower than an otherwise equivalent site with Bortle 2

### 2.3 Sort by Date
> 🟡 **Playwright** — click "Date" radio; assert card order is date ascending

- **Given** forecast results are shown
- **When** the user selects "Date"
- **Then** cards are ordered by date ascending; ties within a night are broken by composite score descending

### 2.4 Sort by Location
> 🟡 **Playwright** — click "Location" radio; assert cards group by site name alphabetically

- **Given** forecast results are shown with multiple sites
- **When** the user selects "Location"
- **Then** cards group by site name alphabetically, then by date within each site

### 2.5 Card header shows both scores
> 🟡 **Playwright** — assert each expander label contains 🔭 and 👁 with numeric scores

- **Given** results are displayed
- **When** any night card is visible
- **Then** the expander label shows 🔭 telescope score and 👁 naked eye score, each colored by their respective quality bands (green ≥70, orange ≥40, red <40)

### 2.6 Naked eye score lower for high Bortle sites
> 🟢 **pytest** `test_naked_eye_lower_for_high_bortle` — scorer logic verified
> 🟡 **Playwright** — assert 👁 score in card header is numerically lower than 🔭 score for a Bortle 7+ site

- **Given** a site with Bortle class 7 or higher
- **When** results are shown
- **Then** the 👁 score in the card header is visibly lower than the 🔭 score (Bortle modifier ≤ 0.65)

### 2.7 Naked eye score equal for Bortle 1–2 sites
> 🟢 **pytest** `test_naked_eye_not_penalised_for_low_bortle` — modifier = 1.0 verified
> 🟡 **Playwright** — assert Bortle 1 and Bortle 2 sites produce identical 👁 scores

- **Given** a site with Bortle class 1 or 2
- **When** results are shown
- **Then** the naked eye score is not penalised; differences from telescope score come only from weight differences (no modifier)

### 2.8 Bortle metric in expanded card
> 🟡 **Playwright** — expand card; assert Bortle metric text = "Class N"; assert color class is correct

- **Given** a site has a Bortle class set (e.g. 4)
- **When** the user expands a night card
- **Then** the Bortle metric shows "Class 4" colored appropriately (green for low values, red for high)

### 2.9 Bortle metric when not set
> 🟢 **pytest** `test_bortle_none_in_stats`, `test_naked_eye_none_bortle_equals_bortle_1` — None handling verified
> 🟡 **Playwright** — expand card for a site with no Bortle; assert metric shows "—"

- **Given** a site has no Bortle class in the database
- **When** the user expands a night card
- **Then** the Bortle metric shows "—" without crashing

### 2.10 Threshold filters composite only
> 🟢 **pytest** `test_composite_unaffected_by_bortle` (partial — confirms Bortle doesn't affect composite)
> 🟡 **Playwright** — set threshold to 60; run forecast; assert a night with composite 55 / naked_eye 75 is absent from scored cards

- **Given** min_score_threshold is set to 60
- **When** results are shown
- **Then** nights with composite < 60 are excluded regardless of their naked_eye score; a night with composite 55 / naked_eye 75 does not appear in results

### 2.11 All nights below threshold
> 🟡 **Playwright** — set threshold to 99; run forecast; assert info message shown and no cards present

- **Given** min_score_threshold is set to 99
- **When** a forecast is run
- **Then** the "No nights scored above 99. Lower your threshold in Preferences." info message is shown; no cards are displayed

### 2.12 7timer toggle with no data
> 🟡 **Playwright** — enable "7timer data only" toggle; assert info message appears when no 7timer nights exist

- **Given** the forecast window extends beyond 3 days and no 7timer slots cover those nights
- **When** the user enables "7timer data only"
- **Then** the info message "No nights with 7timer data in the current results" is shown; no cards appear

### 2.13 Disqualified nights section
> 🟢 **pytest** `test_disqualifier_sets_flag` — scorer flags disqualified reason correctly
> 🟡 **Playwright** — run forecast with tight cloud limit; assert "Disqualified nights (N)" expander present; expand and assert table has Date/Site/Reason columns

- **Given** at least one night exceeds a disqualifier threshold (e.g. cloud cover > limit)
- **When** results are shown
- **Then** a collapsed "Disqualified nights (N)" expander appears below the scored cards; expanding it shows a table with Date, Site, Reason columns

### 2.14 No disqualified nights
> 🟢 **pytest** `test_no_disqualifier_when_within_limits` — scorer produces no flag
> 🟡 **Playwright** — run forecast with loose limits; assert disqualified expander absent

- **Given** no nights exceed any disqualifier threshold
- **When** results are shown
- **Then** the disqualified expander does not appear

### 2.15 Heatmap defaults to Telescope
> 🟡 **Playwright** — assert "🔭 Telescope" radio selected by default in heatmap section

- **Given** forecast results are shown
- **When** the heatmap section renders
- **Then** "🔭 Telescope" is selected and heatmap reflects composite scores

### 2.16 Heatmap switches to Naked Eye
> 🟡 **Playwright** — click "👁 Naked Eye"; assert heatmap cell values change for high-Bortle sites

- **Given** forecast results are shown with heatmap visible
- **When** the user selects "👁 Naked Eye" on the heatmap radio
- **Then** the heatmap re-renders using naked_eye scores; cells for high-Bortle sites should shift toward red

### 2.17 Back button clears results
> 🟡 **Playwright** — click "← Back"; assert pre-forecast landing is visible; assert no result cards remain

- **Given** the user is viewing results
- **When** they click "← Back"
- **Then** the pre-forecast landing is shown with all status cards intact; no stale results are displayed

### 2.18 Distance shown only when location is set
> 🟡 **Playwright** — run forecast with no location; assert card header text contains no "·" distance suffix

- **Given** no location is set
- **When** results are shown
- **Then** card headers contain no distance string; no crash

### 2.19 Distance shown when location is set
> 🟡 **Playwright** — run forecast with location set; assert card header text contains a distance string

- **Given** a location is set
- **When** results are shown
- **Then** each card header includes a distance string (e.g. "· 142 mi") after the site name

---

## 3. Location Page

### 3.1 Submit empty field
> 🟡 **Playwright** — click "Set Location" with empty input; assert warning text appears

- **Given** the location input is blank
- **When** the user clicks "Set Location"
- **Then** a warning "Enter a location first." is shown; session state is unchanged

### 3.2 Valid city resolves
> 🔴 **Manual** — depends on live Nominatim geocoding; assert success message and Planner card switches to ✅

- **Given** the user enters a recognisable city or zip code
- **When** they click "Set Location"
- **Then** success message "📍 Location set: {display}" is shown; Planner Location card switches to ✅

### 3.3 Unrecognised input
> 🔴 **Manual** — depends on live geocoder returning no results; assert error shown and session state unchanged

- **Given** the user enters a nonsense string
- **When** they click "Set Location"
- **Then** an error message is shown; no location is saved to session state

### 3.4 Location already set — display and clear
> 🟡 **Playwright** — pre-set session state; assert coordinates and "Clear location" button visible

- **Given** a location is already saved in session state
- **When** the Location page loads
- **Then** the current location is shown with coordinates; a "Clear location" button is present

### 3.5 Clear location
> 🟡 **Playwright** — click "Clear location"; assert Planner Location card reverts to ⚙️

- **Given** a location is set
- **When** the user clicks "Clear location"
- **Then** session state location is removed; Planner Location card reverts to ⚙️ "Not set"

### 3.6 Add as site — empty name warning
> 🟡 **Playwright** — after resolve, clear site name field; assert "Add as site" button is disabled

- **Given** a location has just been resolved and the "Add as site" panel is shown
- **When** the user clears the pre-filled site name and clicks "Add as site"
- **Then** the button is disabled (name is blank); no site is created

### 3.7 Add as site — success
> 🔴 **Manual** — requires live geocoding; fill site name; assert success message and site appears on Sites page

- **Given** a location has been resolved and the user has entered a site name
- **When** they click "Add as site"
- **Then** "{name} added to your site catalog." is shown; the site appears on the Sites page

### 3.8 Skip add-as-site
> 🟡 **Playwright** — click "Skip"; assert add-as-site panel hidden; assert location still set

- **Given** a location has just been resolved
- **When** the user clicks "Skip"
- **Then** the location remains set and no site is created; the add-as-site panel disappears

---

## 4. Sites Page

### 4.1 Activate by proximity — no location entered
> 🟡 **Playwright** — leave input blank; click "Activate Sites in Range"; assert warning shown

- **Given** the proximity input is blank
- **When** the user clicks "Activate Sites in Range"
- **Then** warning "Enter a location." is shown; no sites are toggled

### 4.2 Activate by proximity — valid location
> 🔴 **Manual** — requires live geocoding and DB sites within range; assert activated count in success message

- **Given** a recognisable location is entered with a radius
- **When** the user clicks "Activate Sites in Range"
- **Then** success message shows the count of sites activated; those sites appear as active in the table

### 4.3 Activate by proximity — no sites in range
> 🟡 **Playwright** — enter a location far from all DB sites; assert "Activated 0 site(s)" message
> *(geocoding still live — partial manual dependency)*

- **Given** a remote location is entered where no DB sites exist within the radius
- **When** the user clicks "Activate Sites in Range"
- **Then** success message reads "Activated 0 site(s)"; no sites are changed

### 4.4 Activate All
> 🟡 **Playwright** — click "Activate All"; assert all rows in table are active; assert Planner count = total

- **Given** some sites are inactive
- **When** the user clicks "Activate All"
- **Then** all sites are marked active; the Sites count in the Planner status card reflects the full total

### 4.5 Deactivate All
> 🟡 **Playwright** — click "Deactivate All"; navigate to Planner; assert Run Forecast button is disabled

- **Given** some sites are active
- **When** the user clicks "Deactivate All"
- **Then** all sites are deactivated; the Planner Run Forecast button becomes disabled

### 4.6 Save Sites persists changes
> 🟡 **Playwright** — toggle site, click "Save Sites", reload page; assert active state persists

- **Given** the user has toggled sites in the data editor
- **When** they click "Save Sites"
- **Then** "Sites saved." is shown; reloading the page reflects the same active states

### 4.7 OSM import — blank location
> 🟡 **Playwright** — leave OSM input blank; click "Find Dark Sky Sites"; assert warning shown

- **Given** the OSM search input is blank
- **When** the user clicks "Find Dark Sky Sites"
- **Then** warning "Enter a location to search." is shown; no API call is made

### 4.8 OSM import — no results
> 🔴 **Manual** — requires live OSM/Overpass API; enter remote location; assert "No dark-sky sites found" info message

- **Given** a location is entered where no IDA dark-sky places exist in OSM
- **When** the user clicks "Find Dark Sky Sites"
- **Then** the info message "No dark-sky sites found in that area. Try a larger radius." is shown

### 4.9 OSM import — results, import selected
> 🔴 **Manual** — requires live OSM API; select results; assert success message and sites in table

- **Given** OSM search returns one or more results
- **When** the user selects some and clicks "Import Selected"
- **Then** "{n} site(s)." success message is shown; the imported sites appear in the main table

### 4.10 Manual add — blank address
> 🟡 **Playwright** — leave address field blank; click "Look Up"; assert warning shown

- **Given** the address lookup field is empty
- **When** the user clicks "Look Up"
- **Then** warning "Enter an address to look up." is shown

### 4.11 Manual add — duplicate detection
> 🔴 **Manual** — requires live geocoding + existing nearby site in DB; assert duplicate warning appears but add still possible

- **Given** an address resolves to coordinates within a few km of an existing site
- **When** the resolution succeeds
- **Then** a warning "⚠️ Possible duplicate: {name} ({distance} away in DB)" is shown; the user can still proceed

### 4.12 Manual add — success
> 🔴 **Manual** — requires live geocoding; assert "Added '{name}'." shown and site appears in table

- **Given** a unique address is resolved and a site name is entered
- **When** the user clicks "Add Site"
- **Then** "Added '{name}'." is shown; the new site appears in the table with the resolved lat/lon

### 4.13 Bortle class editable
> 🟢 **pytest** `test_composite_unaffected_by_bortle`, `test_naked_eye_monotonically_decreases_with_bortle` — scoring effect verified
> 🟡 **Playwright** — edit Bortle cell in data editor; click "Save Sites"; assert value persists on reload

- **Given** a site exists in the table
- **When** the user edits the Bortle Class cell (1–9) and saves
- **Then** the value is stored; the next forecast run reflects the updated Bortle modifier in the naked eye score

---

## 5. Preferences Page

### 5.1 Timezone change reflected in Planner
> 🟡 **Playwright** — change timezone selectbox; navigate to Planner; assert caption contains new timezone string

- **Given** the user changes the timezone selectbox
- **When** they navigate to the Planner
- **Then** the status card caption and button caption show the updated timezone

### 5.2 Threshold filters results
> 🔴 **Manual** — requires live forecast run; raise threshold; assert lower-scored nights disappear from cards

- **Given** the threshold is raised from 40 to 70
- **When** a forecast is run
- **Then** nights with composite 40–69 are excluded from the scored cards

### 5.3 Threshold at 100
> 🔴 **Manual** — requires live forecast run; set threshold to 100; assert "No nights scored above 100" message

- **Given** the threshold slider is set to 100
- **When** a forecast is run
- **Then** effectively no nights are shown; the "No nights scored above 100" message is displayed

### 5.4 Cloud cover disqualifier at 0
> 🔴 **Manual** — requires live forecast run with real cloud data; assert all nights move to disqualified section

- **Given** max_cloud_cover is set to 0%
- **When** a forecast is run
- **Then** all nights with any cloud cover are disqualified and appear in the disqualified section

### 5.5 Reset to defaults
> 🟡 **Playwright** — move sliders; click "Reset to defaults"; assert slider values return to defaults

- **Given** the user has changed multiple sliders
- **When** they click "Reset to defaults"
- **Then** all sliders return to their default values; the Planner status card caption updates accordingly

---

## 6. Feedback Page

### 6.1 Submit button disabled without content
> 🟡 **Playwright** — load page with empty fields; assert Submit button has disabled attribute

- **Given** title or description fields are empty
- **When** the page renders
- **Then** the Submit button is disabled; no submission can be made

### 6.2 Name is optional
> 🟡 **Playwright** — fill title and description, leave name blank; assert Submit enabled and clickable

- **Given** title and description are filled but name is blank
- **When** the user clicks Submit
- **Then** submission proceeds without error; feedback is recorded without a submitter name

### 6.3 Successful submission
> 🔴 **Manual** — requires live feedback endpoint; assert success message shown

- **Given** title and description are filled
- **When** the user clicks Submit and the request succeeds
- **Then** a success message is shown confirming the feedback was received

### 6.4 Submission failure — timeout
> 🔴 **Manual** — requires network disruption or downed endpoint; assert timeout error message shown and form not reset

- **Given** the feedback endpoint is unreachable
- **When** the user clicks Submit
- **Then** the error message "Request timed out. Check your connection and try again." is shown; the form is not reset

---

## 7. Cross-Cutting / Session State

### 7.1 Page refresh resets show_results
> 🟡 **Playwright** — navigate to results; hard refresh (F5); assert pre-forecast landing is shown, no result cards

- **Given** the user is viewing forecast results
- **When** they hard-refresh the browser
- **Then** the pre-forecast landing is shown (show_results resets to False); no stale night data is displayed

### 7.2 API failure during forecast
> 🔴 **Manual** — block network to Open-Meteo (e.g. via hosts file or proxy); click Run Forecast; assert no crash and app remains navigable

- **Given** Open-Meteo is unreachable
- **When** the user clicks Run Forecast
- **Then** no crash occurs; either an empty results state or an error message is shown; the app remains navigable

### 7.3 Mixed Bortle data across sites
> 🟢 **pytest** `test_naked_eye_monotonically_decreases_with_bortle`, `test_naked_eye_none_bortle_equals_bortle_1`, `test_bortle_none_in_stats` — scorer behaviour verified
> 🟡 **Playwright** — run forecast with mixed sites; assert "Class N" shown for sites with Bortle, "—" for sites without

- **Given** some sites have a Bortle class set and others do not
- **When** results are displayed
- **Then** cards for sites with Bortle show "Class N" and a modifier is applied; cards for sites without Bortle show "—" and no modifier is applied (modifier = 1.0)

### 7.4 Session state site toggles persist across page navigation
> 🟡 **Playwright** — deactivate a site on Sites page; navigate to Planner; navigate back to Sites; assert site still deactivated and Planner count consistent

- **Given** the user deactivates a site on the Sites page
- **When** they navigate to the Planner and back to Sites
- **Then** the site remains deactivated; the active count in the Planner status card is consistent
