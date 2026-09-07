# Boundary-aware punt transition study

Status: Milestone 7 complete

Decision: `INCONCLUSIVE`

Development and evaluation data: 2014--2024 only

Protected and not accessed: 2025 and 2026

`coachiq-action-transition-v1` remains the current transition model. No v2
identifier is assigned. This study found a promising bounded formulation, but
it did not satisfy every acceptance gate fixed in
[the preregistered protocol](punt-transition-v2-protocol.md).

## Problem and v1 reproduction

The v1 punt cell samples a decision-team-oriented field-position delta, adds it
to the query start, and clips to 1--99. That is reasonable in the middle of a
cell but not invariant to available field length. The opponent 21--49 cell, for
example, combines punts whose feasible forward runway differs by 28 yards.
Moving its common delta distribution to the opponent 21 turns ordinary punts
into impossible goal-line crossings and then a point mass at the bound.

The rolling replay exactly reproduced the frozen v1 MAE and RMSE. Extended
distributional metrics were:

| Evaluation | Punts | MAE | RMSE | Median AE | P90 AE | CRPS |
|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 1,980 | 7.5715 | 11.6048 | 5.3900 | 15.1247 | 5.6339 |
| 2021 | 2,169 | 7.6275 | 11.0192 | 5.8569 | 15.6968 | 5.6332 |
| 2022 | 2,269 | 7.7994 | 11.7141 | 5.7662 | 15.3943 | 5.7406 |
| 2023 | 2,338 | 7.7543 | 11.3772 | 5.8724 | 15.3789 | 5.6629 |
| 2024 | 2,109 | 8.0552 | 11.8718 | 6.1389 | 15.7488 | 5.8467 |
| Pooled | 10,865 | 7.7635 | 11.5174 | 5.8484 | 15.4574 | 5.7036 |

Among 16,272 supported historical fourth-down query states, v1 pre-boundary
invalid mass was nonzero for 94.77%, above 10% for 31.43%, above 25% for
20.26%, and above 50% for 14.96%. The extreme rates are concentrated where
available field is shortest:

| Query start | States | Any | >10% | >25% | >50% |
|---|---:|---:|---:|---:|---:|
| Own 1--20 | 1,881 | 67.36% | 0.00% | 0.00% | 0.00% |
| Own 21--40 | 6,079 | 100.00% | 0.00% | 0.00% | 0.00% |
| Own 41--midfield | 2,540 | 100.00% | 48.15% | 0.00% | 0.00% |
| Opponent 49--35 | 3,112 | 92.38% | 39.56% | 20.44% | 0.00% |
| Opponent 34--21 | 2,660 | 100.00% | 100.00% | 100.00% | 91.54% |

The same pattern occurs across every yards-to-go and time group. It is worse in
the final two minutes: 30.51% of supported states exceed 25% invalid mass and
23.72% exceed 50%, versus 19.38% and 14.21% in other regulation states. This is
not evidence that time or yards to go causes clipping; those groups contain
different field-position mixes.

## Source-field and mechanism audit

The retained 2014--2024 evidence contains 25,306 reconstructed punt
transitions from 3,004 distinct games. All observed successor locations are
inside 1--99. The raw
punt-attempt, kick-distance, return-yard, touchback, block,
fair-catch, out-of-bounds, downed, end-zone, and inside-20 fields are non-null
on these rows and their binary values are valid.

Recorded kick distance correlates 0.643 with reconstructed net field movement.
Kick distance minus recorded return yards improves the correlation to 0.833,
but still differs from reconstructed net movement by 2.37 yards on average.
Penalties, blocks, scoring plays, and source conventions make that decomposition
inferior to the already audited factual successor state, so it was diagnosed
but not made a model target.

The empirical start-to-destination relationship is strong:

| Historical start | Punts | Mean opponent destination | Median | P10--P90 | Touchback |
|---|---:|---:|---:|---:|---:|
| Own 1--20 | 4,517 | 57.93 | 59 | 43--73 | 0.13% |
| Own 21--40 | 12,319 | 73.53 | 75 | 60--88 | 3.21% |
| Own 41--midfield | 4,688 | 83.83 | 85 | 75--94 | 13.16% |
| Opponent 49--35 | 3,757 | 87.79 | 89 | 80--96 | 18.31% |
| Opponent 34--21 | 25 | 86.76 | 88 | 70--97 | 20.00% |

The final row explains why finer direct cells were rejected before comparison:
only 25 punts exist in eleven seasons, spread across 24 games, and there are no
eligible reconstructed red-zone punts. Fine conditioning would remove clipping
by abstaining in precisely the states of interest.

Unusual outcomes remain real evidence: 79 classified punt blocks, 91 return
touchdowns, 48 punt-team touchdowns, and 17 safeties are present. They were not
trimmed or winsorized.

## Candidates

- **A, v1:** unchanged delta transport followed by clipping.
- **B, direct destination:** sample the observed legal next-possession
  destination from the query's existing four-field-zone cell. This preserves
  support but is constant within a cell.
- **C, bounded transport:** express each ordinary historical movement as the
  fraction of available field traversed in its direction and apply that
  fraction to the query's available field. Observed touchback destinations and
  scoring restarts remain absolute. Possession then determines perspective.

Candidate definitions were fixed before these results were produced. No model
zoo or optional candidate was run.

## Preregistered acceptance gates

The protocol required every accepted candidate to pass all six gates:

1. reduce pooled `>25%` and `>50%` invalid-mass rates by at least 90%, to no
   more than 2% and 1%, and reduce both by at least 85% in every fold;
2. remain within pooled factual tolerances of +0.35 MAE, +0.50 RMSE, +0.50
   median AE, +1.00 P90 AE, and +0.30 CRPS, the stated clustered-interval
   upper bounds, and the stated per-season tolerances;
3. limit any unsupported/sparse-rate increase to 0.5 percentage points,
   preserve at least 95% of median effective observations/games, and leave
   physical availability unchanged;
4. produce finite legal destinations without a concealed final clamp while
   preserving possession, touchbacks, scoring restarts, and rare outcomes;
5. preserve distribution width, avoid unexplained boundary piles or seasonal
   collapse, and keep the largest adjacent one-yard mean jump at or below 12
   yards with no material within-cell reversal; and
6. leave every non-punt action value, support decision, bootstrap rule, and OT
   rule unchanged, with every decision change traceable to punt field position.

These thresholds and the tie-breaking rule are reproduced verbatim in the
protocol. None was changed after candidate results were observed.

## Chronological factual comparison

| Season | Candidate | MAE | RMSE | Median AE | P90 AE | CRPS |
|---:|:---:|---:|---:|---:|---:|---:|
| 2020 | A | 7.5715 | 11.6048 | 5.3900 | 15.1247 | 5.6339 |
|  | B | 8.7764 | 12.4608 | 6.9581 | 17.8327 | 6.3186 |
|  | C | 7.8252 | 11.7581 | 5.8221 | 15.8231 | 5.7833 |
| 2021 | A | 7.6275 | 11.0192 | 5.8569 | 15.6968 | 5.6332 |
|  | B | 8.9352 | 12.1469 | 7.1311 | 18.1602 | 6.3531 |
|  | C | 7.9313 | 11.3174 | 6.0897 | 16.3539 | 5.7849 |
| 2022 | A | 7.7994 | 11.7141 | 5.7662 | 15.3943 | 5.7406 |
|  | B | 9.1469 | 12.7829 | 7.1390 | 17.9333 | 6.5282 |
|  | C | 8.2021 | 12.0071 | 6.2290 | 16.1400 | 5.9677 |
| 2023 | A | 7.7543 | 11.3772 | 5.8724 | 15.3789 | 5.6629 |
|  | B | 8.8516 | 12.4364 | 6.8155 | 17.8155 | 6.3180 |
|  | C | 7.9185 | 11.6380 | 6.0041 | 15.9850 | 5.7752 |
| 2024 | A | 8.0552 | 11.8718 | 6.1389 | 15.7488 | 5.8467 |
|  | B | 9.4343 | 12.9648 | 7.7623 | 18.2377 | 6.6281 |
|  | C | 8.4400 | 12.1923 | 6.6821 | 16.2789 | 6.0823 |
| Pooled | A | 7.7635 | 11.5174 | 5.8484 | 15.4574 | 5.7036 |
|  | B | 9.0294 | 12.5612 | 7.1390 | 17.8610 | 6.4292 |
|  | C | 8.0645 | 11.7844 | 6.1950 | 16.1456 | 5.8784 |

B fails factual noninferiority by wide margins. C is worse than A on every
pooled metric and in every season, but remains inside every preregistered point
and per-season noninferiority tolerance.

The 2,000-draw evaluation-game-clustered bootstrap gives candidate-minus-v1
differences (central 90% intervals):

| Candidate | Delta MAE | Delta RMSE | Delta CRPS |
|:---:|---:|---:|---:|
| B | +1.2658 [1.1771, 1.3531] | +1.0439 [0.9398, 1.1478] | +0.7256 [0.6688, 0.7783] |
| C | +0.3010 [0.2361, 0.3649] | +0.2670 [0.1975, 0.3378] | +0.1748 [0.1341, 0.2139] |

The intervals quantify a consistent factual cost; they do not include model-fit
or model-form uncertainty.

Candidate C's exact pooled tradeoff against v1 is +0.3010 yards MAE, +0.2670
yards RMSE, and +0.1748 yards CRPS. The corresponding clustered 90% intervals
are [0.2361, 0.3649], [0.1975, 0.3378], and [0.1341, 0.2139]. These pass the
noninferiority limits but establish that the modest degradation is systematic,
not an isolated season fluctuation.

## Clipping, legal boundaries, and support

| Candidate | Any invalid | >10% | >25% | >50% |
|:---:|---:|---:|---:|---:|
| A | 94.77% | 31.43% | 20.26% | 14.96% |
| B | 0.00% | 0.00% | 0.00% | 0.00% |
| C | 0.00% | 0.00% | 0.00% | 0.00% |

B and C are legal by construction in every fold and every field, distance, and
time stratum. Both exceed the required 90% reduction. Exact legal positions 1
or 99 still occur because the empirical rows contain genuine bounds, scoring
restarts, and exceptional outcomes. Candidate C's maximum legal-boundary mass
is 3.66%, versus v1's 94.94%; it is not hidden invalid mass.

Support is identical for A, B, and C because all use the same v1 cells and
thresholds. Punt availability is 100%. Pooled support is 82.60% and unsupported
rate is 17.40%; no supported punt cell is sparse. The supported rate by fold is
82.61%, 82.05%, 82.86%, 82.98%, and 82.47%. Across pooled supported queries,
the median effective cell contains 9,476 observations from 1,867 games. Thus
Candidate C's availability, unsupported, sparse, effective-observation, and
effective-game differences from v1 are all exactly zero.

## Touchbacks and transition invariants

There are 1,711 recorded touchbacks. The next-possession destination has median
80 in every season. The exact share at 80 ranges from 92.1% to 98.6%; observed
exceptions range from 10 to 99 and are retained because penalties and data
conventions can affect the ensuing snap. B and C preserve the sampled empirical
touchback destination exactly. In contrast, v1 transports touchback deltas: at
the opponent 25 stress state, its touchback median becomes 99, while B and C
retain 80.

For every tested supported field cell, B and C pass legal bounds, deterministic
repeatability, possession perspective, touchback equality, scoring-restart
equality, and outcome-count equality. All non-field sample columns equal v1.
Go and field-goal distributions equal v1 exactly. Blocks, long returns, scores,
safeties, and possession-retained outcomes remain in the samples.

## Deterministic stress states and shape

Each state is tied, fourth-and-5, at 10:00 of the third quarter with three
timeouts per team. Entries are mean; median; P10--P90 opponent yards to goal.

| Start | A | B | C |
|---|---|---|---|
| Own 10 | 54.09; 54; 41--68 | 57.93; 59; 43--73 | 56.25; 56.48; 41.57--71.19 |
| Own 25 | 67.11; 68; 56--79 | 76.36; 79; 61--91 | 74.09; 75.78; 59.57--88.75 |
| Own 40 | 81.52; 83; 71--94 | 76.36; 79; 61--91 | 78.59; 80; 67.53--90.74 |
| Midfield | 90.07; 93; 80--99 | 76.36; 79; 61--91 | 81.59; 82.45; 72.80--92.12 |
| Opponent 45 | 86.61; 88; 77--95 | 87.79; 89; 80--96 | 87.63; 89; 80--96.19 |
| Opponent 35 | 94.67; 98; 87--99 | 87.79; 89; 80--96 | 89.31; 91.21; 80--96.83 |
| Opponent 25 | 97.90; 99; 97--99 | 87.79; 89; 80--96 | 90.99; 93.50; 80--97.46 |
| Opponent 15 | unsupported | unsupported | unsupported |

V1 collapses at the short boundary: at the opponent 25, 84.51% of the raw
distribution is invalid and 87.28% lands exactly on a legal boundary after
clipping. C has zero invalid mass and 3.46% observed boundary mass there, while
retaining a 17.46-yard P10--P90 width.

On the complete one-yard grid, maximum adjacent mean jumps are 7.38 yards for
A, 18.43 for B, and 12.025 for C. B is piecewise constant and fails the 12-yard
shape gate badly. C evolves smoothly within each cell with no direction
reversal, but the own-21--40 to own-1--20 boundary at yards-to-goal 79--80 is
still a 12.025-yard discontinuity. That narrowly but unambiguously exceeds the
preregistered 12-yard maximum. No rounding exception is applied.

## Frozen decision-layer sensitivity

This is an offline substitution study, not a new decision model. All 19,700
eligible 2020--2024 decisions were rescored with the frozen WP model, 200
shared whole-training-game draws using seed 2505, v1 decision thresholds, and
the unchanged OT policy.

| Measure | B vs A | C vs A |
|---|---:|---:|
| Supported punt states | 16,272 | 16,272 |
| Mean punt EWP change | -0.266 pp | -0.138 pp |
| P10--P90 punt EWP change | -1.835 to +1.103 pp | -1.239 to +0.836 pp |
| Minimum--maximum punt EWP change | -3.295 to +3.134 pp | -2.026 to +2.292 pp |
| Classification changes | 2,028 (10.29%) | 1,495 (7.59%) |
| Preferred-action changes | 1,812 | 1,317 |
| Clear-preference rate | 30.81% | 29.87% |
| Mean actual-action-gap change | +0.058 pp | +0.010 pp |

V1's clear-preference rate is 27.80%. Among its clear cases, 27.24% exceed 25%
punt invalid mass and 20.83% exceed 50%. B and C reduce candidate clear-case
invalid mass to zero. The limited- and insufficient-support counts do not move,
confirming support and OT behavior are unchanged.

For the 3,296 v1 states above 25% invalid mass, C reduces punt EWP by 0.850
percentage points on average and changes 148 classifications. This direction
is coherent: v1's clipped mass overstates the opponent's yards to goal, making
the hypothetical punt look more favorable to the decision team. C's top-20
gap list overlaps v1's in 15 cases; its maximum gap rises from 12.20% to 13.14%
because reducing punt value can enlarge a gap when punt was the observed
action. These are expected consequences, not evidence of causal correctness.

Every go and field-goal point value is bit-for-bit equal across candidates. All
audited changes trace to the punt destination and pass score, clock, timeout,
possession, bootstrap, and OT invariants.

## Representative development cases

These cases are development examples selected from v1's heaviest clipping,
not 2025 cases.

| Case | V1 punt distribution / EWP | C distribution / EWP | Result |
|---|---|---|---|
| 2024 ARI--BUF, play 3763, opponent 21 | mean 98.30, median 99, P10--P90 99--99; 92.89% invalid; EWP 72.29% | mean 91.69, median 94.42, P10--P90 80--97.70; 0% invalid; EWP 71.03% | Removes the collapsed boundary mass; field goal remains preferred. |
| 2024 BAL--KC, play 1783, opponent 35 | mean 94.69, median 98, P10--P90 87--99; 40.69% invalid; EWP 26.19% | mean 89.34, median 91.21, P10--P90 80--96.78; 0% invalid; EWP 25.25% | Restores spread without changing the close-call label. |
| 2020 HOU--KC, play 1039, midfield | mean 89.88, median 93, P10--P90 80--99; 22.67% invalid; EWP 23.95% | mean 81.49, median 82.44, P10--P90 72.35--92.17; 0% invalid; EWP 22.53% | Go remains preferred; actual-punt gap rises from 0.95% to 2.37%. |

C therefore fixes the identified mechanism rather than merely changing a
summary number. Separate largest-change review also exposes its remaining
weakness: many largest positive punt-EWP shifts occur exactly at yards-to-goal
79, immediately before the coarse cell boundary.

## New model-form warnings

- Direct absolute destinations are not adequate with the four support-safe
  cells: B creates piecewise-constant curves and an 18.43-yard boundary jump.
- Normalized available-field transport does not by itself remove coarse-cell
  discontinuity: C still jumps 12.025 yards at 79--80.
- C lowers factual accuracy consistently even though the degradation remains
  inside the fixed noninferiority margins.
- C changes 7.59% of frozen historical classifications, and its largest
  positive EWP shifts cluster at yards-to-goal 79 rather than in the most
  heavily clipped opponent-territory states. That is a reason for caution,
  not a correctness failure.

## Acceptance assessment and decision

| Gate | B | C |
|---|:---:|:---:|
| Boundary reduction | Pass | Pass |
| Factual noninferiority | **Fail** | Pass |
| Support preservation | Pass | Pass |
| Transport/football invariants | Pass | Pass |
| Shape and stability | **Fail** | **Fail** |
| Frozen decision audit | Pass | Pass |

Candidate B is rejected. Candidate C clears the central clipping, factual,
support, clustered-comparison, and correctness gates, but fails the explicit
shape threshold by 0.025 yards and is consistently less accurate than v1.
Those facts create a genuine tradeoff: keeping v1 retains known severe
artificial clipping, while accepting C would waive a preregistered gate and
freeze another coarse-cell discontinuity.

The Milestone 7 decision is therefore exactly:

`INCONCLUSIVE`

No threshold is relaxed after seeing results. No candidate is frozen,
`coachiq-action-transition-v2` does not exist, and
`coachiq-action-transition-v1` remains current.

## Limitations and next scope

This remains an observational conditional transition model. Neither factual
punt accuracy nor decision sensitivity identifies unchosen punt value. The
four broad cells omit punter, coverage, returner, weather, formation, score,
time, and strategic selection. CRPS uses the finite empirical distribution.
The clustered comparison resamples evaluation games but does not refit models.
All design and evaluation seasons have informed this study.

Milestone 8 should move toward the live 2026 product using the frozen v1 stack,
not immediately reopen punt-model research. It should build the internal
decision-audit product path with conservative publication safeguards: suppress
public coach grades/rankings, surface support and uncertainty, prominently flag
punt field-clipping mass, prevent a clear public recommendation when punt
clipping exceeds a fixed safety threshold, preserve the OT safeguard, and add
operational monitoring/version provenance. The exact publication rules should
be fixed before any live 2026 outcome access.

A later, separately preregistered punt-transition-v2 study may build from C
with a principled continuous/boundary-aware formulation, but it should not
block initial product work. The consumed 2025 data must remain excluded from
development and cannot become a holdout again; the first 2026 access must occur
only after the product policy and frozen model identity are recorded.
