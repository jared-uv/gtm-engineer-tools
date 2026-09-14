# forbidden

A registry of information that must never enter the repo, and where each kind goes instead. Enforced as a hook on every write Claude makes, and as a pre-commit check if you wire one up.

## The problem

Secret scanners exist and are good at keys. What they don't know is your business: that a customer list belongs in the CRM, that a national id number has no reason to be in a repo at all, that a raw export is fine in one folder and a leak in another. The scanner says "found a thing". The person who wrote the file needs to hear "and here is where it goes".

So the registry has an Instead column, and `check` reports every row that leaves it empty.

## Install

```
/plugin marketplace add le0li0n/gtm-engineer-tools
/plugin install forbidden
```

Then, inside the repository you want covered:

```
/forbidden:init
```

That writes a sixteen-row `FORBIDDEN.md` at the repository root: fourteen credential and identity patterns and two heuristics for contact lists. It then asks where each kind of information really lives at your company and fills in the Instead column. Commit the file so every clone gets the same rules.

**Until a repository has a `FORBIDDEN.md`, the hook does nothing there.** Installing the plugin changes nothing in repositories you haven't set up, including ones with test fixtures full of fake keys. `/forbidden:scan` says so when it finds no registry.

## Two kinds of finding, kept apart

| Action | For | In a Claude session | At commit |
|---|---|---|---|
| `block` | Objective patterns: a card number that passes Luhn, a key with a known prefix, a PEM header followed by key material | The write is refused, with the class and the Instead in the message | The commit is refused |
| `warn` | Heuristics: twenty-five distinct email addresses in one file | The write becomes a permission prompt that states the finding; you decide | Printed, and the commit goes ahead |

The split is the whole design. A heuristic that blocks is wrong within a week, on the speaker list for an event or the CC line of a saved email, and then it gets disabled, and then it catches nothing. A heuristic hit is a place to look. `check` enforces the split: a heuristic set to `block` is reported as a problem.

The hook asks about a heuristic when a write takes a file across the threshold, so an edit that adds the twenty-fifth address prompts and later edits to that file don't. `scan` reports every file over the threshold, however it got there.

## Built so a block doesn't cry wolf

A block that fires on ordinary text gets the plugin uninstalled, so each objective detector checks more than a regex:

- `card` needs an issuer prefix whose length fits, a passing Luhn digit, and a number that isn't one of the processors' published test cards. Order numbers, timestamps and long ids go through.
- `ssn` ignores the sample numbers printed on forms and in documentation, and won't match inside a longer hyphenated part number.
- The key detectors (`openai-key`, `anthropic-key`, `github-token`, `slack-token`, `stripe-key`, `notion-token`, `google-api-key`, `generic-secret`) need the value to look generated. `sk-market-analysis-2026`, `YOUR_API_KEY_HERE`, `sk-ant-xxxx…` and an environment variable's name are not keys. `aws-key` ignores the documentation example.
- `private-key` needs key material after the header, so a setup guide that names the header is fine.
- `jwt` needs the first segment to decode to a real token header.
- `password-assignment` ignores variables, templates, masks and paths: `password = os.environ[...]`, `password: "{{ vault }}"`, `Password: required`.

All of it is tested against benign text as well as real-shaped secrets.

## The registry

```
| Class | Detect | Action | Instead | Notes |
|---|---|---|---|---|
| Anthropic API key | anthropic-key | block | Environment variables | |
| Contact list | email-list:25 | warn | The CRM. Raw exports go in one named folder. | |
| Bank details | regex: (?i)\bIBAN\b\s*[:#]?\s*\d{6,} | block | The billing system. | |
```

- **Detect**: a built-in name (`/forbidden:scan --patterns` lists all fourteen), a heuristic with a threshold (`email-list:N`, `phone-list:N`; N defaults to 25), or `regex: <pattern>`. A custom regex is matched line by line; write a literal pipe as `\|`.
- **Action**: `block` or `warn`.
- **Instead**: required. Where it belongs.
- **Notes**: optional, for people.

A line containing `forbidden-ok` is skipped, so fixtures and documentation can show what a pattern looks like. The registry file itself is never scanned.

Every file is judged by the `FORBIDDEN.md` of the git repository that holds it, not the one the session started in. A write into a second checkout uses that checkout's rules, or none if it has none. A write outside any git repository isn't checked.

## Commands

```
/forbidden:init               write FORBIDDEN.md and fill in Instead
/forbidden:scan <path>...     scan files or directories
/forbidden:scan --staged      what is about to be committed
/forbidden:scan --check       validate the registry
/forbidden:scan --patterns    the built-in detectors
```

The same verbs work from a terminal against the script itself: `python3 <plugin-dir>/scripts/forbidden.py scan <path>`, and `staged`, `check`, `patterns`, `init`. `scan` exits 1 when it finds a blocking finding.

## Pre-commit

Git hooks run outside Claude Code, where the plugin's install path isn't known, so the commit check needs its own copy of the script. It's one file with no dependencies. Copy `<plugin-dir>/scripts/forbidden.py` into the repository (say `tools/forbidden.py`), note where it came from, and add this to your pre-commit hook:

```
python3 tools/forbidden.py staged || exit 1
```

It reads the same `FORBIDDEN.md`. A copy drifts from the plugin, so update it when you update the plugin. The check only runs for people who have enabled the hook, and `git commit --no-verify` skips it.

## Where it runs, and where it doesn't

- **Claude Code CLI**: the hook checks every Write, Edit, MultiEdit and NotebookEdit.
- **Anywhere hooks don't run** (Claude desktop, claude.ai, other editors): nothing is enforced. `FORBIDDEN.md` is a plain markdown table, so a person or an agent can still read it and follow it, and the skills work wherever the agent can run a shell command.
- **Bash**: a file written by a shell command in a Claude session doesn't pass through the hook. The pre-commit check is what catches those.

## What it does not do

- Scan history. A key committed last year is still in the history; this stops the next one. A real credential that was committed has to be rotated.
- Scan binaries or files over 2MB, or a single write over 2MB.
- Catch a value that has been split, encoded or otherwise disguised.
- Know every national format. `ssn` is the US hyphenated form and `phone-list` counts North American numbers and numbers written with a `+` country code. Add a `regex:` row for anything else.
- Replace a dedicated secret scanner if you have a lot of code. Use one too. This one's job is the business-data classes those tools don't know and the Instead column they don't have.
- Stop someone determined. A guard against accident, not a security boundary.

## Tests

From the plugin directory:

```
python3 scripts/test_forbidden.py
```

It builds throwaway repositories in a temp directory and needs only `python3` and `git`.
