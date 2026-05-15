# SLOcate

**SLO breach → locate the root cause.** A pluggable, chaos-validated RCA
harness over an OpenTelemetry backend.

SLOcate turns SLO violations in an observed microservice system into automated
root-cause analysis. It is RCA-engine-agnostic; [TraceRCA-CD](https://github.com/Jared-Velasquez/TraceRCA-CD) is the reference
backend.

## How it works

1. **Ingest** — services emit OpenTelemetry traces and metrics to an OTel
   Collector.
2. **Forward** — the Collector exports traces to **Grafana Tempo** and metrics
   to **Prometheus**.
3. **Detect** — Sloth-generated burn-rate rules fire an **Alertmanager** alert
   on an SLO breach.
4. **Trigger** — a thin webhook→CLI bridge invokes the co-located RCA engine,
   which queries Tempo and ranks the likely faulty microservice.

A chaos-driven harness injects faults and scores the engine's ranked output.
