"""Tests for IgnorePatternStore (FOR-568) — red before green.

Boundary inventory:
  - missing file/dir → list() returns (), add() creates both
  - empty file → ()
  - blank/whitespace-only lines filtered on read
  - add/list/remove round-trip
  - dedupe: repeated add keeps one copy
  - remove non-existent: no-op, no raise
  - CLI dispatch: ignore list/add/remove action
"""

from __future__ import annotations

import os
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


# ---------------------------------------------------------------------------
# CLI dispatch integration tests
# ---------------------------------------------------------------------------


def test_cli_ignore_list_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from janus.cli import _dispatch

    os.environ["JANUS_HOME"] = str(tmp_path)
    try:
        rc = _dispatch("ignore", ("list",))
        assert rc == 0
        out = capsys.readouterr().out
        # Empty store: output may be blank or contain a "no patterns" message.
        assert "PROSPECT:" not in out
    finally:
        del os.environ["JANUS_HOME"]


def test_cli_ignore_add_then_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from janus.cli import _dispatch

    os.environ["JANUS_HOME"] = str(tmp_path)
    try:
        rc_add = _dispatch("ignore", ("add", "PROSPECT:"))
        assert rc_add == 0

        _dispatch("ignore", ("list",))
        out = capsys.readouterr().out
        assert "PROSPECT:" in out
    finally:
        del os.environ["JANUS_HOME"]


def test_cli_ignore_remove(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from janus.cli import _dispatch

    os.environ["JANUS_HOME"] = str(tmp_path)
    try:
        _dispatch("ignore", ("add", "noise-pattern"))
        _dispatch("ignore", ("remove", "noise-pattern"))
        capsys.readouterr()  # flush add + remove confirmation output

        _dispatch("ignore", ("list",))
        out = capsys.readouterr().out
        assert "noise-pattern" not in out
    finally:
        del os.environ["JANUS_HOME"]


def test_cli_ignore_unknown_subcommand_returns_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from janus.cli import _dispatch

    os.environ["JANUS_HOME"] = str(tmp_path)
    try:
        rc = _dispatch("ignore", ("bogus",))
        assert rc != 0
    finally:
        del os.environ["JANUS_HOME"]


def test_load_settings_unions_env_and_store(tmp_path: Path) -> None:
    """ignore_patterns in Settings must be env-var union store, deduped."""
    from janus.cli import load_settings
    from janus.store.ignore_store import IgnorePatternStore

    store = IgnorePatternStore(tmp_path)
    store.add("from-store")

    os.environ["JANUS_HOME"] = str(tmp_path)
    os.environ["JANUS_IGNORE_PATTERNS"] = "from-env"
    try:
        settings = load_settings()
        assert "from-store" in settings.ignore_patterns
        assert "from-env" in settings.ignore_patterns
    finally:
        del os.environ["JANUS_HOME"]
        del os.environ["JANUS_IGNORE_PATTERNS"]


def test_load_settings_dedupes_env_and_store_overlap(tmp_path: Path) -> None:
    """If same pattern is in both env and store, it must appear exactly once."""
    from janus.cli import load_settings
    from janus.store.ignore_store import IgnorePatternStore

    store = IgnorePatternStore(tmp_path)
    store.add("shared-pattern")

    os.environ["JANUS_HOME"] = str(tmp_path)
    os.environ["JANUS_IGNORE_PATTERNS"] = "shared-pattern"
    try:
        settings = load_settings()
        assert settings.ignore_patterns.count("shared-pattern") == 1
    finally:
        del os.environ["JANUS_HOME"]
        del os.environ["JANUS_IGNORE_PATTERNS"]
