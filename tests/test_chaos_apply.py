"""Tests for src/chaos_apply.py."""
import json
import sys
from pathlib import Path

import chaos_apply


def test_chaos_apply_writes_ground_truth_and_invokes_kubectl(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    calls = []

    def _fake_run(cmd, check=False, **kwargs):
        calls.append({"cmd": list(cmd), "check": check})

        class _Res:
            returncode = 0
        return _Res()

    monkeypatch.setattr(chaos_apply.subprocess, "run", _fake_run)

    manifest = "chaos/cpu_ts-order.yaml"
    target = "ts-order-service"
    fault = "cpu"
    monkeypatch.setattr(sys, "argv", ["chaos_apply", manifest, target, fault])

    chaos_apply.main()

    # kubectl was called with the expected argv.
    assert len(calls) == 1
    assert calls[0]["cmd"] == ["kubectl", "apply", "-f", manifest]
    assert calls[0]["check"] is True

    # ground_truth.jsonl gained exactly one well-formed line.
    gt_path = Path("eval/ground_truth.jsonl")
    assert gt_path.exists()
    lines = [ln for ln in gt_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["target_service"] == target
    assert record["fault_type"] == fault
    assert record["manifest_path"] == manifest
    assert isinstance(record["wall_clock_apply_time"], (int, float))
    assert record["wall_clock_apply_time"] > 0


def test_chaos_apply_appends_to_existing_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("eval").mkdir()
    Path("eval/ground_truth.jsonl").write_text(
        json.dumps({"wall_clock_apply_time": 1.0, "target_service": "prev",
                    "fault_type": "x", "manifest_path": "p"}) + "\n"
    )

    monkeypatch.setattr(chaos_apply.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv",
                        ["chaos_apply", "chaos/memory_ts-auth.yaml",
                         "ts-auth-service", "memory"])
    chaos_apply.main()

    lines = [ln for ln in Path("eval/ground_truth.jsonl").read_text().splitlines() if ln.strip()]
    assert len(lines) == 2
    second = json.loads(lines[1])
    assert second["target_service"] == "ts-auth-service"
    assert second["fault_type"] == "memory"
