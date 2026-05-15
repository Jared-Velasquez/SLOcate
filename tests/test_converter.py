import json
import pickle
from pathlib import Path

from tracerca.converter import convert_otlp_to_raw_pkl


def _span(span_id, parent, service, start_ns, dur_ns, status=200):
    return {
        "span_id": span_id,
        "parent_span_id": parent,
        "service_name": service,
        "start_time_unix_nano": start_ns,
        "end_time_unix_nano": start_ns + dur_ns,
        "attributes": {"http.status_code": status},
    }


def _load(out: Path):
    with out.open("rb") as f:
        return pickle.load(f)


def test_three_span_chain(tmp_path):
    trace = {
        "trace_id": "aaaa",
        "spans": [
            _span("1", "", "ts-order-service", 1_000_000_000, 5_000_000),
            _span("2", "1", "ts-station-service", 1_001_000_000, 3_000_000),
            _span("3", "2", "ts-travel-service", 1_002_000_000, 1_000_000),
        ],
    }
    out = tmp_path / "raw.pkl"
    convert_otlp_to_raw_pkl([trace], out)
    data = _load(out)
    assert len(data) == 1
    t = data[0]
    assert t["s_t"] == [("ts-order", "ts-station"), ("ts-station", "ts-travel")]
    assert t["latency"] == [3000, 1000]
    assert t["timestamp"] == [1_001_000, 1_002_000]
    assert t["endtime"] == [1_004_000, 1_003_000]
    assert t["http_status"] == [200, 200]

    meta_path = Path(f"{out}.meta.json")
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["schema_version"] == "1.0"
    assert meta["trace_count"] == 1
    assert meta["row_count"] == 2


def test_self_call_is_retained(tmp_path):
    trace = {
        "trace_id": "bbbb",
        "spans": [
            _span("1", "", "ts-order-service", 1_000_000_000, 5_000_000),
            _span("2", "1", "ts-order-service", 1_001_000_000, 2_000_000),
        ],
    }
    out = tmp_path / "self.pkl"
    convert_otlp_to_raw_pkl([trace], out)
    data = _load(out)
    assert len(data) == 1
    assert data[0]["s_t"] == [("ts-order", "ts-order")]


def test_orphan_span_dropped(tmp_path):
    trace = {
        "trace_id": "cccc",
        "spans": [
            _span("1", "", "ts-order-service", 1_000_000_000, 5_000_000),
            _span("2", "1", "ts-station-service", 1_001_000_000, 3_000_000),
            _span("9", "missing", "ts-ghost-service", 1_002_000_000, 1_000_000),
        ],
    }
    out = tmp_path / "orphan.pkl"
    convert_otlp_to_raw_pkl([trace], out)
    data = _load(out)
    assert len(data) == 1
    assert data[0]["s_t"] == [("ts-order", "ts-station")]
    assert len(data[0]["s_t"]) == 1
