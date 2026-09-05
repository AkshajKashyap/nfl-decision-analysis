# CoachIQ win-probability model card

Status: locked for the first CoachIQ decision-scoring system

Model version: `coachiq-wp-v1`

Specification: candidate D, uncalibrated ridge logistic regression

Data boundary: nflverse play-by-play from 2014 through 2024; 2025 was not
loaded or inspected

## Purpose and intended use

The model estimates the eventual game value of the team represented by a
canonical regulation state. Its output is used to value possible successor
states in later fourth-down action analysis. The target is 1 for an eventual
win, 0.5 for a regular-season tie, and 0 for a loss.

This is an owned, inspectable state-value model. It is intended for
retrospective decision-support research, comparison of modeled action values,
and reproducible diagnostics. It is not intended to predict betting returns,
set live odds, grade coaches by itself, establish a causal effect of an action,
or represent an unchosen result as known fact.

## Data and evaluation protocol

Every eligible non-deleted, non-no-play regulation scrimmage state is viewed
from the possession team's perspective. Rows require complete score, clock,
field position, down/distance, timeout, team, and final-result fields. Many
rows share a game outcome, so state rows are not independent observations.

Candidate development used expanding-origin folds only:

| Fit seasons | Development season |
|---|---:|
| 2014–2019 | 2020 |
| 2014–2020 | 2021 |
| 2014–2021 | 2022 |
| 2014–2022 | 2023 |

Features, the common L2 penalty, recalibration choice, and final candidate were
selected using these folds. Candidate D without recalibration was then frozen
and evaluated once on 2024 after fitting on 2014–2023. The earlier Milestone 3
baseline had already exposed candidate A's 2024 result, so 2024 is described as
a disclosed **pre-lock validation**, not an untouched holdout. Candidate D's
specification was not revised after its 2024 result. The 2025 season remains
uninspected.

The deployment training policy permits `coachiq-wp-v1` to refit the frozen
specification on any expanding set of complete seasons from 2014 through 2024.
Training on 2025 or later is rejected. Feature means and scales are learned
only from the supplied training rows.

## Required inputs and target isolation

The prediction schema requires score differential, regulation seconds
remaining, yards to the opponent goal line, yards to go, possession-team and
opponent timeouts, home indicator, down, and possession-team pregame spread.
The pregame spread may be null; missingness is modeled explicitly. Training
also requires season and `eventual_win_equivalent`.

The final score is used only to construct the target and never enters the
feature matrix. nflverse expected points, ordinary win probability, and Vegas
win probability are excluded by an explicit feature allow-list and are used
only as external diagnostics.

## Pregame signal

The source is nflverse `spread_line`, already present in the normalized data.
nflfastR documents it as the closing spread from the home-team perspective:
positive means the home team was favored and negative means the away team was
favored ([nflfastR NEWS](https://github.com/nflverse/nflfastR/blob/master/NEWS.md)).
CoachIQ converts it to the possession-team perspective:

```text
team_pregame_spread = spread_line       if possession team is home
                    = -spread_line      if possession team is away
```

This matches nflfastR's possession-side conversion in its published WP
calculator source
([ep_wp_calculators.R](https://github.com/nflverse/nflfastR/blob/master/R/ep_wp_calculators.R)).
The line is fixed before play begins; no live or postgame market field is used.
Its model contribution is multiplied by the fraction of regulation time
remaining, making it exactly zero at expiration. A separate binary feature
marks a missing line; the numerical line value is then filled with zero.

## Candidate specifications

All candidates use deterministic Newton fitting, training-only
standardization, an unpenalized intercept, and an L2 penalty of 1.0. The common
penalty was inherited from the audited baseline; it was not searched against
the development seasons.

The common A feature list is:

1. score differential
2. regulation time fraction, `seconds_remaining / 3600`
3. score differential × fraction of game elapsed
4. score differential / `sqrt(max(minutes_remaining, 1))`
5. field progress, `(100 - yards_to_goal) / 100`
6. `min(yards_to_go, 30) / 10`
7. timeout differential
8. home indicator
9. down 2 indicator
10. down 3 indicator
11. down 4 indicator

| Candidate | Explicit additions | Features |
|---|---|---:|
| A | None; audited Milestone 3 baseline | 11 |
| B | field progress squared; timeout differential × fraction elapsed; home indicator × time fraction | 14 |
| C | all B features; clock-decayed possession-team spread; missing-line indicator | 16 |
| D | A features; clock-decayed possession-team spread; missing-line indicator | 13 |

Development-only prototypes of B also considered time squared, time cubed, and
a nonlinear late-score term. They were removed after deterministic property
grids showed time-direction violations and no proper-score gain. D is the
complexity ablation of C; no boosted model, model zoo, neural network, or
AutoML search was run.

## Rolling results

Each cell is log loss / Brier score / ECE. Sample sizes are 37,471, 38,989,
38,878, and 39,257 state rows for 2020 through 2023, respectively.

| Season | A | B | C | D |
|---:|---:|---:|---:|---:|
| 2020 | .4845 / .1625 / .0114 | .4856 / .1629 / .0136 | .4321 / .1402 / .0083 | .4313 / .1400 / .0087 |
| 2021 | .4615 / .1557 / .0205 | .4608 / .1555 / .0214 | .4348 / .1445 / .0252 | .4345 / .1445 / .0274 |
| 2022 | .5632 / .1902 / .0404 | .5634 / .1903 / .0407 | .5232 / .1725 / .0344 | .5232 / .1725 / .0318 |
| 2023 | .4751 / .1593 / .0158 | .4750 / .1591 / .0154 | .4529 / .1498 / .0090 | .4527 / .1497 / .0101 |
| pooled | .4961 / .1669 / .0103 | .4962 / .1670 / .0105 | .4609 / .1518 / .0108 | **.4607 / .1518 / .0097** |

The constant-prevalence log losses were .6931, .6929, .6930, and .6930. The
ordinary nflverse WP reference log losses on identical rows were .4780, .4616,
.5583, and .4729. Pooled nflverse ordinary WP was .4928 / .1656 / .0109;
pooled nflverse Vegas WP, retained strictly as another external diagnostic,
was .4555 / .1499 / .0076.

The one-time 2024 result for locked D was **.4205 / .1382 / .0255** on 38,507
states. The 2024 constant was .6931 / .2500 / .0028, ordinary nflverse WP was
.4622 / .1566 / .0182, and nflverse Vegas WP was .4150 / .1363 / .0272. These
references do not enter fitting or recalibration.

Before candidate work, the unchanged A implementation reproduced the audited
rolling log losses exactly to four decimals: .4845 (2020), .4615 (2021), .5632
(2022), .4751 (2023), and .4653 (2024).

## Calibration bands

The pooled 2020–2023 reliability table for raw candidate D follows. A band is
declared sparse below 500 rows; none of these pooled bands is sparse.

| Predicted band | Count | Mean WP | Observed | Gap |
|---|---:|---:|---:|---:|
| 0–10% | 22,471 | .039 | .047 | .008 |
| 10–20% | 14,274 | .149 | .172 | .023 |
| 20–30% | 13,583 | .249 | .267 | .018 |
| 30–40% | 12,784 | .350 | .349 | .001 |
| 40–50% | 12,069 | .450 | .452 | .002 |
| 50–60% | 12,437 | .551 | .551 | .000 |
| 60–70% | 13,631 | .650 | .649 | .001 |
| 70–80% | 13,986 | .751 | .725 | .026 |
| 80–90% | 15,786 | .851 | .835 | .016 |
| 90–100% | 23,574 | .960 | .956 | .004 |

The 2024 table shows a directional shift at the extremes that aggregate ECE
does not fully describe:

| Predicted band | Count | Mean WP | Observed | Gap |
|---|---:|---:|---:|---:|
| 0–10% | 5,004 | .037 | .010 | .027 |
| 10–20% | 3,397 | .151 | .126 | .025 |
| 20–30% | 3,361 | .249 | .204 | .045 |
| 30–40% | 3,484 | .351 | .300 | .051 |
| 40–50% | 3,463 | .449 | .436 | .013 |
| 50–60% | 3,246 | .550 | .542 | .008 |
| 60–70% | 3,531 | .651 | .671 | .020 |
| 70–80% | 3,808 | .751 | .776 | .025 |
| 80–90% | 3,801 | .850 | .867 | .017 |
| 90–100% | 5,412 | .961 | .984 | .023 |

## Reliability by game regime

These bins are descriptive, not separately optimized models. Clock bins
overlap only where explicitly named: final two minutes is also part of final
five minutes. Score bins are otherwise exclusive.

Pooled 2020–2023 candidate D:

| Clock regime | Count | Log loss | Brier | ECE |
|---|---:|---:|---:|---:|
| First half | 77,386 | .5555 | .1870 | .0189 |
| Third quarter | 34,915 | .4307 | .1385 | .0090 |
| Fourth quarter, over 5 minutes | 24,573 | .3387 | .1067 | .0123 |
| Final 5 minutes | 17,721 | .2747 | .0865 | .0216 |
| Final 2 minutes | 8,234 | .2762 | .0871 | .0340 |

| Score regime | Count | Log loss | Brier | ECE |
|---|---:|---:|---:|---:|
| Tied | 29,225 | .6224 | .2147 | .0286 |
| Within 3, not tied | 25,873 | .6030 | .2063 | .0141 |
| 4–7 point margin | 42,715 | .5457 | .1820 | .0216 |
| Margin over 7 | 56,782 | .2486 | .0718 | .0049 |

One-time 2024 candidate D:

| Clock regime | Count | Log loss | Brier | ECE |
|---|---:|---:|---:|---:|
| First half | 19,135 | .5226 | .1748 | .0230 |
| Third quarter | 8,720 | .3903 | .1263 | .0318 |
| Fourth quarter, over 5 minutes | 6,211 | .2802 | .0876 | .0441 |
| Final 5 minutes | 4,441 | .2361 | .0742 | .0247 |
| Final 2 minutes | 2,076 | .2433 | .0766 | .0413 |

| Score regime | Count | Log loss | Brier | ECE |
|---|---:|---:|---:|---:|
| Tied | 6,782 | .5908 | .2019 | .0473 |
| Within 3, not tied | 7,206 | .6297 | .2191 | .0234 |
| 4–7 point margin | 10,777 | .4917 | .1611 | .0386 |
| Margin over 7 | 13,742 | .1710 | .0464 | .0326 |

Late and tied-state calibration remains a limitation even when aggregate
proper scores improve.

## Pregame incremental value

Candidate C was compared with B on identical chronological predictions.
Negative deltas favor C.

| States | Count | Δ log loss | Δ Brier | Δ ECE |
|---|---:|---:|---:|---:|
| All development | 154,595 | -.03530 | -.01513 | +.0003 |
| First half | 77,386 | -.05676 | -.02507 | +.0028 |
| Tied | 29,225 | -.05861 | -.02785 | +.0093 |
| Within 7 | 97,813 | -.05000 | -.02263 | -.0012 |
| Final 5 minutes | 17,721 | -.00085 | -.00032 | +.0011 |
| Final 2 minutes | 8,234 | +.00017 | +.00004 | +.0008 |

The signal's proper-score value is concentrated early, tied, and close. It is
near zero in the final five minutes and slightly adverse in the final two,
consistent with the intended clock decay rather than implausible late-game
market dominance.

## Recalibration

The tested method fits an intercept and slope on the most recent season inside
each outer training window. Its base model is fitted on earlier training
seasons only; the base model is then refit on the full outer window before the
held-out season is scored. Evaluation-season targets never enter calibration.

For D, pooled recalibrated results were .4620 / .1522 / .0073 versus raw
.4607 / .1518 / .0097. Recalibration lowered pooled ECE but worsened both
proper scores. The game-clustered recalibrated-minus-raw differences were
+.00136 log loss (90% interval -.00055 to +.00321) and +.00042 Brier
(-.00012 to +.00094). Its seasonal behavior was unstable, including 2023 log
loss .4602 versus .4527 raw. `coachiq-wp-v1` therefore applies no recalibration.

## Game-clustered candidate comparisons

Deterministic 1,000-replicate intervals resample whole game IDs. Differences
are candidate minus reference; negative favors the candidate.

| Comparison | Δ log loss (90% interval) | Δ Brier (90% interval) |
|---|---:|---:|
| B − A | +.00012 [-.00030, +.00053] | +.00004 [-.00013, +.00021] |
| C − B | -.03530 [-.04475, -.02474] | -.01513 [-.01903, -.01095] |
| C − A | -.03518 [-.04553, -.02477] | -.01509 [-.01927, -.01080] |
| D − A | -.03547 [-.04533, -.02496] | -.01518 [-.01912, -.01109] |
| D − C | -.00029 [-.00069, +.00012] | -.00009 [-.00025, +.00007] |

B adds complexity without improvement. C and D deliver stable improvements
over A, while D is statistically indistinguishable from C and uses three fewer
features.

## 2022 investigation

The baseline degradation reproduced exactly: A log loss was .5632. It was not
caused by a missing spread schema field: all retained 2014–2024 state rows had
a line, and nflverse's ordinary WP also weakened to .5583 in 2022.

Compared with 2021 and 2023, 2022 contained more close/tied states and smaller
absolute margins:

| Season | Tied-state rate | Within-7 rate | Mean absolute margin | Mean absolute spread |
|---:|---:|---:|---:|---:|
| 2021 | .187 | .611 | 8.11 | 5.99 |
| 2022 | .208 | .668 | 6.98 | 5.06 |
| 2023 | .192 | .647 | 7.57 | 4.94 |

A's 2022 ECE was .0404, with 5–8 percentage-point gaps across several
20–40% and 70–90% bands. Five games contributed 8.0% of all state-row log
loss, versus 5.9% in 2021 and 6.5% in 2023. Removing each season's five largest
game contributors changed A log loss from .4615 to .4422 in 2021, .5632 to
.5279 in 2022, and .4751 to .4522 in 2023. The 2022 games were
`2022_15_IND_MIN`, `2022_19_LAC_JAX`, `2022_02_ARI_LV`, `2022_02_MIA_BAL`,
and `2022_10_MIN_BUF`, a group containing several large reversals.

Pregame-strength omission was a generalizable deficiency, not a 2022-specific
tuning patch: D reduced 2022 log loss to .5232 and also improved every other
development fold. Residual 2022 weakness and the external-reference decline
indicate an unusually volatile, close-game season rather than one isolated
schema break.

## Football property audit

For selected D, the deterministic grid found:

| Property | Violations / comparisons |
|---|---:|
| Larger score advantage should not lower WP | 0 / 144 |
| Less time with a lead should not lower WP | 0 / 108 |
| Less time with a deficit should not raise WP | 0 / 108 |
| Better offensive field position should not lower WP | 0 / 72 |
| Stronger pregame favorite should not lower WP | 0 / 72 |
| Pregame influence should shrink while score influence grows | 0 |

For a representative ±14 spread grid, the pregame probability range fell from
.867 at 3,600 seconds to .319, .109, .044, .011, and exactly 0 at 900, 300,
120, 30, and 0 seconds. The corresponding ±7 score range grew from .300 to
.594, .742, .856, .926, and .927. All candidate raw and recalibrated grids had
zero declared violations. These finite grids are diagnostics, not a global
mathematical monotonicity guarantee.

## Selection rationale and limitations

Candidate D is selected because it materially improves held-out log loss and
Brier score over A across seasons and clustered games; preserves strong
calibration without a second-stage fit; passes the football property grid;
encodes a defensible pregame prior that vanishes at expiration; and matches C
with fewer features. B's extra interactions do not earn their complexity.

Known limitations include correlated play states, one target repeated through
a game, team and season drift, no player/injury/weather information, a closing
line that may not represent information available at an earlier planning time,
unmodeled overtime states, unconstrained logistic behavior outside the tested
grid, residual late/tied-state calibration error, and no causal interpretation.
The pregame line is a market aggregate and may encode information or biases
that are not separately attributable. The model does not estimate uncertainty
in its fitted coefficients when later action values are bootstrapped.

## Versioning policy

`coachiq-wp-v1` means exactly candidate D's 13-feature transformations, L2
penalty 1.0, deterministic fitting procedure, missing-line treatment, no
recalibration, and pre-2025 training boundary. Later feature, penalty,
calibration, target, training-policy, or algorithm changes require a new model
version. The older baseline feature specification remains callable solely for
reproduction and comparison; it must not silently replace v1 in decision-value
analysis.

Run the full report with:

```bash
PYTHONPATH=src .venv/bin/python scripts/select_wp_model.py \
  --bootstrap-replicates 1000 \
  --json-output /tmp/coachiq-wp-model-selection.json
```

Use `--parquet-dir DIR` to read explicit snapshots named
`play_by_play_YEAR.parquet` instead of loading through nflreadpy. The script
rejects seasons outside 2014–2024. Its JSON contains every candidate's fold,
calibration-band, regime, recalibration, property, and clustered-comparison
detail summarized here.
