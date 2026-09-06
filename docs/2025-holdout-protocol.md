# 2025 holdout protocol

Status: preregistered before first 2025 access

Preregistration timestamp: 2026-09-06T12:48:27Z

This document fixes the evaluation and acceptance rules for the one-time 2025
CoachIQ holdout. At the timestamp above, the repository had been read in full
and no 2025 play-by-play had been loaded, queried, summarized, or inspected in
this worktree or evaluation session. The purpose is evaluation of the frozen v1
stack, not model improvement.

## Frozen artifact identity

The evaluation starts from clean commit
`711022577a5302a6ec6db0b7bf4e3394c324ec46` (`Add audited fourth-down decision-value layer`).
The environment recorded before holdout access is Python 3.13.11, NumPy 2.5.2,
Polars 1.44.1, and nflreadpy 0.1.5.

The locked stack is:

- WP: `coachiq-wp-v1`, Candidate D, uncalibrated deterministic ridge logistic
  regression, L2 penalty 1.0, fitted on complete 2014--2024 seasons;
- action transitions: `coachiq-action-transition-v1`, fitted on eligible,
  reconstructed pre-2025 decisions only;
- decision values: `coachiq-decision-v1`;
- bootstrap: 200 shared multinomial whole-training-game draws, seed 2505,
  central 90% intervals, with differences within `1e-12` counted as ties;
- support: at least 30 comparable observations, sparse below 100, and field
  goals unavailable above 70 derived yards; and
- classification: `decision-threshold-v1`, requiring complete available,
  non-sparse support, zero supported-action overtime-boundary mass, a minimum
  1.0 percentage-point advantage over every supported alternative, and at
  least 95% paired superiority for `clear_model_preference`.

The frozen action cells are go distance (1, 2, 3--5, 6--10, 11+) crossed with
field zone (opponent red zone, opponent 21--49, own 21 to midfield, own 1--20),
field-goal attempt distance (under 30, 30--39, 40--49, 50--59, 60--70), and punt
field zone using the same four zones. The 13 WP features, missing-spread
treatment, target, fitting algorithm, transition filters, transport equations,
physical clipping, possession inversion, and overtime safeguard remain exactly
as documented in the existing model card and methodologies.

Pre-access SHA-256 fingerprints:

| Source | SHA-256 |
|---|---|
| `src/coachiq/models/state_value.py` | `b5a757f513baf04e1ac0bdf37cf34947257cee9b040a1891adf57e634cfb3307` |
| `src/coachiq/models/wp_selection.py` | `0e683d6a2e23989ca1fb840d42255be4e6bcee5669599847d8802a18e75548f2` |
| `src/coachiq/models/action_baselines.py` | `d03391f3ad8dce97ef44e458870453f732321e11cb23ec67c2721a85616a9a97` |
| `src/coachiq/analysis/decision_value.py` | `6709cf7f960dbb53240ed81dc5ab5530ebff0a5a7c48e5bbdbfd2edf6d3da9fe` |
| `src/coachiq/analysis/decision_diagnostics.py` | `bbe816c577c5b9f45b674bbfcfc84ca874dc373c3dd21a80cf842918bc6d9fe2` |
| `src/coachiq/analysis/fourth_down.py` | `0ebec62d5dad9b034c5377aa8be04ee3147f8b7231d2e0bbf53bf771e29a3f9b` |
| `src/coachiq/data/normalize.py` | `22dd09c20f0973f82fba5b514566ac4a7249603094c415c896758b0417418c4f` |
| `src/coachiq/data/schema.py` | `4a940b260d6afd1ddf3fe0ff20c6c9945dcf22773e7db7d0cd4c89d1daaf52d9` |

The explicit holdout runner and reporting code may be added after this
preregistration. It may call and diagnose the frozen stack, but may not change
the files or behavior fingerprinted above. Tests will verify training seasons
are exactly 2014--2024 and evaluation season is exactly 2025.

## Evaluation population and comparisons

The single evaluation population is normalized nflverse 2025 play-by-play.
`coachiq-wp-v1` is fitted once on 2014--2024 state rows; action transitions are
fitted once on 2014--2024 candidate rows. No 2025 row, target, outcome,
transition, calibration residual, support count, or diagnostic enters either
fit. There is no 2025 recalibration, threshold tuning, cell revision, model
selection, or repeat holdout decision.

WP is evaluated on the existing complete regulation state-row definition.
Decision diagnostics are evaluated on existing eligible regulation fourth-down
decisions. Ordinary and Vegas nflverse WP are diagnostic references only and
are evaluated only where present. The constant reference is the 2014--2024
training-target prevalence.

Historical comparisons use like-for-like season results from the frozen
expanding-origin evaluations. The principal CoachIQ WP ranges are:

| Metric | 2020--2024 season range |
|---|---:|
| State-row log loss | 0.4205--0.5232 |
| State-row Brier score | 0.1382--0.1725 |
| State-row ECE | 0.0087--0.0318 |
| Factual observed-action EWP log loss | 0.4216--0.5197 |
| Factual observed-action EWP Brier | 0.1385--0.1713 |
| Factual observed-action EWP ECE | 0.0144--0.0367 |
| Eligible decisions | 3,571--4,188 |
| Any sparse supported action | 8.80%--16.05% |
| OT-boundary affected | 0.50%--0.73% |
| Gap P90 | 1.81%--2.41% |
| Gap P95 | 2.86%--3.84% |
| Maximum gap | 9.49%--12.20% |

All report comparisons will also show the underlying season values rather than
only the ranges.

## Fixed warning criteria

A result outside an observed historical range is descriptive and is not alone
a failure. The following margins define a material warning. A threshold is
applied only to a non-sparse slice: at least 500 WP state rows, 100 factual EWP
rows, 100 binary-transition rows, 100 punt rows, or 100 decisions for a drift
slice. Sparse results are printed and labeled but do not trigger a rate or
metric warning by themselves.

### WP model

- Overall warning: log loss above 0.5532, Brier above 0.1875, or ECE above
  0.0518 (the worst 2020--2024 result plus 0.03, 0.015, or 0.02).
- Fixed calibration-band warning: absolute gap above 0.08 in any non-sparse
  10-point band. Extreme-band warning: absolute gap above 0.06 in either the
  0--10% or 90--100% band.
- Regime warning: a clock- or score-regime log loss more than 0.05 above its
  worst like-for-like 2020--2024 value, or ECE more than 0.03 above its worst
  like-for-like value.
- Sanity warning: any non-finite or out-of-range probability, any declared
  property-grid violation, or failure of the frozen feature/version checks.

The WP result is catastrophic if log loss exceeds 0.6232, Brier exceeds 0.2225,
ECE exceeds 0.08, both proper scores are worse than the constant reference, a
non-sparse calibration band has a gap of at least 0.15, or a probability or
target-integrity check fails.

### Factual-action behavior

- Overall factual EWP warning: log loss above 0.5497, Brier above 0.1913, or
  ECE above 0.0567.
- By-action factual EWP warning: a metric above its 2020--2024 action-specific
  maximum by more than 0.05 log loss, 0.03 Brier, or 0.03 ECE.
- Go/field-goal transition warning: log loss or Brier above its like-for-like
  historical maximum by more than 0.05 or 0.03.
- Punt warning: destination MAE above 10.06 yards or RMSE above 14.87 yards
  (historical maximum plus 2 or 3 yards).

Factual behavior is catastrophic if overall factual EWP log loss exceeds
0.6197 and Brier exceeds 0.2213 together, or if a reconstruction/perspective
correctness invariant fails. These checks remain evidence about observed
actions only and cannot validate unobserved counterfactuals.

### Support, classifications, overtime, and gaps

For 3/2/1/0-action support, any-sparse support, each classification, and OT
frequency, a material drift warning requires the 2025 rate to lie outside the
2020--2024 season range by more than 3 percentage points. For each actual
action's unsupported rate, the fixed margin is 2 percentage points. Zero
supported actions, absent historically, is always flagged if it occurs.

For gap quantiles, a warning requires P75, P90, or P95 to be outside its
historical season range by both more than 25% of the nearer range endpoint and
more than 0.5 percentage points. The maximum is warned above 17.20% (the prior
maximum plus 5 points); the median is reported but its historical value of zero
is not treated as a meaningful denominator. An eligible-decision count outside
the historical range is contextual, not independently adverse.

For OT-boundary mass, in addition to the frequency rule, warn if the median,
P75, P90, or P95 among affected decisions exceeds the historical maximum for
that quantile by more than 10 percentage points. The safeguard is never
relaxed.

## Preregistered clipping audit

Clipping is calculated before the existing bounds are applied. For every
eligible decision and every supported action:

- field clipping mass is the share of non-scoring-reset transition rows whose
  query-relative decision-team yards-to-goal is below 1 or above 99;
- clock clipping mass is the share whose query-relative successor clock is
  below 0; and
- combined clipping mass is the share with either condition (a row satisfying
  both is counted once).

Timeout clipping is retained as an auxiliary diagnostic but is not folded into
the two requested clipping definitions. At decision level, each measure is the
maximum mass among supported actions; decisions without a supported action are
reported separately and excluded from mass-rate denominators. Threshold
labels mean `any` (>0), `>10%`, `>25%`, and `>50%` exactly; equality does not
enter the strict threshold. Reports include counts and rates by action, field
zone, time regime, classification, actual action, and gap-percentile group.
Gap groups are fixed from the holdout distribution as unavailable, 0--50th,
50th--75th, 75th--90th, 90th--95th, and top 5%; deterministic boundary ties go
into the lower-numbered percentile group.

A material clipping warning occurs if any of these conditions holds:

1. decision-level field or clock mass above 25% affects at least 5% of eligible
   decisions or at least 10% of clear-model-preference decisions;
2. mass above 50% affects at least 1% of eligible decisions;
3. at least 5 of the top 20 gaps have field or clock mass above 25%; or
4. a threshold rate exceeds the maximum like-for-like 2020--2024 season rate
   by both 5 percentage points and 50% of that historical maximum.

Clipping is a severe model-form finding if mass above 50% affects at least 20%
of all eligible decisions, at least 33% of clear-model-preference decisions,
or at least 10 of the top 20 largest gaps. Correct transport that reaches a
bound is a model-form warning, not a correctness bug. A mismatch between the
implemented clipped successor and its documented query-relative formula is a
potential correctness bug regardless of frequency.

## Largest-gap review

The 20 largest available actual-action gaps are selected deterministically by
descending raw gap and then game ID and play ID. All 20 will show the input
state, actual action, description, support, modeled values, classification,
possession/score/clock/field/timeout transport checks, scoring restarts,
OT-boundary mass, and pre-clip mass by action. Each case receives exactly one
review label:

- `structurally_clean`: all reconstruction and transport invariants pass and no
  supported action exceeds 25% field or clock clipping;
- `model_form_warning`: invariants pass but an action exceeds 25% clipping, OT
  scope is reached, or the coarse cell exposes an otherwise documented
  modeling limitation; or
- `potential_correctness_bug`: a source-state, reconstruction, perspective,
  transport-formula, bound, version, or training-boundary invariant fails.

No case will be suppressed or repaired during Milestone 6.

## Overall decision rule

Exactly one final status will be assigned:

- **PASS**: no catastrophic or severe finding, no potential correctness bug,
  and none of the fixed material-warning rules fires.
- **PASS WITH LIMITATIONS**: no catastrophic finding or potential correctness
  bug, but one or more fixed warnings or model-form warnings fires and the
  stack remains suitable for internal research with those limitations.
- **FAIL — NEW VERSION REQUIRED**: any contamination, artifact-identity,
  determinism, target-isolation, reconstruction, or transport correctness
  failure; any catastrophic WP/factual criterion; any severe clipping finding;
  or another documented finding that invalidates v1 for downstream public
  decision analysis.

The final clause cannot be used to invent a new numerical cutoff after seeing
2025: it applies only to concrete correctness failures not expressible as a
metric threshold. A fail leads to a separately versioned v2 development cycle,
not a v1 patch. The report will preserve all results, warnings, and limitations
regardless of status.
