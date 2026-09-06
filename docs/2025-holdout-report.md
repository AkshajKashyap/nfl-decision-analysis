# 2025 holdout report

Final status: **PASS WITH LIMITATIONS**

This is the one-time evaluation of the frozen CoachIQ v1 stack on the
deliberately protected 2025 season. The acceptance rules were written and
fingerprinted in [the holdout protocol](2025-holdout-protocol.md) before any
2025 data access. No feature, coefficient rule, action cell, support cutoff,
classification threshold, bootstrap setting, clipping rule, or overtime policy
was changed after access.

The result supports continued internal research use. It does not authorize
coach rankings, public grades, causal claims, or treating modeled unchosen
actions as known outcomes. Material field-position clipping remains a model-form
limitation, especially for hypothetical punts in opponent territory.

## Frozen evaluation identity

| Item | Frozen value |
|---|---|
| Starting commit | `711022577a5302a6ec6db0b7bf4e3394c324ec46` |
| Protocol SHA-256 | `a98c5817a90926f5fe207493f2b7670048d1f2b0fb32c8e802266b47a485034b` |
| WP | `coachiq-wp-v1`, Candidate D, 13 features, ridge 1.0, no recalibration |
| Action transitions | `coachiq-action-transition-v1` |
| Decision values | `coachiq-decision-v1` |
| Support | minimum 30; sparse below 100; field goal unavailable above 70 yards |
| Classification | `decision-threshold-v1`; 1.0-point gap and 95% paired superiority |
| OT policy | any positive supported-action tied-expiration mass forces limited support |
| Bootstrap | 200 shared whole-training-game draws; seed 2505; central 90% interval |
| WP/action fit seasons | exactly 2014--2024 |
| Evaluation season | exactly 2025 |
| Runtime | Python 3.13.11; NumPy 2.5.2; Polars 1.44.1; nflreadpy 0.1.5 |

All eight preregistered frozen source hashes matched before both evaluation
runs. The fitted WP metadata records 416,618 state rows, Candidate D's exact
feature names, ridge 1.0, eight deterministic Newton iterations, and training
seasons 2014--2024. The action model records 42,361 transition rows from 3,010
training games and the same seasons. The report explicitly records
`recalibration_on_holdout: false`, `model_selection_on_holdout: false`, and
`threshold_or_cell_tuning_on_holdout: false`.

The raw 2025 snapshot has 48,771 rows and 372 source columns. It was loaded via
nflreadpy 0.1.5, written outside the repository, and has SHA-256
`04140f9c6d5d8a8000875cc78056eebd2b96f7fcb5690808e32065c82b049797`.
The resolved upstream asset is `play_by_play_2025.parquet`.

## Preregistered acceptance decision

The protocol fixed warning margins relative to the 2020--2024 range, absolute
WP and factual-action catastrophic cutoffs, support/classification/OT drift
margins, and clipping thresholds at any, above 10%, above 25%, and above 50%
transition mass. In particular, material clipping was fixed as at least 5% of
all decisions above 25%, at least 10% of clear cases above 25%, at least 1% of
all decisions above 50%, at least five top-20 cases above 25%, or sufficiently
large historical rate drift. Severe clipping had separate fail thresholds.

No failure criterion fired. Four material warnings fired:

- field-position mass above 25% affected at least 5% of decisions;
- field-position mass above 25% affected at least 10% of clear cases;
- field-position mass above 50% affected at least 1% of decisions; and
- four manually reviewed top-gap cases were model-form warnings.

The first three describe the same coarse-cell transport limitation from
different preregistered views. Their overall 2025 frequencies are close to the
2020--2024 frequencies rather than new holdout drift. No catastrophic WP or
factual criterion, severe clipping threshold, historical clipping-drift rule,
or potential correctness-bug rule fired. The fixed decision rule therefore
produces **PASS WITH LIMITATIONS**.

## Evaluation sample

| Population | Count |
|---|---:|
| Historical normalized rows, 2014--2024 | 531,234 |
| 2025 normalized rows | 48,771 |
| 2025 games | 285 |
| 2025 WP state rows | 37,967 |
| 2025 fourth-down candidate rows | 4,290 |
| 2025 eligible regulation decisions | 3,964 |

## Win-probability holdout

### Overall and references

| Model/reference | Rows | Log loss | Brier | ECE |
|---|---:|---:|---:|---:|
| CoachIQ `coachiq-wp-v1` | 37,967 | 0.4774 | 0.1586 | 0.0168 |
| 2014--2024 training-prevalence constant | 37,967 | 0.6930 | 0.2490 | 0.0031 |
| nflverse ordinary WP | 37,967 | 0.5048 | 0.1705 | 0.0158 |
| nflverse Vegas WP | 37,967 | 0.4762 | 0.1578 | 0.0187 |

CoachIQ's 2025 proper scores and ECE are all inside its 2020--2024 ranges:
0.4205--0.5232 log loss, 0.1382--0.1725 Brier, and 0.0087--0.0318 ECE.
It is numerically better than ordinary nflverse WP and nearly level with the
Vegas reference, but no clustered difference interval was preregistered here,
so this report makes no superiority claim. The constant's low ECE is the
expected artifact of predictions concentrated near prevalence; its proper
scores are poor.

### Fixed calibration bands

| Predicted band | Rows | Mean prediction | Observed | Absolute gap |
|---|---:|---:|---:|---:|
| 0--10% | 5,291 | 0.039 | 0.056 | 0.017 |
| 10--20% | 3,303 | 0.150 | 0.182 | 0.032 |
| 20--30% | 3,511 | 0.250 | 0.274 | 0.024 |
| 30--40% | 3,339 | 0.349 | 0.367 | 0.017 |
| 40--50% | 3,020 | 0.450 | 0.452 | 0.002 |
| 50--60% | 3,113 | 0.551 | 0.551 | 0.001 |
| 60--70% | 3,553 | 0.650 | 0.645 | 0.005 |
| 70--80% | 3,589 | 0.750 | 0.705 | 0.045 |
| 80--90% | 3,538 | 0.851 | 0.834 | 0.016 |
| 90--100% | 5,710 | 0.961 | 0.951 | 0.010 |

All bands are non-sparse. The largest gap is 4.5 points in the 70--80% band,
below the fixed 8-point general warning. Both extreme bands remain below the
fixed 6-point warning.

### Game regimes

| Regime | Rows | Log loss | Brier | ECE | Historical LL range |
|---|---:|---:|---:|---:|---:|
| First half | 18,878 | 0.5626 | 0.1911 | 0.0268 | 0.5226--0.5870 |
| Third quarter | 8,493 | 0.4557 | 0.1476 | 0.0217 | 0.3814--0.5240 |
| Fourth quarter, over 5 minutes | 6,121 | 0.3855 | 0.1223 | 0.0297 | 0.2783--0.4452 |
| Final 5 minutes | 4,475 | 0.2849 | 0.0921 | 0.0383 | 0.2170--0.3536 |
| Final 2 minutes | 2,080 | 0.2840 | 0.0919 | 0.0556 | 0.2292--0.3457 |
| Tied | 7,049 | 0.6274 | 0.2193 | 0.0373 | 0.5883--0.6353 |
| Within 3, not tied | 7,187 | 0.6210 | 0.2152 | 0.0215 | 0.5832--0.6310 |
| Margin 4--7 | 10,210 | 0.5316 | 0.1768 | 0.0171 | 0.4915--0.6146 |
| Margin over 7 | 13,521 | 0.2820 | 0.0831 | 0.0227 | 0.1710--0.3468 |

Every regime's log loss, Brier score, and ECE is within its like-for-like
2020--2024 range. Final-two-minute ECE remains elevated at 0.0556, but is
inside its historical 0.0398--0.0661 range and preserves the already disclosed
late-game calibration limitation.

The deterministic property grid again has zero violations for score direction,
lead time, deficit time, field position, and pregame strength, zero late-game
dominance violations, and bounded finite probabilities.

## Factual-action validation

Factual-action EWP evaluates the modeled value of the action actually observed.
It remains necessary evidence but does not identify the validity of unobserved
alternative-action values.

| Observed action | Rows | Log loss | Brier | ECE |
|---|---:|---:|---:|---:|
| All supported actual actions | 3,944 | 0.4663 | 0.1548 | 0.0170 |
| Go | 904 | 0.3996 | 0.1334 | 0.0450 |
| Field goal | 1,006 | 0.4818 | 0.1606 | 0.0336 |
| Punt | 2,034 | 0.4883 | 0.1615 | 0.0212 |

Overall results are within the 2020--2024 ranges of 0.4216--0.5197 log loss,
0.1385--0.1713 Brier, and 0.0144--0.0367 ECE. Go ECE is 0.23 points above its
prior maximum but far below the preregistered 3-point action-level margin; all
other action-level metrics are within their prior ranges or margins.

| Factual transition | Rows | 2025 result | 2020--2024 range |
|---|---:|---:|---:|
| Go conversion log loss | 901 | 0.6447 | 0.6212--0.6550 |
| Go conversion Brier | 901 | 0.2266 | 0.2158--0.2308 |
| Field-goal make log loss | 1,004 | 0.3535 | 0.3367--0.3694 |
| Field-goal make Brier | 1,004 | 0.1072 | 0.1040--0.1146 |
| Punt destination MAE | 2,034 | 7.68 yards | 7.57--8.06 |
| Punt destination RMSE | 2,034 | 11.16 yards | 11.02--11.87 |

No factual-transition warning fired.

## Support and classification drift

| Measure | 2025 count | 2025 rate | 2020--2024 rate range |
|---|---:|---:|---:|
| Three supported actions | 846 | 21.34% | 19.84%--21.67% |
| Two supported actions | 3,034 | 76.54% | 73.90%--77.79% |
| One supported action | 84 | 2.12% | 1.99%--4.70% |
| Zero supported actions | 0 | 0.00% | 0.00% |
| Any sparse supported action | 347 | 8.75% | 8.80%--16.05% |
| `clear_model_preference` | 1,217 | 30.70% | 23.11%--30.68% |
| `close_call` | 1,158 | 29.21% | 30.25%--32.82% |
| `limited_support` | 1,494 | 37.69% | 36.68%--39.69% |
| `insufficient_support` | 95 | 2.40% | 2.21%--4.77% |

The tiny range crossings for sparse, clear, and close rates are 0.05, 0.02,
and 1.04 percentage points; none reaches the preregistered 3-point drift
margin. Unsupported actual actions were 9/913 go (0.99%), 11/1,017 field goal
(1.08%), and 0/2,034 punt, also below their fixed drift margins.

## Decision-value distribution

| Gap statistic | 2025 | 2020--2024 range |
|---|---:|---:|
| Available gaps | 3,869 | 3,408--4,086 |
| Median | 0.00% | 0.00% |
| P75 | 0.33% | 0.35%--0.73% |
| P90 | 1.87% | 1.81%--2.41% |
| P95 | 3.00% | 2.86%--3.84% |
| Maximum | 12.22% | 9.49%--12.20% |

P90 and P95 are squarely historical. P75 is 0.02 points below the prior range
and the maximum is 0.02 points above it; neither approaches its fixed warning
margin. The classification percentages are shown with support drift above.

## Overtime-boundary behavior

Twenty decisions (0.50%) have positive tied-regulation-expiration mass in at
least one supported action, at the low end of the 2020--2024 frequency range
of 0.50%--0.73%. Among affected decisions, maximum-action mass has median
3.45%, P75 17.81%, P90 41.67%, P95 93.30%, and maximum 99.34%. None exceeds
its preregistered historical-quantile margin.

| Action | Supported queries | Affected | Affected rate | Median affected mass | Maximum |
|---|---:|---:|---:|---:|---:|
| Go | 3,880 | 11 | 0.28% | 8.12% | 94.06% |
| Field goal | 1,567 | 11 | 0.70% | 0.26% | 92.98% |
| Punt | 3,243 | 11 | 0.34% | 0.13% | 99.34% |

Actions overlap within the 20 affected decisions, so action counts do not sum
to 20. The existing safeguard was applied unchanged; none of the top 20 gaps
has positive OT-boundary mass.

## Pre-clip transition audit

Mass is measured before the existing transition bounds. At decision level it
is the maximum across supported actions. `Any` can be high when a large cell
contains only a few boundary-crossing transitions and should not be confused
with the heavier thresholds.

### Overall, clear, and largest-gap rates

| Slice | Measure | Any | >10% | >25% | >50% |
|---|---|---:|---:|---:|---:|
| All 3,964 decisions | Field | 95.28% | 32.80% | 18.06% | 12.99% |
| All 3,964 decisions | Clock | 2.72% | 1.66% | 0.88% | 0.35% |
| 1,217 clear cases | Field | 100.00% | 34.92% | 25.88% | 20.79% |
| 1,217 clear cases | Clock | 2.63% | 1.89% | 0.82% | 0.25% |
| Top 20 gaps | Field | 100.00% | 30.00% | 20.00% | 20.00% |
| Top 20 gaps | Clock | 15.00% | 10.00% | 0.00% | 0.00% |

Overall 2025 field rates at >10/>25/>50 are 32.80/18.06/12.99%, compared with
2020--2024 ranges of 30.04--33.60%, 16.95--18.73%, and 11.58--12.74%.
The 0.25-point crossing at >50 is well below the fixed historical drift rule.
Clock rates are all within their historical ranges. Heavy clipping is therefore
material but persistent, not a newly emerging 2025 shift.

### By modeled action

These denominators are supported action-decision pairs, not unique decisions.

| Action | Measure | Any | >10% | >25% | >50% |
|---|---|---:|---:|---:|---:|
| Go | Field | 60.82% | 6.11% | 1.21% | 0.00% |
| Go | Clock | 2.58% | 1.70% | 0.90% | 0.36% |
| Field goal | Field | 16.98% | 0.00% | 0.00% | 0.00% |
| Field goal | Clock | 3.45% | 0.89% | 0.64% | 0.51% |
| Punt | Field | 96.33% | 32.78% | 20.63% | 15.88% |
| Punt | Clock | 2.56% | 0.25% | 0.15% | 0.15% |

Maximum raw crossings by action were: field goal 5 yards above and 53 seconds
below zero; go 20 yards above, 26 below, and 55 seconds below zero; punt 20
yards above, 28 below, and 48 seconds below zero. Among affected action-query
pairs, median maximum field underflow was 9 yards for go and 13 for punt;
median maximum overflow was 2 yards for field goal, 4 for go, and 8 for punt.
The mass and severity jointly identify punts in opponent territory as the main
limitation.

### Required stratifications

Each cell shows `field any/>10/>25/>50 ; clock any/>10/>25/>50`.

| Stratum | Rates |
|---|---|
| Opponent red zone | 88.90/31.21/6.52/0.00%; 2.64/1.66/0.97/0.69% |
| Opponent 21--49 | 97.44/66.31/55.24/42.53%; 3.96/3.14/1.49/0.58% |
| Own 21 to midfield | 100.00/15.40/0.00/0.00%; 2.25/0.95/0.59/0.12% |
| Own 1--20 | 77.91/3.49/0.00/0.00%; 0.87/0.00/0.00/0.00% |
| Other regulation | 95.36/31.95/17.57/12.84%; 0.00/0.00/0.00/0.00% |
| Q4, 2--5 minutes | 93.98/34.96/16.92/11.28%; 0.00/0.00/0.00/0.00% |
| Q4, final 2 minutes | 95.58/42.17/26.10/16.87%; 43.37/26.51/14.06/5.62% |
| Clear preference | 100.00/34.92/25.88/20.79%; 2.63/1.89/0.82/0.25% |
| Close call | 100.00/41.62/29.71/21.93%; 1.99/0.86/0.52/0.26% |
| Limited support | 88.69/26.31/3.82/0.54%; 3.28/2.14/1.20/0.54% |
| Insufficient support | 81.05/0.00/0.00/0.00%; 4.21/1.05/1.05/0.00% |
| Actual go | 96.06/46.11/25.41/15.01%; 6.46/3.50/1.64/0.66% |
| Actual field goal | 94.69/63.03/47.30/37.07%; 3.05/2.56/1.57/0.79% |
| Actual punt | 95.23/11.70/0.15/0.05%; 0.88/0.39/0.20/0.00% |
| Gap 0--50th percentile | 95.24/32.65/18.17/12.93%; 3.00/1.84/1.08/0.40% |
| Gap 50th--75th | 96.53/36.48/18.61/11.91%; 2.98/1.99/0.99/0.74% |
| Gap 75th--90th | 96.72/36.03/22.59/16.21%; 0.34/0.34/0.17/0.17% |
| Gap 90th--95th | 97.41/36.79/17.10/15.03%; 2.59/2.07/1.04/0.00% |
| Gap top 5% | 93.81/29.38/11.86/10.82%; 5.15/2.58/0.00/0.00% |
| Gap unavailable | 81.05/0.00/0.00/0.00%; 4.21/1.05/1.05/0.00% |

Heavy field clipping is not disproportionately concentrated in the largest
gap percentile: the top 5% has lower >25% field mass than several lower groups.
Actual punts also rarely have heavy clipping; the high rates for actual field
goals and go attempts arise because the decision-level maximum often comes from
the *hypothetical punt* in opponent territory. This remains relevant because
classification compares all supported alternatives even when the clipped
action was not selected.

## Manual audit of the 20 largest gaps

All 20 source descriptions, input states, actual actions, factual next states,
possession and score perspective, query-relative clock and field transport,
timeouts, support cells/counts, scoring restarts, OT mass, clipping, modeled
values, and classifications were inspected. Every recorded possession, score,
clock, field, timeout, team, home-perspective, and bounds check passed. `G/F/P`
support is the number of training transitions used; `--` means unsupported or
unavailable. Maximum clipping is across supported actions.

| # | Decision and factual play | State | Actual -> preferred | G/F/P support | Gap | Class | Max field / clock clip | Finding |
|---:|---|---|---|---:|---:|---|---:|---|
| 1 | `2025_19_SF_PHI` 4063; Hurts incomplete | Q4 :43, -4, opp 21, 4th-11 | go -> FG | 219/3003/3782 | 12.22% | clear | 92.86% / 0.03% | model-form warning |
| 2 | `2025_06_DEN_NYJ` 3352; McNamara punt, fair catch | Q4 10:23, +1, own 30, 4th-1 | punt -> go | 664/--/17007 | 9.79% | clear | 0.15% / 0% | structurally clean |
| 3 | `2025_14_HOU_KC` 3489; Townsend punt, fair catch | Q4 11:32, tied, own 35, 4th-1 | punt -> go | 664/--/17007 | 9.40% | clear | 0.90% / 0% | structurally clean |
| 4 | `2025_05_SF_LA` 3662; Evans punt, downed at SF 2 | Q4 8:18, tied, own 39, 4th-1 | punt -> go | 664/--/17007 | 9.30% | clear | 2.92% / 0% | structurally clean |
| 5 | `2025_01_TEN_DEN` 3565; Hekker punt, muff recovered by TEN | Q4 11:53, -1, own 34, 4th-1 | punt -> go | 664/--/17007 | 9.28% | clear | 0.65% / 0% | structurally clean |
| 6 | `2025_07_GB_ARI` 4341; Brissett incomplete | Q4 :13, -4, opp 27, 4th-11 | go -> FG | 219/3050/3782 | 9.10% | clear | 78.64% / 11.87% | model-form warning |
| 7 | `2025_02_SEA_PIT` 2734; Waitman punt, fair catch | Q3 1:41, tied, own 48, 4th-1 | punt -> go | 664/--/17007 | 7.77% | limited | 16.52% / 0% | structurally clean |
| 8 | `2025_11_SEA_LA` 2674; Dickson punt, fair catch | Q3 3:39, -2, own 40, 4th-1 | punt -> go | 664/--/17007 | 7.70% | clear | 3.55% / 0% | structurally clean |
| 9 | `2025_02_JAX_CIN` 3785; Cooke punt, fair catch | Q4 6:09, +3, opp 47, 4th-2 | punt -> go | 459/--/3782 | 7.45% | limited | 0.69% / 0% | structurally clean |
| 10 | `2025_05_TB_SEA` 3414; Dixon punt, downed at SEA 1 | Q4 7:28, tied, opp 41, 4th-17 | punt -> FG | 219/1632/3782 | 7.44% | clear | 9.73% / 0% | structurally clean |
| 11 | `2025_12_BUF_HOU` 4114; Allen intercepted | Q4 :24, -4, opp 22, 4th-6 | go -> FG | 557/3050/3782 | 7.43% | clear | 91.12% / 18.67% | model-form warning |
| 12 | `2025_11_SEA_LA` 2896; Evans punt out of bounds | Q3 1:28, +2, own 32, 4th-1 | punt -> go | 664/--/17007 | 7.41% | clear | 0.35% / 0% | structurally clean |
| 13 | `2025_17_PIT_CLE` 3009; Waitman punt, fair catch | Q4 9:51, -4, opp 46, 4th-5 | punt -> go | 809/--/3782 | 7.35% | limited | 1.37% / 0% | structurally clean |
| 14 | `2025_12_NYG_DET` 4014; Winston incomplete | Q4 2:59, +3, opp 6, 4th-6 | go -> FG | 181/2537/-- | 7.34% | limited | 16.57% / 0% | structurally clean |
| 15 | `2025_12_JAX_ARI` 3384; Cooke punt, fair catch | Q4 13:45, +3, own 30, 4th-1 | punt -> go | 664/--/17007 | 7.32% | clear | 0.15% / 0% | structurally clean |
| 16 | `2025_13_HOU_IND` 4000; Jones incomplete | Q4 1:49, -4, opp 31, 4th-9 | go -> FG | 557/3050/3782 | 7.32% | clear | 62.27% / 0% | model-form warning |
| 17 | `2025_01_HOU_LA` 3420; Townsend punt, 16-yard return | Q4 9:26, -5, own 26, 4th-1 | punt -> go | 664/--/17007 | 7.29% | clear | 0.13% / 0% | structurally clean |
| 18 | `2025_06_ARI_IND` 4230; Brissett incomplete | Q4 :58, -4, opp 9, 4th-7 | go -> FG | 181/2537/-- | 7.17% | limited | 9.94% / 0% | structurally clean |
| 19 | `2025_09_DEN_HOU` 3951; Townsend punt, touchback | Q4 7:24, tied, own 44, 4th-2 | punt -> go | 187/--/17007 | 6.81% | clear | 8.18% / 0% | structurally clean |
| 20 | `2025_09_DEN_HOU` 4479; Townsend punt, 8-yard return | Q4 1:00, tied, own 17, 4th-6 | punt -> go | 38/--/4517 | 6.78% | limited | 0.02% / 0% | structurally clean |

All top-20 actions had zero OT-boundary mass. Their supported action cells
included and correctly transported scoring-restart samples; exact per-action
restart counts and every factual next-state field remain in the machine report.
The four warnings are ranks 1, 6, 11, and 16. Each is a late deficit in opponent
territory, and each warning is driven by applying the broad opponent-21--49 punt
cell to a query where 62.27%--92.86% of punt transitions cross the field bound.
The implementation clips exactly as v1 documents and all structural checks
remain zero, so these are model-form warnings rather than correctness bugs.

Suspicious-case count: **zero potential correctness bugs; four model-form
warnings; sixteen structurally clean cases**.

## Limitations and interpretation

The holdout improves confidence that the frozen implementation is temporally
stable: WP, factual action behavior, support, classifications, gaps, OT
frequency, and clipping rates are broadly consistent with 2020--2024. It does
not solve the observational identification problem. Coarse empirical cells
still mix score, time, personnel, opponent, formation, and strategic context;
transition intervals omit WP fitting and model-form uncertainty; factual
calibration cannot validate unchosen actions; and overtime remains unmodeled.

The main limitation is now quantified rather than anecdotal. A hypothetical
punt in opponent territory can inherit large relative field movement from a
coarse cell and pile substantial mass at the 1-yard boundary. Because clear
classifications compare all supported actions, this can affect presentation
even when punt is neither actual nor preferred. The stable holdout rates argue
against a new data or implementation defect, but the absolute prevalence is
too large to call an unqualified pass or to support public coach grading.

## Milestone 7 scope

The proposed next milestone is a **pre-registered boundary-transport v2
development study**, not rankings or 2026 product output:

1. keep all v1 artifacts and this report immutable;
2. use only 2014--2024 rolling development folds to compare prespecified,
   football-constrained transition alternatives focused on opponent-territory
   punts and boundary-aware field movement;
3. report how candidate transport specifications change clipping, factual punt
   destination error, support, action ordering, and uncertainty without using
   2025 to choose cells or thresholds;
4. version any accepted change as `coachiq-action-transition-v2` and, where its
   values or classifications change, `coachiq-decision-v2`; and
5. write a new external-evaluation protocol before opening any future season.

Milestone 7 should not produce coach/weekly rankings, public grading, or access
2026 data. The 2025 results remain a disclosed prior diagnostic and cannot be
recast as an untouched v2 holdout.

## Reproduction

First reproduce the frozen historical decision report from explicit snapshots:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_decision_values.py diagnostics \
  --parquet-dir /path/to/2014-2024-snapshots \
  --bootstrap-replicates 200 \
  --json-output /tmp/coachiq-decision-v1.json
```

Then run the explicit holdout path with snapshots named
`play_by_play_YEAR.parquet`:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_2025_holdout.py \
  --parquet-dir /path/to/2014-2025-snapshots \
  --historical-decision-report /tmp/coachiq-decision-v1.json \
  --json-output /tmp/coachiq-2025-holdout.json
```

Or reuse the hashed 2025 snapshot while loading historical seasons through
nflreadpy:

```bash
PYTHONPATH=src .venv/bin/python scripts/evaluate_2025_holdout.py \
  --holdout-parquet /tmp/play_by_play_2025.parquet \
  --historical-decision-report /tmp/coachiq-decision-v1.json \
  --json-output /tmp/coachiq-2025-holdout.json
```

Two complete runs produced identical analytic payloads; only the expected
source-path metadata and the second run's added clipping-severity block differed.
The final machine report used for this document is
`/tmp/coachiq-2025-holdout-rerun.json`.
