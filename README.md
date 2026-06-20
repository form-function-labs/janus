# Janus

> Two faces on the doorway of every session — one reads what happened, one shapes what's next.

Janus is a [Claude Code](https://code.claude.com) plugin that treats your agent's
**memory, skills, and `CLAUDE.md` as trainable, bounded markdown text-state** and improves
them through a **gated, validated, staged** loop. It is the discipline of weight-training
applied to plain text — epochs, a validation gate, accept-only-if-it-helps — *without
touching model weights*.

Conceptual ancestor: Microsoft's [SkillOpt](https://github.com/microsoft/SkillOpt). Janus
rebuilds the deployment-time idea Claude-Code-native, with a **label-free local gate** and a
**trust layer**, and points it first at the surface Claude Code's built-in auto-memory
*saves to but never validates*.

## Why

Claude Code's auto-memory decides what's worth saving — but it does not **gate**, **validate**,
or **probe** what it writes. Janus adds exactly that missing layer: a memory/skill edit is
adopted only if it *measurably helps* a recurring task and breaks nothing, it carries
provenance and a falsifiable probe, and **nothing live changes until you adopt**.

## The loop

```
harvest ~/.claude transcripts
  → mine recurring tasks
  → replay offline   (Sonnet optimizer proposes · Haiku target executes)
  → reflect → bounded edit
  → LIMEN gate        (repairs − regressions on held-out tasks; strict improvement)
  → stage proposal
  → (you) adopt       (atomic, backed up, reversible)
```

## Safety triad (non-negotiable)

1. **optimizer ≠ target** — a separate, stronger model proposes edits; it never grades the run it executed.
2. **held-out validation gate (`limen`)** — an edit is kept only if it strictly improves a score on tasks it did not train on.
3. **staged, never auto-applied** — propose → you adopt, with backup + rollback. Synthetic ("dream") tasks can never enter the gate.

## Architecture

Hexagonal. A pure domain core (`limen` gate, split policy, trust records) behind `Protocol`
ports; the only things that touch the world (`claude -p`, the filesystem, transcripts) are
adapters. The pure core is unit-tested directly; the end-to-end loop runs against **real
Haiku** (opt-in marker), with optional **record/replay of real captures** for deterministic
CI — never fabricated model behavior.

```
src/janus/
  domain/   gate (limen) · split policy (typestate) · trust records · threat scan
  ports.py  TranscriptHarvester · RecurrenceMiner · Worker · TextState · ProposalStore · Adopter
  harvest/  streaming JSONL transcript reader
  mine/     recurrence detection
  worker/   claude_cli adapter (isolated, real model)
  store/    memory text-state · proposal staging · atomic adopter
  cycle.py  orchestration   ·   cli.py  /janus entrypoint   ·   recursion.py  anti-recursion lock
```

## Install (Claude Code plugin)

```
/plugin marketplace add ~/CursorAI/janus      # or a git URL once published
/plugin install janus@mythwave
```

## Usage

```
/janus dry-run     # harvest → mine → replay → report; stages nothing
/janus run         # full cycle; stages a reviewed proposal; nothing live changes
/janus status      # nights so far + the latest staged proposal
/janus adopt       # apply the staged proposal (backup first, reversible)
```

## Status

**v0.1 — memory surface first.** Skills and `CLAUDE.md` ride the same engine via additional
`TextState` adapters next. Workers run on an `ANTHROPIC_API_KEY` (Sonnet optimizer · Haiku target).

## License

MIT © 2026 Form F(x) Labs, Inc.
