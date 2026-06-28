# Bespoke "REM-Sleep" Backseat Loop — Design Notes

Working design for a standalone Claude Code plugin: a **gated optimizer over bounded
markdown text-state** (memory → skills → CLAUDE.md), built in a hexagonal /
ports-and-adapters + typestate idiom. Synthesized from implementation-level recon of
SkillOpt-Sleep, skill-forge, dorveille, agent-retro (clones in this dir).

Status: PRE-BUILD. Repo not yet created. Decisions pending (see end).

---

## Core thesis

The loop is NOT "skill forging" — it is a **gated optimizer over bounded markdown
text-state**. Memory, skills, and CLAUDE.md are three ADAPTERS of one `TextState`
port. Memory is the cleanest first instance (already markdown, already bounded, already
has provenance discipline; Claude Code's `auto-dream` is an un-gated precedent we improve
on by adding a validation gate + trust layer).

The safety triad (universal across all 4 references): **optimizer ≠ target**, **held-out
validation gate**, **staged-not-applied**.

The label-free problem (no gold answers locally) is solved by: RHO self-preference
(re-solve N×, rank new-vs-old harness, keep old unless net-preferred) + SkillGen
repairs−regressions (replay recent tasks with/without the edit on identical inputs; adopt
only if newly-fixed minus newly-broken > 0) + a coreset of the user's own recurring tasks.

---

## Port / Adapter map (from recon, with the pure kernel kept, I/O driver rewritten)

DOMAIN (pure, typestate-driven):
- `TextState` — the trainable bounded markdown. Adapters: MemoryStore, SkillFile, ClaudeMd.
  Protected-block merge (SkillOpt memory.py LEARNED block) so optimizer can't clobber
  hand-written prose.
- `Validator`/`Gate` — pure kernel from SkillOpt gate.py. Strict-`>` PLUS explicit
  epsilon/tie policy (float-dust landmine). accept_new_best / accept / reject.
- `SplitPolicy` — seeded stable-hash assignment; `DreamTask` is a typestate that
  STRUCTURALLY cannot carry a val/test split (the "synthetic can't leak into the gate"
  invariant made unrepresentable).
- `TrustRecord` — provenance {session, trigger, web_influence, created} + trust score +
  falsifiable probe {q, a, history}. Typestate: Active | Quarantined.

PORTS (interfaces):
- `TranscriptHarvester`  (agent-retro extract.py)
- `RecurrenceMiner`      (SkillOpt mine.py — semantic, not byte-identity)
- `Optimizer` (reflect→edits) / `Rollout` / `Judge`   (backend reflect/attempt/judge)
- `ProposalStore` / `Adopter`   (SkillOpt staging.py — re-impl atomic)
- `Scheduler` / `SessionEndTrigger`

ADAPTERS:
- `ClaudeHeadlessWorker` (claude -p) — SEE auth conflict below
- `MockWorker` (deterministic, keeps CI offline — port SkillOpt MockBackend)
- `Jsonl TranscriptHarvester` (~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl;
  encoded-cwd = abs path with '/'→'-')
- `FileProposalStore` / atomic `FileAdopter`

---

## Hardenings (each fixes a specific recon landmine)

| Component | Hardening | Landmine fixed |
|---|---|---|
| TranscriptHarvester | streaming `try/except` per line; head/tail 64KB verify; ALL 4 content shapes (str/list-text/mixed/tool_result-only) tested | list-format user text silently dropped → lose friction signal |
| RecurrenceMiner | semantic recurrence not sha256(intent) | one-char change → new id → not "recurring" |
| Gate | strict-`>` + epsilon/tie policy | float dust flips `mixed` score |
| TextState merge | protected-block, strip-outside | orphaned LEARNED marker truncates to EOF |
| Worker | per-role least privilege; mutate via bounded CLI not model Edit; FAIL LOUD on non-zero exit | swallowed exit → empty output → silent wasted night |
| Anti-recursion | env fast-path + filesystem lockfile/PID backstop; typestate Idle→Reflecting→Idle | env var lost across process boundary → infinite spawn (depth-5 concern) |
| Adopter | atomic (temp+os.replace) + rollback + locked registry | non-atomic, single backup, lost-update on concurrent sessions |
| Inject guard | deterministic regex threat-scan before memory→system prompt | prompt-injection / bidi-unicode poisoning via harvested transcript |
| Write-scope | filesystem/port-enforced (workers→staging; deterministic merger checks provenance before promoting) | dorveille's `forged-by` is PROMPT-only for workers = not real isolation |

---

## Build order

1. **Memory-REM first** (lowest risk; memory designed to be rewritten; improves on
   auto-dream by adding the gate+trust+probe). Decide: layer-on vs replace auto-dream.
2. Same engine → SkillFile adapter.
3. Same engine → ClaudeMd adapter.

Cheap-capture gate (skill-forge): SessionEnd hook, deterministic, NO model call, threshold
≈5 tool calls (but PARSE the transcript, don't grep), queue path-only to an inbox.
Expensive reflection deferred to a gated worker run (cron or next-session trigger).

---

## Open decisions (pending user)

- **Repo name** (conventions: internal `Praxis`, public `Mythwave`; theme REM/sleep/dream)
- **License** (ecosystem is MIT — SkillOpt/skill-forge/dorveille; vs source-available like
  doc-lora-training; user + counsel)
- **Location** (recommend a sibling project directory, e.g. `~/code/<name>/`)
- **Worker isolation / auth**: `--bare` (SkillOpt, works on API-key) vs no-`--bare` +
  allowlist + env-sentinel (dorveille, required for subscription login). Hinges on user auth.
- **First surface**: memory (recommended) vs skills
- **auto-dream**: layer-on vs replace for opted-in projects
