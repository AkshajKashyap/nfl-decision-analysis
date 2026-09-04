# Transparent action-value baseline

Status: Milestone 3 baseline

Development seasons: 2014–2024

Protected holdout: 2025

This is CoachIQ's first end-to-end model-based estimate of fourth-down action
value. It is deliberately simple and inspectable. It does not establish the
true result of an unchosen action, identify a coach's mistake, or remove the
selection bias in historical coaching choices.

## Modeling target and state convention

The state-value target is the eventual observed game value for the team in
possession at a valid regulation scrimmage state: 1 for a win, 0.5 for a
regular-season tie, and 0 for a loss. The target comes from normalized
nflverse `result`, the final home-minus-away margin. nflverse win probability
is neither a feature nor a target.

Every canonical state is represented from the perspective of the team whose
probability is being evaluated. It contains the evaluation and opponent team,
home indicator, evaluation-team score differential, quarter, regulation
seconds remaining, yards to the opponent goal line, down, yards to go, and
both teams' timeouts.

An action transition is first represented from the next possession team's
perspective. If possession changes, score differential and home status switch
perspective. The resulting probability is converted back to the original
decision team as `1 - P(next possession team wins)`. Tests protect both sign
and probability inversion.

## State-value baseline

The callable model is ridge logistic regression fitted by deterministic Newton
updates. The fixed L2 penalty is 1.0, with no search over evaluation seasons.
Continuous transformations are fitted or standardized only on training data.

The fixed feature vector is:

```text
score differential
regulation time fraction
score differential * fraction of game elapsed
score differential / sqrt(max(minutes remaining, 1))
field progress = (100 - yards_to_goal) / 100
min(yards_to_go, 30) / 10
timeout differential
home indicator
down 2, down 3, and down 4 indicators
```

The score/time terms let the same lead carry different meaning late in a game
without a large interaction expansion. Logits are clipped to ±35 only to avoid
numerical overflow; output probabilities are not cosmetically clipped. All
non-no-play, non-deleted, complete regulation scrimmage states are used. The
final margin is converted to the target and then omitted; it is not present in
the model matrix. The model matrix is a fixed allow-list of the features above
and contains no nflverse WP or EP field. Many rows consequently share one game
outcome. Reported log loss and Brier score use the state row as the evaluation
unit, but rows within a game are correlated and play-level sample sizes must not
be interpreted as independent games. Future inferential model comparisons
should use game-clustered resampling where appropriate.

Quarter remains part of the canonical state and transition validation but is
not duplicated as a regression feature because exact regulation seconds
remaining already determine the quarter.

## Action outcome baselines

Only eligible Milestone 2 decisions with reconstructed factual next states are
training evidence. A classifiable live snap whose outcome is `down_replayed`
is excluded as action-outcome evidence; the later genuine decision remains.
Thus a replay sequence is not counted twice as two independent realized
outcomes.

### Go

The empirical transition distribution is conditioned on both yards-to-go and
field position. Fixed distance cells are 1, 2, 3–5, 6–10, and 11+ yards. Fixed
field cells are opponent red zone, opponent 21–49, own 21 to midfield, and own
1–20. The diagnostic conversion estimate is the Beta(1,1)-smoothed empirical
rate within the cell.

Transition samples retain conversions, failures, scoring, turnovers,
possession, next down/distance, elapsed time, score change, timeout change, and
the decision-team-oriented change in yards to goal. For a non-scoring result,
that field-position change is added to the queried line of scrimmage; the
historical absolute field position is not copied. Successful conversions
therefore use empirical post-play movement rather than being placed exactly at
the line to gain. A transported goal-to-go successor caps yards to go at yards
to goal.

### Field goal

Hypothetical kick distance is:

```text
kick distance = yards_to_goal + 18
```

The nflverse [`yardline_100` convention](https://nflreadr.nflverse.com/articles/dictionary_pbp.html)
is distance from the possession team's line of scrimmage to the opponent end
zone. Ten yards from the goal line to the goalposts plus the modern eight-yard
snap/hold depth therefore gives the declared `+18` approximation. Among the
10,666 fourth-down attempts used by the distance audit from 2014–2024, 9,598
use exactly that offset, 170 use `+17`, 897 use `+19`, and one uses `+20`. The
formula's season-level mean absolute difference is 0.064–0.140 yards;
86.0–93.6% match exactly. These observed one-yard variants are why the recorded
distance, rather than the derived approximation, defines training cells. Cells
are under 30, 30–39, 40–49, 50–59, and 60–70 yards. Queries over 70 yards are
unavailable in this baseline.

The empirical transition distribution preserves makes, misses, blocks,
returns, score changes, elapsed time, and the actual post-kick possession
state. A non-scoring miss/block transports the observed decision-team-oriented
field-position change onto the query. A score is a football reset: its
post-kickoff field position is sampled as an absolute successor position, while
the score and clock remain query-relative. The diagnostic make estimate uses
Beta(1,1) smoothing.

### Punt

Punts use the same four starting-field cells as the go model and preserve the
full empirical distribution of decision-team-oriented net field-position
change. Each sampled change is applied to the queried starting position; punts
are not reduced to a fixed net-yardage constant or copied as historical
absolute successor states. Samples retain elapsed time, score changes, returns,
touchbacks, exceptional scores, and subsequent possession. A return score uses
its empirical post-score restart position as described above.

The baseline does not simulate fake punts. A historical fake classified as a
scrimmage play is go evidence under the Milestone 2 policy.

## Support and overlap

Every action query returns physical availability, local observation count,
distinct training-game count, a sparse indicator below 100 observations,
support status and reason, and distance to the nearest occupied empirical
cell.

An available action requires at least 30 observations in its exact fixed cell.
Unsupported estimates are `None`; they are never assigned zero or produced by
unbounded extrapolation. Field goals above 70 yards are unavailable. The
30-observation and 100-observation thresholds were fixed before rolling
evaluation and were not tuned against 2025.

The cell count is a support heuristic, not proof of causal overlap,
exchangeability, or identification. A well-populated cell may still mix very
different score, time, team-strength, formation, personnel, kicker-health,
weather, or injury contexts. Milestone 3 values are therefore descriptive,
model-based baselines rather than causal treatment effects.

## Hypothetical transitions and action value

For a supported action, each comparable training observation contributes an
equally weighted empirical transition. Historical score, clock, timeout, home
status, team identity, and quarter are never copied into a query. Instead, the
query's score, clock, and timeout context is updated by observed deltas, quarter
is recomputed from the query-relative clock, and query teams/home status are
switched only when the sampled transition changes possession. Next down and
distance are sampled football outcomes. Non-scoring field position is the
sampled decision-team-oriented delta applied to the query; only a genuine
scoring restart uses an absolute empirical post-kickoff field position.
Transitions whose next valid state crosses from the first half into the second
are excluded because halftime possession, field position, and timeout resets
are not action transitions. A next state more than 120 game-clock seconds away
is likewise excluded rather than having its elapsed time silently truncated.
Each next state is evaluated by the CoachIQ state-value model and converted
back to the original decision team's perspective.

```text
baseline Q(state, action)
  = mean over supported empirical transitions of
    CoachIQ state value(hypothetical next state)
```

This is a baseline EWP under a historical conditional transition policy. It is
not the known counterfactual or an unbiased causal effect.

## Uncertainty

The reported 90% interval resamples distinct training games with replacement,
retains every selected game's transition observations, and recomputes mean
action value. The seed and number of replicates are fixed by the caller, making
results reproducible.

This interval reflects finite conditional action-transition support and
within-game dependence. It holds the state-value model fixed. It does not
capture state-model parameter uncertainty, bin-definition uncertainty,
unmeasured confounding, policy transport failure, or general model
misspecification. Very large punt/field-goal cells consequently yield narrow
intervals that are not comprehensive uncertainty.

## Chronological evaluation

The fixed expanding-window design is:

| Training seasons | Evaluation season |
|---|---:|
| 2014–2019 | 2020 |
| 2014–2020 | 2021 |
| 2014–2021 | 2022 |
| 2014–2022 | 2023 |
| 2014–2023 | 2024 |

Each state scaler, state model, action cell, smoothing count, transition
distribution, and support decision is fitted only from the listed training
seasons. Calibration uses ten fixed-width bins. Metrics are log loss and Brier
score for state value, go conversion, and field-goal make; punt transition is
reported with opponent-yards-to-goal MAE and RMSE. A training-prevalence
constant is the simple state benchmark. nflverse WP is an external reference
on the same evaluation rows and is never fitted or consumed by CoachIQ.

Observed state-value results:

| Evaluation | CoachIQ log loss | Brier | ECE | Constant log loss | nflverse log loss |
|---:|---:|---:|---:|---:|---:|
| 2020 | 0.4845 | 0.1625 | 0.0114 | 0.6931 | 0.4780 |
| 2021 | 0.4615 | 0.1557 | 0.0205 | 0.6929 | 0.4616 |
| 2022 | 0.5632 | 0.1902 | 0.0404 | 0.6930 | 0.5583 |
| 2023 | 0.4751 | 0.1593 | 0.0158 | 0.6930 | 0.4729 |
| 2024 | 0.4653 | 0.1578 | 0.0208 | 0.6931 | 0.4622 |

These are development results, not a claim of superiority. The 2022 shift is
a useful warning about year-to-year calibration stability. Detailed
calibration bins and action metrics are available in the optional JSON report.

## Assumptions and known failure modes

- Historical action choice is highly selected. Coarse conditioning does not
  make the empirical distributions causal.
- Fixed bins create discontinuities and average together materially different
  situations inside a cell.
- Go outcomes do not yet condition on offense, defense, play concept,
  personnel, weather, or score/time context.
- Field goals do not yet model kicker, venue, weather, or era beyond the
  expanding training window.
- Punt transitions do not condition on punter, returner, coverage unit, or
  detailed punt location.
- Net field-position changes are transported within coarse cells; clipping at
  the physical 1–99 yard bounds and behavior near cell boundaries remain rough
  baseline approximations.
- The state model is intentionally small and does not explicitly model team
  strength or pregame expectations.
- Overtime and unsupported Milestone 2 decisions are not valued.
- Terminal action transitions without a reconstructable scrimmage state are
  excluded from these empirical transition models.
- Evaluation decisions informed by these 2020–2024 results are development
  choices and must not later be portrayed as preregistered. The 2025 holdout
  has not been loaded or inspected.

## Reproduction

Download through nflreadpy:

```bash
.venv/bin/python scripts/evaluate_baseline.py
.venv/bin/python scripts/worked_examples.py
```

Or reuse explicit raw snapshots without hidden caching:

```bash
.venv/bin/python scripts/evaluate_baseline.py \
  --parquet-dir /path/to/raw-snapshots \
  --json-output /tmp/coachiq-baseline-report.json
.venv/bin/python scripts/worked_examples.py \
  --parquet-dir /path/to/raw-snapshots
```
