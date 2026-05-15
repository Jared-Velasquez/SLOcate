import json
from pathlib import Path

import pytest

from tracerca.schema import SchemaMismatchError, read_sidecar, write_sidecar


def test_roundtrip(tmp_path):
    pkl = tmp_path / "model.pkl"
    pkl.write_bytes(b"")
    write_sidecar(
        pkl,
        source_mode="tempo-url",
        source="http://localhost:3200",
        window_start_ts=1715632800,
        window_end_ts=1715634600,
        hyperparams={"contamination": 0.01},
        trace_count=10,
        row_count=42,
    )
    meta = read_sidecar(pkl)
    assert meta["schema_version"] == "1.0"
    assert meta["trace_count"] == 10
    assert meta["row_count"] == 42
    assert meta["source_mode"] == "tempo-url"
    assert meta["hyperparams"] == {"contamination": 0.01}


def test_corrupt_version_raises(tmp_path):
    pkl = tmp_path / "model.pkl"
    pkl.write_bytes(b"")
    write_sidecar(
        pkl,
        source_mode="tempo-url",
        source="x",
        window_start_ts=0,
        window_end_ts=0,
        hyperparams={},
        trace_count=0,
        row_count=0,
    )
    meta_path = Path(f"{pkl}.meta.json")
    meta = json.loads(meta_path.read_text())
    meta["schema_version"] = "9.9"
    meta_path.write_text(json.dumps(meta))

    with pytest.raises(SchemaMismatchError):
        read_sidecar(pkl)
