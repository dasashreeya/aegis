# Aegis — Two-Person Work Plan

How @dasashreeya and @GIND123 build this concurrently without stepping on each other.

**Current state:** one commit (`97d4f2e`), ~1,600 LOC, 3 passing tests. Working end-to-end
boilerplate — FastAPI + Z3 + React + Terraform — with no Gemini, no ADK, no OpenTelemetry, and no
deployment. Roughly 25–30% of what `README.md` claims.

---

## Step 0 — The contract commit (blocking, do first)

Three files are touched by everything. If both people start before these are frozen, every pull
request conflicts.

| Change | Why |
| --- | --- |
| Widen `services/api/app/models.py` | `RuleFinding` gains `citation` + `source_excerpt`; `AuditEvent` gains `trace_id` + `span_id`; `DecisionRecord` gains `policy_version` + `relaxations`. Add the fields both tracks will need now, then stop editing it. |
| Add `services/api/app/contracts.py` | Move `SolverResult` out of `solver.py`, add a `Solver` Protocol. This is the seam — Track A implements it, Track B consumes it, neither reads the other's code. |
| Mirror into `apps/web/src/types.ts` | Frontend never blocks on a backend merge. |
| Split `apps/web/src/App.tsx` | 310 lines holding all five views becomes `views/DecisionsView`, `views/PoliciesView`, `views/AgentsView`, `views/TracesView` + shared `components/StatusBadge`. `App.tsx` keeps only shell, nav, and fetching. |
| Per-view stylesheets | `styles.css` becomes base-only; each view imports its own CSS so nobody appends to a shared file. |

~45 minutes, mechanical, no behavior change. **The 3 existing tests must pass unmodified** — that is
the check it was done right.

---

## Step 1 — Ops sprint (days 1–2, both people, hard cap)

Neither of us wants to own infrastructure for two weeks, and the standard failure mode is
discovering on day 12 that deployment doesn't work. So we split it, do it first against the current
boilerplate, and finish. After this, every later push is just a redeploy.

### @dasashreeya — build pipeline

| Task | Done when |
| --- | --- |
| `.github/workflows/ci.yml` | ruff + pytest + tsc + vitest run on every PR and pass. Repo has no CI today. |
| Dockerfile verification | `docker build` succeeds and the container serves `/api/health` locally. |
| Frontend build integration | `npm run build` output is served by FastAPI — `main.py:86` already mounts `apps/web/dist`, it has never been exercised. |
| Artifact Registry push | Image lands in the `aegis` repo created by `infra/main.tf`. |

### @GIND123 — cloud runtime

| Task | Done when |
| --- | --- |
| `terraform apply` | Project services, Artifact Registry, Firestore, Pub/Sub topic, runtime SA and IAM all exist. `infra/` looks apply-ready but has never run. |
| Cloud Run deploy | A public URL serves the app with `AEGIS_STORAGE_BACKEND=firestore`. |
| Pub/Sub push subscription | Publishing a decision to `aegis-decisions` creates a record via `POST /api/v1/pubsub`. |
| OpenTelemetry → Cloud Trace | One end-to-end decision trace is visible in the console. |

**Exit criteria for the sprint:** a live URL, one traced decision, green CI. Then both people move to
their track and do not touch infra again until the demo.

---

## Step 2 — Tracks (parallel, ~days 3–12)

Split by LLM role, since both of us are strongest there.

### Track A — Rules & Solver — @dasashreeya — `feat/reconcile`

Today `solver.py` checks three rules a human typed in. The pitch claims they're extracted from
governing policy text. Closing that gap is the highest-value work left and the objection a judge
leads with.

**Build:** policy prose → Gemini structured extraction → Z3 constraint compilation → minimal unsat
core → plain-English relaxation, with a citation back to the source clause for every rule.

**Owns exclusively:**

```
services/api/app/rules/__init__.py     (new)
services/api/app/rules/extract.py      (new)
services/api/app/rules/compile.py      (new)
services/api/app/llm.py                (new)
services/api/tests/fixtures/cms_snf.md (new)
services/api/tests/test_rules.py       (new)
services/api/app/solver.py
apps/web/src/views/DecisionsView.tsx
apps/web/src/views/PoliciesView.tsx
```

**Done when:** a test feeds raw policy prose in and asserts the unsat core names the right clauses,
with extraction mocked so CI never calls the model.

**Fallback if extraction proves unreliable near the deadline:** hand-curated constraint set for the
demo case, with live extraction shown working on one document. Real solver, real unsat core,
narrower claim. Decide this by day 10, not day 13.

### Track B — Fleet & Adjudication — @GIND123 — `feat/fleet`

The README sells ADK, Gemini, Model Armor, Memory Bank and Agent Registry. A grep of the source
finds none of them — `orchestrator.py` is a plain Python class and the shield is three regexes.

**Build:** a real ADK `SequentialAgent`, the Gemini re-adjudication agent that evaluates a case
against Track A's constraints, hosted Model Armor on the existing shield boundary, and the
Replay/fork event log.

**Owns exclusively:**

```
services/api/app/agents/__init__.py    (new)
services/api/app/agents/fleet.py       (new)
services/api/app/telemetry.py          (new)
services/api/app/orchestrator.py
services/api/app/armor.py
services/api/app/store.py
services/api/app/config.py
services/api/app/dependencies.py
apps/web/src/views/AgentsView.tsx
apps/web/src/views/TracesView.tsx
```

**Done when:** a decision flows Pub/Sub → Model Armor → ADK orchestrator → solver → verdict, with
every hop emitting a span, and replay forks the event log correctly.

---

## Ownership map

**One rule: if a file is not yours, you do not edit it.** A frozen file that genuinely must change
becomes its own small PR to `main`, announced in the group chat, and both branches rebase.

| File | Owner | Rule |
| --- | --- | --- |
| `app/models.py` | frozen | Changes go to `main` as their own PR. |
| `app/contracts.py` | frozen | The seam between tracks; changing it breaks both. |
| `app/main.py` | B | Route definitions only. A adds no endpoints. |
| `app/solver.py` | A | B calls it through the Protocol, never reads it. |
| `app/rules/`, `app/llm.py` | A | New package. B has no reason to open it. |
| `app/orchestrator.py` | B | Becomes the ADK agent. |
| `app/agents/`, `app/telemetry.py` | B | New. A has no reason to open it. |
| `app/store.py`, `config.py`, `dependencies.py` | B | Infrastructure wiring. |
| `tests/test_api.py` | frozen | Shared regression guard. Each track adds its own test file. |
| `apps/web/src/App.tsx` | frozen | Shell only after step 0. |
| `views/DecisionsView`, `views/PoliciesView` | A | Findings, citations, unsat core, policy registry. |
| `views/AgentsView`, `views/TracesView` | B | Fleet status, traces. |
| `infra/`, `Dockerfile` | B | After the ops sprint, B owns changes. |
| `.github/workflows/` | A | After the ops sprint, A owns changes. |
| `README.md` | frozen | Rewritten jointly at integration. Editing it mid-track guarantees a conflict. |

---

## Git workflow

```bash
# 1. clone
git clone https://github.com/dasashreeya/aegis.git && cd aegis
uv run --with-editable ./services/api --with pytest --with httpx pytest services/api   # 3 passed

# 2. contract commit lands on main first (step 0)

# 3. both branch from it
git switch main && git pull
git switch -c feat/reconcile     # A
git switch -c feat/fleet         # B

# 4. open draft PRs on day one, even empty — continuous visibility into each other's diff
git push -u origin <branch> && gh pr create --draft --base main

# 5. rebase daily, never merge main in
git fetch origin && git rebase origin/main
```

Whoever is green first merges first; the other rebases once and re-runs CI. With the contract frozen
that rebase should be conflict-free — if it isn't, the ownership map was violated and it's worth
finding out where.

**Integration PR is joint work:** wire Track A's extracted constraints into Track B's ADK agent,
rewrite `README.md` to describe what actually exists, record the demo against the deployed URL.

---

## Prerequisites

| Who | Needs |
| --- | --- |
| Both | Python 3.11+, `uv`, Node 24, repo cloned, tests green |
| @dasashreeya | Gemini API key from [AI Studio](https://aistudio.google.com) — free, no billing account, no card |
| @GIND123 | `gcloud` and `terraform` installed; IAM access on the credited project (`roles/editor` + `roles/aiplatform.user`) |
| Project | Google Cloud project with billing enabled and Vertex AI, Firestore, Pub/Sub, Model Armor APIs turned on |
