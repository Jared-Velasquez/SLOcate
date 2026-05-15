"""Tests for src/tracerca/__main__.py — the inference CLI surface and core flow."""
from __future__ import annotations

import json
import pickle
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from tracerca import __main__ as inference
from tracerca.__main__ import main as cli_main
from tracerca.schema import write_sidecar


def _option_names(cmd) -> set[str]:
    names: set[str] = set()
    for p in cmd.params:
        for opt in getattr(p, "opts", []):
            names.add(opt)
    return names


def test_inference_click_options_present():
    opts = _option_names(cli_main)
    for required in ("--service", "--window", "--model", "--tempo-url", "--out-dir"):
        assert required in opts, f"missing {required} in inference CLI"
    # Click stores boolean flag pairs under the primary opt; the secondary
    # half (--no-save-input-pkl) is registered on the same param.
    assert "--save-input-pkl" in opts
    save_param = next(p for p in cli_main.params if "--save-input-pkl" in getattr(p, "opts", []))
    assert "--no-save-input-pkl" in getattr(save_param, "secondary_opts", [])


def test_inference_help_runs():
    runner = CliRunner()
    result = runner.invoke(cli_main, ["--help"])
    assert result.exit_code == 0
    for required in ("--service", "--window", "--model", "--tempo-url", "--out-dir"):
        assert required in result.output


def _build_fake_model(tmp_path: Path) -> Path:
    """Build a model pkl + valid sidecar so load_model succeeds."""
    model_path = tmp_path / "model_live.pkl"
    with model_path.open("wb") as f:
        pickle.dump({"RF-Trace": None, "MLP-Trace": None}, f)
    write_sidecar(
        model_path,
        source_mode="tempo-url",
        source="http://localhost:3200",
        window_start_ts=0,
        window_end_ts=0,
        hyperparams={},
        trace_count=0,
        row_count=0,
    )
    return model_path


class _FakeTempoClient:
    """Replaces TempoClient as used in __main__.fetch_tempo_traces."""

    _traces: list = []

    def __init__(self, *_args, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def fetch_traces(self, *_args, **_kwargs):
        for t in self._traces:
            yield t


def test_inference_empty_window_exits_3(tmp_path, monkeypatch):
    model_path = _build_fake_model(tmp_path)
    out_dir = tmp_path / "eval"

    _FakeTempoClient._traces = []
    monkeypatch.setattr(inference, "TempoClient", _FakeTempoClient)

    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        [
            "--service", "ts-order-service",
            "--window", "5m",
            "--model", str(model_path),
            "--tempo-url", "http://localhost:3200",
            "--out-dir", str(out_dir),
        ],
    )
    assert result.exit_code == 3, result.output
    assert "no spans for service=ts-order-service" in (result.output + result.stderr_bytes.decode() if hasattr(result, "stderr_bytes") else result.output)

    # Empty-window JSONL line should still be appended.
    eval_jsonl = out_dir / "eval.jsonl"
    assert eval_jsonl.exists()
    lines = eval_jsonl.read_text().strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["service"] == "ts-order-service"
    assert obj["ranked_list"] == []
    assert obj["note"] == "empty_window"
    assert obj["source"] == "cli"


def _synthetic_trace() -> dict:
    """One OTLPTrace with a parent→child span in the same service."""
    return {
        "trace_id": "abc123",
        "spans": [
            {
                "trace_id": "abc123",
                "span_id": "p1",
                "parent_span_id": "",
                "service_name": "ts-order-service",
                "start_time_unix_nano": 1_000_000_000,
                "end_time_unix_nano": 2_000_000_000,
                "attributes": {"http.status_code": 200},
            },
            {
                "trace_id": "abc123",
                "span_id": "c1",
                "parent_span_id": "p1",
                "service_name": "ts-station-service",
                "start_time_unix_nano": 1_100_000_000,
                "end_time_unix_nano": 1_500_000_000,
                "attributes": {"http.status_code": 200},
            },
        ],
    }


def test_inference_happy_path_writes_jsonl(tmp_path, monkeypatch):
    model_path = _build_fake_model(tmp_path)
    out_dir = tmp_path / "eval"

    _FakeTempoClient._traces = [_synthetic_trace()]
    monkeypatch.setattr(inference, "TempoClient", _FakeTempoClient)

    # Mock the three vendored-script subprocess calls. The third one
    # (localization) is expected to drop a pkl at --output-file containing
    # {"Ours-noise=0": [...]}, which parse_ranked_output then reads.
    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        # Find the script name in the command for routing.
        script = ""
        for token in cmd:
            if isinstance(token, str) and token.endswith(".py"):
                script = Path(token).name
                break

        if script == "run_localization_association_rule_mining_20210516.py":
            # Locate --output-file value and drop a ranked-list pkl there.
            try:
                idx = cmd.index("--output-file")
                out = Path(cmd[idx + 1])
            except (ValueError, IndexError):
                out = None
            if out is not None:
                with out.open("wb") as f:
                    pickle.dump(
                        {
                            "Ours-noise=0": [
                                "ts-order-service",
                                "ts-station-service",
                                "ts-travel-service",
                            ]
                        },
                        f,
                    )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        # For invo encoding + anomaly detection, write an empty output pkl
        # at the path passed via -o (so any downstream existence checks pass).
        try:
            o_idx = cmd.index("-o")
            o_path = Path(cmd[o_idx + 1])
            o_path.parent.mkdir(parents=True, exist_ok=True)
            with o_path.open("wb") as f:
                pickle.dump({}, f)
        except (ValueError, IndexError):
            pass
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(inference.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        [
            "--service", "ts-order-service",
            "--window", "5m",
            "--model", str(model_path),
            "--tempo-url", "http://localhost:3200",
            "--out-dir", str(out_dir),
        ],
    )
    assert result.exit_code == 0, f"exit={result.exit_code}, output={result.output}, exc={result.exception!r}"

    eval_jsonl = out_dir / "eval.jsonl"
    assert eval_jsonl.exists()
    lines = eval_jsonl.read_text().strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    # Required keys per §3.5 step 11.
    for key in (
        "invoke_time",
        "complete_time",
        "service",
        "window",
        "input_pkl_path",
        "ranked_list",
        "model_id",
        "model_path",
        "source",
    ):
        assert key in obj, f"missing key {key} in JSONL line"
    assert obj["source"] == "cli"
    assert obj["service"] == "ts-order-service"
    assert obj["window"] == "5m"
    assert obj["model_path"] == str(model_path)
    # model_id = "<stem>@<sha256[:8]>"
    assert obj["model_id"].startswith("model_live@")
    assert len(obj["model_id"].split("@", 1)[1]) == 8
    assert obj["ranked_list"] == [
        "ts-order-service",
        "ts-station-service",
        "ts-travel-service",
    ]
    assert obj["complete_time"] >= obj["invoke_time"]
    # save-input-pkl is on by default → input_pkl_path should be set.
    assert obj["input_pkl_path"] is not None
    assert Path(obj["input_pkl_path"]).exists()
