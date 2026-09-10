# Reply queue — routine template

The scheduled half. Copy the prompt into a Claude Code routine (`/schedule`), set the cron, and set the allow-list exactly as below.

**Keep the prompt this short.** It deliberately holds no logic. The skill and the registry are version-controlled and diffable; a routine prompt lives server-side, has no history, and can't be grepped. Every line of behaviour you move into the prompt is a line that will drift without anyone noticing.

---

## The prompt

```
Read .claude/skills/reply-queue/SKILL.md and campaigns/registry.md from the
repo, then do exactly what they say for steps 1 through 6.

Post the queue to the surface named in the registry frontmatter.

Do not send anything. Drafts only.
```

That's the whole prompt. Three sentences.

## The schedule

Every two hours, 7am–7pm, on weekdays, is a sensible default. Reasoning: the window overlaps the lookback (`window_hours: 3` against a two-hour interval) so nothing falls between runs, and stopping in the evening keeps the surface quiet when you can't act anyway.

```
0 14,16,18,20,22,0,2 * * 1-5     # 7am–7pm PT, expressed in UTC
```

The first run of the day is the one that posts the header and the report. Everything after it posts only new cards.

## The allow-list

**This is the safety property.** It is asymmetric on purpose — drafting is a write and it is allowed; sending is a write and it is not.

```
Bash, Read, Glob, Grep,

# read every source
mcp__<mail>__search_threads, mcp__<mail>__get_thread, mcp__<mail>__get_message,
mcp__<sequencer>__get_campaigns, mcp__<sequencer>__get_campaigns_stats,
mcp__<sequencer>__get_inbox_conversations, mcp__<sequencer>__get_inbox_conversation,
mcp__<sequencer>__search_campaign_leads, mcp__<sequencer>__search_contacts,

# write drafts — the point of the thing
mcp__<mail>__create_draft,

# post and read back the queue
mcp__<chat>__send_message, mcp__<chat>__read_channel,
mcp__<chat>__read_thread, mcp__<chat>__get_reactions
```

Deliberately **absent**, and each for a reason worth keeping:

| Withheld | Why |
|---|---|
| `mcp__<mail>__send_message` | A drafted reply is reviewable. A sent one isn't. |
| `mcp__<sequencer>__send_message` | Same, and a sequencer send is attributed to you with no thread to inspect first. |
| Any CRM write | Bookkeeping is proposed on the card and applied by a person. An agent that tags at 3am produces a CRM nobody trusts. |
| Any delete | There is no case where this needs one. |

If you add a source, add its **read** tools here and stop. The rule for extending the allow-list is that a new tool goes in only if the queue can't be built without it.

## Checking it works

The first run should either post cards or post nothing. Two failure modes to watch on day one:

**It posts a "nothing to report" message.** The skill says not to; if you see one, the prompt has grown logic of its own. Cut it back to the three sentences.

**It posts cards for people already handled.** The surface is the state — the run reads the last 7 days back before posting. If it's duplicating, the read tools aren't in the allow-list, and it's flying blind rather than failing loudly.
