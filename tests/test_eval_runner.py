"""Tests for src/eval_runner.py --dry-run mode."""
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import eval_runner


def _write_spec(path, services, faults, replicates):
    fault_lines = "\n".join(
        f"  - {{ type: {f['type']}, template: '{f['template']}' }}" for f in faults
    )
    svc_lines = "\n".join(f"  - {s}" for s in services)
    path.write_text(
        "fault_duration_s: 5\n"
        "recovery_s: 7\n"
        f"replicates_per_combo: {replicates}\n"
        "services:\n"
        f"{svc_lines}\n"
        "faults:\n"
        f"{fault_lines}\n"
    )


def test_eval_runner_dry_run_logs_actions(tmp_path):
    spec = tmp_path / "exp.yaml"
    _write_spec(
        spec,
        services=["ts-order-service", "ts-auth-service"],
        faults=[
            {"type": "cpu", "template": "chaos/cpu_{service}.yaml"},
            {"type": "memory", "template": "chaos/memory_{service}.yaml"},
        ],
        replicates=2,
    )

    buf = io.StringIO()
    with redirect_stdout(buf):
        eval_runner.main(str(spec), dry_run=True)
    out = buf.getvalue()

    # 2 services x 2 faults x 2 reps = 8 combos
    assert "[runner] 8 runs scheduled" in out
    assert "DRY-RUN: no subprocesses will be invoked" in out

    lines = [ln for ln in out.splitlines() if ln.strip()]

    apply_lines = [ln for ln in lines if ln.startswith("[runner] apply ")]
    assert len(apply_lines) == 8

    would_invoke_chaos = [ln for ln in lines if "DRY-RUN would invoke" in ln and "chaos_apply" in ln]
    would_invoke_kubectl = [ln for ln in lines if "DRY-RUN would invoke" in ln and "kubectl" in ln]
    assert len(would_invoke_chaos) == 8
    assert len(would_invoke_kubectl) == 8

    fault_sleeps = [ln for ln in lines if "DRY-RUN would sleep 5s" in ln]
    recovery_sleeps = [ln for ln in lines if "DRY-RUN would sleep 7s" in ln]
    assert len(fault_sleeps) == 8
    assert len(recovery_sleeps) == 8

    # Ordering: for each combo, apply -> chaos_apply invoke -> fault sleep ->
    # kubectl delete invoke -> recovery sleep.
    # Verify by extracting the action stream and checking the pattern repeats.
    action_seq = []
    for ln in lines:
        if ln.startswith("[runner] apply "):
            action_seq.append("APPLY")
        elif "DRY-RUN would invoke" in ln and "chaos_apply" in ln:
            action_seq.append("CHAOS")
        elif "DRY-RUN would sleep 5s" in ln:
            action_seq.append("SLEEP_FAULT")
        elif "DRY-RUN would invoke" in ln and "kubectl" in ln:
            action_seq.append("KDELETE")
        elif "DRY-RUN would sleep 7s" in ln:
            action_seq.append("SLEEP_RECOVERY")

    expected_per_combo = ["APPLY", "CHAOS", "SLEEP_FAULT", "KDELETE", "SLEEP_RECOVERY"]
    assert len(action_seq) == 8 * len(expected_per_combo)
    for i in range(8):
        chunk = action_seq[i * 5:(i + 1) * 5]
        assert chunk == expected_per_combo, f"combo {i} sequence mismatch: {chunk}"

    assert "[runner] done" in out


def test_eval_runner_dry_run_does_not_invoke_subprocess(tmp_path, monkeypatch):
    spec = tmp_path / "exp.yaml"
    _write_spec(
        spec,
        services=["ts-order-service"],
        faults=[{"type": "cpu", "template": "chaos/cpu_{service}.yaml"}],
        replicates=1,
    )

    def _explode(*a, **k):
        raise AssertionError("subprocess.run must not be called in --dry-run mode")

    def _explode_sleep(*a, **k):
        raise AssertionError("time.sleep must not be called in --dry-run mode")

    monkeypatch.setattr(eval_runner.subprocess, "run", _explode)
    monkeypatch.setattr(eval_runner.time, "sleep", _explode_sleep)

    buf = io.StringIO()
    with redirect_stdout(buf):
        eval_runner.main(str(spec), dry_run=True)
    assert "[runner] done" in buf.getvalue()
