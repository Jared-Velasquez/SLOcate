# TraceRCA-CD Capstone Research Report
## Defending RE2TT-Offline → Live-Train-Ticket Generalization

---

## 1. Verdict (~200 words)

**Conditional yes.** RE2TT-offline → live Train-Ticket-with-Chaos-Mesh is a **defensible generalization story, but it is the *weaker* of the two plausible readings**, because RE2TT *is itself* the Train-Ticket subset of RCAEval RE2 (Pham et al., FSE'26 / WWW'25, https://arxiv.org/abs/2412.17015). The two evaluation environments share the *same application* (FudanSE Train-Ticket, 64 services) and a heavily overlapping fault catalog (CPU/MEM/DISK/DELAY/LOSS/SOCKET via stress-ng + tc in RE2TT; CPU/network/abort via Chaos Mesh in live). What changes between offline and live is the **system condition**, not the dataset: streaming ingestion, real OTel-Collector lag, head/tail sampling, and event-driven (SLO-triggered) RCA. That distinction is real — and is exactly the gap the original TraceRCA, MicroRank, MicroRCA, Sage, Eadro and Nezha papers do *not* close — but you must frame the contribution as **"offline-algorithm → online-system generalization on the same application family,"** not as "cross-application generalization." To make the cross-*application* claim defensible you would need a third target (Online Boutique or Sock Shop, both already packaged in RCAEval RE1/RE2/RE3). Add that as a stretch goal; without it, lead with the system/streaming generalization framing.

---

## 2. Capstone Framing Memo (~300 words)

The eval section should open with a **single explicit claim**: *"TraceRCA-CD's RE2TT improvements survive the transition from a static, fully-sampled, post-hoc benchmark to a live, sampled, SLO-triggered streaming pipeline on the same application (Train-Ticket), with comparable ranking accuracy and bounded end-to-end latency."* Naming this scope up front pre-empts the obvious reviewer objection that RE2TT and live Train-Ticket are not independent.

Paragraph 2 — **method recap**. Briefly restate RE2TT setup (RCAEval, https://github.com/phamquiluan/RCAEval) and the live pipeline (OTel Collector → SLO breach detector → TraceRCA-CD). Cite Sage (Gan et al., ASPLOS'21, https://www.csl.cornell.edu/~delimitrou/papers/2021.asplos.sage.pdf) and the Google SRE multi-window multi-burn-rate pattern (https://sre.google/workbook/alerting-on-slos/) as precedent for SLO/QoS-violation-triggered RCA — this isn't novel architecture, it is the standard SRE pattern, and saying so disarms reviewers.

Paragraph 3 — **fault catalog**. Reuse the de-facto RCAEval fault catalog (CPU, MEM, DISK, DELAY, LOSS, SOCKET) but inject via Chaos Mesh `StressChaos` / `NetworkChaos` so results are directly comparable to Eadro, Nezha, MicroRank.

Paragraph 4 — **metrics**. Report AC@1, AC@3, Avg@5 (RCAEval-standard) for RCA quality, **plus** SLO-trigger precision/recall, end-to-end MTTL (fault inject → ranked list), throughput (spans/s sustained), and behavior under 1×, 0.1×, 0.01× head sampling. The last four are the gap the original TraceRCA paper did not fill.

Paragraph 5 — **threats to validity**. Acknowledge that Train-Ticket is shared between RE2TT and the live env; mitigate by reporting per-fault-type breakdowns and ideally a stretch run on Online Boutique (RCAEval RE2-OB).

---

## 3. Tables

### 3.1 Generalization-evidence table (surveyed RCA papers)

| Paper / Year | Venue | App(s) used | Fault tool | Online or offline | Metrics | Generalization claim |
|---|---|---|---|---|---|---|
| **TraceRCA** (Li et al. 2021) | IWQoS'21 | Train-Ticket + 1 production system | Custom scripts | Offline post-hoc on collected traces | Top-K, AC@K | "Open-source benchmark + production"; only one OSS benchmark. https://netman.aiops.org/wp-content/uploads/2021/06/TraceRCA-IWQoS2021.pdf `[unverified — fetch blocked]` |
| **MicroRank** (Yu et al. 2021) | WWW'21 | Train-Ticket only | Custom | Offline | Top-K | Single-dataset. https://dl.acm.org/doi/10.1145/3442381.3449905 |
| **MicroRCA** (Wu et al. 2020) | NOMS'20 | Sock Shop on K8s | Manual fault injection (CPU/network) | Online (real-time) | Precision (89%), MAP (97%) | Single-app; demonstrated streaming. https://inria.hal.science/hal-02441640/file/main.pdf |
| **TraceAnomaly** (Liu et al. 2020) | ISSRE'20 | Production WeChat + testbed | Production faults | Offline | Top-K, recall | Production data is the generalization argument. https://github.com/NetManAIOps/TraceAnomaly |
| **Sage** (Gan et al. 2021) | ASPLOS'21 | DeathStarBench (Hotel, Social Net., Media) | Workload + resource throttling | Online (closed-loop with actuator) | QoS-violation recovery time | Multi-app within DeathStarBench family. https://www.csl.cornell.edu/~delimitrou/papers/2021.asplos.sage.pdf |
| **DejaVu** (Li et al. 2022) | FSE'22 | 3 production + Train-Ticket (D) | Chaos scripts on TT | Offline (recurring failures) | HR@K, MRR | Train-on-A/B/C → test-on-D as cross-system test. https://github.com/NetManAIOps/DejaVu |
| **Eadro** (Lee et al. 2023) | ICSE'23 | Train-Ticket + SocialNetwork (DeathStarBench) | Chaos engineering scripts | Offline | HR@K, NDCG | Two-app generalization is explicit selling point. https://arxiv.org/abs/2302.05092 |
| **Nezha** (Yu et al. 2023) | FSE'23 | Train-Ticket (45 cases) + OnlineBoutique (56 cases) | Not explicitly stated; covers return-error, exception, network delay, CPU contention | Offline | AS@K (service), AIS@K (inner-service); 86.67% AS@1 on TT | Two-app generalization is the headline. https://github.com/IntelligentDDS/Nezha |
| **CIRCA** (Li et al. 2022) | KDD'22 | Synthetic + production | Intervention-based | Offline | Top-K | Causal-inference framing. https://netman.aiops.org/wp-content/uploads/2022/08/KDD22-CIRCA.pdf `[unverified — fetch blocked]` |
| **MicroRCA-Agent / MRCA** (2024) | ASE'24 | Multiple via RCAEval | Inherits RCAEval | Offline | AC@K | LLM-agent style; multi-dataset by virtue of RCAEval. https://dl.acm.org/doi/abs/10.1145/3691620.3695485 |
| **RCAEval** (Pham et al.) | ASE'24 / WWW'25 / FSE'26 | Online Boutique + Sock Shop + Train-Ticket; RE1/RE2/RE3 | stress-ng + tc; **not** Chaos Mesh | Offline benchmark | AC@1, AC@3, Avg@5 | The cross-dataset benchmark; 15 baselines, 735 cases. https://arxiv.org/abs/2412.17015 |
| **TORAI / SparseRCA** (2024) | ASE'24 / ISSRE'24 | RCAEval datasets + sparse-trace setting | Inherits | Offline | AC@K | Generalization-via-RCAEval becoming the new norm. https://dl.acm.org/doi/10.1145/3691620.3695485 |
| **Causal-Inference RCA Survey** (Wu et al. 2024) | arxiv | — | — | — | — | "CausalRCA performs well on Online Boutique and Sock Shop but badly on synthetic" — cross-dataset drops are the norm. https://arxiv.org/abs/2408.13729 |
| **RCA Comprehensive Survey** (Yu et al. 2024) | arxiv | — | — | — | — | Names generalizability and online deployment as open problems. https://arxiv.org/abs/2408.00803 |

**Pattern:** the field's *de facto* defense of generalization is "evaluate on ≥2 OSS benchmarks (Train-Ticket + DeathStarBench/SocialNetwork or Train-Ticket + OnlineBoutique)." Single-benchmark papers (MicroRank, original TraceRCA on TT alone) get critiqued. Live/streaming evaluation is *much rarer* — Sage and MicroRCA are the main exceptions. **A live Train-Ticket pipeline is therefore a genuine differentiator even if the application overlaps with RE2TT.**

### 3.2 Train-Ticket fault catalog (de facto standard)

Compiled from RCAEval RE2 (https://arxiv.org/abs/2412.17015), Nezha (https://github.com/IntelligentDDS/Nezha), Eadro replication packages, and Chaos Mesh docs (https://chaos-mesh.org/).

| Fault category | Concrete fault | RCAEval (RE2) injection | Equivalent Chaos Mesh primitive | Typical params used in literature |
|---|---|---|---|---|
| Resource — CPU | CPU hog / contention | `stress-ng --cpu N --cpu-load X` | `StressChaos` (`stressors.cpu`) | 1–4 workers, 80–100% load, 1–5 min |
| Resource — Memory | Memory leak / pressure | `stress-ng --vm N --vm-bytes Y` | `StressChaos` (`stressors.memory`) | 256MB–1GB, 1–5 min |
| Resource — Disk | Disk I/O saturation | `stress-ng --hdd N` or `dd` | `IOChaos` (`latency` / `errno`) | 1–4 workers, 1–5 min |
| Resource — Socket | FD/socket exhaustion | `stress-ng --sock N` | `StressChaos` (custom) | 1–5 min |
| Network — Delay | Latency injection | `tc qdisc … netem delay Xms` | `NetworkChaos` (`action: delay`) | 100ms–5s, jitter 10–100ms |
| Network — Loss | Packet loss | `tc qdisc … netem loss X%` | `NetworkChaos` (`action: loss`) | 5–50% loss |
| Network — Partition | Connection abort | iptables drop | `NetworkChaos` (`action: partition`) | 30s–5min |
| Application — Return error | Wrong return / exception | Code-injection / proxy | `HTTPChaos` (`action: replace`) | HTTP 500 on K% of requests |
| Application — Latency | Per-request slowdown | Code injection | `HTTPChaos` (`action: delay`) | 500ms–5s on K% of requests |

**Recommended capstone catalog (Chaos Mesh on live Train-Ticket):**
1. `StressChaos.cpu` (3-min, 4 workers, 100% load)
2. `StressChaos.memory` (3-min, 512MB)
3. `NetworkChaos.delay` (3-min, 1s, jitter 100ms)
4. `NetworkChaos.loss` (3-min, 30%)
5. `HTTPChaos.replace` (3-min, HTTP 500 on 50%)
6. `HTTPChaos.delay` (3-min, 2s on 50%)

Targets: rotate across 5 services per RCAEval convention; pick high-in-degree services (`ts-order-service`, `ts-travel-service`, `ts-seat-service`, `ts-station-service`, `ts-basic-service`).

### 3.3 Comparable-systems table (commercial + OSS)

| System | Trigger model | RCA technique (disclosed) | OTel-native? | OSS? | Source |
|---|---|---|---|---|---|
| **Datadog Watchdog RCA** | Continuous (anomaly 24/7) | Causal-relationship correlation across APM + infra (state-change graph: deploy/infra/traffic) | Ingests OTel | No | https://docs.datadoghq.com/watchdog/rca/ |
| **Dynatrace Davis AI** | Continuous + alert-driven | Deterministic causal graph traversal over Smartscape topology + Grail | Yes | No | https://docs.dynatrace.com/docs/discover-dynatrace/platform/davis-ai |
| **New Relic Applied Intelligence** | Anomaly + alert correlation | Time / context / topology correlation; LLM summarization. RCA technique only partially disclosed. | Yes | No | https://newrelic.com/platform/applied-intelligence |
| **Grafana Cloud Asserts** | Continuous (SAAFE assertions) + alert-driven RCA Workbench | Knowledge graph + assertion rules; not ML | Yes | Closed (host stack OSS) | https://grafana.com/products/cloud/asserts/ |
| **Honeycomb BubbleUp + Anomaly Detection** | Anomaly-triggered + interactive | Statistical comparison of attribute distributions (selection vs baseline) | Yes (OTel-first) | No | https://www.honeycomb.io/platform/bubbleup |
| **Causely** | SLO/symptom-driven | Explicit causal model ("Causality Graph" + Codebook); not LLM-only | Yes (OTel + K8s) | No | https://www.causely.ai/blog/how-causal-ai-is-transforming-sre-reliability-in-k8s |
| **Lightstep / ServiceNow Cloud Obs.** | Anomaly + change-event correlation | "Change Intelligence" — span-to-deploy correlation | Yes | No | `[unverified — fetch blocked]` |
| **Chronosphere** | Alert-driven | Trace-event correlation; method largely undisclosed | Yes | No | `[unverified — fetch blocked]` |
| **Pixie** | On-demand + scripted | eBPF data collection; RCA is user-script driven | Yes (exports OTel) | Yes | https://github.com/pixie-io/pixie |
| **DeepFlow** | Continuous | eBPF + SmartEncoding correlation graph | Yes | Yes | https://github.com/deepflowio/deepflow |
| **Pyrra** | SLO burn-rate (multi-window multi-burn-rate); generates Prom rules | Trigger only — not RCA | Prom-native | Yes | https://pyrra.dev/ |
| **Sloth** | SLO burn-rate (MWMBR); Prom rule generator | Trigger only — not RCA | Prom-native | Yes | https://sloth.dev/ |
| **Nobl9** | SLO burn-rate, multi-source | SLO orchestrator — not RCA | Multi-source | No (OpenSLO is OSS spec) | `[unverified — fetch blocked]` |
| **Keptn** | SLO/SLI quality gates in CD | Not RCA | Yes | Yes | `[unverified — fetch blocked]` |
| **Robusta** | Alert-driven enrichment for Prom alerts | LLM + playbook diagnosis | Prom-native | Yes | `[unverified — fetch blocked]` |

**Q5 takeaways:**

1. **SLO-burn-rate-as-trigger** is a recognized SRE pattern (Google SRE Workbook, https://sre.google/workbook/alerting-on-slos/) with mature OSS implementations (Pyrra, Sloth) — the *trigger* layer is conventional.
2. **SLO-trigger → ML-RCA pipeline** in OSS is **rare**: Pyrra/Sloth/Keptn handle the trigger; nothing OSS chains a published academic RCA algorithm onto that trigger end-to-end. Commercial products (Datadog, Dynatrace, Causely) do this internally with proprietary methods. **This is the genuine novelty of the capstone architecture.**
3. **OTel-native ingest** is now standard across both commercial and OSS — no novelty there.
4. **Vendor "AI-powered RCA"** disclosures vary: Dynatrace Davis is the most explicit (deterministic causal graph over Smartscape); Datadog discloses partial structure; New Relic and Chronosphere are vague; Causely explicitly rejects LLM-only framing in favor of explicit causal models.

---

## 4. Annotated reading list (12 entries)

1. **Li et al., "Practical Root Cause Localization for Microservice Systems via Trace Analysis" (TraceRCA), IWQoS 2021.** https://netman.aiops.org/wp-content/uploads/2021/06/TraceRCA-IWQoS2021.pdf · https://github.com/NetManAIOps/TraceRCA. Direct ancestor: unsupervised trace-anomaly + frequent-pattern mining + spectrum ranking.
2. **Pham et al., "RCAEval," ASE'24 / WWW'25 / FSE'26.** https://arxiv.org/abs/2412.17015 · https://github.com/phamquiluan/RCAEval. Defines RE1/RE2/RE3 across Online Boutique, Sock Shop, Train-Ticket; RE2 introduces multi-source data with 6 fault types via stress-ng + tc. RE2-TT is your offline anchor.
3. **Yu et al., "MicroRank," WWW 2021.** https://dl.acm.org/doi/10.1145/3442381.3449905 · https://github.com/IntelligentDDS/MicroRank. PageRank-weighted spectrum ranking on Train-Ticket.
4. **Lee et al., "Eadro," ICSE 2023.** https://arxiv.org/abs/2302.05092 · https://github.com/BEbillionaireUSD/Eadro. Anomaly + localization unified via multi-task learning over traces+logs+KPIs; TT + DeathStarBench-SocialNetwork. Gold standard for cross-app generalization framing.
5. **Yu et al., "Nezha," FSE 2023.** https://dl.acm.org/doi/abs/10.1145/3611643.3616249 · https://github.com/IntelligentDDS/Nezha · https://zenodo.org/records/8276375. TT (45 cases) + OnlineBoutique (56 cases); reports AS@K and AIS@K; 86.67% AS@1 on TT. Most directly comparable two-app eval to your target.
6. **Gan et al., "Sage," ASPLOS 2021.** https://www.csl.cornell.edu/~delimitrou/papers/2021.asplos.sage.pdf. CBN + GVAE counterfactuals; **online closed-loop on QoS violation** — precedent for SLO-trigger-as-RCA-trigger.
7. **Wu et al., "MicroRCA," NOMS 2020.** https://inria.hal.science/hal-02441640/file/main.pdf. Real-time, agentless, anomalous-subgraph extraction. The other key online-streaming precedent.
8. **Liu et al., "TraceAnomaly," ISSRE 2020.** https://github.com/NetManAIOps/TraceAnomaly. VAE on service-trace vectors; production WeChat dataset.
9. **Li et al., "DejaVu," FSE 2022.** https://github.com/NetManAIOps/DejaVu. Four datasets including Train-Ticket as dataset D; train/test split methodology.
10. **Li et al., "CIRCA," KDD 2022.** https://netman.aiops.org/wp-content/uploads/2022/08/KDD22-CIRCA.pdf `[unverified]`. Causal-inference; included as RCAEval baseline.
11. **Wu et al., "Root Cause Analysis for Microservice System based on Causal Inference: How Far Are We?," ASE 2024.** https://arxiv.org/abs/2408.13729. Empirical re-evaluation showing the cross-dataset performance drop you must defend against. Cite as the threat-to-validity reference.
12. **Yu et al., "A Comprehensive Survey on RCA in (Micro)Services," 2024.** https://arxiv.org/abs/2408.00803. Names generalizability + online deployment as open problems.

**Honorable mentions:** *Trace-based Multi-Dimensional RCA* (Zhang et al., ICSE'24, https://zhendong2050.github.io/res/ICSE24.pdf); *SparseRCA* (ISSRE'24) — directly relevant since "sparse traces" = sampling; *Failure Diagnosis Survey* (TOSEM 2024) https://dl.acm.org/doi/full/10.1145/3715005.

---

## 5. Recommended operational metrics

| Metric | Definition | Why it matters / why TraceRCA-original lacked it |
|---|---|---|
| **AC@K** (k=1,3,5) | Fraction of cases where ground-truth service appears in top-K. RCAEval-standard. | Direct comparability to RE2TT, Eadro, Nezha, MicroRank. |
| **Avg@K** (k=5) | Mean of AC@k for k=1..K. | RCAEval-standard summary. |
| **MAR / MRR** | Mean rank / mean reciprocal rank of true root cause. | DejaVu and Eadro report MRR. |
| **MTTL (Mean Time-To-Localize)** | Wall-clock from `chaos-mesh apply` → ranked list. Decompose: trigger latency (fault → SLO breach) + RCA latency (breach → ranked list). | Sage and MicroRCA report QoS-recovery time; offline papers don't. **Headline streaming metric.** |
| **Trigger precision / recall** | Of all SLO-burn-rate alerts, what fraction = injected faults (precision); what fraction of injected faults produced an alert (recall). | Pre-empts "your trigger is biased." |
| **Throughput (spans/sec)** | Sustained rate before queue backpressure or RCA latency exceeds budget. | Operational realism no offline paper can claim. |
| **Sampling robustness** | AC@K at head-sampling 100%/10%/1%; ideally tail-sampling. | Direct response to SparseRCA observation. |
| **Cold-start time** | Service startup → first valid SLO baseline → first usable RCA. | Real systems boot; benchmarks don't. |
| **Memory / CPU footprint** | Peak RSS and CPU% of streaming RCA process. | Operational. |
| **End-to-end time-budget compliance** | % of incidents where ranked list emerges within declared budget (e.g., <2 min). | Frame minute-scale RCA as an SLO of the RCA system itself. |

---

## 6. Threats-to-validity checklist

| Threat | Why it bites | Mitigation in capstone |
|---|---|---|
| **Same-application risk:** RE2TT *is* Train-Ticket; live env is also TT. Not cross-app generalization. | Reviewers will say the two evals aren't independent. | (a) Reframe scope to "offline → online generalization on the same app family"; (b) **stretch run on Online Boutique** (RCAEval RE2-OB); (c) per-fault-type breakdowns. |
| **Fault catalog overlap:** reusing RE2TT's catalog verbatim doesn't test fault-type generalization. | Same critique. | Inject **two extra application-level faults** (HTTP-500 replace, HTTPChaos delay) — *not* in RE2TT (which uses only stress-ng + tc). Report results separately. |
| **"Chaos Mesh faults aren't real faults"** (recurrent chaos-eng critique). | Synthetic ≠ production failures. | Cite Eadro, Nezha, MicroRank, Sage all using chaos-style injection — field standard. Acknowledge limitation; cite TraceAnomaly's WeChat data as the production counterpoint and explain why production data is out of capstone scope. |
| **SLO-trigger bias:** trigger only fires for faults the SLO is sensitive to (latency / error-rate breaches). | Async background failures are invisible. | Define **two SLIs**: request-error-rate and p99 latency. Acknowledge silent-failure class is out of scope, like every other published RCA system. |
| **Sampling bias:** if you only run at 100% head sampling, you're not online — you're RCAEval-with-Kafka. | Defeats the point. | Mandatory ablation at 100/10/1% head sampling; ideally tail sampling via OTel-Collector tail-sampler. |
| **Throughput is a single-number lie** under steady load. | Bursty workloads break pipelines. | Burst test (2–10× normal rate for 60s); report queue-depth + drop rate. |
| **MTTL is gameable** by tuning the SLO window short. | "Did you just shorten the burn-rate window?" | Use the standard Google SRE multi-window multi-burn-rate config (1h/5min, 6h/30min); cite explicitly; don't tune. |
| **Comparison to original TraceRCA isn't apples-to-apples** if original was offline and yours is online. | Yes. | Run TraceRCA *also* under your live pipeline. Report three rows: (i) TraceRCA on RE2TT-offline, (ii) TraceRCA on live-TT, (iii) TraceRCA-CD on live-TT. |
| **"Just engineering, not research"** — common live-deployment critique. | Pipeline-building ≠ contribution. | Frame the contribution as the **operational-metrics gap** + the **SLO-triggered RCA pattern** as a unit, citing that no published OSS work chains this end-to-end. |
| **Reproducibility:** Train-Ticket and Chaos Mesh APIs drift. | Future readers can't rerun. | Pin TT commit, Chaos Mesh version, K8s version, OTel-Collector version. Publish chaos YAMLs RCAEval-style. |

---

## 7. Suggested capstone results-section outline

1. **§5.1 Setup** — versions, OTel-Collector pipeline, fault catalog, service targets, baselines.
2. **§5.2 RQ1 — Does TraceRCA-CD's RE2TT advantage carry to live TT?** Per-fault AC@1/3/5 + Avg@5 table; 3 baseline columns.
3. **§5.3 RQ2 — Operational metrics.** MTTL CDF, throughput-vs-RCA-latency curve, sampling-robustness sweep, cold-start.
4. **§5.4 RQ3 — Trigger calibration.** SLO precision/recall, false-alarm rate over fault-free baseline window.
5. **§5.5 RQ4 (stretch) — Cross-application generalization.** Reduced-scale RCAEval-RE2-OB run.
6. **§5.6 Threats to validity.**
7. **§5.7 Comparison to SOTA.** AC@K vs. published Nezha (TT 86.67% AS@1) and Eadro, *with caveats* about fault-catalog and sampling.

---

## 8. Sources flagged unverified

- `netman.aiops.org/...` PDFs (TraceRCA, TraceAnomaly, DejaVu, CIRCA, Chain-of-Event, SparseRCA) — domain not in WebFetch allowlist. Citations corroborated from search summaries + GitHub READMEs.
- `arxiv.org/pdf/2302.05092` (Eadro full PDF) — fetched as binary, not extractable; abstract page used.
- `nobl9.com`, `chronosphere.io`, `lightstep.com`, `keptn.sh`, `robusta.dev` — outside allowlist.

All ACM, arXiv-HTML, GitHub, IEEE-Xplore, Datadog, Dynatrace, Grafana, Honeycomb, Causely, Sloth, Pyrra, OpenTelemetry, Google SRE links were verified directly.
