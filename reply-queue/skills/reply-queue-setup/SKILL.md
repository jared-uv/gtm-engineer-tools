---
name: reply-queue-setup
description: >-
  Install the reply queue in the repo you are in — scaffold campaigns/registry.md
  from the template, fill its config from a short interview, check which
  connectors are actually reachable, and print the routine prompt and allow-list
  ready to paste into /schedule. Use when the user says "/reply-queue-setup",
  "set up the reply queue", "install reply queue", or has the plugin installed
  and no registry yet.
---

# reply-queue-setup

Gets the reply queue running in the current repo. One interview, one file written, one prompt to paste.

**Ask one question at a time.** This is an interview, not a form — batching them gets vague answers to the ones in the middle.

## Step 1 — Check the ground

Confirm the repo is a git checkout, then check whether `campaigns/registry.md` already exists. If it does, **do not overwrite it.** Say it's there, offer to add a campaign to it instead, and stop.

Then list the MCP connectors actually reachable in this session. That list decides what's worth asking about — there's no point interviewing someone about their sequencer if it isn't connected. Report what you found in one line before asking anything.

## Step 2 — The interview

Six questions, one at a time. Skip any the connector check already answered.

1. **Where should the queue post?** A Slack DM to yourself is the default; a channel works if others act on replies too. Email if there's no chat connector. Get the actual id or address — don't proceed on "my Slack."
2. **Which mailbox do your replies land in?** This is the one that decides whether drafts go into a drafts folder or come back as paste-text. If the connected mailbox isn't the one their campaigns send from, say so plainly now rather than letting them discover it on the first run.
3. **What's in flight right now?** Get names, not ids — the ids come from the sources in step 3.
4. **For each campaign: what did it ask for?** One line each.
5. **What does a yes get?** Per campaign. This is the part people skip and it's the part that makes the drafts usable. If they can't answer, the campaign goes in as `draft` status rather than `live`.
6. **Is there a voice or author profile to write in?** Optional. A path if yes.

## Step 3 — Resolve the ids

For each named campaign, query the connected sources and match by name. Show what you matched and ask them to confirm before writing — campaign names are rarely unique and a wrong id means a playbook applied to the wrong people.

Anything you can't match goes in as `manual:` with a note, not as a guess.

## Step 4 — Write the registry

Copy `templates/registry.template.md` to `campaigns/registry.md`, fill the frontmatter from the interview, write one index row and one playbook section per campaign.

Leave the template's commentary in for any campaign whose playbook is incomplete — a visible `TODO` is better than a plausible-looking playbook that makes the checker guess. Say which ones are incomplete when you report.

## Step 5 — Hand over the routine

Print, in a fenced block ready to copy:

1. The three-sentence prompt from `templates/routine.template.md`.
2. The allow-list, with the connector names substituted for the ones actually found in step 1.
3. The cron line.

Then say plainly: **they paste this into `/schedule` themselves.** Don't create the routine for them. A scheduled agent that starts running against someone's real inbox should be a thing they deliberately turned on.

## Step 6 — Report

Four lines:

- Registry written, and how many campaigns are `live` versus `draft`.
- Which connectors resolved, and which didn't.
- Whether drafts will land in a real drafts folder or fall back to paste-text — and if it's the latter, which mailbox they'd need to connect to fix it.
- The one command to try it now: `/reply-queue`.

Suggest running it once in-session before scheduling anything. The first run against real campaigns is where a wrong id or a thin playbook shows up, and it's much better to see that in a conversation than in a Slack DM at 7am.
