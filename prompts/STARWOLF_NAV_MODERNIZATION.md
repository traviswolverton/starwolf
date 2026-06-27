# StarWolf Nav & UI Modernization — Claude Code Prompt

## Context

StarWolf is a dark-themed stargazing planning app built in Django templates with custom CSS. The current color scheme (near-black background `#0d0f14` or similar, teal accent `#3dd68c` or similar) and overall card-based layout are *keepers* — do not change the color palette or the fundamental dark aesthetic. The goal is to modernize the navigation bar and polish several UI details that feel dated, without a full redesign.

---

## Phase 1 — Discovery (STOP after this phase and report findings before touching any code)

Explore the codebase and report back on:

1. The base template file(s) that render the nav bar (likely `base.html` or `_navbar.html` or similar in `templates/`)
2. What CSS file(s) or `<style>` blocks control nav styling — note exact file paths and relevant class names
3. The exact nav items currently rendered and how they're structured in the template (hard-coded links vs. dynamic, any `{% active %}` or `{% url %}` logic, dropdown implementation)
4. How the user dropdown (the "Travis ▾" menu) is currently built — JS toggle, Alpine.js, a `<details>` element, etc.
5. Whether any CSS framework (Bootstrap, Tailwind, Bulma) is in use, or if it's fully custom CSS
6. Any existing active-state logic on nav links (CSS class, template tag, etc.)
7. The main card/border styling used on the Planner page location card and the radius/shadow values currently in use

Report all of this as a structured summary. **Do not write or modify any code in Phase 1.**

---

## Phase 2 — Implementation (only after Travis approves Phase 1 findings)

Apply the following changes. Work file by file and describe each change before making it.

### 1. Nav bar — condensed height and visual hierarchy

- Reduce nav height. Target a slim `48–52px` bar. Tighten padding on nav links (`padding: 0 12px`, vertically centered).
- Establish **two tiers of nav items** visually:
  - **Primary** (full brightness, current teal on hover/active): `Planner`, `Sites`, `Tonight's Sky Map`
  - **Secondary** (slightly dimmer, ~70% opacity at rest, full on hover): `Bortle Scorer`, `Developers ▾`
  - This should be achieved via a CSS class (e.g. `.nav-secondary`) rather than separate markup if possible
- Add an **active page indicator**: a 2px teal underline (`border-bottom: 2px solid var(--accent)`) on the current page's nav link. Implement via whatever active-state mechanism already exists, or add a simple `{% if request.resolver_match.url_name == 'planner' %}active{% endif %}` pattern if nothing exists yet.
- Keep the StarWolf logo/wordmark exactly as-is — it's working.

### 2. User menu — modern avatar button

Replace the current `👤 Travis ▾` text button with a small **initials badge**:

- A `32px` circle, teal border (`2px solid var(--accent)`), dark fill (`background: #1e2128` or the card background color), with the user's initials in teal (`T` or `TR` depending on what's available from the user context).
- The dropdown caret `▾` should sit just outside the circle, small and subtle.
- The dropdown menu itself: add `border-radius: 8px`, a subtle `box-shadow`, and `border: 1px solid rgba(255,255,255,0.08)`. Ensure it's at least `200px` wide so items don't feel cramped.
- **Remove "Two-factor auth" from the dropdown** — auth is handled by Cloudflare Zero Trust upstream; this option is misleading and should not appear in the user menu.

### 3. Card borders — softer, more modern

On the Planner page's location card (the "LOCATION & SITES" card with the teal left border) and any similar cards:

- Keep the teal left accent border — it's a nice design signature.
- Replace any hard `border` on the remaining three sides with: `box-shadow: 0 2px 12px rgba(0,0,0,0.4)` and `border: 1px solid rgba(255,255,255,0.06)`.
- Increase `border-radius` to `12px` if it's currently less than that.

### 4. Hero action cards (homepage only)

The three action cards on the homepage ("Set your location", "Run the Planner", "Check tonight's map") currently feel visually identical. Add subtle differentiation:

- Give each card a faint left border accent in the teal color at varying opacity: first card `100%`, second `70%`, third `50%`. This creates a natural visual priority without changing the layout.
- Alternatively, if the left border is already present only on the active/complete step, preserve that logic and just ensure incomplete steps have no left border (or a muted gray one).

### 5. Typography tightening (light touch)

- Nav link font size: `14px`, `font-weight: 500`, `letter-spacing: 0.01em`
- Page titles (e.g. "Stargazing Trip Planner"): ensure `font-weight: 700`, not 600
- Section labels like "LOCATION & SITES": these all-caps labels are a nice touch — ensure they're `11px`, `letter-spacing: 0.08em`, `font-weight: 600`, and using the secondary text color (not full white)

---

## Constraints

- **Do not change** the color palette, dark background, or teal accent color
- **Do not introduce** a new CSS framework — work within whatever is already there
- **Do not touch** scoring logic, API calls, or any Python/backend files
- **Mobile responsiveness**: note any places where the nav collapses to a hamburger menu — do not break that behavior, but you don't need to redesign the mobile nav in this pass
- Keep changes surgical — this is a polish pass, not a redesign

---

## Deliverable

After Phase 2, provide a summary of every file modified with a one-line description of what changed in each.
