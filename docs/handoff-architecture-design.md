# Handoff: Architecture Design for TraceRCA-CD Live Deployment

**Audience:** A fresh agent (or human collaborator) tasked with researching and producing a concrete implementation architecture for the system described below. This file is self-contained — anyone reading it should be able to pick up the project without prior conversation context.

**Author's note:** The capstone owner has already done the upstream algorithmic work and the literature/product research. The next phase is **architecture and implementation planning**. Do not redo the research — read the linked artifacts and build on them.

---

## 1. Project Overview

This is a CS capstone project. The owner authored [TraceRCA-CD](https://github.com/Jared-Velasquez/TraceRCA-CD), an extension of the original [TraceRCA](https://github.com/NetManAIOps/TraceRCA) (IWQoS 2021) trace-based root cause analysis algorithm. TraceRCA-CD has already been shown to improve top-1 RCA accuracy on the **RCAEval RE2TT** offline benchmark.

**The capstone deliverable being planned now:** Build an OpenTelemetry observability backend that:

1. Ingests traces (and metrics derived from those traces) from a deployed **OTel Collector**.
2. Detects sustained **SLO violations** using burn-rate alerting (the Google SRE multi-window multi-burn-rate pattern).
3. On each SLO breach, **triggers TraceRCA-CD** against a recent trace window and produces a **ranked list of suspect services/spans**.
4. Runs against a live **Train-Ticket** (FudanSE) microservices benchmark with **Chaos Mesh** injecting faults as ground truth.

The goal is to defend the claim that *TraceRCA-CD's offline RE2TT improvements survive the transition to a live, sampled, SLO-triggered streaming pipeline* — i.e., the algorithm generalizes from the static benchmark to a real operational system.

---

## 2. Capstone Framing (Important — Don't Rederive)

A research pass uncovered that **RE2TT is itself the Train-Ticket subset of RCAEval RE2** (same application, overlapping fault catalog). This means RE2TT-offline → live-Train-Ticket is **not** cross-application generalization. The reframed contribution is:

> **"Offline-algorithm → online-system generalization on the same application,"** validated by reporting operational metrics (MTTL, throughput, sampling robustness, trigger precision/recall) that no prior trace-RCA paper reports.

The architecture must enable measuring those operational metrics, not just running the algorithm.

---

## 3. Architectural Decisions Already Made

These are settled. Do **not** re-litigate; design around them.

| Component | Choice | Why |
|---|---|---|
| **Workload** | Train-Ticket — specifically the [OperationsPAI fork](https://github.com/OperationsPAI/train-ticket) on Kubernetes (pin a commit SHA at install time) | Standard RCA benchmark; comparable to Eadro / Nezha / MicroRank. The OperationsPAI fork ships with OTel instrumentation as a Helm flag (`--set global.monitoring=opentelemetry`) and Helm charts — eliminates the instrumentation phase entirely. Original FudanSELab/train-ticket has no OTel out of the box; reusing this fork is a substantial scope reduction. |
| **Fault injection** | Chaos Mesh | Train-Ticket community standard; matches Eadro / Nezha / Sage methodology |
| **Trace ingest** | OTel Collector (OTLP receiver) | OTel-native pipeline is now industry standard |
| **Span → metric derivation** | OTel Collector `spanmetrics` connector | Single source of truth — same span data drives SLO trigger and TraceRCA-CD |
| **Trace storage** | Tempo (or Jaeger if simpler) | Need windowed query for TraceRCA-CD input |
| **Metric storage** | Prometheus | Required by Sloth |
| **SLO trigger** | **Sloth** (not Pyrra, not Keptn, not Nobl9) | OSS, OpenSLO-compatible, simpler CRD-based config than Pyrra; Keptn is for CI/CD gating, not production RCA |
| **Alert routing** | Alertmanager → tiny HTTP shim | Standard Prometheus stack |
| **RCA orchestration** | **Tiny shim (~15 lines)** that receives Alertmanager POSTs and shells out to a TraceRCA-CD CLI; plus the CLI itself for ad-hoc / reproducibility runs | Capstone scope. Not a service. Shim exists *only* to record start/end timestamps so MTTL is measurable end-to-end without human-reaction noise. Manual CLI invocation remains supported for debugging and ablations. |
| **RCA algorithm** | TraceRCA-CD (already built) | The thing being validated |
| **Anomaly-detector model** | **Retrained on a fault-free baseline of the live system**, *not* imported from RE2TT | Feature distributions (latency, sampling, instrumentation) differ between RE2TT and the live deployment even though the application is the same. Retraining isolates the *algorithmic* contribution from data-distribution effects; this is the correct generalization framing and matches standard ML practice for unsupervised anomaly detectors. The imported-RE2TT-model variant should also be run as a control column to confirm retraining is necessary. |
| **Workload deployment** | Local single-node Kubernetes (kind / minikube / k3d) — **not** EKS or any cloud | Train-Ticket and Chaos Mesh are K8s-native. Local-only is settled; the host-side colocation premise of the obs stack depends on it. Cloud is out of scope for capstone. |
| **Load generator** | [RCAEval's Locust scripts for Train-Ticket](https://github.com/phamquiluan/RCAEval) | Used during baseline-training and during chaos eval. Same load profile as RE2TT was generated under → maximizes offline→online comparability of feature distributions. Document RPS and duration. |
| **SLO config** | Short multi-window multi-burn-rate windows tuned to fault duration: **5min/1min and 15min/3min** (not the standard 1h/5min and 6h/30min) | Faults are ~3 min each per the recommended catalog. The standard SRE window won't fire within the fault duration. Cite the chaos-experiment cadence as the rationale; acknowledge the higher false-positive rate as a documented tradeoff (the trigger precision/recall metric measures it). |
| **Chaos targets / SLO scope** | The **5 services RCAEval RE2TT targets**: `ts-auth`, `ts-order`, `ts-route`, `ts-train`, `ts-travel`. Service-level SLOs only (one error-rate SLO + one p99-latency SLO per service = 10 SLOs total) | Matching RE2TT's target set is the single biggest lever for offline→online comparability. Eliminates the confound "did you pick easier services?" Note: an earlier draft (and the research report) speculatively named different services — those were not verified. Defer to RE2TT. |
| **Ground-truth log** | Thin wrapper script (Python or bash, ~10 lines) around `kubectl apply -f chaos.yaml` that appends `{wall_clock_apply_time, target_service, fault_type, manifest_path}` to `eval/ground_truth.jsonl` before invoking kubectl | Gives MTTL a deterministic timestamp source independent of Chaos Mesh's K8s status (which can lag). Trivial, no Chaos Mesh API coupling. The eval runner (deliverable #9 in §8) calls this wrapper instead of kubectl directly. |
| **Obs-stack deployment** | docker-compose or systemd on the host (Tempo, Prometheus, Alertmanager, Sloth-standalone, shim) | Reduces K8s surface area to only what Chaos Mesh requires. Sloth supports a [standalone CLI mode](https://sloth.dev/usage/cli/) that emits Prom rules to a file — no K8s CRDs needed. Single-node co-location is the point. |

### Tools that were considered and rejected

- **DeepFlow / Pixie** — bring their own RCA logic; can't swap in TraceRCA-CD
- **Keptn** — gates deploys, doesn't trigger RCA on production breaches
- **Pyrra** — fine, but Sloth's CRD-based UX is simpler for capstone scope
- **Nobl9** — closed-source SaaS

---

## 4. Data Flow (Reference)

```
┌─────────────────┐
│ Train-Ticket    │ (~64 K8s services, OTel SDK auto-instrumented)
│ services        │
└────────┬────────┘
         │ OTLP (gRPC/HTTP)
         ▼
┌─────────────────┐
│ OTel Collector  │
│  receivers: otlp│
│  connectors:    │
│    spanmetrics  │
└──┬───────────┬──┘
   │ traces    │ derived metrics
   ▼           ▼
┌──────┐   ┌────────────┐         ┌──────────────┐         ┌──────────────┐
│Tempo │   │ Prometheus │ ──────► │ Sloth-       │ ──────► │ Alertmanager │
│      │   │            │ scrape  │ generated    │ rules   │              │
└──┬───┘   └────────────┘         │ recording +  │ fire    └──────┬───────┘
   │                              │ alerting     │                │ POST
   │                              │ rules        │                ▼
   │                              └──────────────┘         ┌──────────────────┐
   │                                                       │ Shim (~15 LOC)   │
   │                                                       │  1. receive POST │
   │  TraceQL window query for affected service ◄──────────┤  2. shell out to │
   └──────────────────────────────────────────────────────►│     RCA CLI      │
                                                           │  3. log start /  │
                                                           │     end times    │
                                                           └────────┬─────────┘
                                                                    │ subprocess
                                                                    ▼
                                                           ┌──────────────────┐
                                                           │ TraceRCA-CD CLI  │
                                                           │ (also runnable   │
                                                           │  by hand for     │
                                                           │  ablations)      │
                                                           │  a. OTLP → pkl   │
                                                           │     (converter)  │
                                                           │  b. invoke       │
                                                           │     TraceRCA-CD  │
                                                           │     on the pkl   │
                                                           │  c. parse output │
                                                           │   → ranked list  │
                                                           │   → eval.jsonl   │
                                                           │     (MTTL, AC@K) │
                                                           │   → save input   │
                                                           │     pkl for      │
                                                           │     replay       │
                                                           └──────────────────┘

(Parallel) Chaos Mesh ──► injects faults on selected ts-* services
                              │
                              └──► ground-truth log for eval
```

---

## 5. Pointers to Existing Artifacts

- **Original research prompt** (capstone framing, research questions):
  `/Users/jaredvelasquez/.claude/plans/i-am-starting-this-nested-alpaca.md`
- **Research report** (the literature + product survey, with verdict and threats-to-validity):
  `/Users/jaredvelasquez/.claude/plans/rca-research-report.md`
  (also copied to `docs/rca-research-report.md` in this repo)
- **TraceRCA-CD source** (the algorithm to be deployed): https://github.com/Jared-Velasquez/TraceRCA-CD
- **Original TraceRCA**: https://github.com/NetManAIOps/TraceRCA
- **RCAEval benchmark** (offline anchor): https://github.com/phamquiluan/RCAEval
- **Train-Ticket**: https://github.com/FudanSELab/train-ticket
- **Chaos Mesh**: https://chaos-mesh.org/
- **Sloth**: https://sloth.dev/
- **OTel spanmetrics connector**: https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/connector/spanmetricsconnector
- **Tempo**: https://grafana.com/oss/tempo/
- **Google SRE Workbook (burn-rate alerting)**: https://sre.google/workbook/alerting-on-slos/

---

## 6. Constraints and Non-Goals

**Constraints:**
- OSS only (no Datadog, Dynatrace, Causely, etc.)
- Capstone scope: **minimal viable** system. Avoid over-engineering. The grade is for the algorithm + eval, not the orchestration.
- Train-Ticket and Chaos Mesh on a single-node K8s cluster (kind / minikube / k3d). Obs stack (Tempo, Prom, Alertmanager, Sloth, shim) on the same host via docker-compose or systemd — not in K8s. Document the split and version-pin everything.
- Python for the shim and CLI (TraceRCA-CD is Python; same runtime simplifies invocation).
- Must produce reproducible results: pin all component versions.

**Operational metrics the system must enable measuring** (drive design):
- AC@1, AC@3, Avg@5 (RCAEval-standard ranking accuracy)
- MTTL (mean time-to-localize): wall-clock from `chaos-mesh apply` → ranked list emitted
- SLO trigger precision / recall (vs. Chaos Mesh ground-truth log)
- Throughput: spans/sec sustained before backpressure
- Sampling robustness: AC@K at head-sampling 100%, 10%, 1%
- Cold-start time: service start → first usable RCA

**Non-goals:**
- Production-grade HA, multi-tenancy, RBAC, secrets management
- A polished UI (Grafana dashboard for demo is enough; no custom frontend)
- **A webhook *service*** — explicitly out of scope. The shim is a script, not a service: no API design, no framework (FastAPI / Flask / etc.), no concurrency model beyond serial subprocess invocation, no authentication, no health endpoint, no retries. If the design starts to resemble a service, the design is wrong.
- Replacing the algorithm (TraceRCA-CD is fixed)
- Cross-application generalization in v1 (RCAEval RE2-OB is a stretch goal)

**Defaults the architecture agent should assume (don't ask the capstone owner):**
- Shim binds to `127.0.0.1` on a fixed port (default 8080); Alertmanager runs on the same host so localhost is sufficient
- `eval.jsonl` lives at `eval/eval.jsonl`, ground-truth log at `eval/ground_truth.jsonl`, input pkls at `eval/inputs/`. All under `eval/`, append-only, gitignored
- No Slack / email / external notification — `eval/*.jsonl` are the only sinks
- One model file per variant: `models/model_live.pkl` (retrained on live baseline) and `models/model_re2tt.pkl` (control); both gitignored, regenerable from the trainer + sidecar metadata
- All chaos manifests, Sloth SLO specs, Sloth's generated Prometheus rule output, and the eval runner are **committed** for reproducibility
- Time sync between K8s node (kind/minikube/k3d) and host is assumed; the agent should add a one-line check (`kubectl exec -- date` vs host `date`) to the smoke-test list
- Prometheus retention defaults are fine; long-term storage out of scope
- **Alertmanager → shim payload field for service name**: `labels.service_name` (OTel semantic convention)
- **RCA trace-window size**: default 5 min (≈1.5× fault duration); CLI flag `--window` overrides
- **Tempo storage**: local filesystem volume mounted into the Tempo container — no S3/GCS
- **Sampling sweep**: one OTel Collector config knob; rerun the experiment per rate (100% / 10% / 1%). The architecture exposes the knob — no fancy sweep automation
- **Concurrent / overlapping faults**: out of scope. Experimental protocol is serial with recovery windows; shim's serial-subprocess model is sufficient
- **Baseline-training filtering**: no filtering. Train on raw fault-free traces; document that natural Train-Ticket flakiness is part of the baseline
- **Repo layout**: follow existing `src/tracerca/` Python-module convention. Suggested: `src/tracerca/train.py`, `src/tracerca/__main__.py` (inference CLI), `src/tracerca/converter.py` (OTLP→pkl), `src/shim.py`, `src/eval_runner.py`, `eval/`, `models/`, `chaos/`, `slo/`, `deploy/{k8s,compose}/`

**Verify-before-designing checks the agent must run early (don't assume):**
- **TraceRCA-CD pkl schema.** TraceRCA and TraceRCA-CD read traces stored as **pickle files** before running — both training and inference. Inspect the [TraceRCA-CD repo](https://github.com/Jared-Velasquez/TraceRCA-CD) (data loader / preprocess / training entry points) and document the exact schema the pkls must contain: is it a `pandas.DataFrame` (one row per span vs. one row per trace?), a list of dicts, or a custom Trace/Span class? What columns / fields are required? What dtypes? This is the single most important integration detail — every other piece of the CLI and trainer hangs off it. **Discover this in the first hour, not the last.** Document the schema in `docs/architecture.md` so the converter has a concrete spec to write against.
- **OperationsPAI fork's OTel exporter target.** Confirm where the fork's OTel SDK is configured to send spans (default OTLP endpoint, which protocol — gRPC vs HTTP) so the OTel Collector receivers match.
- **OperationsPAI fork's bundled obs stack.** Does `--set global.monitoring=opentelemetry` install just the SDKs on the Train-Ticket pods, or does it also stand up its own OTel Collector (and possibly Jaeger/Prom) inside the cluster? If a Collector ships with the fork, decide: (a) disable it and use your standalone Collector config so the pipeline is yours end-to-end, or (b) keep it and have it forward to your host-side Tempo/Prom. Option (a) is preferred for explicit control; document the override.
- **RCAEval RE2TT pkl format.** Verify whether RCAEval distributes RE2TT data as pkls in the same schema TraceRCA-CD's loader expects, or whether a converter is needed between RCAEval's format and TraceRCA-CD's loader. If they're already compatible, the trainer can ingest RE2TT pkls directly to produce `model_re2tt.pkl` — no conversion needed for the control variant.

---

## 7. Repo State Snapshot

The current repo is mostly cleared (deleted ingestion scaffolding from a prior iteration — see `git log`). Treat it as nearly green-field. Recent commits:

- `61ee945` feat: implement localization
- `27bbf71` feat: rewrite baseline for ring buffer design, implement anomaly detection
- `f36be48` feat: marshal protobuf into json before enqueuing onto stream, move pyproject.toml into tracerca module
- `714a14d` feat: implement docker-compose, switch Kafka to Redis Streams for enqueuing spans after ingestion

The deleted scaffolding shows the prior direction (Go ingestion service + Python `tracerca` module + Redis Streams). The new architecture supersedes that — the OTel Collector replaces the custom Go ingestion service, and Sloth/Prometheus/Alertmanager replace the Redis Streams + custom queue trigger. Decide what (if anything) from the old `src/tracerca/` Python module is worth resurrecting after consulting the [TraceRCA-CD](https://github.com/Jared-Velasquez/TraceRCA-CD) repo.

The project's `CLAUDE.md` defines workflow conventions: plan-mode for non-trivial tasks, `tasks/todo.md` for plans, `tasks/lessons.md` for self-improvement notes, simplicity-first, root-cause fixes only.

---

## 8. The Architecture Agent Prompt

Copy everything below the `---` line into the new agent's context.

---

### PROMPT BEGIN

You are designing the implementation architecture for a CS capstone project. Read the handoff document at `docs/handoff-architecture-design.md` (in the project repo) **first** — it contains all upstream context, settled architectural decisions, the data flow reference, and the constraints you must respect. Also read `docs/rca-research-report.md` for the literature grounding behind these decisions.

Do not redo the upstream research. Do not propose alternative tools (Pyrra vs. Sloth, Tempo vs. Jaeger, etc. — those are settled). Your job is to turn the settled stack into an actionable implementation plan.

#### What you must produce

A single comprehensive architecture document at `docs/architecture.md` containing:

1. **Component inventory** — every service/process to be deployed, with: image (or build source), version pin, K8s namespace, replica count for capstone scale, resource requests/limits (rough guesses are fine).

2. **Configuration artifacts** — concrete config (not pseudocode) for:
   - OTel Collector pipeline YAML (receivers, processors, the `spanmetrics` connector, exporters to Tempo and Prometheus)
   - One example Sloth SLO CRD for `ts-order-service` covering both an availability SLI (request error rate) and a latency SLI (p99 over a budget). Use the standard Google SRE multi-window multi-burn-rate config (1h/5min, 6h/30min).
   - Prometheus scrape config for the OTel Collector's metric endpoint
   - Alertmanager routing config that POSTs to the RCA webhook service
   - Tempo configuration sufficient for windowed TraceQL queries

3. **RCA CLI + shim + trainer spec** — Python. Three pieces, none of them is a service:

   **Critical integration fact**: TraceRCA-CD reads traces stored as **pkl files** for both training and inference. Every component below has to produce or consume that pkl schema. The exact schema is a verify-before-designing item (§6) — do not write the trainer or CLI until it's documented.

   **Shared component: the OTLP→pkl converter.** A single Python module that takes a list/iterable of OTLP spans (from a Tempo TraceQL response) and produces a pkl file matching the TraceRCA-CD-expected schema. Used by both the trainer and the inference CLI. Test it standalone first.

   **(a) The trainer** — `python -m tracerca.train` (or equivalent), a separate entry point that produces the isolation-forest model file consumed by the inference CLI:
   - Arguments: `--baseline-source <tempo-url|pkl-dir> --window <e.g. 30m> --out model.pkl [--hyperparams hp.yaml]`
   - Two source modes:
     - `tempo-url`: pulls fault-free traces from Tempo via TraceQL over the given window, runs the OTLP→pkl converter, then trains. Used for `model_live.pkl`.
     - `pkl-dir`: reads pre-existing pkl files directly (skips conversion). Used for `model_re2tt.pkl` (RCAEval RE2TT data ships as pkls — verify schema compatibility per §6).
   - Same code path, two model variants. This is the simplest control-experiment setup.
   - Runs **the unmodified TraceRCA-CD training routine** — verify the exact API in the [TraceRCA-CD repo](https://github.com/Jared-Velasquez/TraceRCA-CD); do not reinvent
   - Default hyperparameters must match the RE2TT-trained model so that the *algorithm* is the constant and the *data* is the variable. Allow overrides via `--hyperparams` for ablation
   - Persists the model + a small sidecar JSON capturing: training-window timestamps, source mode, source URL/dir, hyperparameters, TraceRCA-CD commit SHA, pkl schema version. Reproducibility depends on this metadata.

   **(b) The TraceRCA-CD inference CLI** — a single `python -m tracerca` entry point invokable by hand:
   - Arguments: `--service <name> --window <duration> --model <path-to-model-pkl> [--tempo-url ...] [--out-dir eval/] [--save-input-pkl]`
   - Pipeline:
     1. Load the pickled isolation-forest model at startup; fail loud if the sidecar's pkl schema version doesn't match the converter's
     2. TraceQL query to Tempo for spans matching the service in the requested window
     3. Run the shared OTLP→pkl converter to produce a temporary input pkl
     4. Optionally persist that input pkl to `eval/inputs/<invoke_time>.pkl` (`--save-input-pkl`, **default on**) so any case can be re-run by hand against the exact same input
     5. Invoke TraceRCA-CD's inference function on the input pkl
     6. Parse the ranked output
   - Document behavior when the window is empty or the service is unknown (exit non-zero with a clear message; don't crash)
   - TraceRCA-CD packaging: pick **one** of (i) git submodule under `vendor/`, (ii) `pip install` from the GitHub repo via a pinned commit SHA in `pyproject.toml`. Recommend one, justify in a sentence
   - Output: a ranked list to stdout (human-readable) **and** one JSONL line appended to `eval/eval.jsonl` with `{invoke_time, complete_time, service, window, input_pkl_path, ranked_list, model_id, source: "cli"|"shim"}`. `model_id` separates the retrained-model column from the imported-RE2TT-model control column at analysis time; `input_pkl_path` enables exact replay. Eval logging is mandatory because metric computation depends on it.

   **(c) The shim** — a single file, ~15 lines, stdlib `http.server` only:
   - Listens on a configurable port for Alertmanager webhook POSTs
   - For each alert in the payload, records `t0`, shells out to the CLI above, records `t1`, appends to `eval.jsonl` with `source: "shim"` (the CLI also appends its own line; that's fine — joining on `invoke_time` reconstructs end-to-end)
   - **No** framework, no async, no health endpoint, no auth, no retries, no graceful shutdown handling. Serial subprocess invocation. If two alerts arrive concurrently, the second blocks until the first completes — this is acceptable; document it
   - The shim's only architectural reason to exist is recording timestamps so MTTL is automatic. If a reviewer asks "why not just call the CLI by hand," the answer is "MTTL would include human reaction time."

   **MTTL definition** to use throughout: `complete_time` (from the shim or CLI eval line) minus `chaos-mesh apply` timestamp (from the Chaos Mesh ground-truth log). Decompose into trigger latency (fault → alert) and RCA latency (alert → complete) when reporting.

4. **Repo file structure** — the full directory tree of the project after implementation, with one-line purpose for each directory and key file. Match the existing `src/` layout where reasonable.

5. **Deployment plan** — ordered, executable steps. Note the K8s/host split (see §3 and §6):
   - **K8s side** (kind / minikube / k3d — pick one and justify; capstone owner runs on a single laptop): cert-manager → Chaos Mesh → Train-Ticket → OTel Collector (deployed to the cluster so it can reach Train-Ticket pods over the cluster network, and exposed via NodePort/host-port for the host-side Tempo + Prom to scrape)
   - **Host side** (docker-compose recommended for one-command up/down; document the compose file): Tempo → Prometheus → Alertmanager → Sloth (run in CLI mode to generate Prom rule files; commit the rule output) → shim
   - **Baseline-training step** (after the stack is up and Train-Ticket is healthy, but before any chaos): drive realistic load into Train-Ticket for a fixed window (use the existing Train-Ticket load generator or the [Locust scripts in RCAEval](https://github.com/phamquiluan/RCAEval); document the load profile — RPS, duration, recommend ≥30 min). Then run `python -m tracerca.train --baseline-source <tempo-url> --window 30m --out model.pkl`. Verify the model file and sidecar JSON were written. **No chaos is run during this window.** The shim is up but should not fire; if it does, the SLO is mis-configured — fix before proceeding.
   - **Optional control-model step**: also produce or download the RE2TT-trained model (`model_re2tt.pkl`) so the eval can run an "imported model" control column alongside the retrained model.
   - For each step: the exact `helm install` / `kubectl apply` / `docker compose up` command and any version pins
   - Smoke test after each step (e.g., "after OTel Collector install, exec a curl to verify OTLP receiver health"; "after host-side Tempo, query for any spans to verify ingest"; "after baseline training, run the CLI by hand against a known-good service window and verify a non-empty ranked list appears in `eval.jsonl`"; "after shim, POST a fake Alertmanager payload and verify a CLI invocation runs")

6. **End-to-end verification recipe** — one walkthrough that proves the whole pipeline works (assumes baseline-training step from #5 is complete and `models/model_live.pkl` exists):
   - Invoke `python -m src.chaos_apply chaos/cpu_ts-order.yaml ts-order cpu` (the wrapper logs to `ground_truth.jsonl` and applies the manifest)
   - Show the SLO breach firing in Alertmanager
   - Show the shim receiving the POST and shelling out to the CLI with `--model models/model_live.pkl` (logs)
   - Show a ranked list emitted to `eval/eval.jsonl` with the right `model_id` and an `input_pkl_path` pointing under `eval/inputs/`
   - Run `python -m src.analysis` and confirm AC@1 = 1.0 for this case (`ts-order` is rank-1) and MTTL is reported
   - (Optional) Re-run the same chaos with `--model models/model_re2tt.pkl`; show the AC@1 difference as the control-experiment evidence that retraining matters

7. **Operational-metric instrumentation plan** — for each metric in `docs/handoff-architecture-design.md` §6, identify where in the pipeline it gets measured and how it's exported (the eval logger handles AC@K / MTTL; Prometheus self-scrape handles throughput; ad-hoc scripts handle sampling robustness sweeps).

8. **Eval runner + chaos wrapper + analysis script** — three small Python scripts in `src/`:

   **(i) `chaos_apply.py`** — the ground-truth wrapper. ~10 lines. Takes a chaos manifest path + target service + fault type as args; appends `{wall_clock_apply_time, target_service, fault_type, manifest_path}` to `eval/ground_truth.jsonl`; then `subprocess.run(["kubectl", "apply", "-f", manifest])`. The eval runner calls this, never `kubectl apply` directly.

   **(ii) `eval_runner.py`** — drives the experiment. ~100–150 lines. Reads a YAML / JSON experiment spec listing fault types × target services × replicates. For each fault: invoke `chaos_apply.py`, sleep for `fault_duration + recovery_window`, invoke `kubectl delete` to clear the chaos resource, sleep for inter-fault recovery. No magic — a serial loop with logging. Document the spec format. Targets: the 5 RE2TT services (`ts-auth`, `ts-order`, `ts-route`, `ts-train`, `ts-travel`); fault catalog from the research report (CPU stress, memory stress, network delay, network loss, HTTP error replace, HTTP delay).

   **(iii) `analysis.py`** — post-hoc metric computation. Joins `eval/eval.jsonl` (RCA invocations) with `eval/ground_truth.jsonl` (chaos applies) by timestamp proximity. For each matched pair, computes AC@1, AC@3, Avg@5, MTTL = `complete_time − apply_time`. Outputs a per-fault-type table plus an overall summary. Should also compute SLO trigger precision/recall by checking whether each ground-truth fault produced a matching alert in eval.jsonl within the alert window.

   These scripts together are the experimental harness. Without them every run is manual; with them the capstone owner runs `python -m src.eval_runner experiment.yaml && python -m src.analysis` and gets a results table.

9. **Open questions** — a short section at the bottom listing anything you couldn't resolve from the handoff + research-report alone. Don't invent answers; surface the questions for the capstone owner to decide.

#### Constraints on your work

- **Read existing code before designing.** Look at the deleted `src/tracerca/` paths in `git log` to understand what existed before; check the current state of [TraceRCA-CD](https://github.com/Jared-Velasquez/TraceRCA-CD) (you have WebFetch on `github.com`) for its actual API surface. Don't design an integration without verifying the function signatures. **Run the verify-before-designing checks listed in §6 in the first hour.**
- **No new tools.** Sloth, Tempo, Prometheus, Alertmanager, OTel Collector, Chaos Mesh, [OperationsPAI/train-ticket](https://github.com/OperationsPAI/train-ticket), [RCAEval](https://github.com/phamquiluan/RCAEval) load scripts, K8s. Anything else needs explicit justification in the "Open questions" section.
- **Defaults are settled.** The "Defaults the architecture agent should assume" list in §6 covers shim binding, file paths, model file naming, notification scope, and reproducibility artifacts. Don't ask the capstone owner about any of these — apply them and move on.
- **SLO windows are settled.** 5min/1min and 15min/3min multi-window multi-burn-rate. Justified by chaos-fault duration in §3. Don't propose alternatives.
- **Pin versions.** Every chart, container, library — pinned. The capstone needs to be reproducible six months from now.
- **Cite primary docs.** Each config snippet should link to the upstream documentation page that defines the schema. WebFetch is allowlisted for `github.com`, `grafana.com`, `opentelemetry.io`, `sloth.dev`, etc. — see `.claude/settings.local.json`.
- **Be concrete.** Pseudocode and "TODO" stubs are not deliverables. If you can't write the YAML, you didn't finish the section.
- **Match the project's stated style:** simplicity first, no premature abstraction, no comments unless the why is non-obvious (see this project's `CLAUDE.md`).

#### Working approach

This is a research-and-synthesis task with several mostly-independent areas (collector config, Sloth/Prom config, Tempo + TraceQL, webhook service design, deployment plan). Fan out aggressively if your harness supports subagents — spawn 2–4 in parallel scoped to non-overlapping sections, then synthesize. If subagents aren't available, do the research yourself with WebFetch + WebSearch (both allowlisted in this project).

When you're done, return a tight summary back to the user: (1) one-paragraph architecture overview, (2) the most important open question(s), and (3) the path to `docs/architecture.md`.

### PROMPT END

---

## 9. Suggested Slash to Hand Off

When you're ready, paste the prompt block above into a new Claude Code session in this repo (or `cd` into the repo and run `claude`). The agent will have access to the same web allowlist via `.claude/settings.local.json`.
