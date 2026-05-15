"""Tests for src/shim.py — Alertmanager webhook → CLI shim.

We patch subprocess.run before instantiating the server so the CLI subprocess
never actually runs. Server is started on an ephemeral port (overriding the
hardcoded 8080) by binding the HTTPServer ourselves.
"""
from __future__ import annotations

import json
import socket
import subprocess
import threading
import time
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

import shim


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def patched_shim(tmp_path, monkeypatch):
    """Patch shim.EVAL, shim.subprocess.run, then start the server in a thread."""
    eval_path = tmp_path / "eval" / "eval.jsonl"
    monkeypatch.setattr(shim, "EVAL", eval_path)

    def fake_run(cmd, *args, **kwargs):
        # Tiny sleep so complete_time > invoke_time deterministically.
        time.sleep(0.01)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(shim.subprocess, "run", fake_run)

    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), shim.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, eval_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_shim_writes_jsonl_for_firing_alert(patched_shim):
    port, eval_path = patched_shim

    payload = {
        "version": "4",
        "status": "firing",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "TsOrderHighLatency",
                    "service_name": "ts-order-service",
                },
                "annotations": {},
                "startsAt": "2026-05-14T12:00:00Z",
            }
        ],
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t_send = time.time()
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
    t_recv = time.time()
    # POST returns ~instantly (well under a second).
    assert (t_recv - t_send) < 2.0

    # The handler sends 200 *before* doing the work (intentional, per §3.7),
    # so wait briefly for the eval.jsonl write to land.
    deadline = time.time() + 5.0
    while time.time() < deadline and not eval_path.exists():
        time.sleep(0.05)

    assert eval_path.exists(), "shim did not write eval.jsonl"
    lines = eval_path.read_text().strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["source"] == "shim"
    assert obj["service"] == "ts-order-service"
    assert obj["window"] == "5m"
    assert obj["complete_time"] > obj["invoke_time"]
    assert obj["subprocess_rc"] == 0


def test_shim_ignores_resolved_alerts(patched_shim):
    port, eval_path = patched_shim

    payload = {
        "alerts": [
            {
                "status": "resolved",
                "labels": {"service_name": "ts-order-service"},
            }
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200

    # Give the handler a chance to run; it should be a no-op.
    time.sleep(0.2)
    assert not eval_path.exists() or eval_path.read_text().strip() == ""
