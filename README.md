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
/plugin install deck-graphics
/plugin install always-worktree
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

### `deck-graphics`

A talk needs thirty small graphics: a dozen vendor logos, a handful of icons in the house style, three screenshots that show an app without showing a customer. This fills them from a manifest. Logos come through a chain that degrades instead of failing (Brandfetch, then SimpleIcons, then Google's favicon service, or a URL or file you pin when the chain gets a mark wrong). Props come through an image model with your existing illustrations passed as references, so the new ones match. Mocks are HTML you control, rendered through headless Chrome. Every file gets a sidecar saying which tier or which model, prompt and seed produced it.

The scripts are the cheap part. `/deck-graphics:fill` then looks at every PNG and judges it: does it read at slide size, does it match the references, is there text baked in, is the logo on a transparent ground, is it the right mark. That look is what makes the result trustworthy.

Assets and sidecars only. The deck builder is yours, because that's where the house style lives. Needs an OpenRouter key for props, a free Brandfetch client ID for real logos, and Chrome.

[Full documentation →](./deck-graphics/)

### `always-worktree`

Keeps an agent off your default branch. A session opens in the main checkout on `main`, the first edit lands there, and by the time anyone notices there are six commits on `main` that should have been a PR. Or two sessions open in the same checkout and edit the same files.

On the default branch, Write and Edit are refused with a message naming the fix: move to a worktree. Bash commands that look like writes (a redirect, a heredoc, `sed -i`, `git commit`) are refused too, and reads pass. Each prompt also gets a line telling the agent where it is, so it usually moves before it tries to edit.

When you do mean to work on `main`, `/always-worktree:main-ok` allows it for four hours and then expires. It runs when you ask for it, never because the guard fired. Needs Python 3.

[Full documentation →](./always-worktree/)

### `slop-check`

Flags AI writing tells in outward-facing prose before it's sent or published. Warns, never blocks, because a gate that fires on a judgement call gets bypassed, and rewriting prose until a regex goes quiet produces text that passes and still reads like a chatbot.

Lives in [its own repo](https://github.com/le0li0n/slop-check) with its 382-document human corpus and its attribution chain. Listed here so one marketplace covers the set.

## Why these five

They're the parts of one person's stack that turned out to be portable. The context layer underneath them — a git repo per company holding positioning, clients, deals and call transcripts, which every agent reads before acting — is the part that matters most and the part nobody can hand you.

These are what sits on top of it.

## Licence

MIT for `reply-queue`, `automerge`, `deck-graphics` and `always-worktree`. `slop-check` carries its own chain — CC BY-SA 4.0, built on [blader/humanizer](https://github.com/blader/humanizer) (MIT) and Wikipedia's [Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing).
