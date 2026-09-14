# What never goes in this repo

Information that must not be written or committed here, and where each kind belongs instead. The repo is shared with everyone who clones it and with every agent that reads it; the Instead column is the point.

**Detect** is a built-in detector (`/forbidden:scan --patterns` lists them), a heuristic with a threshold such as `email-list:25`, or `regex: <pattern>`. **Action** is `block` for objective patterns (a card number that passes Luhn, a key with a known prefix) and `warn` for heuristics, because a heuristic that blocks gets disabled the first time it is wrong. A line containing `forbidden-ok` is skipped, for fixtures and documentation.

The Instead column below is a starting point. Replace it with the real places your company uses.

| Class | Detect | Action | Instead | Notes |
|---|---|---|---|---|
| Social security number | ssn | block | Never stored. If a process needs it, that process does not run through this repo. | US format. Add a `regex:` row for other national id numbers. |
| Card number | card | block | The payment processor. | Issuer prefix, length and Luhn all have to fit, and the processors' published test numbers are ignored. |
| Private key | private-key | block | The machine's key store, or the secrets manager. | Needs key material after the header, so a doc that names the header does not trip it. |
| AWS access key | aws-key | block | Environment variables, or the secrets manager. | |
| GitHub token | github-token | block | `gh auth login`; never a file. | |
| Slack token | slack-token | block | Environment variables. | |
| Anthropic API key | anthropic-key | block | Environment variables, or `.claude/settings.local.json` if it is gitignored. | |
| OpenAI API key | openai-key | block | Environment variables. | |
| Google API key | google-api-key | block | Environment variables. | Some Google keys are meant to ship in a web page. If yours is, mark that line `forbidden-ok`. |
| Stripe key | stripe-key | block | Environment variables. | Test-mode secret keys too: they still open your test account. |
| Notion token | notion-token | block | Environment variables, or a connector that authenticates each user. | |
| JSON web token | jwt | block | Nowhere. Tokens expire; a committed one is a leak with a timestamp. | Some hosted databases issue a public key that is a JWT. Mark that line `forbidden-ok`. |
| Password in text | password-assignment | block | A password manager. | Variables, templates and placeholders are ignored; a literal value is not. |
| Token next to a word that means token | generic-secret | block | Environment variables. | Catches `api_key = ...` in a script. |
| Customer or contact list | email-list:25 | warn | The CRM. If raw exports have to live in the repo, name the one folder they go in, here. | Heuristic. Twenty-five distinct addresses in one file. |
| Phone list | phone-list:25 | warn | The CRM. | Heuristic. North American numbers, and any number written with a +country code. |
