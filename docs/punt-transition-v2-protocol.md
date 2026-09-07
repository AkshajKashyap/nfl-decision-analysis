# Punt transition v2 development protocol

Status: preregistered before candidate comparison

Preregistration timestamp: 2026-09-06T14:47:10Z

Starting commit: `2e0fb3e2618fb0e98005b29a01c051ff8e922c81`

This protocol fixes the Milestone 7 comparison of boundary-aware punt
transitions. Candidate design and thresholds use only the 2014--2024
development data and the frozen v1 diagnosis. No 2025 or 2026 play-by-play,
candidate result, or case may be loaded or inspected. The already-consumed
2025 holdout remains unchanged and is not evidence for candidate selection.

## Scope and frozen components

Only punt field-position transport is in scope. `coachiq-wp-v1`, the go and
field-goal transitions in `coachiq-action-transition-v1`, the 30-observation
support threshold, the 100-observation sparse threshold, decision thresholds,
the paired game bootstrap, the overtime safeguard, and all score, possession,
clock, timeout, down, and distance transport rules remain fixed.

The chronological folds are 2014--2019 to 2020, expanding one season at a time
through 2014--2023 to 2024. All model fitting and support counts for a fold use
only seasons earlier than its evaluation season. The five evaluation seasons
are development evaluations, not untouched holdouts.

## Frozen v1 diagnosis

Candidate A reproduces the existing punt model exactly. Its fold metrics are:

| Evaluation | Punts | MAE | RMSE | Median AE | P90 AE | CRPS |
|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 1,980 | 7.5715 | 11.6048 | 5.3900 | 15.1247 | 5.6339 |
| 2021 | 2,169 | 7.6275 | 11.0192 | 5.8569 | 15.6968 | 5.6332 |
| 2022 | 2,269 | 7.7994 | 11.7141 | 5.7662 | 15.3943 | 5.7406 |
| 2023 | 2,338 | 7.7543 | 11.3772 | 5.8724 | 15.3789 | 5.6629 |
| 2024 | 2,109 | 8.0552 | 11.8718 | 6.1389 | 15.7488 | 5.8467 |

Across 16,272 supported historical query states, v1 has nonzero pre-boundary
clip mass for 94.77%, more than 10% mass for 31.43%, more than 25% for 20.26%,
and more than 50% for 14.96%. The concentration is structural. A delta learned
from the broad opponent 21--49 cell is applied regardless of exact starting
spot, so many otherwise ordinary punt advances cross the opponent goal line
when transported to the short end of that cell. The final `.clip(1, 99)` keeps
outputs legal but converts impossible movement into artificial boundary mass.

The 25,306 reconstructed punt transitions have legal observed destinations.
Kick distance, return yards, touchback, block, fair-catch, out-of-bounds,
downed, end-zone, and inside-20 fields are non-null on all retained rows. Kick
distance minus recorded return yards correlates 0.833 with reconstructed net
movement but differs by 2.37 yards on average, consistent with penalties and
play-record conventions. Those components are useful diagnostics, but not
reliable enough to replace the reconstructed successor state in this study.

Destination behavior varies materially with the start: mean opponent
destination is 57.9 after punts from the punting team's own 1--20, 73.5 from
its own 21--40, 83.8 from its own 41 through midfield, and 87.8 from the
opponent 49--35. Finer cells would collapse support: only 25 qualifying punts
from the opponent 34--21 exist across all 2014--2024, and none from the
opponent red zone. Candidate conditioning therefore retains the four v1 cells.

There are 1,711 recorded touchbacks. The observed next-possession destination
has median 80 in every season and equals 80 for 92.1%--98.6% by season. The
exceptions are retained rather than overwritten because penalties and source
conventions can move the ensuing snap. No unobserved rule change is encoded.

## Candidate definitions

All candidates retain each sampled row's game cluster, possession result,
score and clock deltas, timeouts, next down and distance, outcome label, and
terminal-state eligibility. A nonzero score delta remains a football reset and
uses the observed absolute successor field position.

### Candidate A: frozen v1

Use the existing four starting-field cells. For every non-scoring sample, add
the historical decision-team-oriented yards-to-goal delta to the query and
clip the result to 1--99 before applying the sampled possession perspective.
This implementation and version remain immutable.

### Candidate B: direct conditional destination

Use the same four cells and support policy. For every non-scoring sample, copy
the sampled row's observed `next_yards_to_goal`, already expressed from the
sampled next possession's perspective. This models the legal absolute
destination distribution conditional on the query's coarse starting cell.
It is empirical, deterministic, and bounded without post-hoc clipping, but it
can be piecewise constant within a cell and may jump at a cell boundary.

### Candidate C: bounded available-field-fraction transport

Use the same four cells and support policy. Let `s` be the historical start,
`h` the historical non-scoring successor in decision-team yards-to-goal
coordinates, and `q` the query start. For non-touchback samples:

```text
if h <= s: f = (s - h) / (s - 1);  h_query = q - f * (q - 1)
if h >  s: f = (h - s) / (99 - s); h_query = q + f * (99 - q)
```

Zero-length denominators use fraction zero. Fractions must lie in `[0, 1]`
apart from floating-point tolerance; violations are correctness failures, not
values to clip. The sampled possession perspective converts `h_query` to the
next state's yards to goal. Recorded touchbacks use their observed absolute
next-possession destinations so the empirical point mass, including
penalty/convention exceptions, is preserved rather than smeared. Scoring
samples continue to use their existing absolute restart destination.

No fourth candidate will be evaluated: the source audit gives no strong reason
to add one, and a kick-minus-return decomposition would discard known
reconstruction information.

## Fixed evaluation outputs

For factual punts, report MAE, RMSE, median absolute error, P90 absolute error,
and empirical CRPS by fold and pooled. Pooled point metrics are computed from
all fold-level prediction errors, not by averaging nonlinear season metrics.

For every eligible query state, report availability, support, sparsity,
effective observations/games, and pre-boundary invalid mass at strict `>0`,
`>10%`, `>25%`, and `>50%` thresholds. Stratify by start zone, the six
diagnostic position bands, yards-to-go band, time regime, and frozen v1
classification when available. Intrinsically bounded candidates report zero
invalid mass; legal mass exactly at 1 or 99 is reported separately and is not
called clipping.

Deterministic stress starts are own 10/25/40, midfield, and opponent 45/35/25/15.
Each uses fourth-and-5, tied score, third quarter, 1,500 regulation seconds
remaining, three timeouts per team, home possession, and zero pregame spread.
Report support, mean, median, P10/P90, legal-boundary mass, touchback mass, and
width. A full one-yard grid checks within-cell evolution and cell-boundary
jumps.

Factual differences use 2,000 deterministic whole-evaluation-game bootstrap
draws with seed 2707. Predictions remain fixed inside each chronological fold;
games are resampled within fold, folds are pooled, and central 90% percentile
intervals are reported for candidate-minus-v1 MAE, RMSE, and CRPS. This
captures evaluation-game clustering, not training-fit or model-form
uncertainty.

The offline decision sensitivity refits only the frozen chronological inputs,
then substitutes each candidate's punt distribution while retaining
`coachiq-wp-v1`, v1 go/field-goal behavior, seed 2505, 200 shared training-game
draws, threshold policy, and overtime safeguard. Report punt EWP changes,
actual-action gap changes, classification changes, clear-case invalid-mass
rates, largest gap changes, and audited development cases with heavy v1 punt
clipping. These are diagnostics and do not create or modify a decision model.

## Preregistered acceptance rule

A candidate is eligible for acceptance only if all gates pass:

1. **Boundary improvement.** Pooled rates above 25% and above 50% invalid
   field mass must each fall by at least 90% from v1 and be no greater than 2%
   and 1%, respectively. Every fold must reduce both rates by at least 85%.
2. **Factual noninferiority.** Relative to v1, pooled MAE may increase by at
   most 0.35 yards, RMSE by 0.50, median AE by 0.50, P90 AE by 1.00, and CRPS
   by 0.30. The upper endpoint of the clustered 90% interval may not exceed
   +0.50 for MAE, +0.75 for RMSE, or +0.40 for CRPS. In every season, MAE may
   increase by at most 0.75, RMSE by 1.00, and CRPS by 0.50.
3. **Support preservation.** Unsupported and sparse rates may each rise by at
   most 0.5 percentage points overall and in every fold. Median effective
   observations and games must each remain at least 95% of v1. Physical punt
   availability must be unchanged.
4. **Football and transport sanity.** All destinations must be finite and in
   1--99 without concealing invalid transport through a final clamp. Scoring
   restarts and all non-field state columns must equal v1 sample-for-sample.
   Possession perspective must be correct. Touchback successor destinations
   must equal their sampled empirical destinations. Genuine long returns,
   blocks, scores, safeties, and possession-retained samples must remain.
5. **Shape and stability.** No stress distribution may have P90--P10 below
   five yards unless the underlying cell itself does. The largest adjacent
   one-yard change in mean destination may not exceed 12 yards. Within-cell
   behavior may not create a greater-than-five-yard reversal against the
   historical start/destination relationship. There may be no unexplained
   artificial pile at 1 or 99 and no fold-specific support or accuracy
   collapse.
6. **Decision audit.** No non-punt action value, support decision, bootstrap
   draw, or OT rule may change. Every audited large EWP/gap or classification
   change must trace only to the candidate field destination. Any unexplained
   change or transport invariant failure rejects the candidate. Decision
   movement alone is not optimized and cannot rescue failure on gates 1--5.

If exactly one candidate passes, accept it. If both pass, choose the one with
lower pooled CRPS when they differ by at least 0.05 yards; otherwise choose the
lower pooled MAE when it differs by at least 0.10 yards; otherwise choose the
one with the smaller maximum one-yard mean-destination jump. If that final
difference is below 0.25 yards, the result is `INCONCLUSIVE`. A failed gate
cannot be waived because another metric improves. If neither candidate passes,
the result is `KEEP V1` unless the failures expose unresolved, materially
opposed tradeoffs, in which case it is `INCONCLUSIVE`.

The final study decision must be exactly `KEEP V1`, `ACCEPT V2`, or
`INCONCLUSIVE`. Only an accepted candidate receives the
`coachiq-action-transition-v2` identifier; v1 is never modified or deleted.
