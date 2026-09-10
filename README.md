# GTM Engineer Tools

Claude Code plugins for people who run go-to-market on a stack they built themselves.

These were extracted from a working setup rather than written as examples. The mechanics in them are the cheap part; the rules that came out of things going wrong are the reason they're worth installing.

## Install

```
/plugin marketplace add le0li0n/gtm-engineer-tools
```

Then install what you want:

```
/plugin install reply-queue
/plugin install automerge
/plugin install slop-check
```

## What's here

### `reply-queue`

One pass over every outbound campaign you have in flight, ending in a queue of cards — one per person waiting on you, each with the reply already drafted.

**Drafts everywhere it can. Sends nowhere.** Mail replies are written into your drafts folder, on the thread, with the right recipient and subject, waiting for one click. Channels with no draft object come back paste-ready. The scheduled version's tool allow-list is asymmetric on purpose: draft creation is in, send is out on every channel. "Never sends" is a fact about what it can do, not a rule it's been asked to follow.

Run `/reply-queue-setup` in your repo. It interviews you, writes the registry, resolves your campaign ids against whatever sources are connected, and prints the routine prompt for you to schedule yourself.

[Full documentation →](./reply-queue/)

### `automerge`

For repos where PRs pile up because there's nobody to review them — which is most solo and small-team repos where an agent opens the PRs.

Installs a scheduled workflow that squash-merges any open PR at least 15 minutes old with no conflict, no failing check, no `hold` label, and not a draft. Deliberately not GitHub's own auto-merge, which needs branch protection that private repos on the free plan don't get.

One script, three idempotent steps, and one PR you merge by hand at the end — GitHub only runs scheduled workflows from the default branch, so it can't merge itself in.

### `slop-check`

Flags AI writing tells in outward-facing prose before it's sent or published. Warns, never blocks, because a gate that fires on a judgement call gets bypassed, and rewriting prose until a regex goes quiet produces text that passes and still reads like a chatbot.

Lives in [its own repo](https://github.com/le0li0n/slop-check) with its 382-document human corpus and its attribution chain. Listed here so one marketplace covers the set.

## Why these three

They're the parts of one person's stack that turned out to be portable. The context layer underneath them — a git repo per company holding positioning, clients, deals and call transcripts, which every agent reads before acting — is the part that matters most and the part nobody can hand you.

These are what sits on top of it.

## Licence

MIT for `reply-queue` and `automerge`. `slop-check` carries its own chain — CC BY-SA 4.0, built on [blader/humanizer](https://github.com/blader/humanizer) (MIT) and Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing).
