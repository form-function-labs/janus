from __future__ import annotations

from janus.worker import ClaudeCliWorker


def test_judge_model_defaults_to_run_model() -> None:
    worker = ClaudeCliWorker(role="target", model="haiku")
    assert worker._judge_model == "haiku"


def test_build_cmd_uses_judge_model_override() -> None:
    worker = ClaudeCliWorker(role="target", model="sonnet", judge_model="opus")
    run_cmd = worker._build_cmd("p", "")  # execution uses the run model
    judge_cmd = worker._build_cmd("p", worker._judge_model)  # judging uses the override
    assert "sonnet" in run_cmd and "opus" not in run_cmd
    assert "opus" in judge_cmd
    assert run_cmd[-2:] == ["--", "p"]  # prompt is passed after `--` (injection-safe)
