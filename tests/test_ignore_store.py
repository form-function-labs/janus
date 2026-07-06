"""Tests for IgnorePatternStore (FOR-568) — red before green.

Boundary inventory:
  - missing file/dir → list() returns (), add() creates both
  - empty file → ()
  - blank/whitespace-only lines filtered on read
  - add/list/remove round-trip
  - dedupe: repeated add keeps one copy
  - remove non-existent: no-op, no raise
  - add onto a file lacking a trailing newline must NOT fuse two patterns
  - add rejects blank / whitespace-only / multi-line patterns (ValueError)
  - writes are atomic (temp-file + os.replace) and leave no .tmp behind
  - CLI dispatch: ignore list/add/remove action; invalid add → non-zero
"""

from __future__ import annotations

from pathlib import Path

import pytest

from janus.store.ignore_store import IgnorePatternStore

# ---------------------------------------------------------------------------
# IgnorePatternStore unit tests
# ---------------------------------------------------------------------------


def test_missing_dir_returns_empty_tuple(tmp_path: Path) -> None:
    home = tmp_path / "no-such-dir"
    store = IgnorePatternStore(home)
    assert store.list() == ()


def test_missing_file_returns_empty_tuple(tmp_path: Path) -> None:
    home = tmp_path / "janus-home"
    home.mkdir()
    store = IgnorePatternStore(home)
    assert store.list() == ()


def test_empty_file_returns_empty_tuple(tmp_path: Path) -> None:
    home = tmp_path / "janus-home"
    home.mkdir()
    (home / "ignore-patterns").write_text("", encoding="utf-8")
    store = IgnorePatternStore(home)
    assert store.list() == ()


def test_blank_whitespace_lines_filtered(tmp_path: Path) -> None:
    home = tmp_path / "janus-home"
    home.mkdir()
    (home / "ignore-patterns").write_text("  \n\nreal-pattern\n   \n", encoding="utf-8")
    store = IgnorePatternStore(home)
    assert store.list() == ("real-pattern",)


def test_add_creates_dir_and_file(tmp_path: Path) -> None:
    home = tmp_path / "no-such-dir"
    store = IgnorePatternStore(home)
    store.add("PROSPECT:")
    assert home.is_dir()
    assert (home / "ignore-patterns").is_file()
    assert store.list() == ("PROSPECT:",)


def test_add_list_remove_round_trip(tmp_path: Path) -> None:
    store = IgnorePatternStore(tmp_path)
    store.add("alpha")
    store.add("beta")
    assert "alpha" in store.list()
    assert "beta" in store.list()

    store.remove("alpha")
    assert "alpha" not in store.list()
    assert "beta" in store.list()


def test_add_dedupes_repeated_pattern(tmp_path: Path) -> None:
    store = IgnorePatternStore(tmp_path)
    store.add("PROSPECT:")
    store.add("PROSPECT:")
    store.add("PROSPECT:")
    result = store.list()
    assert result.count("PROSPECT:") == 1


def test_remove_nonexistent_is_noop(tmp_path: Path) -> None:
    store = IgnorePatternStore(tmp_path)
    store.add("keep-this")
    # Removing something that was never added must not raise or corrupt state.
    store.remove("never-added")
    assert store.list() == ("keep-this",)


def test_remove_from_missing_file_is_noop(tmp_path: Path) -> None:
    home = tmp_path / "empty-home"
    home.mkdir()
    store = IgnorePatternStore(home)
    store.remove("ghost")  # file doesn't exist — no raise
    assert store.list() == ()


def test_list_preserves_insertion_order(tmp_path: Path) -> None:
    store = IgnorePatternStore(tmp_path)
    patterns = ["gamma", "alpha", "beta"]
    for p in patterns:
        store.add(p)
    assert list(store.list()) == patterns


def test_add_onto_file_without_trailing_newline_does_not_fuse(tmp_path: Path) -> None:
    """A hand-edited file whose last line lacks a newline must not fuse on add.

    Regression: the old append-based add() turned "alpha" + add("beta") into the
    single line "alphabeta". The canonical rewrite keeps them distinct.
    """
    (tmp_path / "ignore-patterns").write_text("alpha", encoding="utf-8")  # no trailing \n
    store = IgnorePatternStore(tmp_path)
    store.add("beta")
    assert store.list() == ("alpha", "beta")


def test_add_rejects_blank_pattern(tmp_path: Path) -> None:
    store = IgnorePatternStore(tmp_path)
    with pytest.raises(ValueError):
        store.add("")


def test_add_rejects_whitespace_only_pattern(tmp_path: Path) -> None:
    store = IgnorePatternStore(tmp_path)
    with pytest.raises(ValueError):
        store.add("   ")
    assert store.list() == ()  # nothing persisted


def test_add_rejects_multiline_pattern(tmp_path: Path) -> None:
    store = IgnorePatternStore(tmp_path)
    with pytest.raises(ValueError):
        store.add("foo\nbar")
    with pytest.raises(ValueError):
        store.add("foo\rbar")
    assert store.list() == ()


def test_add_normalizes_preexisting_duplicates(tmp_path: Path) -> None:
    """A hand-edited file with repeats is re-normalized on the next mutation."""
    (tmp_path / "ignore-patterns").write_text("alpha\nalpha\nbeta\n", encoding="utf-8")
    store = IgnorePatternStore(tmp_path)
    store.add("gamma")
    assert store.list() == ("alpha", "beta", "gamma")  # first-seen order, deduped


def test_writes_leave_no_temp_file(tmp_path: Path) -> None:
    """Atomic temp-file + os.replace must not leak its .tmp sidecar."""
    store = IgnorePatternStore(tmp_path)
    store.add("alpha")
    store.remove("alpha")
    # The exact sidecar the atomic write creates must be gone...
    assert not (tmp_path / ".ignore-patterns.janus.tmp").exists()
    # ...and no other temp/dotfile may linger either.
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".")] == []


# ---------------------------------------------------------------------------
# CLI dispatch integration tests
# ---------------------------------------------------------------------------


def test_cli_ignore_list_empty(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from janus.cli import _dispatch

    monkeypatch.setenv("JANUS_HOME", str(tmp_path))
    rc = _dispatch("ignore", ("list",))
    assert rc == 0
    out = capsys.readouterr().out
    # Empty store: output may be blank or contain a "no patterns" message.
    assert "PROSPECT:" not in out


def test_cli_ignore_add_then_list(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from janus.cli import _dispatch

    monkeypatch.setenv("JANUS_HOME", str(tmp_path))
    rc_add = _dispatch("ignore", ("add", "PROSPECT:"))
    assert rc_add == 0

    _dispatch("ignore", ("list",))
    out = capsys.readouterr().out
    assert "PROSPECT:" in out


def test_cli_ignore_remove(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from janus.cli import _dispatch

    monkeypatch.setenv("JANUS_HOME", str(tmp_path))
    _dispatch("ignore", ("add", "noise-pattern"))
    _dispatch("ignore", ("remove", "noise-pattern"))
    capsys.readouterr()  # flush add + remove confirmation output

    _dispatch("ignore", ("list",))
    out = capsys.readouterr().out
    assert "noise-pattern" not in out


def test_cli_ignore_add_blank_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An invalid (blank) pattern must fail cleanly with a non-zero exit, not a traceback."""
    from janus.cli import _dispatch

    monkeypatch.setenv("JANUS_HOME", str(tmp_path))
    rc = _dispatch("ignore", ("add", "   "))
    assert rc != 0
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "invalid ignore pattern" in combined
    assert "Traceback" not in combined  # clean failure, not an unhandled exception
    # Nothing should have been persisted.
    assert IgnorePatternStore(tmp_path).list() == ()


def test_cli_ignore_unknown_subcommand_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from janus.cli import _dispatch

    monkeypatch.setenv("JANUS_HOME", str(tmp_path))
    rc = _dispatch("ignore", ("bogus",))
    assert rc != 0


def test_load_settings_unions_env_and_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ignore_patterns in Settings must be env-var union store, deduped."""
    from janus.cli import load_settings
    from janus.store.ignore_store import IgnorePatternStore

    store = IgnorePatternStore(tmp_path)
    store.add("from-store")

    monkeypatch.setenv("JANUS_HOME", str(tmp_path))
    monkeypatch.setenv("JANUS_IGNORE_PATTERNS", "from-env")
    settings = load_settings()
    assert "from-store" in settings.ignore_patterns
    assert "from-env" in settings.ignore_patterns


def test_load_settings_dedupes_env_and_store_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If same pattern is in both env and store, it must appear exactly once."""
    from janus.cli import load_settings
    from janus.store.ignore_store import IgnorePatternStore

    store = IgnorePatternStore(tmp_path)
    store.add("shared-pattern")

    monkeypatch.setenv("JANUS_HOME", str(tmp_path))
    monkeypatch.setenv("JANUS_IGNORE_PATTERNS", "shared-pattern")
    settings = load_settings()
    assert settings.ignore_patterns.count("shared-pattern") == 1
