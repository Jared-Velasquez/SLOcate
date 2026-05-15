from __future__ import annotations

# Tempo HTTP API response shapes assumed by this client (see Grafana Tempo API docs):
#
# GET /api/search?q=<traceql>&start=<unix_s>&end=<unix_s>&limit=<n>
#   -> {"traces": [{"traceID": "<hex>", ...}, ...]}
#
# GET /api/traces/{traceID}?start=<unix_s>&end=<unix_s>
#   -> {"batches": [
#         {"resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "..."}}, ...]},
#          "scopeSpans": [
#             {"spans": [
#                 {"traceId": "<hex>", "spanId": "<hex>", "parentSpanId": "<hex>",
#                  "startTimeUnixNano": "<int-as-str>", "endTimeUnixNano": "<int-as-str>",
#                  "attributes": [{"key": "http.status_code", "value": {"intValue": "200"}}, ...]},
#                 ...]},
#             ...]},
#         ...]}
#
# Tempo emits OTLP-JSON; numeric fields arrive as strings, attribute values are
# tagged unions ({"stringValue"|"intValue"|"doubleValue"|"boolValue": ...}).

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterator

import httpx

from .converter import OTLPSpan, OTLPTrace


def _attr_value(v: dict[str, Any]) -> Any:
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        try:
            return int(v["intValue"])
        except (TypeError, ValueError):
            return 0
    if "doubleValue" in v:
        return v["doubleValue"]
    if "boolValue" in v:
        return v["boolValue"]
    return None


def _attrs_to_dict(attrs: list[dict[str, Any]] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for a in attrs or []:
        key = a.get("key")
        if key is None:
            continue
        out[key] = _attr_value(a.get("value") or {})
    return out


def _parse_trace_body(body: dict[str, Any]) -> OTLPTrace:
    spans: list[OTLPSpan] = []
    trace_id = ""
    for batch in body.get("batches") or []:
        resource_attrs = _attrs_to_dict((batch.get("resource") or {}).get("attributes"))
        service_name = str(resource_attrs.get("service.name", ""))
        for scope in batch.get("scopeSpans") or batch.get("instrumentationLibrarySpans") or []:
            for s in scope.get("spans") or []:
                tid = s.get("traceId", "")
                if tid and not trace_id:
                    trace_id = tid
                span: OTLPSpan = {
                    "trace_id": tid,
                    "span_id": s.get("spanId", ""),
                    "parent_span_id": s.get("parentSpanId", "") or "",
                    "service_name": service_name,
                    "start_time_unix_nano": int(s.get("startTimeUnixNano", 0) or 0),
                    "end_time_unix_nano": int(s.get("endTimeUnixNano", 0) or 0),
                    "attributes": _attrs_to_dict(s.get("attributes")),
                }
                spans.append(span)
    return {"trace_id": trace_id, "spans": spans}


class TempoClient:
    def __init__(self, base_url: str, *, timeout: float = 10.0, concurrency: int = 8) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.concurrency = concurrency
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TempoClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _search(self, traceql: str, start_ts: int, end_ts: int, limit: int) -> list[str]:
        resp = self._client.get(
            f"{self.base_url}/api/search",
            params={"q": traceql, "start": start_ts, "end": end_ts, "limit": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        ids: list[str] = []
        for hit in data.get("traces") or []:
            tid = hit.get("traceID") or hit.get("trace_id")
            if tid:
                ids.append(tid)
        return ids

    def _fetch_one(self, trace_id: str, start_ts: int, end_ts: int) -> OTLPTrace:
        resp = self._client.get(
            f"{self.base_url}/api/traces/{trace_id}",
            params={"start": start_ts, "end": end_ts},
        )
        resp.raise_for_status()
        return _parse_trace_body(resp.json())

    def fetch_traces(
        self,
        traceql: str,
        start_ts: int,
        end_ts: int,
        limit: int = 1000,
    ) -> Iterator[OTLPTrace]:
        trace_ids = self._search(traceql, start_ts, end_ts, limit)
        if not trace_ids:
            return
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            for trace in pool.map(lambda tid: self._fetch_one(tid, start_ts, end_ts), trace_ids):
                if trace["spans"]:
                    yield trace
