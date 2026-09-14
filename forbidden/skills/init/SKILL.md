---
name: init
description: >-
  Set up the forbidden registry in the current repository: write FORBIDDEN.md
  from the template at the repo root, then walk through the Instead column so
  it names the places this company actually uses. Use when the user says
  "/forbidden:init", "set up forbidden", "add a FORBIDDEN.md", or has just
  installed the forbidden plugin and nothing is being checked yet.
---

# init

Until a repository has a `FORBIDDEN.md` at its root, the forbidden hook does nothing there. This writes one.

## Steps

1. Run it from inside the repository.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forbidden.py" init
```

   It refuses outside a git repository and never overwrites an existing `FORBIDDEN.md`. If one exists, skip to step 3.

2. Read the new `FORBIDDEN.md` back to the user as a short list: each class and its Instead.

3. Ask where each kind of information really goes at this company, one question at a time, starting with the two heuristic rows (contact lists and phone lists), because their Instead is the most company-specific. Typical answers: the CRM by name, a secrets manager by name, "environment variables". Edit the Instead cell with what they say. Do not invent a system they did not name.

4. Ask whether there is a class the template lacks, such as bank details, national id numbers from outside the US, or an internal customer id format. Add each as a `regex:` row with `block` only if the pattern is objective; anything that counts or guesses is `warn`.

5. Validate.

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/forbidden.py" check
```

   Fix what it reports and run it again until it says no problems.

6. Offer a first scan of the repository with `/forbidden:scan .`, and mention that `FORBIDDEN.md` should be committed so every clone gets the same rules.
