## Inspiration

In 2022, Cigna doctors denied more than 300,000 requests for payment over two months. ProPublica found the average time spent on each was 1.2 seconds, and the medical file was never opened. Around the same time, UnitedHealth's nH Predict was cutting off post-acute care for elderly patients. It was reversed about 90% of the time on appeal, which sounds like a system that failed until you read the other number: only 0.2% of patients appeal at all. The reversal rate was not a bug. It was the business model.

Gene Lokken was 91. His therapy was stopped on day 19 of a 100-day benefit. His family paid $150,000.

What struck us was that none of these denials were hard to check. The rules are public. They are in the United States Code and the Code of Federal Regulations. A denial either follows them or it does not, and that is a question with an answer, not an opinion. Nobody was asking it.

Every hackathon project we looked at built a decision maker. We wanted to build the thing that audits one.

## What it does

Aegis sits alongside an automated eligibility engine and independently re-adjudicates every decision it makes. When a denial contradicts the rules it claims to apply, Aegis proves it, names the exact clauses that cannot all hold at once, and says in plain English what would have to change.

A decision takes seven hops. Intake, a Model Armor input shield, rules ingestion, the Z3 solver, Gemini re-adjudication, an output shield, and a seal into an append-only ledger. Every hop opens an OpenTelemetry span and commits to its predecessor by SHA-256, so the reasoning chain is something you verify rather than something you trust.

## The one design decision that matters

The solver holds the verdict. The model does not.

Gemini reviews every case against the same compiled constraints Z3 sees, and writes the rationale a claimant will read. What it cannot do is clear a violation. Its verdict is measured against the binding solver result in three postures: it can concur, it can escalate for more scrutiny, and if it argues for a more permissive outcome than the constraints support, that dissent is recorded and not honoured.

Every outcome Aegis produces is reachable from the Z3 result alone. That asymmetry is our answer to the obvious objection about using AI to audit AI, and it is enforced in `adjudicator.py` and pinned by tests, not by a prompt.

We measured it rather than asserting it. The deterministic core audits a claim in 85 ms and reaches the same 52 of 52 verdicts as the full fleet at 6.1 s. Removing the model changes nothing about who gets flagged.

## How we built it

Policy prose goes to Gemini for structured extraction, and comes back as constraints that are validated before they are trusted. Every extracted rule is checked against the fact schema, so an invented field is rejected, and every quotation is checked against the source document, so a hallucinated citation fails loudly instead of quietly becoming a constraint. The model proposes. Deterministic validation disposes.

Those constraints compile to Z3 expressions over the case facts. Z3 decides satisfaction, not Python conditionals, which means the clauses we explain are exactly the clauses we solved. When a denial contradicts the rules, Z3 returns an unsat core. Its core is not guaranteed minimal, so we run a drop-one refinement loop until it is, then render the result as a citation and a suggested relaxation.

The stack is ADK `SequentialAgent` orchestration, Gemini 2.5 Flash on Vertex AI, hosted Model Armor on the shield boundary, Z3 for the solver, Firestore for state and the ledger, Pub/Sub for the decision stream, OpenTelemetry to Cloud Trace, and Cloud Run for the deployment. Infrastructure is Terraform.

Two people built it in parallel. Before writing any feature code we froze the shared seam: the data models, a `Solver` protocol, the TypeScript mirror of the contract, and a per-view split of the frontend, all in one commit. Then we wrote a file-level ownership map with one rule, which is that if a file is not yours you do not edit it. When the two tracks finally met, the merge had zero conflicts. That is the part of the process we would repeat.

## Proving it, instead of claiming it

The pitch says Aegis would have caught these denials. That is checkable, so we checked it.

`incidents/` holds six recorded failures reconstructed from the public record. Each one carries its sources with real URLs and dates, the governing rule with a citation to the statute or regulation, an explicit note on what in it is reconstructed, and the outcome every decision must reach. A test suite replays all 52 cases on every push. All 52 reach the recorded outcome with an intact ledger chain.

The control set is the part we care about most. Three of those cases are denials that are *correct*, where the benefit period is exhausted, the care is custodial, or necessity is undocumented. Aegis must uphold them, and the run fails if any of them flags. A layer that flags every denial has told you nothing. The Senate PSI cohort carries the same discipline: of its five findings, four are unsupported denials and one is an unsupported approval, because oversight that only ever pushes in one direction is advocacy.

Where the record is incomplete, we say so. Lokken's complaint does not state how many further days were ordered, so rather than pick a convenient number, the test sweeps all 81 values that fit inside the benefit period and confirms the contradiction holds at every one.

## Challenges we ran into

**Z3 is not thread safe.** The Python bindings share one global context. Both runtimes hand steps to worker threads and the decision endpoint is async, so two overlapping requests were enough to reach it. It does not raise something catchable. It faults inside the native library with an assertion violation in `ast.cpp` and the process goes down. We found it running the incident corpus eight at a time, and now serialise solver access.

**Terraform planned clean and failed on apply, twice.** The Model Armor template rejected every update with "the `template_metadata` field is required". All of that block's attributes are optional but the block itself is not, so the first apply created the template and every apply after it failed. Since Cloud Run reads the template id, nothing could be deployed at all until we found it.

**Spans were generated and never arrived.** OpenTelemetry's `BatchSpanProcessor` exports on a background thread, and Cloud Run throttles CPU between requests by default. The thread never got scheduled, so traces sat in a buffer while the app cheerfully reported that the Cloud Trace exporter was active. Setting `cpu_idle = false` fixed it.

**Dead-lettering was configured and inert.** We had `max_delivery_attempts` set, but Pub/Sub moves a message using its own service agent, which needs publish on the dead-letter topic and subscribe on the subscription. Neither was granted. A message that could not be audited would have redelivered forever, against Vertex, on a public endpoint. We only found it by publishing a poison message and watching where it went.

**The SPA fallback served the whole filesystem.** The static route joined the request path onto the bundle directory and returned anything that was a file, with no check that it stayed inside. It had been latent since the first commit because the route only registers when a build exists, and we had never exercised it locally.

Every one of these was invisible to unit tests and to `terraform plan`. They only appeared when the thing actually ran.

## What we learned

Freezing the interface before writing features cost us an evening and saved the entire merge.

"It is deployed" and "it is correct" are different claims, and the gap between them is where all of our real bugs lived.

The most persuasive thing you can put in front of someone reviewing a governance tool is not the flags it raises. It is the three cases it refuses to flag.

## What's next

Widening the fact schema past Medicare post-acute coverage. Robodebt, Michigan's MiDAS false-fraud system, and the Dutch childcare benefits scandal are the obvious next incidents and none of them fit the current contract. Integrating Memory Bank and Agent Identity, and implementing the declared `cached` mode, which currently behaves as `live`.

One limitation worth stating plainly: Aegis re-adjudicates the facts it is given. Nothing here validates them against a source system, so an upstream engine that misreports the record defeats the audit. Detecting that is a different product.
