# src/analysis.py — post-hoc metrics for the TraceRCA-CD eval harness.
#
# Joins eval/eval.jsonl x eval/ground_truth.jsonl per the proximity rule defined
# in docs/architecture.md §8.3: each ground-truth fault is matched to the first
# eval.jsonl line with complete_time > apply_time, service == target_service,
# within a window of fault_duration_s + 5min.
#
# Computes AC@1, AC@3, Avg@5, MTTL (complete_time - apply_time) per the RCAEval
# paper. Also computes SLO trigger precision and recall.
import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path


DEFAULT_FAULT_DURATION_S = 180
SLO_TRIGGER_WINDOW_S = 5 * 60  # 5 minutes


def _load_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def ac_at_k(ranked, target, k):
    return 1 if target in ranked[:k] else 0


def percentile(values, q):
    if not values:
        return float("nan")
    s = sorted(values)
    if len(s) == 1:
        return float(s[0])
    # linear interpolation between closest ranks
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(s[int(pos)])
    frac = pos - lo
    return float(s[lo] + (s[hi] - s[lo]) * frac)


def join_pairs(eval_lines, ground_truth, fault_duration_s, model_id=None):
    """Apply proximity-match rule. Returns list of dicts with keys:
    apply_time, target_service, fault_type, eval (matched line or None),
    matched (bool).
    """
    window_s = fault_duration_s + SLO_TRIGGER_WINDOW_S
    pairs = []
    # Filter eval lines by model_id if requested.
    if model_id is not None:
        eval_lines = [e for e in eval_lines if e.get("model_id") == model_id]

    for gt in ground_truth:
        apply_time = gt["wall_clock_apply_time"]
        target = gt["target_service"]
        # First eval line with complete_time > apply_time, matching service,
        # within (apply_time, apply_time + window_s].
        best = None
        for e in eval_lines:
            if e.get("service") != target:
                continue
            ct = e.get("complete_time")
            if ct is None or ct <= apply_time:
                continue
            if ct - apply_time > window_s:
                continue
            if best is None or ct < best.get("complete_time", math.inf):
                best = e
        pairs.append({
            "apply_time": apply_time,
            "target_service": target,
            "fault_type": gt["fault_type"],
            "eval": best,
            "matched": best is not None,
        })
    return pairs


def compute_metrics(pairs):
    """Compute per-fault-type and overall metrics."""
    by_fault = defaultdict(list)
    for p in pairs:
        by_fault[p["fault_type"]].append(p)

    def _row(fault_label, ps):
        n = len(ps)
        matched = [p for p in ps if p["matched"]]
        ac1, ac3, avg5 = [], [], []
        mttls = []
        for p in matched:
            ranked = p["eval"].get("ranked_list", []) or []
            target = p["target_service"]
            a1 = ac_at_k(ranked, target, 1)
            a3 = ac_at_k(ranked, target, 3)
            per_k = [ac_at_k(ranked, target, k) for k in range(1, 6)]
            ac1.append(a1)
            ac3.append(a3)
            avg5.append(statistics.mean(per_k))
            mttls.append(p["eval"]["complete_time"] - p["apply_time"])
        # Unmatched contribute 0 to AC@K and Avg@5 (no detection)
        unmatched_n = n - len(matched)
        ac1.extend([0] * unmatched_n)
        ac3.extend([0] * unmatched_n)
        avg5.extend([0.0] * unmatched_n)
        return {
            "fault": fault_label,
            "n": n,
            "AC@1": statistics.mean(ac1) if ac1 else float("nan"),
            "AC@3": statistics.mean(ac3) if ac3 else float("nan"),
            "Avg@5": statistics.mean(avg5) if avg5 else float("nan"),
            "MTTL_p50": percentile(mttls, 0.50),
            "MTTL_p95": percentile(mttls, 0.95),
        }

    per_fault = [_row(f, ps) for f, ps in sorted(by_fault.items())]
    overall = _row("OVERALL", pairs)
    return per_fault, overall


def compute_slo_metrics(eval_lines, ground_truth, model_id=None):
    """SLO trigger precision/recall.

    A ground-truth fault is "matched" if there exists an eval line with
    service == target_service AND apply_time <= invoke_time <= apply_time + 5min.

    precision = matched_alerts / total_eval_lines
    recall    = matched_faults / total_faults
    """
    if model_id is not None:
        eval_lines = [e for e in eval_lines if e.get("model_id") == model_id]

    total_evals = len(eval_lines)
    total_faults = len(ground_truth)

    matched_alerts = 0
    for e in eval_lines:
        inv = e.get("invoke_time")
        svc = e.get("service")
        if inv is None or svc is None:
            continue
        for gt in ground_truth:
            if gt["target_service"] != svc:
                continue
            apply_time = gt["wall_clock_apply_time"]
            if apply_time <= inv <= apply_time + SLO_TRIGGER_WINDOW_S:
                matched_alerts += 1
                break

    matched_faults = 0
    for gt in ground_truth:
        apply_time = gt["wall_clock_apply_time"]
        svc = gt["target_service"]
        for e in eval_lines:
            if e.get("service") != svc:
                continue
            inv = e.get("invoke_time")
            if inv is None:
                continue
            if apply_time <= inv <= apply_time + SLO_TRIGGER_WINDOW_S:
                matched_faults += 1
                break

    precision = matched_alerts / total_evals if total_evals else float("nan")
    recall = matched_faults / total_faults if total_faults else float("nan")
    return {
        "trigger_precision": precision,
        "trigger_recall": recall,
        "matched_alerts": matched_alerts,
        "matched_faults": matched_faults,
        "total_eval_lines": total_evals,
        "total_faults": total_faults,
    }


def _fmt(v, kind="float"):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "  -  "
    if kind == "pct":
        return f"{v:.2f}"
    if kind == "secs":
        return f"{v:.1f}s"
    if kind == "int":
        return f"{int(v)}"
    return f"{v:.2f}"


def format_table(per_fault, overall, slo):
    header = (
        "fault          n   AC@1   AC@3   Avg@5    MTTL_p50   MTTL_p95   "
        "trigger_recall   trigger_precision"
    )
    lines = ["[analysis] per-fault-type results:", header]
    for row in per_fault:
        lines.append(
            f"{row['fault']:<14} {row['n']:<3} "
            f"{_fmt(row['AC@1'])}   {_fmt(row['AC@3'])}   {_fmt(row['Avg@5'])}    "
            f"{_fmt(row['MTTL_p50'], 'secs'):<10} {_fmt(row['MTTL_p95'], 'secs'):<10} "
            f"{_fmt(slo['trigger_recall']):<16} {_fmt(slo['trigger_precision'])}"
        )
    lines.append(
        f"{overall['fault']:<14} {overall['n']:<3} "
        f"{_fmt(overall['AC@1'])}   {_fmt(overall['AC@3'])}   {_fmt(overall['Avg@5'])}    "
        f"{_fmt(overall['MTTL_p50'], 'secs'):<10} {_fmt(overall['MTTL_p95'], 'secs'):<10} "
        f"{_fmt(slo['trigger_recall']):<16} {_fmt(slo['trigger_precision'])}"
    )
    return "\n".join(lines)


def run(eval_path, gt_path, fault_duration_s, model_id=None):
    eval_lines = _load_jsonl(eval_path)
    ground_truth = _load_jsonl(gt_path)
    pairs = join_pairs(eval_lines, ground_truth, fault_duration_s, model_id=model_id)
    per_fault, overall = compute_metrics(pairs)
    slo = compute_slo_metrics(eval_lines, ground_truth, model_id=model_id)
    return per_fault, overall, slo


def _parse_args(argv):
    p = argparse.ArgumentParser(description="TraceRCA-CD post-hoc analysis")
    p.add_argument("--eval", default="eval/eval.jsonl",
                   help="Path to eval.jsonl (default: eval/eval.jsonl)")
    p.add_argument("--ground-truth", default="eval/ground_truth.jsonl",
                   help="Path to ground_truth.jsonl (default: eval/ground_truth.jsonl)")
    p.add_argument("--fault-duration-s", type=int, default=DEFAULT_FAULT_DURATION_S,
                   help="Fault duration in seconds (default: 180)")
    p.add_argument("--model-id", default=None,
                   help="Filter eval lines by model_id (e.g. 'model_live@abc123')")
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    per_fault, overall, slo = run(
        args.eval, args.ground_truth, args.fault_duration_s, model_id=args.model_id,
    )
    print(format_table(per_fault, overall, slo))
    return 0


if __name__ == "__main__":
    sys.exit(main())
