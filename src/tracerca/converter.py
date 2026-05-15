from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Iterable, TypedDict

from .schema import write_sidecar


class OTLPSpan(TypedDict, total=False):
    trace_id: str
    span_id: str
    parent_span_id: str
    service_name: str
    start_time_unix_nano: int
    end_time_unix_nano: int
    attributes: dict[str, Any]


class OTLPTrace(TypedDict, total=False):
    trace_id: str
    spans: list[OTLPSpan]


def _simple_name(service_name: str) -> str:
    name = service_name
    if "/" in name:
        name = name.split("/", 1)[1]
    if name.endswith("-service"):
        name = name[: -len("-service")]
    return name


def _http_status(span: OTLPSpan) -> int:
    attrs = span.get("attributes") or {}
    code = attrs.get("http.status_code", 0)
    try:
        return int(code)
    except (TypeError, ValueError):
        return 0


def convert_otlp_to_raw_pkl(
    traces: Iterable[OTLPTrace],
    out_path: str | Path,
    *,
    label: int = 0,
    fault_type: str = "",
    root_cause: list[str] | None = None,
) -> Path:
    out_path = Path(out_path)
    rc = list(root_cause) if root_cause is not None else []

    traces_list: list[dict[str, Any]] = []
    total_rows = 0

    for trace in traces:
        spans = list(trace.get("spans") or [])
        if not spans:
            continue

        by_id: dict[str, OTLPSpan] = {s["span_id"]: s for s in spans if "span_id" in s}
        non_root = [s for s in spans if s.get("parent_span_id")]
        kept = [s for s in non_root if s.get("parent_span_id") in by_id]
        kept.sort(key=lambda s: s.get("start_time_unix_nano", 0))

        if not kept:
            continue

        s_t: list[tuple[str, str]] = []
        timestamp: list[int] = []
        endtime: list[int] = []
        latency: list[int] = []
        http_status: list[int] = []

        for span in kept:
            parent = by_id[span["parent_span_id"]]
            src = _simple_name(parent.get("service_name", ""))
            dst = _simple_name(span.get("service_name", ""))
            start_ns = int(span.get("start_time_unix_nano", 0))
            end_ns = int(span.get("end_time_unix_nano", 0))
            start_us = start_ns // 1000
            end_us = end_ns // 1000
            s_t.append((src, dst))
            timestamp.append(start_us)
            endtime.append(end_us)
            latency.append(end_us - start_us)
            http_status.append(_http_status(span))

        traces_list.append(
            {
                "trace_id": trace.get("trace_id", ""),
                "label": label,
                "fault_type": fault_type,
                "root_cause": rc,
                "s_t": s_t,
                "timestamp": timestamp,
                "endtime": endtime,
                "latency": latency,
                "http_status": http_status,
            }
        )
        total_rows += len(s_t)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        pickle.dump(traces_list, f)

    if traces_list:
        ws = min(t["timestamp"][0] for t in traces_list) // 1_000_000
        we = max(t["endtime"][-1] for t in traces_list) // 1_000_000
    else:
        ws = 0
        we = 0

    write_sidecar(
        out_path,
        source_mode="otlp",
        source="",
        window_start_ts=ws,
        window_end_ts=we,
        hyperparams={},
        trace_count=len(traces_list),
        row_count=total_rows,
    )
    return out_path
