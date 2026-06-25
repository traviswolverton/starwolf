# StarWolf Release Notes — Ongoing Maintenance Workflow

## Context

I maintain a Streamlit app called StarWolf at `/opt/stargazing-app`.
There is a file at `/opt/stargazing-app/release_notes.json` that tracks user-facing release notes.

Its structure is:

```json
{
  "releases": [
    {
      "date": "YYYY-MM-DD",
      "features": [
        "Added something new the user can do or see."
      ],
      "fixes": [
        "Fixed an issue where something wasn't working correctly."
      ]
    }
  ]
}
```

Releases are ordered newest-first. One entry per deployment date; if multiple changes ship the same day, their notes are merged into a single entry. Either `features` or `fixes` may be an empty array if there's nothing to report in that category.

---

## Style Guide

Write release notes in plain conversational language, as if explaining to a friend who loves
stargazing but doesn't write code.

- Lead each bullet with a verb ("Added", "Fixed", "Improved", "Removed", "Changed")
- Focus on what the user can now *do* or *see* differently — not what changed technically
- Avoid: "refactored", "endpoint", "component", "parameter", "API", "backend", "cache", "query"
- Prefer specificity: "Moon score now weighs more heavily for naked eye viewing" beats "Improved scoring logic"
- Keep each bullet to one sentence
- Omit changes that have zero visible user impact (pure backend/infra work)
- If a bug fix resolves something the user would have noticed, include it: "Fixed an issue where cloud cover scores occasionally appeared as 0% on windy nights"

---

## Task

I'm about to deploy a set of changes to StarWolf. Please do the following:

### 1. Read the current release notes file

Read `/opt/stargazing-app/release_notes.json` and note the most recent entry date.

### 2. Polish my change descriptions into release note bullets

Take my raw change descriptions below and rewrite each one as a clean, user-friendly bullet
following the style guide above. If a change has no user-visible impact, flag it and ask
whether to omit it rather than silently dropping it.

### 3. Propose the new entry

Show me the complete new JSON entry (date and notes array) **before writing anything**.
If today's date matches the most recent entry, propose merging the new bullets into that
existing entry instead of creating a new one.

Wait for my explicit approval ("looks good", "approved", "go ahead", or similar) before
modifying the file.

### 4. Write the approved entry

Once I approve, prepend the new entry to the `releases` array in `release_notes.json`
(or merge into today's entry if one already exists). Confirm the write succeeded by showing
me the first entry of the updated file.

---

## My Changes

> Replace this section with a plain-English description of what you changed.
> Bullet points, sentence fragments, or dev shorthand are all fine — Claude will clean them up.
> Example:
>
> - fixed the humidity threshold bug that was making humid nights look better than they are
> - added a "share this forecast" button that copies a link to the clipboard
> - swapped out the old font for something more legible on mobile
> - updated Open-Meteo API call to use the new endpoint (no user-visible change)

[DESCRIBE YOUR CHANGES HERE]
