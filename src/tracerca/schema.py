from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
SCHEMA_VERSION_ALLOWLIST = frozenset({"1.0"})


class SchemaMismatchError(Exception):
    pass


def _git_head(cwd: str | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"] if cwd is None else ["git", "-C", cwd, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def write_sidecar(
    pkl_path: str | Path,
    *,
    source_mode: str,
    source: str,
    window_start_ts: int,
    window_end_ts: int,
    hyperparams: dict[str, Any],
    trace_count: int,
    row_count: int,
) -> Path:
    pkl_path = Path(pkl_path)
    meta = {
        "schema_version": SCHEMA_VERSION,
        "producer": "tracerca.converter",
        "producer_commit": _git_head(),
        "tracerca_cd_commit": _git_head("vendor/TraceRCA-CD"),
        "feature_names": ["latency", "http_status"],
        "window_start_ts": window_start_ts,
        "window_end_ts": window_end_ts,
        "source_mode": source_mode,
        "source": source,
        "hyperparams": hyperparams,
        "trace_count": trace_count,
        "row_count": row_count,
    }
    meta_path = Path(f"{pkl_path}.meta.json")
    with meta_path.open("w") as f:
        json.dump(meta, f, indent=2)
    return meta_path


def read_sidecar(pkl_path: str | Path) -> dict[str, Any]:
    meta_path = Path(f"{pkl_path}.meta.json")
    with meta_path.open("r") as f:
        meta = json.load(f)
    version = meta.get("schema_version")
    if version not in SCHEMA_VERSION_ALLOWLIST:
        raise SchemaMismatchError(
            f"sidecar schema_version={version!r} not in allowlist {sorted(SCHEMA_VERSION_ALLOWLIST)}"
        )
    return meta
