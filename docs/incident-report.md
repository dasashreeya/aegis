# Incident replay report

`live` mode · adjudicator `gemini-2.5-flash` · 52 cases across 6 incidents

| Incident | Cases | Flagged | Upheld | Expected outcome reached |
| --- | --- | --- | --- | --- |
| nH Predict cut off a 91-year-old's therapy at day 19 of a 100-day benefit | 1 | 1 | 0 | all |
| nH Predict ended stroke rehabilitation after 20 days against the physician's recommendation | 1 | 1 | 0 | all |
| A post-acute cohort at the 22.7% denial rate the Senate found for 2022 | 22 | 5 | 17 | all |
| Bulk denial without opening the file: 1.2 seconds per claim | 24 | 24 | 0 | all |
| Denied for not improving, when the regulation says improvement is not the test | 1 | 1 | 0 | all |
| Control: denials the rules do support | 3 | 0 | 3 | all |

**52 of 52 cases reached the expected outcome with an intact ledger chain.**

Mean 6078 ms per audited decision, median 3999 ms, wall clock 107.8 s for the whole corpus. PxDx spent 1.2 seconds per claim without opening the file.

## nH Predict cut off a 91-year-old's therapy at day 19 of a 100-day benefit

*UnitedHealth Group · nH Predict (NaviHealth) · May 2022 - July 2023*

Gene Lokken, 91, fractured his leg and ankle in May 2022 and spent a month in a nursing home before his physician approved physical therapy. UnitedHealth and its NaviHealth subsidiary paid for 19 days of that therapy and then stopped, on the ground that he was safe to go home. The complaint alleges the stop was driven by nH Predict, an algorithm that projects a length of stay, and that roughly 90% of its denials were reversed when families appealed - a rate the company is alleged to have tolerated because only about 0.2% of patients appeal at all.

**Harm.** The family paid roughly $150,000 out of pocket over the following year to keep him in skilled care. He died in July 2023.

**What is reconstructed.** The number of additional therapy days the physician ordered after day 19 is not stated in the public record. The value below is a reconstruction; the runner sweeps the entire admissible range to show the finding does not depend on it. Everything else - the 19 days covered, the ages, the dates, the amounts - comes from the filed complaint as reported.

Governing rules:

- `medical_necessity` — 42 U.S.C. 1395y(a)(1)(A). No payment may be made for items or services that are not reasonable and necessary for the diagnosis or treatment of illness or injury. The physician had ordered the therapy.
- `skilled_care_required` — 42 CFR 409.31(b)(1). Post-hospital SNF care is covered where the beneficiary requires skilled nursing or skilled rehabilitation services on a daily basis.
- `benefit_days_available` — 42 CFR 409.61(b); 42 U.S.C. 1395d(a)(2)(A). Medicare covers up to 100 days of post-hospital SNF care in a benefit period. Nineteen were used.
- `individualized_reassessment` — 42 CFR 422.101(c); CMS FAQ of 6 February 2024. A predicted length of stay cannot by itself terminate post-acute care. Termination requires re-assessing the individual patient's condition before the notice issues. This is the backdrop rule, not a solver constraint.

| Case | Original | Expected | Aegis | Latency |
| --- | --- | --- | --- | --- |
| Lokken - therapy terminated at day 19 | — | flagged | flagged | 12450 ms |

> The requested continued therapy is approved because it meets all necessary criteria. The service is medically necessary, requires skilled care, and the claimant has sufficient benefit days remaining, as confirmed by the Medical Necessity, Skilled Care Requirement, and Benefit Period Limit rules.

Minimal unsat core: `medical_necessity`, `skilled_care_required`, `benefit_days_available`, `original_denied`

Sources:

- [UnitedHealth faces class action lawsuit over algorithmic care denials in Medicare Advantage plans](https://www.statnews.com/2023/11/14/unitedhealth-class-action-lawsuit-algorithm-medicare-advantage/) — STAT News, 2023-11-14
- [Estate of Gene B. Lokken, et al. v. UnitedHealth Group, Inc. - AI Risks in Medical Insurance Coverage Disputes](https://www.tresslerllp.com/thought-leadership/estate-of-gene-b-lokken-et-al-v-unitedhealth-group-inc-ai-risks-in-medical-insurance-coverage-disputes/) — Tressler LLP, 2025-02-13
- [CMS clarifies Medicare Advantage organizations' use of AI and algorithms in coverage decisions](https://www.nortonrosefulbright.com/en/knowledge/publications/644bd9a2/cms-clarifies-medicare-advantage-organizations-use-of-ai-and-algorithms-in-coverage-decisions) — Norton Rose Fulbright, 2024-02-16

## nH Predict ended stroke rehabilitation after 20 days against the physician's recommendation

*UnitedHealth Group · nH Predict (NaviHealth) · October 2022 - October 2023*

Dale Tetzloff, 74, had a stroke in October 2022. His physician recommended long-term nursing home care. Coverage was cut off after 20 days. He is the second named plaintiff in the same class action as Gene Lokken, filed in the U.S. District Court for the District of Minnesota on 14 November 2023. A federal judge allowed key claims to proceed on 13 February 2025.

**Harm.** The family paid roughly $70,000 out of pocket while appealing. He died in October 2023 in an assisted living facility.

**What is reconstructed.** As with Lokken, the number of further days recommended is not in the public record and is reconstructed here. The 20 days covered, the ages, the dates and the amount are from the filed complaint as reported.

Governing rules:

- `medical_necessity` — 42 U.S.C. 1395y(a)(1)(A). Reasonable and necessary for the treatment of illness or injury. The treating physician recommended continued nursing home care after a stroke.
- `skilled_care_required` — 42 CFR 409.31(b)(1). The beneficiary requires skilled nursing or skilled rehabilitation services on a daily basis.
- `benefit_days_available` — 42 CFR 409.61(b); 42 U.S.C. 1395d(a)(2)(A). Up to 100 days of post-hospital SNF care per benefit period. Twenty were used.

| Case | Original | Expected | Aegis | Latency |
| --- | --- | --- | --- | --- |
| Tetzloff - post-stroke care terminated at day 20 | — | flagged | flagged | 15822 ms |

> Your request for continued skilled nursing facility care is approved. This decision is based on the satisfaction of the 'Medical necessity' rule, the 'Skilled care requirement' rule, and the 'Benefit period limit' rule, all of which indicate eligibility for the requested service.

Minimal unsat core: `medical_necessity`, `skilled_care_required`, `benefit_days_available`, `original_denied`

Sources:

- [UnitedHealth faces class action lawsuit over algorithmic care denials in Medicare Advantage plans](https://www.statnews.com/2023/11/14/unitedhealth-class-action-lawsuit-algorithm-medicare-advantage/) — STAT News, 2023-11-14
- [Estate of Gene B. Lokken, et al. v. UnitedHealth Group, Inc. - AI Risks in Medical Insurance Coverage Disputes](https://www.tresslerllp.com/thought-leadership/estate-of-gene-b-lokken-et-al-v-unitedhealth-group-inc-ai-risks-in-medical-insurance-coverage-disputes/) — Tressler LLP, 2025-02-13

## A post-acute cohort at the 22.7% denial rate the Senate found for 2022

*UnitedHealthcare (rate as reported by the Senate PSI) · Medicare Advantage prior authorization · 2020 - 2022*  ·  **reconstructed**

The Senate Permanent Subcommittee on Investigations reported on 17 October 2024 that UnitedHealthcare's denial rate for post-acute care prior authorization rose from 10.9% in 2020 to 16.3% in 2021 to 22.7% in 2022, while its overall denial rate stayed far lower. The subcommittee, working from more than 280,000 pages of company documents, concluded the insurers were targeting post-acute care specifically. This file reconstructs a 22-case post-acute population at that 2022 rate.

**Harm.** The report frames the pattern as substituting a calculation about financial gain for a judgment about medical necessity, for patients recovering from falls and strokes.

**What is reconstructed.** This is a population reconstruction, not a set of real claimants. The 22.7% denial rate is the published figure; the mix of eligible and ineligible cases behind it is not public and is chosen here to test precision as well as recall. Aegis must uphold the correct denial and flag the unsupported approval, or the flag rate means nothing.

Governing rules:

- `medical_necessity` — 42 U.S.C. 1395y(a)(1)(A). Reasonable and necessary for the diagnosis or treatment of illness or injury.
- `skilled_care_required` — 42 CFR 409.31(b)(1). Skilled nursing or skilled rehabilitation services required on a daily basis.
- `benefit_days_available` — 42 CFR 409.61(b); 42 U.S.C. 1395d(a)(2)(A). Up to 100 days of post-hospital SNF care per benefit period.
- `parity_with_traditional_medicare` — 42 CFR 422.101(b). A Medicare Advantage organisation must provide coverage no less than what Traditional Medicare covers. Backdrop rule, not a solver constraint.

| Case | Original | Expected | Aegis | Latency |
| --- | --- | --- | --- | --- |
| Approved, requirements met #01 | — | upheld | upheld | 16422 ms |
| Approved, requirements met #02 | — | upheld | upheld | 4302 ms |
| Approved, requirements met #03 | — | upheld | upheld | 2944 ms |
| Approved, requirements met #04 | — | upheld | upheld | 6068 ms |
| Approved, requirements met #05 | — | upheld | upheld | 3177 ms |
| Approved, requirements met #06 | — | upheld | upheld | 4564 ms |
| Approved, requirements met #07 | — | upheld | upheld | 3644 ms |
| Approved, requirements met #08 | — | upheld | upheld | 2757 ms |
| … 14 more | | | | |

> Your request for post-acute skilled nursing facility care is approved. This decision is based on the satisfaction of the 'Medical necessity' rule, the 'Skilled care requirement' rule, and the 'Benefit period limit' rule, indicating that you have sufficient covered days remaining.

Sources:

- [Refusal of Recovery: How Medicare Advantage Insurers Have Denied Patients Access to Post-Acute Care (Majority Staff Report)](https://www.blumenthal.senate.gov/newsroom/press/release/senate-permanent-subcommittee-on-investigations-releases-majority-staff-report-exposing-medicare-advantage-insurers-refusal-of-care-for-vulnerable-seniors) — U.S. Senate Permanent Subcommittee on Investigations, 2024-10-17
- [Senate report scrutinizes Medicare Advantage prior authorization denials for post-acute care services](https://www.aha.org/news/headline/2024-10-17-senate-report-scrutinizes-medicare-advantage-prior-authorization-denials-post-acute-care-services) — American Hospital Association, 2024-10-17
- [Senate Subcommittee Report Details Medicare Advantage Coverage Denials](https://medicareadvocacy.org/medicare-advantage-coverage-denials/) — Center for Medicare Advocacy, 2024-10-24

## Bulk denial without opening the file: 1.2 seconds per claim

*Cigna · PxDx · 2022 (two-month window reported)*  ·  **reconstructed**

ProPublica and The Capitol Forum reported on 25 March 2023 that over a two-month period Cigna doctors denied more than 300,000 requests for payment using the PxDx system, spending an average of 1.2 seconds on each case, according to internal documents. A former Cigna doctor described the process: 'We literally click and submit. It takes all of 10 seconds to do 50 at a time.' The claims were labelled not medically necessary without anyone opening the patient file. Cigna disputed the reporting.

**Harm.** Patients were billed for care their physicians had ordered, on a determination that no clinician had read.

**What is reconstructed.** This reconstructs the mechanism, not the claims. PxDx targeted tests and procedures matched by code pair; Aegis's fact schema models skilled nursing eligibility, so the cases below are post-acute claims denied the PxDx way rather than the specific procedure codes PxDx used. What transfers exactly is the failure mode - a bulk determination of 'not medically necessary' made without reading the record - and the throughput comparison the runner measures.

Governing rules:

- `medical_necessity` — 42 U.S.C. 1395y(a)(1)(A). The statutory test is whether the service is reasonable and necessary for the diagnosis or treatment of illness or injury. A determination made without reading the record cannot have applied it.
- `skilled_care_required` — 42 CFR 409.31(b)(1). Skilled nursing or skilled rehabilitation services required on a daily basis.
- `benefit_days_available` — 42 CFR 409.61(b); 42 U.S.C. 1395d(a)(2)(A). Up to 100 days of post-hospital SNF care per benefit period.

| Case | Original | Expected | Aegis | Latency |
| --- | --- | --- | --- | --- |
| Denied unread #01 | — | flagged | flagged | 7840 ms |
| Denied unread #02 | — | flagged | flagged | 3744 ms |
| Denied unread #03 | — | flagged | flagged | 3602 ms |
| Denied unread #04 | — | flagged | flagged | 3727 ms |
| Denied unread #05 | — | flagged | flagged | 3186 ms |
| Denied unread #06 | — | flagged | flagged | 4415 ms |
| Denied unread #07 | — | flagged | flagged | 3849 ms |
| Denied unread #08 | — | flagged | flagged | 5019 ms |
| … 16 more | | | | |

> Your request for post-acute skilled nursing care is approved. Our review found that the service meets the medical necessity requirement, requires skilled care, and you have sufficient benefit days remaining, as per the Medical necessity, Skilled care requirement, and Benefit period limit rules.

Minimal unsat core: `medical_necessity`, `skilled_care_required`, `benefit_days_available`, `original_denied`

Sources:

- [How Cigna Saves Millions by Having Its Doctors Reject Claims Without Reading Them](https://www.propublica.org/article/cigna-pxdx-medical-health-insurance-rejection-claims) — ProPublica and The Capitol Forum (Patrick Rucker, Maya Miller, David Armstrong), 2023-03-25
- [Cigna accused of using an algorithm to automatically reject patient claims](https://www.cbsnews.com/news/cigna-algorithm-patient-claims-lawsuit/) — CBS News, 2023-07-25
- [Cigna hits back on claims review report from ProPublica](https://www.beckerspayer.com/payer/cigna-hits-back-on-claims-review-report-from-propublica/) — Becker's Payer Issues, 2023-03-27

## Denied for not improving, when the regulation says improvement is not the test

*Pattern litigated in Jimmo v. Sebelius · Utilization management, improvement-standard rule · Settled 24 January 2013; CMS re-issued guidance in 2017*  ·  **reconstructed**

Jimmo v. Sebelius was a nationwide class action for Medicare beneficiaries denied coverage on the ground that they were not improving or had no potential to improve. The settlement approved by the District of Vermont on 24 January 2013 confirmed there is no 'improvement standard': coverage of skilled nursing and therapy turns on the need for skilled care, not on the presence of restoration potential, and is available to maintain a condition or slow deterioration. The regulation says so directly - 42 CFR 409.32 states that the restoration potential of a patient is not the deciding factor in determining whether skilled services are needed.

**Harm.** Beneficiaries with stable chronic conditions lost skilled care they needed to avoid deteriorating, on a criterion that was never in the law.

**What is reconstructed.** A pattern case, not a named claimant. The litigation and the regulation are real; this specific decision is constructed to isolate the failure mode - every eligibility requirement is met and the denial rests entirely on a criterion the rules do not contain.

Governing rules:

- `medical_necessity` — 42 U.S.C. 1395y(a)(1)(A). Reasonable and necessary for the treatment of illness or injury, including to maintain a condition or slow deterioration.
- `skilled_care_required` — 42 CFR 409.31(b)(1); 42 CFR 409.32. Skilled services are required on a daily basis. 'The restoration potential of a patient is not the deciding factor in determining whether skilled services are needed.'
- `benefit_days_available` — 42 CFR 409.61(b); 42 U.S.C. 1395d(a)(2)(A). Up to 100 days of post-hospital SNF care per benefit period. Twenty-four were used.

| Case | Original | Expected | Aegis | Latency |
| --- | --- | --- | --- | --- |
| Maintenance therapy denied for lack of improvement potential | — | flagged | flagged | 17095 ms |

> Your request for skilled maintenance therapy is approved. This decision is based on the fact that the service is medically necessary, requires skilled care, and you have sufficient benefit days remaining, satisfying the "Medical necessity", "Skilled care requirement", and "Benefit period limit" rules.

Minimal unsat core: `medical_necessity`, `skilled_care_required`, `benefit_days_available`, `original_denied`

Sources:

- [Jimmo v. Sebelius Settlement Agreement Fact Sheet](https://www.cms.gov/medicare/medicare-fee-for-service-payment/snfpps/downloads/jimmo_fact_sheet2_022014_final.pdf) — Centers for Medicare & Medicaid Services, 2014-02-02
- [Jimmo v. Sebelius Improvement Standard Case Summary](https://medicareadvocacy.org/jimmo-v-sebelius-improvement-standard-case-summary/) — Center for Medicare Advocacy, 2023-09-01
- [42 CFR 409.32 - Criteria for skilled services and the need for skilled services](https://www.law.cornell.edu/cfr/text/42/409.32) — Legal Information Institute, Cornell Law School, 2024-01-01

## Control: denials the rules do support

*Aegis · Control set · n/a*  ·  **reconstructed**

A system that flags every denial is not an oversight layer, it is a rubber stamp pointed the other way. These cases are constructed so that the governing constraints genuinely fail, which means the denial is correct and Aegis must uphold it. If any of them flags, the flag rate on the real incidents means nothing.

**Harm.** None. That is the point.

**What is reconstructed.** Entirely constructed. No incident, no citation to a specific decision - only the same regulations applied to facts that do not meet them.

Governing rules:

- `medical_necessity` — 42 U.S.C. 1395y(a)(1)(A). Reasonable and necessary for the diagnosis or treatment of illness or injury.
- `skilled_care_required` — 42 CFR 409.31(b)(1). Skilled nursing or skilled rehabilitation services required on a daily basis. Custodial care does not qualify.
- `benefit_days_available` — 42 CFR 409.61(b); 42 U.S.C. 1395d(a)(2)(A). Up to 100 days of post-hospital SNF care per benefit period.

| Case | Original | Expected | Aegis | Latency |
| --- | --- | --- | --- | --- |
| Benefit period exhausted | — | upheld | upheld | 2546 ms |
| Custodial care, no skilled requirement | — | upheld | upheld | 6180 ms |
| Necessity not documented | — | upheld | upheld | 7746 ms |

> Your request for continued skilled nursing facility care is denied because the requested stay exceeds the 100-day benefit period, as outlined in the 'Benefit period limit' rule (§ 30.6). While medical necessity and skilled care requirements were met, the benefit period has been exhausted.

Sources:

- [42 CFR 409.31 - Level of care requirement](https://www.law.cornell.edu/cfr/text/42/409.31) — Legal Information Institute, Cornell Law School, 2024-01-01
