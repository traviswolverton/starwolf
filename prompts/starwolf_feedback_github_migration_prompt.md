# StarWolf Claude Code Prompt: Migrate Feedback Form from Gitea → GitHub Issues

## Context

StarWolf is a Streamlit-based stargazing planning app. It has an existing feedback form
wired to a self-hosted Gitea instance that creates issues automatically. The app is
being migrated from Gitea to GitHub, so the feedback pipeline needs to follow.

The goal is to swap the Gitea API integration for the GitHub Issues API with minimal
disruption to the UX or the existing form structure.

---

## Phase 1: Discover and Report (DO NOT WRITE CODE YET)

Before making any changes, explore the codebase and report back on the following.
Wait for my approval before proceeding to Phase 2.

Find and examine the feedback form implementation. Answer these questions:

1. **What file(s) contain the feedback form UI and submission logic?**
2. **What does the current Gitea API call look like?**
   - Endpoint URL (how is the Gitea base URL constructed — hardcoded, env var, config file?)
   - Auth method (token in env var, secrets file, hardcoded?)
   - Request payload structure (title, body, labels, assignees — what fields are sent?)
   - Any error handling or success/failure feedback shown to the user?
3. **What fields does the form collect from the user?** (e.g., name, email, type of feedback, description)
4. **How are secrets/credentials currently managed in this project?**
   - Is there a `.env` file, a `secrets.toml` (Streamlit secrets), a config module, or something else?
   - Where would it be appropriate to add the new GitHub token?
5. **Are there any labels being created or assigned on the Gitea side?** If so, list them — we'll need to ensure matching labels exist in the GitHub repo.
6. **Any other files or configs that reference the Gitea URL or token?**

Report your findings in a clear summary before touching anything.

---

## Phase 2: Implementation (after approval)

### Objective

Replace the Gitea issue creation API call with the GitHub Issues REST API.
Preserve all existing form fields, UX, and error handling behavior.

### GitHub Issues API Details

- **Endpoint:** `POST https://api.github.com/repos/{owner}/{repo}/issues`
- **Auth header:** `Authorization: Bearer {GITHUB_TOKEN}`
- **Required headers:**
  ```
  Accept: application/vnd.github+json
  X-GitHub-Api-Version: 2022-11-28
  ```
- **Payload:**
  ```json
  {
    "title": "...",
    "body": "...",
    "labels": ["bug"],        // optional, must exist in repo
    "assignees": ["username"] // optional
  }
  ```
- **Success response:** HTTP 201

### Token

- Add `GITHUB_TOKEN` using whatever secret/credential pattern is already in use
  (Streamlit secrets, .env, config file — match existing convention)
- The token needs `repo` scope (or `public_repo` if the repo is public)
- DO NOT hardcode the token

### Label mapping

- If the existing form lets users choose a feedback type (bug, feature request, etc.),
  map those to GitHub label names
- Use whatever labels already exist in the GitHub repo, OR create a note in your
  report about what labels should be created before going live
- Suggested defaults if starting fresh: `bug`, `enhancement`, `question`

### Body formatting

Preserve the existing issue body format. If the Gitea body used a markdown template
(e.g., "**Reported by:** ...\n**Description:** ..."), keep the same structure.
GitHub Issues renders standard markdown.

### Error handling

- On HTTP 201: show existing success message to user
- On any other status: show a user-friendly error (do not expose raw API response)
  and log the status code + response body for debugging
- Wrap the API call in try/except for network errors

### What NOT to change

- The form UI, field names, or layout
- The existing secrets management pattern
- Any other functionality in the file

---

## Out of Scope

- Creating the GitHub repo or configuring labels (that's manual setup)
- Migrating existing Gitea issues to GitHub
- Adding new form fields
- Changing issue assignment logic

---

## Deliverable

After Phase 2, provide:
1. A diff or summary of exactly what changed
2. The name of the env var / secret key to set (`GITHUB_TOKEN`)
3. A reminder of what labels need to exist in the GitHub repo before the form goes live
4. A one-line test you can run to verify the token is working before deploying
