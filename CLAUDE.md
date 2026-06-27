# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Read Lazily

**Only read what the task requires. Don't pre-load context speculatively.**

Before reading a file, ask: "Will I actually use this?"
- Check TODO.md only for tasks that might conflict with in-progress work (migrations, refactors, infra changes). Skip it for isolated additions.
- Read reference files (playbooks, existing configs) only if you need to copy a pattern or modify them — not to "understand the system."
- Read files you're editing just-in-time, not upfront as orientation.

If you catch yourself reading something "just to be safe," stop. Read it when the task demands it.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Stargazing App Context

### API Documentation
After completing any turn where you touched `django/engine/forecast.py`, `django/engine/scorer.py`, or any Django view in a way that changes the shape of API requests or responses (new fields, removed fields, changed error behavior, new parameters), immediately update `docs/API_GUIDE.md`. Changes that only affect internal logic with no effect on the request/response contract can be omitted.

**Adding a new endpoint:** The Django `api_guide` view reads `docs/API_GUIDE.md` by `###` headings — each `### GET /v1/your-endpoint` section automatically becomes a new tab with no code changes required. Steps:
1. Add the endpoint to the relevant Django view
2. Add a `### GET /v1/your-endpoint` section to `docs/API_GUIDE.md` (parameters, response example, field notes, error responses)
3. Add a curl + Python example to the `## Examples` section of `docs/API_GUIDE.md`

### Release Notes
After completing any turn where you touched any of the following, immediately update `release_notes.json` — do not wait for a commit or push:
- User-facing files: pages, UI logic, scoring, site data
- API changes: new endpoints, changed request/response shape, new error behavior

Prepend a new entry with plain-English bullets following the style guide in `prompts/phase3-maintenance-workflow.md`. Pure infrastructure changes with no user- or developer-visible effect (e.g. Docker internals, CI config) can be omitted. When in doubt, include it.

A Stop hook will remind you if you end a turn with changed `.py`/`.html`/`.css`/`.js` files but no update to `release_notes.json`. Treat that reminder as a blocker — update release notes before moving on.

**Date accuracy:** Do NOT use the `currentDate` context variable for release note dates — it is set at session start and can be stale. The server runs UTC but the user is in Houston (CDT, UTC−5). Always run `TZ=America/Chicago date +%Y-%m-%d` to get the correct local date before writing or updating a release entry.

### Commit & Push Cadence

Every completed task ends with a commit and push — no exceptions. The sequence is:

1. Make the change
2. Update `release_notes.json` if user-facing (see above)
3. Commit with a short imperative message (≤72 chars)
4. Ask the user to confirm, then push to `origin main`

A task is not done until it is committed and pushed. Do not pile unrelated changes into one commit.

**Before committing:** confirm release notes are updated if needed. The Stop hook will catch this, but don't rely on it — build the habit.
