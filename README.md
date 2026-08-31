# Aegis — an institutional fleet that audits automated decisions before they harm people

**One-sentence pitch:** Aegis is a Fortified Enterprise Fleet of governed AI agents that sits alongside any automated eligibility/claims/benefits engine, independently re-adjudicates each decision against the real governing rules, and blocks or flags decisions that a formal solver proves are contradictory or unsupported — with a hash-chained audit trail that can be replayed and forked.

**Cold-open (demo second 0–20):** "In 2022, Cigna's PxDx system denied 300,000 medical claims in two months — 1.2 seconds of review per claim. UnitedHealth's nH Predict denied post-acute care for elderly patients and was reversed 90% of the time on appeal, because it counted on the fact that only 0.2% of patients appeal. Ninety-one-year-old Gene Lokken lost his coverage after 19 days. Here is what our system would have done." Then show Aegis intercepting a denial on real data.

**Why it's not saturated:** No ADK-hackathon or Gemini-competition winner has built an *oversight/governance layer for automated decisions*. Past winners built the decision-makers (SalesShortcut, Energy Agent) — nobody built the auditor.

**Track & secondary prizes:** Primary = **Fortified Enterprise Fleet ($20k)**; strongest **Grand Prize ($50k)** candidate because it maximally exercises the newest Google infra. Also plausibly **Best Architectural Design ($5k)** and **Individual/Hobbyist ($10k)** — only one prize per project.

---

## The one design decision that matters

**The solver holds the verdict. The model does not.**

Gemini reviews every case against the same compiled constraints the Z3 solver sees, and writes the rationale a claimant will read. What it cannot do is clear a flag. Its verdict is measured against the binding solver result and recorded as one of three postures:

| Posture | Meaning | Effect on the outcome |
| --- | --- | --- |
| `concur` | Model agrees with the solver | None; it supplied the rationale |
| `escalate` | Model wants *more* scrutiny than the constraints require | Decision is flagged for human review |
| `dissent` | Model wants a more permissive outcome than the constraints support | Recorded, **not honoured** |

Every outcome Aegis produces is reachable from the Z3 result alone. That asymmetry is the answer to the obvious objection about an AI system auditing AI systems, and it is enforced in code ([`adjudicator.py`](services/api/app/agents/adjudicator.py)) and pinned by tests, not by a prompt.

---

## What actually runs today

A decision takes seven hops. Every hop opens an OpenTelemetry span, and every hop is sealed into an append-only ledger where each entry commits to its predecessor by SHA-256.

| # | Hop | Agent | What it does |
| --- | --- | --- | --- |
| 0 | `decision.received` | Intake | Normalises the inbound decision, opens the ledger |
| 1 | `shield.input` | Model Armor | Screens claim narrative for injection, tool poisoning, PII. **Fails closed** |
| 2 | `rules.loaded` | Rules ingestion | Loads the governing policy for the case |
| 3 | `solver.completed` | Reconcile | Z3 evaluation; minimal unsat core when the source decision contradicts the rules |
| 4 | `adjudication.completed` | Re-adjudication | Gemini on Vertex, structured output, advisory only |
| 5 | `shield.output` | Output shield | Screens the generated rationale before it is stored or shown |
| 6 | `verdict.sealed` | Replay ledger | Seals the status and commits the chain |

Two interchangeable runtimes execute those seven steps:

- **`adk`** — a real ADK `SequentialAgent`. The deterministic hops are `BaseAgent` subclasses; re-adjudication is an `LlmAgent` bound to `gemini-2.5-flash` on Vertex with a Pydantic response schema, so the model leg runs *through* ADK rather than beside it.
- **`local`** — the same seven steps in process. No ADK, no network, no credentials.

They share [`steps.py`](services/api/app/agents/steps.py), so they produce the same ledger, the same spans and the same record — [pinned by a parity test](services/api/tests/test_fleet.py). This is why CI needs no Google project and the suite runs offline in under two seconds.

### Replay and fork

The ledger is not a status column, it is a chain. That makes two things possible:

**Replay.** Re-read the chain and recompute it. Edit one byte of one payload after the fact and verification reports exactly which entry broke.

**Fork.** Resume from any step, substitute a fact, re-execute only what comes after. Steps before the fork point are *not* re-run — they are replayed out of the log carrying the original hashes forward as provenance, and marked `*.replayed` in the new record. So "replay to the point of denial, correct the rule, re-execute" produces a record that is honest about which parts were observed and which were recomputed.

```
AD-5EEC1B1A  denied -> flagged
  0  decision.received      3820660b72
  1  shield.input           c47cb2b37c
  2  rules.loaded           7ac4c498a1
  3  solver.completed       ff1b5fa196   contradiction found
  4  adjudication.completed 74abe4c241   gemini-2.5-flash (adk/vertex)
  5  shield.output          1228ab4a5f
  6  verdict.sealed         c3dfd06720
  chain: INTACT over 7 entries

AD-00B7C89E  forked from AD-5EEC1B1A after input_shield -> upheld
  [replayed] decision.received.replayed
  [replayed] shield.input.replayed
  [executed] rules.loaded / solver.completed / adjudication.completed / ...
```

---

## Quickstart

```bash
# API — mock mode, no credentials, no spend
python -m venv .venv && .venv/bin/pip install -e "./services/api[dev]"
.venv/bin/pytest services/api                       # 34 passed

# Web
npm install && npm run build

# The whole thing
.venv/bin/uvicorn app.main:app --app-dir services/api --port 8080
```

For the live fleet, `cp .env.example .env` and set `AEGIS_MODE=live`, `AEGIS_GOOGLE_CLOUD_PROJECT` and `AEGIS_GOOGLE_APPLICATION_CREDENTIALS`, then:

```bash
.venv/bin/pip install -e "./services/api[dev,cloud,agents,telemetry,armor]"
python scripts/demo.py            # one denial, audited, forked, plus a blocked injection
.venv/bin/pytest services/api -m live    # hits real Vertex AI; costs money
```

`pytest` runs in mock mode regardless of your `.env` ([`conftest.py`](services/api/tests/conftest.py)) — only `-m live` reaches the network.

### API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Live runtime: mode, fleet runtime, store, ledger, trace exporter |
| `GET /api/v1/fleet` | Agent Registry card for every agent actually wired in |
| `POST /api/v1/decisions` | Audit a decision. `422` if a shield blocks it |
| `GET /api/v1/decisions/{id}/timeline` | The hash-chained ledger and its integrity check |
| `POST /api/v1/decisions/{id}/fork` | Replay to `fork_after`, substitute, re-execute |
| `POST /api/v1/decisions/{id}/replay` | Compatibility alias using the default fork point |
| `GET /api/v1/traces` | Recent ledger entries and, in memory mode, their spans |
| `POST /api/v1/pubsub` | Push endpoint for the decision stream |

---

## Architecture

- **Orchestrator** — ADK `SequentialAgent` routes each decision through the seven hops. (ADK 2.8 marks `SequentialAgent` deprecated in favour of `Workflow`; `Workflow` cannot yet be an `LlmAgent` sub-agent, so `SequentialAgent` stays until it can.)
- **Reconcile** — Z3/SMT. When a denial is inconsistent with the rules, the solver returns a **minimal unsat core** — the smallest contradictory rule set — rendered in plain English with proposed relaxations.
- **Re-adjudication** — `gemini-2.5-flash` on Vertex AI, structured output, advisory posture as above.
- **Replay** — hash-chained event ledger, verifiable and forkable.
- **Model Armor** — hosted screening on both the input and output boundary, layered over a local pattern shield so an outage degrades screening rather than removing it.
- **Agent Observability** — OpenTelemetry spans exported to Cloud Trace; every audit event carries the trace and span id it was recorded under.
- **Infra** — Cloud Run (scale-to-zero, startup probe on `/api/health`), Firestore for decisions and the ledger, Pub/Sub with a dead-letter topic for the decision stream, all in [`infra/`](infra/).

**Real data:** Synthea synthetic patients + CMS coverage criteria (claims/eligibility variant), or openFDA recall data. All public, no PHI.

---

## Status

| Step / track | Owner | Scope | Status |
| --- | --- | --- | --- |
| Step 0 — shared contract | joint | `models.py`, `contracts.py`, `types.ts`, per-view split of `App.tsx`, CI | Merged (`58f8454`) |
| Step 1 — build pipeline | @dasashreeya | Dockerfile, frontend build served by FastAPI, Artifact Registry push | Docker and frontend done; registry push blocked on `terraform apply` |
| Step 1 — cloud runtime | @GIND123 | `terraform apply`, Cloud Run deploy, Pub/Sub push subscription, OpenTelemetry to Cloud Trace | **Config written and reviewed, not applied** — see below |
| Track A — Rules & Solver | @dasashreeya | Policy prose → Gemini extraction → Z3 → minimal unsat core → plain-English relaxation | Built, in review (#1) |
| Track B — Fleet & Adjudication | @GIND123 | ADK `SequentialAgent`, Gemini re-adjudication, Model Armor, Replay/fork ledger | **Built and verified against live Vertex AI** |

### What is not done

Honesty about the gap is the point of the project, so:

- **`terraform apply` has not run.** [`infra/`](infra/) is written and extended (Vertex, Cloud Trace, Model Armor template, Firestore index, dead-letter topic, probes) but neither `terraform` nor `gcloud` is installed on the build machine, so it has never been planned or applied. Until it runs there is no Cloud Run URL, no Artifact Registry push, and no Cloud Trace footage.
- **Model Armor runs local-only** until that template exists. The hosted path is implemented and wired; `/api/v1/fleet` reports the shields as `degraded` rather than pretending otherwise.
- **Memory Bank, Agent Identity and Agent Gateway are not integrated.** `/api/v1/fleet` is an in-application registry, not the Google Agent Registry product.
- **`cached` mode is declared but not implemented** — it currently behaves as `live`.
- Gemma, Groundplan/PDDL and the Antigravity SDK are unstarted, as planned.

### Track A integration

Track B consumes the rules track only through the `Solver` protocol in [`contracts.py`](services/api/app/contracts.py), which has not changed. When #1 merges, extracted constraints flow into the fleet with no edit to `app/agents/`. `RulesIngestionStep` will additionally call an optional `describe_policy(policy_id)` on the solver if the rules track chooses to implement it — absent on the base solver, and not part of the frozen contract.

---

## Demo script (4 minutes)

1. (0:00–0:20) Cold open: the incident, the numbers, the human cost.
2. (0:20–0:50) Value prop + architecture diagram.
3. (0:50–2:20) **Live, unedited:** `python scripts/demo.py` — a denial flows in → Model Armor screens it → Reconcile builds constraints → Z3 returns an unsat core → Gemini writes the rationale and concurs → the ledger seals with an intact chain → Replay forks the timeline to show the correct outcome → a poisoned narrative is blocked and the block is itself sealed.
4. (2:20–3:10) Google Cloud Console: Cloud Run dashboard, Vertex AI logs, the Cloud Trace waterfall, the Model Armor block event.
5. (3:10–3:50) Scale story: the fleet registry, Firestore-backed ledger, Pub/Sub stream with dead-lettering.
6. (3:50–4:00) Close: "If Aegis had been running, this would have been caught."

**Strongest judge objection & preemption:** "Is the Z3/formal layer real or theater?" → Show the unsat core live and the governance rule that keeps the model out of the verdict. Second: "Could this scale to real production data?" → Show the registry, the dead-letter policy and the hash chain; frame synthetic data as a deliberate compliance decision.

---

## Working agreement

Two people, split by LLM role rather than by layer. File-level ownership map, git workflow and prerequisites in [`WORKPLAN.md`](WORKPLAN.md).

**One rule: if a file is not yours, you do not edit it.** Track B touched two files outside its column and both are called out here rather than buried in the diff:

- `tests/test_api.py` — `assert len(result["events"]) == 4` no longer holds now that the fleet emits one event per hop. It is replaced by an assertion on the *sequence* of hop kinds, which is a stronger regression guard than a count.
- `README.md` — rewritten to describe what exists. It was due for a joint rewrite at integration; treat this as the Track B half.
