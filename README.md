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

The richest signal Janus learns from is the moment you *corrected* the agent. A `(request,
correction)` pair is a free, gradeable lesson: "given this ask, the output must now satisfy
*this* criterion." Janus extracts those pairs from your own transcripts and turns them into
held-out tasks the gate can score against.

## The loop

```
harvest   live ~/.claude transcripts + Janus's durable archive
  → mine   recurring tasks  +  confirmed corrections (Haiku classifier → rubric)
  → split  seeded, held-out (a synthetic "dream" can never enter the gate)
  → reflect   Sonnet optimizer proposes bounded edits from scored rollouts
  → render    edits land only inside a protected LEARNED block
  → LIMEN gate   replay held-out tasks with/without the edit on identical input;
                 keep only if repairs − regressions clears the bar (do-no-harm)
  → stage     proposal written to ~/.janus; nothing live changes
  → (you) adopt   atomic, backed up, reversible
```

The target executes; a *separate, stronger* optimizer proposes. The optimizer never grades
the run it produced.

## Safety triad (non-negotiable)

1. **optimizer ≠ target** — a separate, stronger model proposes edits; it never grades the run it executed. Enforced by wiring two distinct workers (`reflect` vs `run`/`_judge`).
2. **held-out validation gate (`limen`)** — an edit is kept only if it strictly improves a score on tasks it did not train on, **and breaks nothing** (`repairs − regressions ≥ min_net`, hard regressions ≤ `regression_budget`).
3. **staged, never auto-applied** — propose → you adopt, with backup + rollback. Synthetic ("dream") tasks are a typestate with no `split` field, so they *structurally cannot* enter the gate.

## Highlights

- **Correction-driven optimization.** The harvester extracts candidate `(request, correction)`
  pairs with a cheap regex pre-filter (a redirect at the start of a user turn that follows an
  assistant turn). The `CorrectionMiner` then asks a Haiku classifier
  (`ClaudeCliWorker.classify_correction`) to confirm each candidate is a *genuine* agent-correction
  and to extract a one-line gradeable **rubric**. Confirmed corrections become `RealTask`s
  (`intent` = the request, `rubric` = the criterion the output must satisfy); the target's judge
  grades against that rubric. `CompositeMiner` runs recurrence + corrections together behind one
  port. Validated on real transcripts: of 41 regex candidates, ~16 were confirmed as genuine lessons.
- **Three surfaces, one engine.** A single `BlockTextState` is parameterized by `Surface`;
  `MemoryTextState` / `SkillTextState` / `ClaudeMdTextState` are thin subclasses. The surface is
  selected via `JANUS_SURFACE` (`memory` | `skill` | `claude_md`). The *same* gate and loop target
  all three; edits only apply to the state matching their surface.
- **Corpus durability.** The SessionEnd capture hook gzip-archives qualifying transcripts to
  `~/.janus/archive/`, and the harvester reads that archive as a durable *second root* (deduped by
  `session_id`, live wins). This matters because Claude Code prunes transcripts: in one real case the
  user had 852 lifetime sessions but only ~59 retained on disk — the archive is the corpus that
  outlives pruning.

## Architecture

Hexagonal. A pure domain core (`limen` gate, split policy, trust records, threat scan) behind
`Protocol` ports; the only things that touch the world (`claude -p`, the filesystem, transcripts)
are adapters. The pure core is unit-tested directly; the end-to-end loop runs against **real
Haiku**, never fabricated model behavior.

```
src/janus/
  domain/      gate (limen) · split policy (typestate) · trust records · threat scan · proposal · types
  ports.py     TranscriptHarvester · RecurrenceMiner · CorrectionClassifier
               · TargetWorker · OptimizerWorker · TextState · ProposalStore · Adopter
  harvest/     streaming JSONL reader (live + gzipped archive, deduped)
  mine/        recurrence (HeuristicMiner) · corrections (CorrectionMiner) · CompositeMiner
  worker/      claude_cli adapter — one worker, three roles (target · optimizer · classifier)
  store/       BlockTextState (3 surfaces) · proposal staging · atomic adopter
  recursion.py anti-recursion lock (env fast-path + PID lockfile backstop)
  clock.py     SystemClock
  cycle.py     orchestration   ·   cli.py  janus CLI entrypoint
hooks/         session_end_capture.py  (cheap capture + archive; no model call)
```

One worker class (`ClaudeCliWorker`) plays three roles — **target** (`run` + internal judge),
**optimizer** (`reflect` → bounded edits), and **correction classifier**
(`classify_correction`) — wired as separate instances so the optimizer ≠ target line holds.

## Install (Claude Code plugin)

**Prerequisites:** [Claude Code](https://code.claude.com), [`uv`](https://docs.astral.sh/uv/) (`brew install uv`),
and `ANTHROPIC_API_KEY` in your environment (only needed for `run`/`dry-run`, which call the model).

```
/plugin marketplace add form-function-labs/janus   # the GitHub repo is also the marketplace
/plugin install janus@mythwave
/reload-plugins
```

The command is namespaced by plugin → invoke it as `/janus:janus` (see Usage). No `uv sync` step is
needed — `uv run --project "${CLAUDE_PLUGIN_ROOT}"` builds the venv from the committed `uv.lock` on first call.

For local development you can also add the marketplace from a local clone: `/plugin marketplace add /path/to/janus`.

## Usage

The model-driving actions need an `ANTHROPIC_API_KEY` (the optimizer and target both call
`claude -p`). Run them with whatever injects that key — e.g. Doppler:

```
doppler run -- uv run janus dry-run     # harvest → mine → replay → report; stages nothing
doppler run -- uv run janus run         # full cycle; stages a reviewed proposal; nothing live changes
uv run janus status                     # latest staged proposal (no model call)
uv run janus adopt                      # apply the staged proposal (backup first, reversible)
doppler run -- uv run janus harvest     # harvest + show recurring tasks and candidate corrections
```

Inside Claude Code these are exposed as `/janus:janus dry-run | run | status | adopt | harvest`
(the command is namespaced `<plugin>:<command>`).

## Configuration

Configuration is environment variables (session-scoped), so the plugin command stays declarative.
Read from `load_settings` (`cli.py`) and the capture hook. The one durable exception is the ignore
store: `janus ignore add` persists patterns to `$JANUS_HOME/ignore-patterns` across sessions
(see [Durable ignore patterns](#durable-ignore-patterns) below).

### Cycle & surface

| Variable | Default | Meaning |
|---|---|---|
| `JANUS_SURFACE` | `memory` | Which surface to optimize: `memory` \| `skill` \| `claude_md`. |
| `JANUS_TARGET` | derived from surface + cwd | Path to the markdown file being optimized. Memory defaults to `~/.claude/projects/<encoded-cwd>/memory/MEMORY.md`; `claude_md` to `./CLAUDE.md`; **skill has no universal default — set this explicitly**. |
| `JANUS_HOME` | `~/.janus` | Janus's state dir: staged proposals, the gzip archive, the inbox, the lockfile, the `OFF` kill switch. |
| `JANUS_PROJECTS_DIR` | `~/.claude/projects` | Root of live Claude Code transcripts. |
| `JANUS_STALE_STAGING_DAYS` | `7` | `run` warns loudly (age + target + adopt hint) if a staged proposal is older than this — `run` neither supersedes nor discards existing staging on its own. |

### Models & worker

| Variable | Default | Meaning |
|---|---|---|
| `JANUS_OPTIMIZER_MODEL` | `sonnet` | The (stronger) model that proposes edits. |
| `JANUS_TARGET_MODEL` | `haiku` | The model that executes tasks, judges, and classifies corrections. |
| `JANUS_CLAUDE_PATH` | `claude` | Path to the `claude` binary the worker shells out to. |
| `ANTHROPIC_API_KEY` | — | **Required** for `dry-run`/`run`. Workers always run `--bare`, which bypasses the OAuth keychain session `claude /login` sets up — an interactive login never reaches them. `run`/`dry-run` preflight this and fail fast with an actionable message if it's missing. |
| `JANUS_TIMEOUT` | `600` | Per-call subprocess timeout (seconds) for the **target/rollout** worker — it replays real harvested prompts, which routinely exceed a tight timeout. A timed-out rollout is scored as a failure and reported, not a run-aborting error. The classifier role keeps the tighter 120s default. |

### Mining

| Variable | Default | Meaning |
|---|---|---|
| `JANUS_MIN_RECURRENCE` | `2` | Distinct sessions a normalized intent must appear in to count as recurring. |
| `JANUS_MINE_CORRECTIONS` | on | Mine `(request, correction)` pairs in addition to recurrence. Off → recurrence only. |
| `JANUS_MAX_CORRECTIONS` | `20` | Budget on classifier calls per run (cost control). |
| `JANUS_IGNORE_PATTERNS` | — | Session-scoped noise to drop, **one substring pattern per line**. For durable patterns, use `janus ignore add <pattern>` instead (persisted to `$JANUS_HOME/ignore-patterns`). Both sources are merged at startup. |

#### Durable ignore patterns

`JANUS_IGNORE_PATTERNS` is ephemeral (env-var, gone after the session). To persist patterns across sessions, use the `ignore` subcommand:

```sh
janus ignore add "PROSPECT:"       # add a noise pattern
janus ignore list                  # show all stored patterns
janus ignore remove "PROSPECT:"    # remove a pattern
```

Patterns are stored in `$JANUS_HOME/ignore-patterns` (one substring per line). At startup, stored patterns are unioned with any `JANUS_IGNORE_PATTERNS` env-var value; duplicates are dropped.

### Split & gate

| Variable | Default | Meaning |
|---|---|---|
| `JANUS_VAL_FRACTION` | `0.34` | Fraction of mined tasks held out for the gate. |
| `JANUS_SEED` | `42` | Seed for deterministic, stable split assignment. |
| `JANUS_MIN_NET` | `1` | Minimum `repairs − regressions` required to accept. Must be ≥ 1 — a gate that accepts net 0 is not a gate. |
| `JANUS_REGRESSION_BUDGET` | `0` | Max tolerated hard regressions (do-no-harm; `0` = none). |

### Capture hook

| Variable | Default | Meaning |
|---|---|---|
| `JANUS_MIN_TOOL_CALLS` | `5` | A finished session must have made at least this many tool calls to be archived + queued for review. |

### Safety switches

- **Kill switch** — create `~/.janus/OFF` (i.e. `$JANUS_HOME/OFF`) and the SessionEnd hook no-ops immediately: no archive, no queueing.
- **Anti-recursion guard** — `JANUS_REVIEWING=1` is set on every worker the loop spawns, so a worker's own SessionEnd hook no-ops and the loop can never recurse into itself. A PID lockfile (`$JANUS_HOME/reflecting.lock`) is the filesystem backstop if the env var is ever lost across a process boundary; a stale lock (dead PID) is reclaimed.

## Status

**Working & proven.**

- The full pipeline runs end-to-end on real sessions: harvest (live + archive) → mine (recurrence + corrections) → split → reflect → gate → stage a reviewed proposal. Nothing live changes until you `adopt`.
- The safety triad holds in practice: optimizer ≠ target, held-out gate, staged-not-applied.
- The correction classifier is validated on real transcripts (~16 of 41 regex candidates confirmed as genuine lessons).
- The optimizer's **reflect prompt is v2**: the editable `DOCUMENT` and the read-only `EVIDENCE` are now hard-fenced, and confirmed-correction *lessons* are threaded directly into the optimizer (via `RolloutResult.lesson`). On real transcripts this reliably yields clean, general, lesson-shaped rules — e.g. *"Always review the complete diff before approving or endorsing a decision"* — instead of the v1 garbage that targeted evidence fragments (proven: 0 malformed edits across repeated reflect trials).
- **66 tests green** (`ruff` + `mypy --strict`). Repo: [github.com/form-function-labs/janus](https://github.com/form-function-labs/janus).

**Honest v1 limits** (the edit *quality* frontier is next, not the *plumbing*):

- The **held-out gate can stay red on a small, diverse correction corpus** — and when it does, it is *correctly* withholding, not failing. Two measured mechanisms (instrumented on real runs): **(a)** the seeded hash split scatters one-shot corrections so `train` and `val` land on *disjoint topics* (e.g. train teaches diff-review while val tests SSH-keychain export) — a topically-unrelated edit can't repair a held-out task, so candidate == baseline. The structural fix is **topic-coherent splitting**: cluster corrections by topic and split *within* each cluster, preserving the held-out property. **(b)** the gate scores repairs/regressions as pass/fail *flips*, so a real but sub-threshold behavioural lift (measured 0.25 → 0.45, never crossing the 0.5 pass bar) is invisible to it; a **continuous `mean_delta`-based repair signal** (still held-out, still do-no-harm) could surface it. Neither fix relaxes the gate — testing an edit against *its own source correction* would remove the held-out property and is explicitly off-limits.
- The **judge + small validation sets can pass marginal edits** — a v1 judge over a handful of held-out tasks is a coarse gate. **Judge hardening** is the follow-on.
- **Auto-dream layering** (synthetic task augmentation that feeds only `train`) is design-noted (`DreamTask` exists as the train-only typestate) but **not yet wired** into the loop.
- **Recurrence is per-project** — a task only counts as recurring within one project's sessions; cross-project recurrence is not yet detected.

## License

MIT © 2026 Form F(x) Labs, Inc.
</content>
</invoke>
