"""Hand-calculated metric tests for src/analysis.py."""
import json
import math
from pathlib import Path

import analysis


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _fixture(tmp_path):
    eval_path = tmp_path / "eval" / "eval.jsonl"
    gt_path = tmp_path / "eval" / "ground_truth.jsonl"

    # GT1: cpu on ts-order, perfect match -> AC@1=1
    # GT2: memory on ts-auth, target at rank 3 -> AC@1=0, AC@3=1, Avg@5=0.6
    # GT3: network-delay on ts-route, no eval line in window -> unmatched
    ground_truth = [
        {
            "wall_clock_apply_time": 1000.0,
            "target_service": "ts-order-service",
            "fault_type": "cpu",
            "manifest_path": "chaos/cpu_ts-order.yaml",
        },
        {
            "wall_clock_apply_time": 2000.0,
            "target_service": "ts-auth-service",
            "fault_type": "memory",
            "manifest_path": "chaos/memory_ts-auth.yaml",
        },
        {
            "wall_clock_apply_time": 3000.0,
            "target_service": "ts-route-service",
            "fault_type": "network-delay",
            "manifest_path": "chaos/network-delay_ts-route.yaml",
        },
    ]

    eval_lines = [
        {
            "invoke_time": 1010.0,
            "complete_time": 1020.0,
            "service": "ts-order-service",
            "window": "5m",
            "ranked_list": ["ts-order-service", "ts-station-service", "ts-travel-service"],
            "model_id": "model_live@abc",
            "source": "cli",
        },
        {
            "invoke_time": 2030.0,
            "complete_time": 2040.0,
            "service": "ts-auth-service",
            "window": "5m",
            "ranked_list": ["ts-x", "ts-y", "ts-auth-service", "ts-z", "ts-w"],
            "model_id": "model_live@abc",
            "source": "cli",
        },
        # A spurious eval line that does NOT match any GT (wrong service)
        {
            "invoke_time": 9000.0,
            "complete_time": 9010.0,
            "service": "ts-payment-service",
            "window": "5m",
            "ranked_list": [],
            "model_id": "model_live@abc",
            "source": "cli",
        },
    ]
    _write_jsonl(eval_path, eval_lines)
    _write_jsonl(gt_path, ground_truth)
    return eval_path, gt_path


def test_analysis_per_fault_and_overall(tmp_path):
    eval_path, gt_path = _fixture(tmp_path)
    per_fault, overall, slo = analysis.run(
        str(eval_path), str(gt_path), fault_duration_s=180,
    )

    by_fault = {row["fault"]: row for row in per_fault}

    # cpu: perfect match
    cpu = by_fault["cpu"]
    assert cpu["n"] == 1
    assert cpu["AC@1"] == 1.0
    assert cpu["AC@3"] == 1.0
    assert cpu["Avg@5"] == 1.0
    assert cpu["MTTL_p50"] == 20.0
    assert cpu["MTTL_p95"] == 20.0

    # memory: rank-3 target -> AC@1=0, AC@3=1, Avg@5 = (0+0+1+1+1)/5 = 0.6
    mem = by_fault["memory"]
    assert mem["n"] == 1
    assert mem["AC@1"] == 0.0
    assert mem["AC@3"] == 1.0
    assert math.isclose(mem["Avg@5"], 0.6, rel_tol=1e-9)
    assert mem["MTTL_p50"] == 40.0
    assert mem["MTTL_p95"] == 40.0

    # network-delay: unmatched
    nd = by_fault["network-delay"]
    assert nd["n"] == 1
    assert nd["AC@1"] == 0.0
    assert nd["AC@3"] == 0.0
    assert nd["Avg@5"] == 0.0
    assert math.isnan(nd["MTTL_p50"])
    assert math.isnan(nd["MTTL_p95"])

    # overall: n=3, AC@1 = 1/3, AC@3 = 2/3, Avg@5 = (1.0+0.6+0)/3
    assert overall["n"] == 3
    assert math.isclose(overall["AC@1"], 1.0 / 3, rel_tol=1e-9)
    assert math.isclose(overall["AC@3"], 2.0 / 3, rel_tol=1e-9)
    assert math.isclose(overall["Avg@5"], (1.0 + 0.6 + 0.0) / 3, rel_tol=1e-9)
    # MTTLs are [20, 40]; p50 = 30, p95 = 20 + 0.95*20 = 39
    assert math.isclose(overall["MTTL_p50"], 30.0, rel_tol=1e-9)
    assert math.isclose(overall["MTTL_p95"], 39.0, rel_tol=1e-9)


def test_analysis_slo_precision_recall(tmp_path):
    eval_path, gt_path = _fixture(tmp_path)
    _, _, slo = analysis.run(
        str(eval_path), str(gt_path), fault_duration_s=180,
    )
    # 2 eval lines match a GT in window, 1 spurious eval line
    assert slo["total_eval_lines"] == 3
    assert slo["total_faults"] == 3
    assert slo["matched_alerts"] == 2
    assert slo["matched_faults"] == 2
    assert math.isclose(slo["trigger_precision"], 2 / 3, rel_tol=1e-9)
    assert math.isclose(slo["trigger_recall"], 2 / 3, rel_tol=1e-9)


def test_analysis_model_id_filter(tmp_path):
    eval_path, gt_path = _fixture(tmp_path)
    # Filtering by a non-existent model_id zeros all eval lines.
    per_fault, overall, slo = analysis.run(
        str(eval_path), str(gt_path), fault_duration_s=180,
        model_id="model_does_not_exist@xyz",
    )
    assert overall["n"] == 3
    assert overall["AC@1"] == 0.0
    assert overall["AC@3"] == 0.0
    assert overall["Avg@5"] == 0.0
    assert slo["matched_alerts"] == 0
    assert slo["matched_faults"] == 0
    assert slo["total_eval_lines"] == 0


def test_analysis_cli_runs(tmp_path, capsys, monkeypatch):
    eval_path, gt_path = _fixture(tmp_path)
    rc = analysis.main([
        "--eval", str(eval_path),
        "--ground-truth", str(gt_path),
        "--fault-duration-s", "180",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "per-fault-type results" in out
    assert "OVERALL" in out
    assert "cpu" in out and "memory" in out and "network-delay" in out
