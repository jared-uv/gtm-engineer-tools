---
name: reply-queue
description: >-
  Work every live outbound campaign at once — read the campaign registry, pull
  new replies from every connected source, sort each by what the person actually
  said, draft the reply that campaign's playbook calls for, draft nudges for
  silence past the window, and post one card per person to your chat surface.
  Drafts everywhere it can, sends nowhere. Use when the user says
  "/reply-queue", "what's waiting on me", "any replies", "check the campaigns",
  or "send" a draft the queue surfaced. A scheduled routine runs the same steps
  on a timer; this skill is also how a draft gets sent once approved.
---

# Reply queue

One pass over every outbound campaign you have in flight, ending in a queue of cards — one per person waiting on you, each with the reply already written.

The problem it solves: campaigns accumulate, follow-up gets built separately for each one, and most of them end up relying on someone remembering to ask. Replies get answered because they're loud. The bookkeeping and the silences get dropped.

**The registry is the config.** `campaigns/registry.md` in your repo says where each campaign lives, what the ask was, what each kind of reply gets, when to nudge, and what to record. Read it first, every time. **A campaign not in the registry does not get worked** — and step 1 catches the ones that should be.

**Never sends. Always drafts.** Those are two different properties and the second is the point. Where a draft object exists — a mail thread — the reply is written into your drafts folder, on the thread, right recipient, right subject, waiting for one click. Where it doesn't — LinkedIn, most sequencer inboxes — the card carries paste-ready text. Sending is a separate step, in a session, on your say-so.

---

## Configuration

Set once, in `campaigns/registry.md` frontmatter. Everything else in this skill is generic.

```yaml
surface:      slack            # slack | email — where the queue posts
surface_id:   D0123456789      # Slack DM or channel id; an address for email
draft_mailbox: you@company.com # the connected mailbox drafts are written into
voice:        marketing/authors/you.md   # optional; the voice drafts are written in
window_hours: 3                # reply lookback, ≥ the routine interval
```

**`draft_mailbox` is the one that decides how good this feels.** Connect the mailbox your replies actually land in. A campaign that sends from an address you haven't connected can still be *read* through the sequencer, but its drafts fall back to paste-text, which is a worse experience and the reason people abandon tools like this.

---

## Step 1 — Reconcile the registry against the sources

For each source adapter named in the registry, list what's actually running. Every campaign the registry marks `live` must resolve to a real id; a rebuilt campaign gets a new id and the table goes stale.

Any **running** campaign the source knows about and the registry does not goes at the top of the queue as **Unregistered**, with its name and id. That line is the whole point of the registry; do not drop it because it is awkward. Paused campaigns absent from the registry are not flagged — there are usually hundreds.

## Step 2 — Pull what came in

Run `date -u` first. Two sets: everything inside `window_hours` is **new**; everything already flagged as awaiting your reply is **waiting**.

**Mail adapter.** For registry rows naming a mail search, run it with a recency filter for the new set and without for the waiting set. Read the whole thread before judging the reply.

**Sequencer adapter.** Per live campaign, pull inbox conversations filtered to that campaign's ids. Page through; a busy week is a hundred-plus conversations. Three traps, all of which have cost real replies:

- **A "your turn" flag is a hint, not a verdict.** "Thanks!" sets it and needs nothing.
- **A campaign filter matches contacts, not replies.** It returns every conversation whose contact sits in that campaign, and the same person often sits in five or six at once — so the reply on top may belong to a different ask entirely. The reply activity carries its own campaign id; *that* is what picks the playbook. A reply with no campaign id was sent outside any campaign and gets sorted by what the thread above it is about.
- **A thread where your own message is last is closed**, whatever the flag says. Compare last-replied against last-sent before opening it.
- **Preview text truncates.** Fetch the full conversation for anything longer than a sentence.

**What you cannot see:** replies a sequencer hasn't synced yet (hours, sometimes), and anything sent natively outside a tracked thread. Say "nothing has reached the queue," never "nobody replied."

## Step 3 — Sort by what they said

Four buckets, per that campaign's playbook. Any interest score the source provides sorts the queue; it never decides the bucket.

- **Needs an answer** — a yes, a question, an objection, a referral. Draft.
- **Needs a hand** — a yes whose next step isn't a message: a code to look up, an invite to re-send, a lead to end elsewhere, a number that's your call. Card with no draft, or with the draft that follows the hand action.
- **Closed** — thanks, 👍, "sounds good," out of office, a bounce. Nothing. Keep these out of the queue; they're noise and the queue's job is to be short.

  **Unless your last message was a question.** A short positive reply is closed *only when the message it answers made no ask.* If your previous message ended in a question or an offer — "want me to send it?", "does that work?" — then the same 👍 is a **yes**, and it goes in Needs-an-answer with the playbook's yes path. Read the message above the reply before deciding; the reply alone cannot tell you. This rule exists because a 👍 filed as closed sat unworked for days.
- **Off-campaign** — a reply about something else entirely. Its own card, no draft, unless the answer is in the repo.

**When the playbook does not cover the reply,** say so on the card and do not draft. A confident wrong answer to a pricing question costs more than a two-hour delay.

## Step 4 — Draft

One message per person, in the channel they replied on. Shorter on LinkedIn, no subject and no signature there; mail gets the signature the campaign used. Copy sources are named in each playbook — use them, and use the repo's facts. **Never invent a number, a name, or a policy to make a draft complete.** Leave the gap in square brackets and flag it on the card.

Voice: whatever `voice:` points at, if anything.

**Where the draft goes:**

- **Mail, in the connected mailbox** → write it into the drafts folder as a reply on the thread, same subject, same recipient. Link it on the card. This is the primary path and the reason to connect the right mailbox.
- **Everything else** → a fenced block on the card, so it copies clean.

## Step 5 — Nudges

For each live campaign whose playbook has a nudge rule: contacts with no reply, whose last touch is older than the window, **whose sequence has no steps left to send**, and who haven't been nudged. Draft from the playbook's named copy, mark the card **Nudge**, and say who it's for. One nudge, then stop, unless the playbook says otherwise.

Do not nudge anyone whose sequence still has steps pending. The sequencer will.

## Step 6 — Post the queue

**One card per person**, so each can be ticked off independently. A single long message with the links somewhere else is the layout to avoid — it disconnects the reply from the thing it's replying to.

**The surface is the state.** Before posting, read the last 7 days of it. A card already exists for someone if a message there carries their profile URL, or their name and campaign. Post a card only when there is none, or when they've replied again since the existing card's timestamp — then the new card opens with "New since the last card:". Cards that have been reacted to are done; don't repost them, and don't post "still waiting" reminders for cards without a reaction.

The first run of the day posts a header: how many cards went up since yesterday's, and how many from the last 7 days are still unticked. Other runs post only new cards, and nothing at all if there are none.

The card, top to bottom, every line present:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
*<https://www.linkedin.com/in/slug|First Last>* · Title, Company · email@address
Campaign: example-outbound
*Reply* · 5 days since their message          ← or  *Nudge* · 9 days since your message
> "what they said, one line, their words"

Send from: LinkedIn (or the sequencer inbox)  ← or  Draft is in your Gmail: <link>
```<the message>```
Notes: what the playbook says happens after the send; the tag; the lead to end; the thing that's your call.
```

**Three chat-rendering rules, all learned the hard way.** The card opens with a rule line (`━` × 30) so the eye can find where one person ends and the next begins. The quote line is **followed by a blank line** — Slack keeps a `>` blockquote running until it hits one, and without it "Send from" and "Notes" render inside the quote as if the person had said them. And **both fences sit on their own lines**: newline, opening ```, the message, newline, closing ``` alone, blank line, then Notes. A closing fence glued to a signature means the block never closes and Notes renders as code with a scrollbar. Keep message lines under ~100 characters too; code blocks don't wrap.

Line by line:

- **Name** links their profile; most chat surfaces have no derivable URL for the message thread itself, so the profile is the way in. Title and company from the source, then your CRM; write "title unknown" rather than leaving it blank.
- **Campaign** is the registry slug the reply's own campaign id maps to.
- **Reply / Nudge / Hand**, then the count. For a reply, days since *their* last message; for a nudge, days since *yours*. Whole days, from `date -u`.
- **What they said**, quoted, one line, cut to the point. For a nudge, the last thing you sent instead.
- **Send from** is the channel they replied on — or, for the connected mailbox, a link straight to the draft.
- **The message**, fenced. When the playbook says surface rather than draft, the block holds the one-line question for you instead, and Notes says why there's no draft.
- **Notes** carries the bookkeeping: the tag, the lead to end, the record to reconcile.

**Hand actions with no message** get their own short card in the same shape, reading *Hand*, with no message block.

**A thread reply from you is an instruction.** While reading the surface back, check every card from the last 7 days that has replies. If the last message in the thread is yours and the card isn't ticked, treat it as feedback on the draft: shorter, different tone, a fact you're adding, or an answer to a your-call line. Rewrite with that in it, re-read the source thread if the note changes what the person is being answered about, and post the revised draft **as a reply in that thread**, same fenced block, one line above saying what changed. Don't post a new card and don't touch the original. If the note is a question answerable from the repo, answer it in the thread; if it needs something you can't see, say so rather than guessing. A thread whose last message is yours is waiting on them; leave it.

This is a timed loop, not a conversation — the reply arrives on the next run. For anything faster, use a session.

**Unregistered campaigns** and **sources that failed** go in the header, or in a one-line message of their own when there's no header. Never bury them in a card.

Nothing else goes to the surface. No summaries, no "all clear," no stats beyond the header counts.

## Step 7 — Send, on approval, in a session only

When the user says send, for the drafts they name:

- **Mail** — the draft is already on the thread; they send it from their mail client, or explicitly ask for it to be sent and confirm the recipient.
- **Sequencer / LinkedIn** — send on the contact, channel matching where they replied. Two failures are not draft problems: a not-connected error is that one person and won't clear, and a rate-limit error is usually a daily cap that clears on its own. Either way, hand over the text to send natively.
- **Bookkeeping**, per the playbook: CRM tags, ledger rows, codes. Anything that's UI-only — ending a lead in a sibling campaign, usually — gets listed, not attempted.

Then report: what was sent, to whom, on which channel, and what still needs hands.

## Step 8 — The report, by campaign

One message, every campaign the registry marks `live`, posted on the first run of the day after the header. On demand in a session, or by posting `report` as a plain message on the surface (not in a thread) — on the next run, if no report has gone up since, post one whatever the hour.

**Where each number comes from, because sources disagree on purpose:**

- **Leads, first sends, reached, replied** — from the source's lifetime campaign stats. *First sends* is the opening step's sent count, not total messages, which counts follow-ups too. *Replied* counts people, not messages.
- **👍 / ❓ / 👎** — from reading the replies, the same sort as step 3. A source's own interest counts only exist where someone clicked a control, so they undercount; use them as a floor and say when a reply wasn't read. Never make the three add up to the reply total by guessing.
- **Waiting on you** is open cards for that campaign. **Waiting on them** is reached minus replied, less anyone the sequence is still working.

```
*Campaign report · Mon 14 Sep · 7 live campaigns · 49 replies from 260 reached · +3 since yesterday*

*example-outbound* · running since 9 Sep
84 leads · 53 first sends · 17 opened · *1 replied* (2%)
👍 1 · ❓ 0 · 👎 0 · waiting on you 0 · on them 52
```

One block per campaign, biggest reply count first. The header carries the delta since the previous report — read it back off the surface and diff. A campaign whose numbers didn't move gets its block anyway, so the report is always complete. Add a line under a block only when something needs saying: a zero-open campaign, a bounce, a sequence still mid-flight. Split into two messages past ten live campaigns rather than shrinking the blocks.

**What the report is not.** Not a dashboard mirror, and open rate is not a headline — "opened" means something different on LinkedIn than in mail, and averaging them produces nonsense. It answers "which of these is working, and what's stuck on me."

---

## Routine mode

A scheduled routine runs steps 1–6 on a timer. Its tool allow-list is deliberately asymmetric:

| Allowed | Withheld |
|---|---|
| Reads across every connected source | Send, on every channel |
| **Draft creation in the connected mailbox** | Any CRM or sequencer write |

That asymmetry is the safety property. "Never sends" is a fact about what the routine *can do*, not a rule it's asked to follow — and it coexists with writing real drafts into a real mailbox, which is a write, and is the point.

**The logic lives in this skill, not in the routine's prompt.** The prompt says "read the skill and the registry, then do what they say," so editing this file changes the routine on its next run with no redeploy. That's the opposite of how most scheduled agents are built, and it's deliberate: a prompt that lives only server-side drifts, and there's no diff to catch it.

If a run can't reach a source, the queue says which campaigns went unchecked. It does not skip them silently.

## Watch for

**Someone in two campaigns.** Check the campaign id on the reply activity before choosing a playbook, answer once on the channel they used most recently, and list the other lead for ending.

**A reply that's really a hand-off.** "Talk to my colleague X" is a new contact, not a reply. List X with what's known; don't draft to X.

**The stop date passing.** A campaign past its stop date still gets its replies answered; what stops is nudging. Flag it once so the registry gets updated.

**"Ended" in a sequencer means the sequence has no more steps, not that the conversation is over.** Campaigns routinely produce replies for days after they end. A campaign leaves the `live` set when its stop date passes, never because the sequencer changed its status.

**Money.** Pricing, discounts, fee numbers — anything not written down in the repo is the user's call. Surface, do not draft.
