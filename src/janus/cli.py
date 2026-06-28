"""``janus`` CLI — the composition root and action dispatch.

This is the single place concrete adapters are constructed and wired into the
``Cycle`` (the hexagon's outermost ring). Actions: ``dry-run | run | status |
adopt | harvest``. Configuration comes from environment variables so the plugin
command can stay declarative.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .clock import SystemClock
from .cycle import Cycle, CycleConfig, SleepReport
from .domain.gate import GatePolicy
from .domain.split import SplitConfig
from .domain.types import Surface
from .harvest import JsonlTranscriptHarvester
from .mine import CompositeMiner, CorrectionMiner, HeuristicMiner
from .ports import RecurrenceMiner
from .recursion import ReflectionInProgress, ReflectionLock
from .store import (
    BlockTextState,
    ClaudeMdTextState,
    FileAdopter,
    FileProposalStore,
    IgnorePatternStore,
    MemoryTextState,
    SkillTextState,
)
from .worker import ClaudeCliWorker, WorkerError

_SURFACES: dict[str, Surface] = {
    "memory": Surface.MEMORY,
    "skill": Surface.SKILL,
    "claude_md": Surface.CLAUDE_MD,
}


@dataclass(frozen=True, slots=True)
class Settings:
    home: Path
    projects_dir: Path
    target_path: Path
    optimizer_model: str
    target_model: str
    claude_path: str
    min_recurrence: int
    val_fraction: float
    seed: int
    min_net: int
    regression_budget: int
    ignore_patterns: tuple[str, ...] = ()
    mine_corrections: bool = True
    max_corrections: int = 20
    surface: Surface = Surface.MEMORY
    judge_model: str = ""


def _default_target(surface: Surface) -> Path:
    cwd = Path.cwd()
    if surface is Surface.CLAUDE_MD:
        return cwd / "CLAUDE.md"
    if surface is Surface.SKILL:
        # No universal default for skills — set JANUS_TARGET to the SKILL.md.
        return cwd / ".claude" / "skills" / "SKILL.md"
    encoded = str(cwd).replace("/", "-")
    return Path.home() / ".claude" / "projects" / encoded / "memory" / "MEMORY.md"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    home = Path(os.environ.get("JANUS_HOME", str(Path.home() / ".janus")))
    projects = Path(os.environ.get("JANUS_PROJECTS_DIR", str(Path.home() / ".claude" / "projects")))
    surface = _SURFACES.get(os.environ.get("JANUS_SURFACE", "memory").lower(), Surface.MEMORY)
    raw_target = os.environ.get("JANUS_TARGET")
    target = Path(raw_target) if raw_target else _default_target(surface)
    # User-declared noise to ignore (one pattern per line) — e.g. a personal
    # automation's prompt. Keeps user-specific filtering out of the shared tool.
    # Sources: env-var (session override) unioned with the durable ignore store.
    env_patterns = tuple(
        line for line in os.environ.get("JANUS_IGNORE_PATTERNS", "").splitlines() if line.strip()
    )
    store_patterns = IgnorePatternStore(home).list()
    seen: set[str] = set()
    ignore_list: list[str] = []
    for p in (*env_patterns, *store_patterns):
        if p not in seen:
            seen.add(p)
            ignore_list.append(p)
    ignore = tuple(ignore_list)
    return Settings(
        home=home,
        projects_dir=projects,
        target_path=target,
        surface=surface,
        optimizer_model=os.environ.get("JANUS_OPTIMIZER_MODEL", "sonnet"),
        target_model=os.environ.get("JANUS_TARGET_MODEL", "haiku"),
        claude_path=os.environ.get("JANUS_CLAUDE_PATH", "claude"),
        min_recurrence=_env_int("JANUS_MIN_RECURRENCE", 2),
        val_fraction=_env_float("JANUS_VAL_FRACTION", 0.34),
        seed=_env_int("JANUS_SEED", 42),
        min_net=_env_int("JANUS_MIN_NET", 1),
        regression_budget=_env_int("JANUS_REGRESSION_BUDGET", 0),
        ignore_patterns=ignore,
        mine_corrections=_env_bool("JANUS_MINE_CORRECTIONS", True),
        max_corrections=_env_int("JANUS_MAX_CORRECTIONS", 20),
        judge_model=os.environ.get("JANUS_JUDGE_MODEL", ""),
    )


def _build_miner(settings: Settings) -> RecurrenceMiner:
    heuristic = HeuristicMiner(settings.min_recurrence)
    if not settings.mine_corrections:
        return heuristic
    classifier = ClaudeCliWorker(
        role="classifier", model=settings.target_model, claude_path=settings.claude_path
    )
    return CompositeMiner(heuristic, CorrectionMiner(classifier, settings.max_corrections))


def _text_state(settings: Settings) -> BlockTextState:
    if settings.surface is Surface.SKILL:
        return SkillTextState(settings.target_path)
    if settings.surface is Surface.CLAUDE_MD:
        return ClaudeMdTextState(settings.target_path)
    return MemoryTextState(settings.target_path)


def build_cycle(settings: Settings) -> Cycle:
    clock = SystemClock()
    return Cycle(
        harvester=JsonlTranscriptHarvester(
            settings.projects_dir, settings.ignore_patterns, settings.home / "archive"
        ),
        miner=_build_miner(settings),
        target=ClaudeCliWorker(
            role="target",
            model=settings.target_model,
            claude_path=settings.claude_path,
            judge_model=settings.judge_model,
        ),
        optimizer=ClaudeCliWorker(
            role="optimizer",
            model=settings.optimizer_model,
            surface=settings.surface,
            claude_path=settings.claude_path,
        ),
        state=_text_state(settings),
        store=FileProposalStore(settings.home, clock),
        clock=clock,
        lock=ReflectionLock(settings.home / "reflecting.lock"),
    )


def _cycle_config(settings: Settings) -> CycleConfig:
    return CycleConfig(
        target_path=settings.target_path,
        split=SplitConfig(seed=settings.seed, val_fraction=settings.val_fraction),
        policy=GatePolicy(min_net=settings.min_net, regression_budget=settings.regression_budget),
    )


def _print_report(report: SleepReport) -> None:
    print(f"  sessions harvested : {report.sessions}")
    print(f"  recurring tasks    : {report.tasks_mined}  (train {report.train} / val {report.val})")
    print(f"  edits proposed     : {report.edits_proposed}")
    if report.decision in ("rejected", "preview", "staged"):
        print(
            f"  gate               : repairs {report.repairs} "
            f"- regressions {report.regressions} = net {report.net}"
        )
    print(f"  decision           : {report.decision}")
    for edit in report.edits:
        print(f"    [{edit.op.value}] {edit.target[:80]}")
        if edit.rationale:
            print(f"       reason: {edit.rationale[:88]}")
    if report.staging_dir:
        print(f"  staged at          : {report.staging_dir}")
    print(f"  {report.message}")


def _dispatch(action: str, sub_args: tuple[str, ...] = ()) -> int:
    settings = load_settings()

    if action == "ignore":
        store = IgnorePatternStore(settings.home)
        subcmd = sub_args[0] if sub_args else ""
        if subcmd == "list":
            patterns = store.list()
            if patterns:
                for p in patterns:
                    print(p)
            else:
                print("janus: no ignore patterns stored.")
            return 0
        if subcmd == "add":
            if len(sub_args) < 2:
                print("usage: janus ignore add <pattern>")
                return 2
            store.add(sub_args[1])
            print(f"janus: added ignore pattern {sub_args[1]!r}")
            return 0
        if subcmd == "remove":
            if len(sub_args) < 2:
                print("usage: janus ignore remove <pattern>")
                return 2
            store.remove(sub_args[1])
            print(f"janus: removed ignore pattern {sub_args[1]!r}")
            return 0
        print(f"janus: unknown ignore subcommand {subcmd!r}")
        print("usage: janus ignore [list|add <pattern>|remove <pattern>]")
        return 2

    if action == "harvest":
        digests = JsonlTranscriptHarvester(
            settings.projects_dir, settings.ignore_patterns, settings.home / "archive"
        ).harvest()
        candidate_corrections = sum(len(d.corrections) for d in digests)
        tasks = HeuristicMiner(settings.min_recurrence).mine(digests)
        print(f"harvested {len(digests)} session(s); {len(tasks)} recurring task(s):")
        for task in tasks:
            print(f"  - [{len(task.source_sessions)}x] {task.intent[:80]}")
        print(f"+ {candidate_corrections} candidate correction(s) (classified during run).")
        return 0

    if action in ("dry-run", "run"):
        print(f"janus {action}: optimizing {settings.surface.value} @ {settings.target_path}")
        report = build_cycle(settings).run(_cycle_config(settings), stage=(action == "run"))
        _print_report(report)
        return 0

    if action == "status":
        latest = FileProposalStore(settings.home, SystemClock()).latest()
        if latest is None:
            print("janus: no staged proposal.")
            return 0
        print(f"janus: latest staged proposal ({latest.created})")
        print(f"  target : {latest.target_path}")
        print(f"  edits  : {len(latest.edits)}  (net {latest.outcome.effect.net})")
        for edit in latest.edits:
            print(f"    {edit.op.value}: {edit.target[:70]}")
        print(f"  staged : {latest.staging_dir}")
        print("  run `/janus adopt` to apply (backs up first).")
        return 0

    if action == "adopt":
        latest = FileProposalStore(settings.home, SystemClock()).latest()
        if latest is None:
            print("janus: nothing to adopt.")
            return 1
        result = FileAdopter().adopt(latest)
        if result.adopted:
            print(f"janus: adopted -> {result.target_path}")
            if result.backup_path:
                print(f"  backup: {result.backup_path}")
            return 0
        print(f"janus: adopt failed: {result.message}")
        return 1

    print(f"janus: unknown action {action!r}")
    print("usage: janus [dry-run|run|status|adopt|harvest]")
    return 2


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    action = args[0] if args else "status"
    try:
        return _dispatch(action, tuple(args[1:]))
    except ReflectionInProgress as exc:
        print(f"janus: a reflection cycle is already running ({exc}).")
        return 1
    except WorkerError as exc:
        print(f"janus: worker failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
