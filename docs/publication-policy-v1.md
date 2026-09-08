# CoachIQ publication policy v1

Status: **frozen as `coachiq-publication-v1`**

Scientific dependencies:

- `coachiq-wp-v1`
- `coachiq-action-transition-v1`
- `coachiq-decision-v1`

Training boundary: 2014–2024. The policy was fixed without accessing or
inspecting 2026 outcomes. Historical 2020–2025 data were used only for
chronological sensitivity and mechanical dry-runs.

## Purpose and separation

Publication-v1 is a safety policy around frozen scientific output. It does not
change action values, empirical support cells, uncertainty, bootstrap design,
the 200-draw bootstrap, seed 2505, decision thresholds, OT logic, features, or
coefficients. In particular, `clear_model_preference`, `close_call`,
`limited_support`, and `insufficient_support` remain decision-v1
classifications.

A decision-v1 `clear_model_preference` can still be withheld by
publication-v1. Abstention is expected behavior when a directional statement
would rest on structurally weak transitions.

## Frozen public-eligibility gates

A directional decision is publishable only when every condition below holds:

1. Decision-v1 classification is `clear_model_preference` under its frozen
   1-percentage-point minimum gap and 0.95 minimum pairwise-superiority
   requirements.
2. The actual action is empirically supported.
3. Every available action needed to establish the preferred supported action
   is supported. Publication-v1 does not weaken decision-v1's complete-support
   rule.
4. No supported action is sparse under the existing support policy.
5. Maximum tied-regulation-expiration transition mass is exactly zero.
6. Maximum pre-clip field-boundary mass among supported actions is at most
   **10%**. The comparison is inclusive at exactly 10% and withheld above it.
7. Maximum pre-clip clock-boundary mass among supported actions is exactly
   **zero**. Any positive clock clipping is withheld.

Field clipping is measured against the same empirical cell used by frozen
action-transition-v1, before its `[1, 99]` yards-to-goal clip. Scoring restarts
are not field clipping. Clock clipping is mass for which empirical elapsed time
would carry the hypothetical successor below zero seconds. The maximum is
taken across supported actions because the preferred action is selected from
that supported comparison set.

The zero clock limit is intentionally stricter than the field limit. Clock
clipping was historically uncommon, and publication-v1 has no validated model
for elapsed-time truncation at expiration. OT-boundary mass is separately
reported even when it co-occurs with clock clipping.

## Withholding taxonomy

The canonical record contains a primary status and all applicable
machine-readable reasons. Reasons can overlap; the primary status is only a
display grouping.

| Primary status | Meaning |
|---|---|
| `publishable` | Every publication-v1 gate passed. |
| `withhold_close_call` | Decision-v1 did not find a clear preference. |
| `withhold_support` | Actual, alternative, complete, or sparse support failed. |
| `withhold_clipping` | Field or clock clipping exceeded policy. |
| `withhold_overtime_scope` | A successor distribution includes unmodeled tied-expiration mass. |
| `withhold_uncertainty` | Frozen pairwise evidence is absent or internally inconsistent. |
| `withhold_model_form_risk` | A future explicit model-form safeguard not covered above failed. |

The current reason codes are:

- `decision_v1_close_call`
- `decision_v1_not_clear_model_preference`
- `actual_action_unsupported`
- `available_action_unsupported`
- `supported_action_sparse`
- `overtime_boundary_mass_nonzero`
- `decision_v1_pairwise_evidence_incomplete`
- `field_clipping_mass_above_policy`
- `clock_clipping_mass_above_policy`
- `known_heavy_field_clipping_regime`

No public wording is generated for a withheld record. Its internal explanation
states the operative limitation without being presented as a public excuse.

## Field-clipping sensitivity

The threshold candidates were 5%, 10%, and 25%. The diagnostic used
chronological folds: each season from 2020 through 2025 was evaluated using the
unchanged v1 specification fitted only on 2014 through the prior season. There
were 23,664 eligible decisions and 6,694 decision-v1 clear preferences.

| Maximum field clipping | Publishable | Eligible rate | Clear-preference rate | Max publishable clipping | Publishable support |
|---:|---:|---:|---:|---:|---|
| 5% | 3,606 | 15.24% | 53.87% | 4.59% | 3,606 two-action; 0 three-action |
| **10%** | **4,266** | **18.03%** | **63.73%** | **9.79%** | **4,182 two-action; 84 three-action** |
| 25% | 4,824 | 20.39% | 72.06% | 22.90% | 4,467 two-action; 357 three-action |

At 10%, publishable field clipping had median 0.66% and p90 6.73%. At 25%,
p90 rose to 11.62% and the maximum to 22.90%, approaching the historically
identified heavy-clipping regime. The 5% rule removed every otherwise-clean
three-action comparison. The 10% rule is therefore selected as a conservative
interior guardrail: it stays materially below the known `>25%` failure regime,
retains a small clean set of complete three-action comparisons, and was not
selected to maximize output volume.

The failed Milestone 7 Candidate C shape criterion remains failed. This policy
does not accept Candidate C, change the 12-yard gate, or create any v2 model.

## Historical result at the selected policy

Pooled 2020–2025 primary outcomes were:

| Outcome | Decisions | Eligible rate |
|---|---:|---:|
| Publishable | 4,266 | 18.03% |
| Withheld: support | 9,492 | 40.11% |
| Withheld: close call | 7,338 | 31.01% |
| Withheld: clipping | 2,428 | 10.26% |
| Withheld: OT scope | 140 | 0.59% |

Thus 36.27% of otherwise-clear decision-v1 preferences were withheld for
field or clock clipping. Multi-reason counts were 7,535 field-clipping, 581
clock-clipping, 7,790 available-action-unsupported, 2,510 sparse-supported,
140 OT-boundary, and 86 actual-action-unsupported flags. These counts overlap
and should not be added.

Selected-policy publishable rates were 15.26%, 14.07%, 19.70%, 19.41%, 19.64%,
and 19.68% for 2020 through 2025 respectively. The policy is not rubber-stamping
decision-v1.

## Permitted and prohibited language

Permitted language is model-specific and non-causal:

- “CoachIQ favored…”
- “the model estimated…”
- “modeled advantage…”
- “met CoachIQ v1's frozen evidence threshold…”

Do not say that a coach “made a mistake,” “cost the team” a modeled percentage,
made an “objectively correct” choice, or selected/nonselected an “optimal”
action. Do not turn model gaps into causal claims. Publication-v1 produces no
coach grades, rankings, or leaderboards.

## Known limitations

- V1 uses coarse empirical transition cells. The principal known limitation is
  hypothetical punt transport near field boundaries.
- The 10% cutoff reduces exposure; it does not repair model form.
- Pairwise intervals reflect a paired training-game cluster bootstrap, not all
  sources of structural uncertainty.
- Tied regulation-expiration successor states are out of scope and withheld.
- Source play-by-play can be corrected after retrieval; every report therefore
  retains a timestamp and source fingerprint and should be regenerated when a
  fingerprint changes.

Candidate C remains experimental. A later punt study may preregister a
principled continuous, boundary-aware formulation, but it does not block the
frozen-v1 product path.

## Reproduction

The complete sensitivity report is produced from explicit snapshots with:

```bash
PYTHONPATH=src .venv/bin/python scripts/study_publication_policy.py \
  --parquet-dir /tmp/coachiq-m8 \
  --json-output /tmp/coachiq-publication-study.json
```

The measured run took 786.37 seconds. Its report SHA-256 was
`6470e8a3196440fb1800371eef2b0d9e1f57c344f5e0d0b7faeb0e2240d5a629`.
The explicit 2025 source SHA-256 was
`5ed293fdf54d79e34426133829f3111faf577db29b8cfc25cf910d75eb55b2ef`.
No raw dataset or generated audit JSON is committed.
