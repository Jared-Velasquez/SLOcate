# src/chaos_apply.py
import json, subprocess, sys, time
from pathlib import Path

def main():
    manifest, target, fault = sys.argv[1], sys.argv[2], sys.argv[3]
    Path("eval").mkdir(exist_ok=True)
    with open("eval/ground_truth.jsonl", "a") as f:
        f.write(json.dumps({
            "wall_clock_apply_time": time.time(),
            "target_service": target,
            "fault_type": fault,
            "manifest_path": manifest,
        }) + "\n")
    subprocess.run(["kubectl", "apply", "-f", manifest], check=True)

if __name__ == "__main__":
    main()
