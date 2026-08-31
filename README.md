# Aegis — an institutional fleet that audits automated decisions before they harm people

**Live:** https://aegis-708478134642.us-central1.run.app — deployed on Cloud Run from `7508bc8`, with Firestore state, hosted Model Armor, the ADK fleet in `live` mode and OpenTelemetry spans reaching Cloud Trace.

> **The deployed revision is behind `main`.** It was built from `85fecd7`, which predates the Z3 concurrency fix in `c6a4d20`. The service takes 40 concurrent requests per container, and two overlapping decisions are enough to fault inside z3's native library — so production still needs a redeploy. Details in [What is not done](#what-is-not-done).

**One-sentence pitch:** Aegis is a Fortified Enterprise Fleet of governed AI agents that sits alongside any automated eligibility/claims/benefits engine, independently re-adjudicates each decision against the real governing rules, and blocks or flags decisions that a formal solver proves are contradictory or unsupported — with a hash-chained audit trail that can be replayed and forked.

**Cold-open (demo second 0–20):** "Over two months in 2022, Cigna doctors denied more than 300,000 requests for payment using its PxDx system, spending an average of 1.2 seconds on each — without opening the file. UnitedHealth's nH Predict cut off post-acute care for elderly patients and was reversed about 90% of the time on appeal, because only 0.2% of patients appeal at all. Ninety-one-year-old Gene Lokken lost his coverage after 19 days of a 100-day benefit and his family paid $150,000. Here is what our system would have done." Then show Aegis intercepting that exact denial — see [Recreating the incidents](#recreating-the-incidents), which is not a claim, it is a test that runs in CI.

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

## Recreating the incidents

The pitch says Aegis would have caught these. That is checkable, so it is checked. [`incidents/`](incidents/) holds six files, each carrying the sources it was built from, the governing rules with their citations, an explicit note on what in it is reconstructed, and the outcome every decision must reach. [`scripts/incidents.py`](scripts/incidents.py) replays them through the fleet; [`test_incidents.py`](services/api/tests/test_incidents.py) asserts the outcomes on every push.

**52 of 52 cases reached the recorded outcome with an intact ledger chain**, against live `gemini-2.5-flash` on Vertex AI.

| Incident | Operator | Cases | Aegis | Primary source |
| --- | --- | --- | --- | --- |
| nH Predict cut off a 91-year-old's therapy at day 19 | UnitedHealth / NaviHealth | 1 | flagged | [STAT, 14 Nov 2023](https://www.statnews.com/2023/11/14/unitedhealth-class-action-lawsuit-algorithm-medicare-advantage/) |
| nH Predict ended stroke rehab at day 20 against the physician | UnitedHealth / NaviHealth | 1 | flagged | [STAT, 14 Nov 2023](https://www.statnews.com/2023/11/14/unitedhealth-class-action-lawsuit-algorithm-medicare-advantage/) |
| Post-acute cohort at the 22.7% denial rate found for 2022 | UnitedHealthcare | 22 | 5 flagged, 17 upheld | [Senate PSI, 17 Oct 2024](https://www.blumenthal.senate.gov/newsroom/press/release/senate-permanent-subcommittee-on-investigations-releases-majority-staff-report-exposing-medicare-advantage-insurers-refusal-of-care-for-vulnerable-seniors) |
| Bulk denial without opening the file, 1.2 s per claim | Cigna PxDx | 24 | 24 flagged | [ProPublica, 25 Mar 2023](https://www.propublica.org/article/cigna-pxdx-medical-health-insurance-rejection-claims) |
| Denied for not improving, when the rule says improvement is not the test | Jimmo pattern | 1 | flagged | [CMS Jimmo fact sheet](https://www.cms.gov/medicare/medicare-fee-for-service-payment/snfpps/downloads/jimmo_fact_sheet2_022014_final.pdf) · [42 CFR 409.32](https://www.law.cornell.edu/cfr/text/42/409.32) |
| **Control — denials the rules do support** | — | 3 | **3 upheld** | — |

The control set is the one that matters. A layer that flags every denial has told you nothing, so three denials that are *correct* — benefit period exhausted, custodial care with no skilled component, necessity not documented — must come back `upheld`, and the run fails if any of them flags. The cohort carries the same discipline: of its five findings, four are unsupported denials and one is an unsupported **approval**, because oversight that only ever pushes one direction is advocacy.

### The rules, and where they come from

Three constraints do the work, and each is a citation rather than an opinion:

| Constraint | Authority |
| --- | --- |
| `medical_necessity` | [42 U.S.C. §1395y(a)(1)(A)](https://www.law.cornell.edu/uscode/text/42/1395y) — no payment for services not reasonable and necessary for the diagnosis or treatment of illness or injury |
| `skilled_care_required` | [42 CFR §409.31(b)(1)](https://www.law.cornell.edu/cfr/text/42/409.31) — skilled nursing or rehabilitation required on a daily basis |
| `benefit_days_available` | [42 CFR §409.61(b)](https://www.law.cornell.edu/cfr/text/42/409.61); 42 U.S.C. §1395d(a)(2)(A) — up to 100 days per benefit period |

Two more sit behind them as the legal backdrop. [42 CFR §409.32](https://www.law.cornell.edu/cfr/text/42/409.32) says outright that "the restoration potential of a patient is not the deciding factor in determining whether skilled services are needed" — the Jimmo rule, in the regulation itself. And in [guidance issued 6 February 2024](https://www.nortonrosefulbright.com/en/knowledge/publications/644bd9a2/cms-clarifies-medicare-advantage-organizations-use-of-ai-and-algorithms-in-coverage-decisions), CMS told Medicare Advantage plans that a predicted length of stay "cannot be used as the basis to terminate post-acute care services" — termination requires re-assessing the individual patient under §422.101(c). That is a description of the nH Predict failure mode, written by the regulator, ten months after the complaint was filed.

### What Aegis actually proves

A conditional, and it is worth stating precisely because the overclaim is tempting: **given the facts of record, this decision contradicts the rules that govern it.** If the upstream engine misstates the facts, Aegis inherits the misstatement.

That is exactly why this class of failure is the right target. nH Predict did not dispute the clinical facts — the physician's order, the skilled requirement, the days remaining were never in question. It substituted a predicted length of stay for them. The contradiction is therefore visible in the record itself, which is the only place a downstream auditor can ever look.

### The unknown parameter

Lokken's complaint says 19 days were covered. It does not say how many further days his physician ordered, so any single value we picked would be a guess doing load-bearing work. Instead the runner and [a test](services/api/tests/test_incidents.py) sweep every value that fits inside the benefit period — 1 through 81 days — and confirm the contradiction holds at all of them. The finding does not depend on the number we chose.

### Throughput

| | Per decision | 52 cases | Opens the record? |
| --- | --- | --- | --- |
| Cigna PxDx, as reported | 1,200 ms | ~62 s | **No** |
| Aegis, deterministic core (shield + Z3 + ledger) | **85 ms** | 1.0 s | Yes |
| Aegis, full fleet with Gemini rationale | 6,078 ms | 107.8 s | Yes |

Both Aegis rows produce **identical verdicts** — 52 of 52, the same in each direction. That is the governance rule showing up as a measurement rather than a promise: the model writes the explanation, the solver decides, and removing the model changes nothing about who gets flagged. It also means the formal layer audits a claim fourteen times faster than PxDx dismissed one, while actually reading it.

```bash
python scripts/incidents.py --live -c 8 --report docs/incident-report.md
python scripts/incidents.py --mock            # the deterministic core alone
```

---

## Quickstart

```bash
# API — mock mode, no credentials, no spend
python -m venv .venv && .venv/bin/pip install -e "./services/api[dev]"
.venv/bin/pytest services/api                       # 115 passed, incident corpus included

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
python scripts/incidents.py --live -c 8   # replay all six recorded incidents
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
| Step 1 — build pipeline | @dasashreeya | Dockerfile, frontend build served by FastAPI, Artifact Registry push | Done; image builds and serves the SPA |
| Step 1 — cloud runtime | @GIND123 | `terraform apply`, Cloud Run deploy, Pub/Sub push subscription, OpenTelemetry to Cloud Trace | **Deployed.** `/api/health` reports `firestore` store and ledger, `cloud` traces, `hosted` Model Armor |
| Track A — Rules & Solver | @dasashreeya | Policy prose → Gemini extraction → Z3 → minimal unsat core → plain-English relaxation | Merged (`2e19f18`) |
| Track B — Fleet & Adjudication | @GIND123 | ADK `SequentialAgent`, Gemini re-adjudication, Model Armor, Replay/fork ledger | **Built and verified against live Vertex AI** |
| Incident corpus | @GIND123 | Six recorded failures with citations, replayed as a regression suite | 52/52 live |

### What is not done

Honesty about the gap is the point of the project, so:

- **Memory Bank, Agent Identity and Agent Gateway are not integrated.** `/api/v1/fleet` is an in-application registry, not the Google Agent Registry product.
- **`cached` mode is declared but not implemented** — it currently behaves as `live`.
- **The corpus is one policy domain.** All six incidents are Medicare post-acute coverage, because that is the domain `CMS-SNF-100` encodes. Robodebt, Michigan's MiDAS and the Dutch childcare benefits scandal are the obvious next cases and none of them fit this fact schema; adding them means widening `DecisionFacts`, which is a change to the frozen contract and therefore its own PR.
- **The fact schema is the trust boundary.** Aegis re-adjudicates the facts it is given. Nothing here validates them against a source system, so an upstream engine that misreports the record defeats the audit. Detecting *that* is a different product.
- Gemma, Groundplan/PDDL and the Antigravity SDK are unstarted, as planned.

### Track A integration

Track B consumes the rules track only through the `Solver` protocol in [`contracts.py`](services/api/app/contracts.py), which never changed — the merge needed no edit to `app/agents/`. `RulesIngestionStep` calls an optional `describe_policy(policy_id)` on the solver when the rules track provides one, guarded by the same lock as the solver itself because compiling a policy builds Z3 terms.

**One thing the merge exposed.** z3-solver's Python bindings share a single global context, and it is not thread safe: concurrent calls fault inside the native library rather than raising. Both fleet runtimes hand steps to worker threads, and `POST /api/v1/decisions` is async, so two overlapping requests were enough to reach it — reproducible as an `ASSERTION VIOLATION` in `ast.cpp` that takes the process down, not an exception you can catch. Every call into the solver is now serialised in [`steps.py`](services/api/app/agents/steps.py); evaluation is sub-millisecond so the contention is not measurable, and two tests audit 16 decisions concurrently to keep it fixed. The proper fix is a Z3 context per thread, which belongs in the rules track's code rather than the fleet's.

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

## Sources

Every number quoted above traces to one of these. The per-incident files in
[`incidents/`](incidents/) carry the same citations machine-readably, and a test
rejects any incident file that lacks them.

**The incidents**

- Bannow, Tara. ["UnitedHealth faces class action lawsuit over algorithmic care denials in Medicare Advantage plans."](https://www.statnews.com/2023/11/14/unitedhealth-class-action-lawsuit-algorithm-medicare-advantage/) *STAT News*, 14 November 2023. — Gene Lokken, 91, fractured leg and ankle May 2022, 19 days of therapy covered then cut off, ~$150,000 paid out of pocket, died July 2023. Dale Tetzloff, 74, stroke October 2022, cut off after 20 days, $70,000 paid, died October 2023. Alleged 90% error rate measured by reversal on appeal; 0.2% of patients appeal.
- ["Estate of Gene B. Lokken, et al. v. UnitedHealth Group, Inc. — AI Risks in Medical Insurance Coverage Disputes."](https://www.tresslerllp.com/thought-leadership/estate-of-gene-b-lokken-et-al-v-unitedhealth-group-inc-ai-risks-in-medical-insurance-coverage-disputes/) *Tressler LLP*, 2025. — Filed in the U.S. District Court for the District of Minnesota, 14 November 2023; key claims allowed to proceed 13 February 2025.
- Rucker, Patrick (The Capitol Forum), Maya Miller and David Armstrong. ["How Cigna Saves Millions by Having Its Doctors Reject Claims Without Reading Them."](https://www.propublica.org/article/cigna-pxdx-medical-health-insurance-rejection-claims) *ProPublica*, 25 March 2023. — "Over a period of two months last year, Cigna doctors denied over 300,000 requests for payments using this method, spending an average of 1.2 seconds on each case." A former Cigna doctor: "We literally click and submit. It takes all of 10 seconds to do 50 at a time."
- ["Cigna hits back on claims review report from ProPublica."](https://www.beckerspayer.com/payer/cigna-hits-back-on-claims-review-report-from-propublica/) *Becker's Payer Issues*, March 2023. — Cigna's response; included because a corpus that cites only one side of a disputed report is not evidence.
- ["Refusal of Recovery: How Medicare Advantage Insurers Have Denied Patients Access to Post-Acute Care"](https://www.blumenthal.senate.gov/newsroom/press/release/senate-permanent-subcommittee-on-investigations-releases-majority-staff-report-exposing-medicare-advantage-insurers-refusal-of-care-for-vulnerable-seniors) (Majority Staff Report). *U.S. Senate Permanent Subcommittee on Investigations*, 17 October 2024. — UnitedHealthcare's post-acute prior-authorisation denial rate rose 10.9% (2020) → 16.3% (2021) → **22.7% (2022)**, from more than 280,000 pages of company documents. Also [AHA's summary](https://www.aha.org/news/headline/2024-10-17-senate-report-scrutinizes-medicare-advantage-prior-authorization-denials-post-acute-care-services) and the [Center for Medicare Advocacy's](https://medicareadvocacy.org/medicare-advantage-coverage-denials/).

**The rules the solver enforces**

- [42 U.S.C. §1395y(a)(1)(A)](https://www.law.cornell.edu/uscode/text/42/1395y) — reasonable and necessary. Backs `medical_necessity`.
- [42 CFR §409.31](https://www.law.cornell.edu/cfr/text/42/409.31) — level of care; skilled services required on a daily basis. Backs `skilled_care_required`.
- [42 CFR §409.61](https://www.law.cornell.edu/cfr/text/42/409.61); 42 U.S.C. §1395d(a)(2)(A) — 100 days per benefit period. Backs `benefit_days_available`.
- [42 CFR §409.32](https://www.law.cornell.edu/cfr/text/42/409.32) — "The restoration potential of a patient is not the deciding factor in determining whether skilled services are needed." The Jimmo rule, in the regulation itself.
- [*Jimmo v. Sebelius* settlement fact sheet](https://www.cms.gov/medicare/medicare-fee-for-service-payment/snfpps/downloads/jimmo_fact_sheet2_022014_final.pdf), CMS — no improvement standard; approved by the District of Vermont, 24 January 2013. Background from the [Center for Medicare Advocacy](https://medicareadvocacy.org/jimmo-v-sebelius-improvement-standard-case-summary/).
- [CMS FAQ of 6 February 2024 on Medicare Advantage and AI](https://www.nortonrosefulbright.com/en/knowledge/publications/644bd9a2/cms-clarifies-medicare-advantage-organizations-use-of-ai-and-algorithms-in-coverage-decisions) — a predicted length of stay "cannot be used as the basis to terminate post-acute care services"; §422.101(c) requires re-assessing the individual patient first.

---

## Working agreement

Two people, split by LLM role rather than by layer. File-level ownership map, git workflow and prerequisites in [`WORKPLAN.md`](WORKPLAN.md).

**One rule: if a file is not yours, you do not edit it.** Track B touched two files outside its column and both are called out here rather than buried in the diff:

- `tests/test_api.py` — `assert len(result["events"]) == 4` no longer holds now that the fleet emits one event per hop. It is replaced by an assertion on the *sequence* of hop kinds, which is a stronger regression guard than a count.
- `README.md` — rewritten to describe what exists. It was due for a joint rewrite at integration; treat this as the Track B half.
