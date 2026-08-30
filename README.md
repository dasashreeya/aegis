# Aegis — an institutional fleet that audits automated decisions before they harm people

**One-sentence pitch:** Aegis is a Fortified Enterprise Fleet of governed AI agents that sits alongside any automated eligibility/claims/benefits engine, independently re-adjudicates each decision against the real governing rules, and blocks or flags decisions that a formal solver proves are contradictory or unsupported — with a full audit trail.

**Cold-open (demo second 0–20):** "In 2022, Cigna's PxDx system denied 300,000 medical claims in two months — 1.2 seconds of review per claim. UnitedHealth's nH Predict denied post-acute care for elderly patients and was reversed 90% of the time on appeal, because it counted on the fact that only 0.2% of patients appeal. Ninety-one-year-old Gene Lokken lost his coverage after 19 days. Here is what our system would have done." Then show Aegis intercepting a denial on real data.

**Why it's not saturated:** No ADK-hackathon or Gemini-competition winner has built an *oversight/governance layer for automated decisions*. Past winners built the decision-makers (SalesShortcut, Energy Agent) — nobody built the auditor. Aegis uses the exact GEAP governance stack the Fortified Enterprise Fleet track names, which almost no team will implement credibly.

**Track & secondary prizes:** Primary = **Fortified Enterprise Fleet ($20k)**, and it is the strongest **Grand Prize ($50k)** candidate because it maximally exercises the newest Google infra. Also plausibly **Best Architectural Design ($5k)** and **Individual/Hobbyist ($10k)** — but remember only one prize per project.

**Architecture (mapped to the 30% criterion):**
- **Orchestrator agent (ADK SequentialAgent)** routes each incoming decision through specialized sub-agents.
- **Rules-ingestion agent** pulls the governing policy (CMS coverage criteria, plan contract text, ClinicalTrials.gov eligibility) and, via **"Reconcile,"** translates requirements into **Z3/SMT constraints**. When a denial is inconsistent with the rules, Z3 returns a **minimal unsat core** — the smallest contradictory rule set — rendered in plain English with proposed relaxations.
- **Re-adjudication agent** (Gemini 3.5 Flash) evaluates the specific case against the constraints and produces a verdict + rationale.
- **"Replay" component:** every decision is recorded as a deterministic event log (model outputs, tool results, timestamps) so any decision is replayable step-for-step and **forkable** ("replay to the point of denial, substitute the correct rule, re-execute → the claim is approved").
- **Memory Bank** stores per-institution policy context and prior adjudications across sessions.
- **Model Armor** screens all inbound documents/prompts for prompt injection, tool poisoning, and PII leaks (directly demonstrable via the Model Armor codelab pattern).
- **Agent Identity** enforces zero-trust access to the (synthetic) claims database; **Agent Gateway** routes and enforces policy; **Agent Observability** (OpenTelemetry) emits audit logs and end-to-end reasoning-chain traces — the literal "here's why" a regulator would demand.
- **Agent Registry** publishes each specialized agent for cross-department discovery/versioning.
- **Infra:** Cloud Run (scale-to-zero), Firestore or Cloud SQL for state, Pub/Sub for the event-driven decision stream, deployed on GEAP Agent Runtime.

**Real data:** openFDA recall data (for a device/drug-recall variant) OR Synthea synthetic patients + a FHIR test server + CMS coverage criteria + ClinicalTrials.gov eligibility (for the claims/eligibility variant). All public, no PHI.

**4-minute demo script (shot-by-shot):**
1. (0:00–0:20) Cold open: the incident, the numbers, the human cost.
2. (0:20–0:50) Value prop + architecture diagram (10 seconds on screen).
3. (0:50–2:20) **Live, unedited:** a real denial flows in via Pub/Sub → Model Armor screens it → Reconcile builds constraints → Z3 returns an unsat core → the agent flags "this denial contradicts CMS rule X and plan clause Y" → Replay forks the timeline to show the correct outcome.
4. (2:20–3:10) Show the Google Cloud Console: Cloud Run dashboard, Vertex AI/Agent Engine logs, Agent Observability trace, Agent Registry catalog, Model Armor block event.
5. (3:10–3:50) Scale story: multiple institutional agents discoverable in the registry; Memory Bank persistence across weeks.
6. (3:50–4:00) Close: "If Aegis had been running, this would have been caught."

**Architecture diagram description:** A left-to-right flow — external decision source → Pub/Sub event bus → Model Armor input shield → ADK Orchestrator (SequentialAgent) branching to three labeled sub-agents (Rules-Ingestion→Z3, Re-adjudication→Gemini 3.5 Flash, Replay/Audit) → Memory Bank + Firestore state stores below → Agent Identity/Agent Gateway wrapping the data-access boundary → Agent Observability/OpenTelemetry emitting to Cloud Trace on the right → all boxes sitting inside a "Cloud Run / GEAP Agent Runtime" container, with Agent Registry as a catalog card on top.

**Who is building what:** two people, split by LLM role rather than by layer, so neither of us owns infrastructure alone. File-level ownership map, git workflow and prerequisites in [`WORKPLAN.md`](WORKPLAN.md).

| Step / track | Owner | Scope | Status |
| --- | --- | --- | --- |
| Step 0 — shared contract | joint | `models.py`, `contracts.py`, `types.ts`, per-view split of `App.tsx`, CI | Merged (`58f8454`) |
| Step 1 — build pipeline | @dasashreeya | Dockerfile, frontend build served by FastAPI, Artifact Registry push | Docker and frontend done; registry push blocked on `terraform apply` |
| Step 1 — cloud runtime | @GIND123 | `terraform apply`, Cloud Run deploy, Pub/Sub push subscription, OpenTelemetry to Cloud Trace | Not started |
| Track A — Rules & Solver | @dasashreeya | Policy prose to Gemini extraction to Z3 to minimal unsat core to plain-English relaxation, with a clause citation per rule | Built, in review (#1) |
| Track B — Fleet & Adjudication | @GIND123 | ADK `SequentialAgent`, Gemini re-adjudication, hosted Model Armor, Replay/fork event log | Not started |

**One rule:** if a file is not yours, you do not edit it. A shared file that genuinely must change becomes its own small PR to `main`, announced in the group chat, and both branches rebase. The integration PR is joint work: wire Track A's extracted constraints into Track B's ADK agent, and rewrite this README to describe what actually exists.

**14-day build plan:**
- Days 1–2: Stand up the ADK multi-agent skeleton on Cloud Run; wire Gemini 3.5 Flash; ingest one real dataset (Synthea/FHIR + CMS criteria).
- Days 3–5: Build Reconcile (LLM→Z3, unsat core, plain-English relaxation) on a narrow, hard-coded rule domain (this is the demo's intellectual centerpiece — make it bulletproof).
- Days 6–7: Add Memory Bank + Firestore state + the Pub/Sub event flow.
- Days 8–9: Add Model Armor input/output shields (follow the codelab) + Agent Identity + Agent Registry publish.
- Days 10–11: Add the Replay event log + one forkable counterfactual (fake the UI polish, make the core real).
- Day 12: Agent Observability/OpenTelemetry traces; capture all Google Cloud Console proof footage.
- Day 13: Record and edit the 4-minute video; write the README + architecture diagram; publish a build blog (+0.2) and a social post with #AllThingsAgenticHackathon (+0.2); integrate Gemma for a lightweight local classifier (+0.2).
- Day 14: Buffer, dry-run judging reproducibility, submit early.
- **What to fake:** UI chrome, the breadth of rule domains (one deep domain, not ten), multi-week persistence (simulate elapsed time). **What to cut if behind:** Groundplan/PDDL, the second submission, the Antigravity SDK.

**Strongest judge objection & preemption:** "Is the Z3/formal layer real or theater?" → Preempt by showing the actual unsat core output live and providing a reproducible README that runs the solver on the real rule set. Second objection: "Could this scale to real production data?" → Show the Agent Registry/Gateway/Identity governance and frame the synthetic-data choice as a deliberate compliance decision, not a limitation.

**Scorecard (self-estimate):** Innovation & Operational Utility 40% → very strong (novel oversight category, real incident, autonomous action). Architectural Discipline 30% → very strong (exercises the entire newest GA governance stack plus a formal solver). Demo & Production Readiness 30% → strong if the live run is clean and the Cloud Console proof is unambiguous.
