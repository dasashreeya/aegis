# Incident corpus

Recorded automated-decision failures, reconstructed from the public record and
replayed through the fleet. One JSON file per incident, loaded by
[`app/corpus.py`](../services/api/app/corpus.py), run by
[`scripts/incidents.py`](../scripts/incidents.py), and asserted on every push by
[`test_incidents.py`](../services/api/tests/test_incidents.py).

| File | Cases | Expected | Traced to a named claimant? |
| --- | --- | --- | --- |
| `01-lokken-nh-predict.json` | 1 | flagged | Yes — filed complaint |
| `02-tetzloff-nh-predict.json` | 1 | flagged | Yes — filed complaint |
| `03-psi-refusal-of-recovery.json` | 22 | 5 flagged, 17 upheld | No — population built from a published rate |
| `04-cigna-pxdx-throughput.json` | 24 | flagged | No — mechanism, not the specific claims |
| `05-jimmo-restoration-potential.json` | 1 | flagged | No — litigated pattern |
| `06-control-correct-denials.json` | 3 | upheld | No — control set |

## Rules for adding one

1. **Every factual claim carries a citation.** `sources` needs a real URL, a
   publisher and a date. A test rejects a file without them.
2. **Say what is reconstructed.** The `caveat` field is not decoration. If the
   public record does not give you a number, say so there, and prefer a
   sensitivity sweep over a confident guess — see how Lokken's unknown day
   count is handled.
3. **`reconstructed` is not a mood.** It is `false` only for a case traced to a
   named claimant in a filed complaint. Populations and patterns are `true`,
   and a test enforces the two cases that may claim otherwise.
4. **Name the governing rule, not the vibe.** `governing_rules` takes a
   citation to the statute or regulation the decision is alleged to contradict.
   Where a rule is legal backdrop rather than a solver constraint, say that in
   the `requirement` text.
5. **Add a case that should be upheld.** Every incident that only ever produces
   flags makes the corpus weaker, not stronger.

## Scope

All six sit in Medicare post-acute coverage, because that is the domain the
`CMS-SNF-100` policy encodes. Robodebt, Michigan's MiDAS false-fraud system and
the Dutch childcare benefits scandal are the obvious next cases and none of them
fit the current `DecisionFacts` schema — adding them means widening the frozen
contract, which is its own PR.
