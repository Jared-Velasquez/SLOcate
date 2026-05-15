# src/eval_runner.py — ~120 lines, serial loop, no magic
import argparse
import itertools
import subprocess
import sys
import time
from pathlib import Path

import yaml


def main(spec_path, dry_run=False):
    spec = yaml.safe_load(open(spec_path))
    combos = list(itertools.product(
        spec["services"],
        spec["faults"],
        range(spec["replicates_per_combo"]),
    ))
    print(f"[runner] {len(combos)} runs scheduled")
    if dry_run:
        print("[runner] DRY-RUN: no subprocesses will be invoked")

    for service, fault, rep in combos:
        manifest = fault["template"].format(service=service)
        if not Path(manifest).exists() and not dry_run:
            print(f"[runner] SKIP {manifest} (not found)")
            continue
        print(f"[runner] apply {service} {fault['type']} rep={rep}")
        apply_cmd = [
            sys.executable, "-m", "src.chaos_apply",
            manifest, service, fault["type"],
        ]
        if dry_run:
            print(f"[runner] DRY-RUN would invoke: {apply_cmd}")
        else:
            subprocess.run(apply_cmd, check=True)

        print(f"[runner] fault sleep {spec['fault_duration_s']}s")
        if dry_run:
            print(f"[runner] DRY-RUN would sleep {spec['fault_duration_s']}s")
        else:
            time.sleep(spec["fault_duration_s"])

        # Chaos Mesh experiments have spec.duration; we delete to guarantee cleanup
        delete_cmd = ["kubectl", "delete", "-f", manifest, "--ignore-not-found"]
        if dry_run:
            print(f"[runner] DRY-RUN would invoke: {delete_cmd}")
        else:
            subprocess.run(delete_cmd, check=False)

        print(f"[runner] recovery sleep {spec['recovery_s']}s")
        if dry_run:
            print(f"[runner] DRY-RUN would sleep {spec['recovery_s']}s")
        else:
            time.sleep(spec["recovery_s"])

    print("[runner] done")


def _parse_args(argv):
    p = argparse.ArgumentParser(description="TraceRCA-CD eval runner")
    p.add_argument("spec", help="Path to experiments YAML spec")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Log every kubectl/sleep action without invoking subprocess or sleeping",
    )
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    main(args.spec, dry_run=args.dry_run)
