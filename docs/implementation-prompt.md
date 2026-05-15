# Implementation Prompt — TraceRCA-CD Live Deployment

**How to use:** Paste everything below the next `---` line into a fresh Claude Code session opened in this repository (`/Users/jaredvelasquez/projects/tracerca-prod`). The session will orchestrate parallel subagents on git worktrees, pausing between phases so the human can review and commit. **Subagents do not commit.** When work is ready for a commit, the orchestrator notifies the human, the human commits, and only then does the orchestrator continue.

The authoritative architectural spec is `docs/architecture.md` in this repo. The prompt below tells the orchestrator how to apply it — file lists, dependencies between slices, worktree layout, commit handoff protocol — without restating the configuration content (which would just diverge over time).

---

You are implementing the architecture described in `docs/architecture.md` of this repository. Read that document fully **before** spawning any subagent — it contains the paste-ready configs, schemas, and CLI specs that every slice below depends on. Also skim `docs/handoff-architecture-design.md` for upstream context and `docs/rca-research-report.md` for the fault catalog.

**Scope of this session: code + unit tests only.** You will *not* run `kubectl`, `helm`, `docker compose up`, or any chaos injection. You will produce the file artifacts (Python, YAML, JSON, chaos manifests) so that a future session can run the deploy plan in `docs/architecture.md` §5. The one runtime command you *may* run is `docker run --rm ghcr.io/slok/sloth:v0.12.0 generate ...` to compile committed Sloth rules — that is read-only artifact generation, not a deploy.

## Resolved decisions (apply silently — don't re-ask the human)

The human has resolved every open question in `docs/architecture.md` §10. Apply these defaults; flag any conflicts you encounter but do not pause for them unless they would actually break the build.

| Open question | Resolution |
|---|---|
| `caller_discount_alpha` default | **1.5** — optimal for TraceRCA-CD on Train-Ticket. Bake into the default hyperparams YAML; remain overridable via `--hyperparams`. |
| Host platform | **macOS + Docker Desktop.** `host.docker.internal` resolves natively from kind nodes and compose containers. Add a one-line comment everywhere it appears noting the Linux fallback (`extra_hosts: host-gateway` for compose; `--add-host` for docker run). Do not add extra fallback wiring. |
| `generic_service` vs `trainticket` Helm chart path | Use `manifests/helm/trainticket/`. |
| `status_code` label value | Assume default `STATUS_CODE_ERROR`. Add a one-line comment in `slo/specs/*.yaml` instructing post-deploy verification against the live `/metrics` scrape. |
| `run_invo_encoding.py` directory vs file input | Pass a directory; if it errors at runtime, the deploy session will adjust. Don't pre-flight-fix what's not broken. |
| HTTPChaos request-percentage | Chaos Mesh has no native per-request percent on `HTTPChaos.replace`. Manifests use `mode: all` (all matching pods) with the inject duration shortened proportionally if needed. Document the deviation from the research report's "50% of requests" in a comment at the top of each `http-*` manifest. |
| Sampling-vs-SLO-fidelity wiring | Keep the simple wiring (single trace pipeline with `probabilistic_sampler` upstream of `spanmetrics`). Do not introduce the `forward` connector split. The sampling sweep's effect on SLO metric power is a known measured trade-off. |
| `models/*.pkl` committed? | No — gitignored. |
| Locust load profile | 50 users, spawn rate 5/s, 30 min. Document in the deploy plan only; do not script it now (we're not deploying). |

## Commit handoff protocol

Subagents must not commit. The handoff between subagent work and a human commit is the entire point of this workflow. After every subagent finishes:

1. The subagent's worktree contains uncommitted changes on its own branch (auto-named by `isolation: worktree`).
2. The orchestrator (you) prints a **commit notification** with: branch name, worktree path, list of new/modified files, a one-paragraph summary of what the slice produced, and a suggested commit message.
3. The orchestrator **pauses** until the human replies. Acceptable replies: "committed slice X, continue" / "merged slice X" / equivalent.
4. The orchestrator then proceeds to the next phase. Phase 2 must not start until at least Slice A (Python core) is merged into `main`, because Phase 2 imports from it.

Commit-notification format (use this exactly):

```
=== COMMIT READY — Slice <name> ===
Worktree:  <absolute path>
Branch:    <branch name>
New files: <list>
Modified:  <list>
Summary:   <2–3 sentences>

Suggested commit message:
<imperative one-liner, then optional bullet list>

Waiting for you to commit + merge. Reply "continue" when done.
```

If a subagent fails or produces incomplete work, surface the failure *instead of* a commit notification, and do not advance.

## Worktree mechanics

Use the `Agent` tool with `isolation: "worktree"`. Each subagent gets its own temporary worktree on its own branch — your top-level working copy is untouched. When the human reports a slice merged into `main`, the worktree's branch is what they merged; the worktree directory itself can be left for the harness to clean up.

For Phase 2, agents read from `main` as it now contains Slice A's code. If the human hasn't merged Slice A yet, the Phase 2 agents will not have the imports they need — that's why we gate.

## Phase layout

```
Phase 0 ── orchestrator-only (no subagent)
              repo plumbing: .gitignore, pyproject.toml, vendor submodule,
              src/tracerca/__init__.py, tasks/ directory
              → 1 commit, human commits, continue

Phase 1 ── 5 subagents on worktrees, parallel:
              Slice A — Python core (converter, schema, tempo_client, ranked_output, tests)
              Slice D — K8s manifests (kind-config + otel-collector/*)
              Slice E — Host compose (compose + tempo + prom + alertmanager)
              Slice F — SLO specs + generated Sloth rules
              Slice G — Chaos manifests (6 faults × 5 services = 30 files)
              → 5 commits, human commits each, continue

Phase 2 ── 2 subagents on worktrees, parallel:
              Slice B — Trainer + inference CLI + shim
              Slice C — Eval harness (chaos_apply, eval_runner, analysis + tests)
              → 2 commits, human commits each, done
```

Total: 8 commits across 8 logical slices.

---

## Phase 0 — Repo plumbing (orchestrator-only, no subagent)

Do this directly in the main working copy. It's small enough to not warrant a subagent.

**Files to create:**

1. `.gitignore` — append (don't overwrite the existing one):
   ```
   # Python
   __pycache__/
   *.py[cod]
   .venv/
   *.egg-info/

   # Eval + model artifacts (gitignored per architecture §6)
   eval/
   models/
   data/

   # Logs from the shim
   shim.log

   # OS
   .DS_Store
   ```

2. `pyproject.toml` — minimal package definition with runtime deps:
   - `name = "tracerca"`, `version = "0.1.0"`, `requires-python = ">=3.11"`
   - Dependencies: `pandas`, `scikit-learn`, `numpy`, `click`, `httpx`, `pyyaml`
   - Dev dependencies: `pytest`, `pytest-asyncio`
   - `[project.scripts]` — none (the CLIs use `python -m tracerca` and `python -m tracerca.train`, no console_scripts)
   - `[tool.setuptools.packages.find]` with `where = ["src"]`
   - Package layout: src-style

3. `src/tracerca/__init__.py` — single line: `__version__ = "0.1.0"`

4. `tasks/todo.md`, `tasks/lessons.md` — empty placeholders (per the project's CLAUDE.md convention).

5. Add the TraceRCA-CD submodule:
   ```bash
   git submodule add https://github.com/Jared-Velasquez/TraceRCA-CD.git vendor/TraceRCA-CD
   cd vendor/TraceRCA-CD
   git checkout 8df3e4431d849f96c206079db3e50c00963cb848
   cd -
   ```

6. Verify the submodule shows up: `git submodule status` should print `8df3e44... vendor/TraceRCA-CD (heads/main)`.

Surface the commit notification and pause. Suggested commit message:
```
chore: repo plumbing — pyproject.toml, submodule pin, gitignore
```

---

## Phase 1 — Five parallel subagents on worktrees

Spawn these in a **single message** with five `Agent` tool calls. Each uses `subagent_type: "general-purpose"` and `isolation: "worktree"`. Do not wait between them; let them run concurrently. After all five report back, surface five commit notifications in this order: A → D → E → F → G. (Order doesn't matter functionally; A is listed first because it gates Phase 2.)

### Slice A — Python core

**Subagent prompt (paste verbatim into the Agent call):**

> You are implementing the Python core of the TraceRCA-CD live deployment in an isolated worktree. The architectural spec is in `docs/architecture.md` of this repo — read §3.1 (pkl schemas), §3.3 (converter), and §0.1–0.3 (the TraceRCA-CD integration findings) before writing code. The repo's `CLAUDE.md` mandates: simplicity first, no comments unless the why is non-obvious, no premature abstraction, no half-finished implementations.
>
> Create these files in `src/tracerca/`:
>
> 1. `schema.py` — sidecar JSON writer + reader. Public surface:
>    - `SCHEMA_VERSION = "1.0"` constant
>    - `SCHEMA_VERSION_ALLOWLIST = frozenset({"1.0"})` constant
>    - `write_sidecar(pkl_path, *, source_mode, source, window_start_ts, window_end_ts, hyperparams, trace_count, row_count)` — writes `{pkl_path}.meta.json` with the schema in architecture.md §3.1 ("Sidecar metadata"). Captures `producer_commit` via `subprocess.run(["git","rev-parse","HEAD"])` and `tracerca_cd_commit` via `git -C vendor/TraceRCA-CD rev-parse HEAD`.
>    - `read_sidecar(pkl_path)` — returns the dict; raises `SchemaMismatchError` if `schema_version` not in allowlist. Define `SchemaMismatchError(Exception)`.
>
> 2. `converter.py` — implement `convert_otlp_to_raw_pkl(traces, out_path, *, label=0, fault_type="", root_cause=None)` exactly per architecture.md §3.3. Also exports `_simple_name(service_name)` that strips a trailing `"-service"` and any leading `"<namespace>/"` (this is the minimum needed to interoperate with TraceRCA-CD's `run_invo_encoding.py`). The function takes an iterable of `OTLPTrace`-shaped dicts (define a `TypedDict` for `OTLPSpan` and `OTLPTrace` at module top); it does NOT depend on Tempo. Pure transformation.
>
> 3. `tempo_client.py` — `class TempoClient` with:
>    - `__init__(self, base_url, *, timeout=10.0, concurrency=8)`
>    - `def fetch_traces(self, traceql, start_ts, end_ts, limit=1000) -> Iterator[OTLPTrace]` — calls `/api/search`, then fans out `/api/traces/{id}?start=...&end=...` per hit using `httpx.Client` (sync; concurrency via a thread pool of size `self.concurrency`). Returns full trace bodies converted into the `OTLPTrace` TypedDict shape consumed by `converter.py`. Use the TraceQL examples in architecture.md §2.3.
>    - Document the assumed Tempo response shape inline as a comment block at the top of the file (one-time, since this is non-obvious from code).
>
> 4. `ranked_output.py` — `parse_ranked_output(stdout, pkl_path) -> list[str]`. TraceRCA-CD's localization script (`run_localization_association_rule_mining_20210516.py`) writes a pkl at its output path containing `{"Ours-noise=0": list[str]}`. Prefer reading the pkl over parsing stdout; pass `stdout` only as a fallback. Return the list of ranked service names.
>
> Tests (in `tests/`, pytest, no fixtures framework — just plain test functions):
>
> 5. `tests/test_converter.py` — hand-craft three synthetic OTLP traces:
>    - One 3-span trace: root → child → grandchild, all different services. Assert the produced pkl has `s_t == [(root_svc, child_svc), (child_svc, grandchild_svc)]`, `latency` in microseconds, `timestamp` in microseconds.
>    - One trace with a self-call (span.service == parent.service). Assert it's retained in the raw pkl (filtering happens later in `run_invo_encoding.py`).
>    - One orphan-span trace (`parent_span_id` references a span not in the trace). Assert the orphan is dropped silently.
>    - Assert the sidecar JSON is written next to the pkl and contains the expected `schema_version`, `trace_count`, `row_count`.
>
> 6. `tests/test_schema.py` — write a sidecar, read it back; corrupt the schema_version; assert `read_sidecar` raises `SchemaMismatchError`.
>
> 7. `tests/test_ranked_output.py` — pickle `{"Ours-noise=0": ["ts-order-service","ts-station-service"]}` to a temp file, assert `parse_ranked_output("", path) == ["ts-order-service","ts-station-service"]`.
>
> Run the test suite before stopping: `python -m pytest tests/ -q`. All tests must pass. If any fail, fix the code, not the test.
>
> **Do NOT commit.** Stop when files exist and tests pass. Report: which files you created, the pytest output, any deviations from the spec that you had to make (and why).

### Slice D — K8s manifests

**Subagent prompt:**

> You are creating the in-cluster Kubernetes manifests for the TraceRCA-CD live deployment in an isolated worktree. The architectural spec is in `docs/architecture.md`. Read §2.1 (kind config) and §2.2 (OTel Collector deployment) verbatim — they contain the YAML you must write to disk.
>
> Create these files exactly as they appear in §2.1 and §2.2 of the architecture document. Preserve indentation, field order, and comments. The architecture's YAML is the spec; your job is to land it on disk.
>
> 1. `deploy/k8s/kind-config.yaml`
> 2. `deploy/k8s/otel-collector/00-namespace.yaml`
> 3. `deploy/k8s/otel-collector/10-configmap.yaml`
> 4. `deploy/k8s/otel-collector/20-deployment.yaml`
> 5. `deploy/k8s/otel-collector/30-service-clusterip.yaml`
> 6. `deploy/k8s/otel-collector/31-service-nodeport.yaml`
>
> Then run static validation:
>
> - `python -c 'import yaml,glob; [yaml.safe_load_all(open(f)) for f in glob.glob("deploy/k8s/**/*.yaml", recursive=True)]'` — must succeed without exception
> - If `kubectl` is installed locally, run `kubectl apply --dry-run=client -f deploy/k8s/otel-collector/ --validate=false` to confirm shape. If `kubectl` is absent, skip this and note it.
>
> Do NOT run `kind create cluster` or `kubectl apply`. The purpose is artifact authoring, not deployment.
>
> **Do NOT commit.** Stop when files exist and validation succeeds. Report: list of files created, validation output, anything unexpected.

### Slice E — Host stack compose + configs

**Subagent prompt:**

> You are creating the host-side docker-compose stack and configs for the TraceRCA-CD live deployment in an isolated worktree. The architectural spec is in `docs/architecture.md` — read §2.3 (Tempo), §2.5 (Prometheus), §2.6 (Alertmanager), §2.7 (compose stack) verbatim.
>
> Create these files exactly as they appear in the architecture document:
>
> 1. `deploy/compose/docker-compose.yaml` — §2.7
> 2. `deploy/compose/tempo.yaml` — §2.3
> 3. `deploy/compose/prometheus.yml` — §2.5
> 4. `deploy/compose/alertmanager.yml` — §2.6
>
> Validation:
>
> - `python -c 'import yaml; [yaml.safe_load(open(f)) for f in ["deploy/compose/docker-compose.yaml","deploy/compose/tempo.yaml","deploy/compose/prometheus.yml","deploy/compose/alertmanager.yml"]]'` — must succeed
> - If `docker compose` is available locally, run `docker compose -f deploy/compose/docker-compose.yaml config -q` to confirm syntax. Otherwise skip and note it.
> - Confirm `prometheus.yml` references `/etc/prometheus/rules/*.yaml`, which is the in-container mount point for `slo/generated/` (mounted by `docker-compose.yaml`). Cross-check the mount path matches the rule_files glob.
>
> Do NOT run `docker compose up`. Artifact authoring only.
>
> **Do NOT commit.** Stop when files exist and validation succeeds. Report files created, validation output.

### Slice F — SLO specs + generated Sloth rules

**Subagent prompt:**

> You are creating the SLO definitions for the TraceRCA-CD live deployment in an isolated worktree. The architectural spec is in `docs/architecture.md` §2.4 — that section contains the AlertWindows catalog and a full Sloth spec for `ts-order-service`. You must produce the analogous spec for the other four RE2TT services and (if Docker is available) the Sloth-generated rules.
>
> Files to create:
>
> 1. `slo/windows/short-catalog.yaml` — copy verbatim from §2.4 (the `AlertWindows` block).
>
> 2. `slo/specs/ts-order.yaml` — copy verbatim from §2.4 (the `version: "prometheus/v1"` block).
>
> 3. `slo/specs/ts-auth.yaml`, `slo/specs/ts-route.yaml`, `slo/specs/ts-train.yaml`, `slo/specs/ts-travel.yaml` — produce by templating the `ts-order` spec: replace every occurrence of `ts-order` with `ts-auth` / `ts-route` / `ts-train` / `ts-travel`, and replace `TsOrder` (in `alerting.name`) with `TsAuth` / `TsRoute` / `TsTrain` / `TsTravel`. The `service_name` label values use the full `ts-{X}-service` form. Keep latency-budget identical (500ms) and objective identical (99.0%) across all five services — per architecture.md §6, the experimental control is "same algorithm + same SLO config" across services, so varying budgets would confound results. Add a comment at the top of `ts-order.yaml` only: "Post-deploy: verify `status_code` label value matches `STATUS_CODE_ERROR` against the live /metrics scrape; if the spanmetrics feature gate `useOtelPrefix` is on, change to `otel_status_code`."
>
> 4. `slo/generated/` directory must exist (committed, even if currently empty). Create an empty `.gitkeep` if no rules generated.
>
> If `docker` is available on this worktree's host:
>
> 5. Run the generation step from architecture.md §2.4:
>    ```bash
>    docker run --rm \
>      -v "$PWD/slo/specs:/in:ro" \
>      -v "$PWD/slo/generated:/out" \
>      -v "$PWD/slo/windows:/windows:ro" \
>      ghcr.io/slok/sloth:v0.12.0 \
>      generate -i /in -o /out --default-slo-period=30d --slo-period-windows-path=/windows
>    ```
>
>    This produces `slo/generated/ts-{auth,order,route,train,travel}.rules.yaml`. Inspect one and confirm it contains both `sloth-slo-sli-recordings-*` and `sloth-slo-alerts-*` groups, plus alert rules with `sloth_severity` and `service_name` labels per the §2.4 sample. Commit these files alongside the specs.
>
>    If `docker` is not available or the generation fails: leave `slo/generated/.gitkeep` and note in your report that the generation step is deferred to deploy time. The architecture's §5.3.2 covers running it then.
>
> Validation:
> - Every YAML file is parseable: `python -c 'import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob("slo/**/*.yaml", recursive=True)]'`
>
> **Do NOT commit.** Stop when files exist and validation succeeds. Report: files created, whether Sloth generation ran (and its output if so), any anomalies.

### Slice G — Chaos manifests (30 files)

**Subagent prompt:**

> You are creating Chaos Mesh manifests for the TraceRCA-CD live deployment in an isolated worktree. The architectural spec is in `docs/architecture.md` §2 / Subagent D's chaos manifests appear in the "Chaos manifests" subsection of the K8s deployment plan (and §5 of the K8s-side subagent transcript referenced from there; if uncertain, the canonical YAML is in architecture.md's K8s side discussion or `docs/handoff-architecture-design.md`). Read the chaos-manifest examples in `docs/architecture.md` — Subagent D's report produced six for `ts-order`. Reproduce all six **and** generalize to the other four services for 30 manifests total.
>
> File matrix: `chaos/{fault}_{service}.yaml` where:
> - `{fault}` ∈ {`cpu`, `memory`, `network-delay`, `network-loss`, `http-error`, `http-delay`}
> - `{service}` ∈ {`ts-auth`, `ts-order`, `ts-route`, `ts-train`, `ts-travel`}
>
> Per-manifest rules:
> - All have `metadata.namespace: chaos-mesh`, `metadata.name: {fault}-{service}`, `spec.selector.namespaces: [ts]`, `spec.selector.labelSelectors.app: ts-{service}-service`, `spec.duration: "3m"`, `spec.mode: all`.
> - StressChaos manifests have the stressors from §2 — `cpu: {workers: 4, load: 100}` or `memory: {workers: 1, size: "512MB"}`.
> - NetworkChaos manifests have `delay: {latency: "1s", jitter: "100ms", correlation: "25"}` or `loss: {loss: "30", correlation: "25"}`.
> - HTTPChaos manifests have `target: Response` + `replace: {code: 500}` for `http-error`, and `target: Request` + `delay: "2s"` for `http-delay`. Both use `port: 8080`. Both carry a top-of-file comment: `# NOTE: HTTPChaos has no per-request percentage knob. mode: all applies to all matching pods for the duration; this approximates 'inject 50% of requests' only in the time-integral sense. See docs/architecture.md §10.2.`
>
> Use the architecture.md `ts-order` examples as the canonical shape and substitute service names.
>
> Validation:
> - `python -c 'import yaml,glob; assert len(glob.glob("chaos/*.yaml"))==30; [yaml.safe_load(open(f)) for f in glob.glob("chaos/*.yaml")]'`
> - For each file, assert `spec.selector.labelSelectors.app == f"ts-{service}-service"` matches the filename's service segment.
>
> **Do NOT commit.** Stop when 30 files exist and validation succeeds. Report files created and validation output.

---

## Phase 2 — Two parallel subagents (Slice A must be merged first)

Before spawning Phase 2: confirm with the human that Slice A is merged into `main` (you should already have received a "continue" after Phase 1's Slice A commit notification). The Phase 2 worktrees are created from `main`, which now contains `src/tracerca/{converter,schema,tempo_client,ranked_output}.py`. Spawn both subagents in a single message with two `Agent` tool calls.

### Slice B — Trainer + inference CLI + shim

**Subagent prompt:**

> You are implementing the trainer, inference CLI, and Alertmanager shim for the TraceRCA-CD live deployment in an isolated worktree. The architectural spec is in `docs/architecture.md` — read §3.4 (trainer), §3.5 (inference CLI), §3.6 (control model recipe), §3.7 (shim) verbatim before writing code.
>
> Slice A landed `src/tracerca/{converter,schema,tempo_client,ranked_output}.py` on `main`. You depend on those. Import them, do not re-implement.
>
> Files to create:
>
> 1. `src/tracerca/train.py` — `python -m tracerca.train` entry point (Click). Implements the trainer per §3.4. Default hyperparameters per §3.4's `hp.yaml` block **with one change: `caller_discount_alpha: 1.5`** (the human resolved this — see "Resolved decisions" in `docs/implementation-prompt.md`). Subprocess calls to the vendored `run_invo_encoding.py` and `run_anomaly_detection_prepare_model.py` per §3.4. Writes sidecar JSON via `tracerca.schema.write_sidecar`.
>
> 2. `src/tracerca/__main__.py` — `python -m tracerca` entry point (Click). Implements the inference CLI per §3.5. Steps 1–11 from §3.5 must each be its own helper function so they're independently testable. Exit codes 0/2/3/4 per §3.5. Appends one JSONL line to `eval/eval.jsonl` with the schema in §3.5 step 11. `model_id` is `f"{Path(model_path).stem}@{sha256(model_bytes)[:8]}"`.
>
> 3. `src/shim.py` — single file, stdlib-only HTTP server per §3.7. Copy the implementation from §3.7 verbatim (it's ~25 lines). Add a single docstring at the top: `"""Alertmanager webhook → tracerca CLI. See docs/architecture.md §3.7."""`. Nothing else. No retries, no auth, no health endpoint — those are explicitly out of scope.
>
> 4. `src/tracerca/default_hyperparams.yaml` — the default hyperparams YAML so it can be referenced from the trainer and tests. Same shape as §3.4 with `caller_discount_alpha: 1.5`.
>
> Tests:
>
> 5. `tests/test_train_cli.py` — assert the Click command exposes the right options (`--baseline-source`, `--window`, `--out`, `--tempo-url`, `--hyperparams`). Assert reading `default_hyperparams.yaml` parses cleanly and contains `caller_discount_alpha: 1.5`. Do NOT run the trainer end-to-end — it depends on the vendored scripts which depend on Tempo. End-to-end runs in the deploy session.
>
> 6. `tests/test_inference_cli.py` — same pattern as the trainer: assert the Click surface matches §3.5. Mock `TempoClient.fetch_traces` to return empty; assert the CLI exits 3 with the documented message. Mock it to return a fixed synthetic trace iterable; mock `subprocess.run` for the three vendored-script calls to write a dummy output pkl; assert one well-formed JSONL line lands in `eval/eval.jsonl` with the expected keys (`invoke_time`, `complete_time`, `service`, `window`, `input_pkl_path`, `ranked_list`, `model_id`, `model_path`, `source: "cli"`).
>
> 7. `tests/test_shim.py` — start the shim in a thread; POST a synthetic Alertmanager v4 payload with `labels.service_name=ts-order-service`; mock `subprocess.run` (monkeypatch it before the shim starts) so the CLI doesn't actually run; assert (a) the POST returns 200 instantly, (b) a JSONL line is written to `eval/eval.jsonl` with `source: "shim"`, `service: "ts-order-service"`, and `complete_time > invoke_time`.
>
> Run `python -m pytest tests/ -q`. All tests must pass.
>
> **Do NOT commit.** Stop when files exist and tests pass. Report.

### Slice C — Eval harness

**Subagent prompt:**

> You are implementing the eval harness (chaos wrapper + experiment runner + analysis) for the TraceRCA-CD live deployment in an isolated worktree. The architectural spec is in `docs/architecture.md` §8 — read all of it verbatim before writing code.
>
> Slice A is on `main`. You don't import directly from `tracerca/*` but your `analysis.py` reads the same `eval/eval.jsonl` shape that the CLI/shim write (defined in §3.5 step 11) and the `eval/ground_truth.jsonl` shape that `chaos_apply.py` writes (defined in §8.1). Keep these schemas in sync.
>
> Files to create:
>
> 1. `src/chaos_apply.py` — verbatim from §8.1 (~12 lines). No additions.
>
> 2. `src/eval_runner.py` — verbatim from §8.2 (~120 lines, serial loop reading YAML spec). Add a `--dry-run` flag that logs every `kubectl apply` / `kubectl delete` it *would* invoke and the sleep durations, but doesn't actually subprocess. This makes the runner testable without K8s.
>
> 3. `src/analysis.py` — implements §8.3. Joins `eval.jsonl` × `ground_truth.jsonl` per the proximity rule (first eval line with `complete_time > apply_time` and matching `service`, within `fault_duration_s + 5min`). Computes AC@1, AC@3, Avg@5 per [the RCAEval paper's definitions](https://arxiv.org/abs/2412.17015): AC@K = 1 if ground-truth root cause appears in the top-K ranked list else 0; Avg@5 = mean of AC@1..AC@5. MTTL = `complete_time - apply_time`. Outputs a per-fault-type table (use `pandas` or hand-rolled formatting — either is fine) and an overall row. Add `--model-id` filter to slice live vs control. SLO trigger precision/recall by checking whether each ground-truth fault has a matching eval-line `service` and the eval line's `invoke_time` falls within `[apply_time, apply_time + 5min]`; precision = matched_alerts / total_eval_lines, recall = matched_faults / total_faults.
>
> 4. `experiments/re2tt-replication.yaml` — verbatim from §8.2. List 5 services × 6 fault types × 3 replicates.
>
> 5. `experiments/sampling-sweep.yaml` — same shape as `re2tt-replication.yaml` but with `replicates_per_combo: 1` and a comment at the top: `# Run once per probabilistic_sampler.sampling_percentage in {100, 10, 1}. Operator flips the OTel Collector ConfigMap between runs.`
>
> Tests:
>
> 6. `tests/test_analysis.py` — hand-write a small `eval.jsonl` (3 lines) and `ground_truth.jsonl` (3 lines) covering: (a) a perfect match where the ranked list's first entry is the target — AC@1=1; (b) a match where the target is rank-3 — AC@3=1 but AC@1=0; (c) an unmatched ground-truth fault (no eval line in window) — counts against recall. Run `analysis.py` against these and assert the per-fault and overall metrics match hand-calculated values.
>
> 7. `tests/test_eval_runner.py` — invoke `eval_runner.py --dry-run` against a minimal experiments YAML; assert the logged actions match the spec (count, ordering).
>
> 8. `tests/test_chaos_apply.py` — monkeypatch `subprocess.run`; invoke `chaos_apply.py`; assert `ground_truth.jsonl` gains one well-formed line and `subprocess.run` was called with `["kubectl","apply","-f", <manifest>]`.
>
> Run `python -m pytest tests/ -q`. All tests must pass.
>
> **Do NOT commit.** Stop when files exist and tests pass. Report.

---

## When all Phase 2 work is committed

You are done. Print a final summary:

```
=== Implementation complete ===
8 commits landed across 8 slices. Architecture-document compliance: verified at slice level.

Next steps for the human:
  1. Run the deploy plan in docs/architecture.md §5.
  2. Run the baseline-training step (§5.4) — produces models/model_live.pkl.
  3. (Optional) Produce models/model_re2tt.pkl per §5.5.
  4. Run the E2E verification recipe in §6.
  5. Then `python -m src.eval_runner experiments/re2tt-replication.yaml`.

Open items still flagged from docs/architecture.md §10 that this implementation did NOT resolve:
  - §10.2 HTTPChaos request-percentage: manifests use mode: all; document the deviation in the writeup.
  - §10.4 status_code label name: verify post-deploy; SLO specs carry a reminder comment.
  - §10.6 OperationsPAI fork master SHA: record at clone time during deploy.
  - §10.8 run_invo_encoding directory vs file: confirm at first trainer run.
  - §10.9 Locust load profile parameters: document in the writeup; 50/5/30min defaults applied.
```

---

## Operating rules (the orchestrator must follow these)

1. **Do not run kubectl, helm, or `docker compose up`.** Only `docker run --rm ghcr.io/slok/sloth:...` (read-only artifact generation) is permitted, and only inside Slice F.
2. **Do not commit on behalf of the human.** All commits are the human's.
3. **Read `docs/architecture.md` before spawning anything.** The subagent prompts above tell each agent to read it, but you also need to know the contents to validate their reports.
4. **Spawn Phase 1 subagents in a single message.** Five parallel `Agent` calls in one tool-use block. Same for Phase 2 (two calls).
5. **Surface every commit-ready point.** Pause until the human says "continue." If the human says "skip slice X" or "abandon slice X," remove that slice's worktree branch from your mental model and proceed.
6. **If a subagent fails or stalls,** report exactly what failed and do not retry the same prompt blindly. Diagnose first.
7. **When the user references `tasks/lessons.md`,** record any corrections they make to your workflow there — that file is the project's self-improvement log (see this repo's `CLAUDE.md`).
