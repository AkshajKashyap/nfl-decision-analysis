# Milestone 0: fourth-down decision-auditor foundation

Status: proposed design  
Decision date: 2026-09-03  
Initial product name: CoachIQ  

## 1. Purpose and claims

CoachIQ will estimate the value of an NFL coach's fourth-down choice relative
to modeled alternatives. It will not claim to know what would have happened
under an action that was not taken.

For pre-snap state `s` and action `a`, the central estimand is:

```text
Q(s, a) = E[V(S_next) | S = s, do(A = a), assumptions]
decision_loss(s) = max_a Q(s, a) - Q(s, chosen_action)
```

`V` is the offense's probability of eventually winning from a post-action game
state. `Q` and `decision_loss` are model estimates, not observed facts. The
word `do` states the intended causal interpretation; observational data alone
does not make that interpretation valid. The identifying assumptions and
remaining confounding must accompany published results.

For terminal utility, use 1 for a win, 0.5 for a regular-season tie, and 0 for
a loss. Thus `V` is technically expected win-equivalent game value. If a public
report calls it win probability, it must disclose the half-win tie convention;
a later three-outcome model may report literal win, tie, and loss probabilities.

The first usable version answers one bounded question:

> At a valid NFL fourth-down decision in regulation, which of go, field goal,
> and punt had the highest modeled win probability, and how much modeled win
> probability did the chosen action leave relative to that option?

It does not initially evaluate play calls, fourth-down execution, timeouts,
two-point attempts, kickoffs, challenges, clock management, or whether a team
should deliberately take a penalty.

The foundation decisions in brief are:

- start with 2014-present regular-season and postseason data, score regulation
  only, and retain an explicit ledger for every exclusion;
- compare `go`, `field_goal`, and `punt` only when each alternative is both
  physically available and inside trained-model support;
- model complete action-outcome distributions and feed their resulting states
  into an owned, callable state-value model;
- use nflverse WP and nfl4th as benchmarks, never as counterfactual truth or
  production labels;
- evaluate every component with rolling season splits and reserve 2025 for a
  disclosed, locked performance test; and
- publish uncertainty/support with every score before building rankings or a
  delivery application.

## 2. MVP population and decision policy

The extraction policy is part of the model specification. It must be versioned,
tested, and emitted with every result.

### 2.1 Unit of analysis

One record represents one genuine opportunity to choose an action immediately
before a valid fourth-down snap. Its stable key is `(game_id, play_id)`. Keep
`drive` and `order_sequence` for ordering and validation, but do not rely on
`play_id` alone across games.

The initial historical population is regular-season and postseason NFL games
from 2014 onward. This gives a reasonably modern rules and kicking era while
leaving multiple seasons for rolling out-of-time evaluation. Older data may be
used to fit a state-value model only after an era-stability study; it must not
silently enter the action models.

The scored MVP includes quarters 1 through 4. Overtime is extracted and tagged
but not scored until the state transition and win-value logic represents the
applicable overtime rules by season.

### 2.2 Candidate row requirements

A candidate must satisfy all of the following:

- `down == 4` at the start of the play;
- non-null `game_id`, `play_id`, `posteam`, `defteam`, `ydstogo`,
  `yardline_100`, `qtr`, pre-play clock, pre-play score differential, and both
  teams' remaining timeouts;
- `play_deleted != 1`;
- a regulation quarter for scoring; and
- a classifiable football action under the priority rules below.

Rows that fail a requirement remain in an exclusions table with exactly one
primary reason and any secondary diagnostic tags. They are never silently
dropped.

### 2.3 Action classification

Action labels describe the action selected, not whether it worked. Classification
uses structured fields before description text.

Apply this precedence:

1. `play_type_nfl == "FIELD_GOAL"` or `field_goal_attempt == 1` ->
   `field_goal`.
2. `play_type_nfl == "PUNT"` or `punt_attempt == 1` -> `punt`.
3. A valid scrimmage rush, pass, sack, interception, or offensive fumble on
   fourth down -> `go`.
4. A fake punt or fake field goal recorded as a scrimmage rush/pass rather
   than an actual kick -> `go`; the strategic choice was to attempt conversion.
5. Anything still ambiguous -> `unknown`, never guessed from a single keyword.

The precedence prevents a blocked kick or botched special-teams play from being
mistaken for `go`. Description parsing is allowed only as a documented fallback
for a small, audited exception table.

### 2.4 Penalties and no-plays

Penalty treatment separates the decision record from the model-training
outcome.

| Situation | Decision dataset | Transition-model dataset |
|---|---|---|
| False start, encroachment, neutral-zone infraction, or other `play_type == "no_play"` | Exclude that row because action intent is not reliable; if the next valid snap is still fourth down, it becomes a new opportunity with its new state | Exclude |
| Accepted live-ball penalty after a classifiable snap | Include and retain the selected action | Include the realized transition, including automatic first down, replayed down, or changed field position, when reconstructable |
| Declined or offsetting penalty with a valid play result | Include | Use the enforced official resulting state |
| Penalty with ambiguous action or irreconcilable next state | `unknown` / non-scoreable | Exclude with reason |
| Deleted play | Exclude | Exclude |

This means a defensive penalty can be one possible outcome of going for it. A
pre-snap no-play cannot be treated as a conversion attempt merely because the
offense appeared to line up for one.

### 2.5 Aborted plays, kneels, and unusual tactics

- Aborted/botched snaps are tagged. Include them only when structured fields
  establish the intended punt or field-goal action; otherwise classify as
  `unknown`. Do not infer coaching intent from the eventual loose-ball result.
- Fourth-down quarterback kneels are excluded as `clock_kill`. They are not an
  ordinary go attempt and would distort the conversion model.
- Intentional safeties are extracted but non-scoreable until represented as a
  fourth action. Forcing them into `punt` or `go` would compare the wrong policy.
- Spikes, untimed downs, and administrative end-of-period rows are non-scoreable.
- Surprise onside-like or other unrecognized special-team plays are
  `unsupported_action`, not forced into one of the three labels.

### 2.6 End-of-game and desperation states

Low win probability is not by itself a reason to erase a real decision. Valid
late-game fourth downs remain in coverage statistics and can be scored when all
candidate actions are in model support.

Use explicit reporting tags:

- `late_half`: at most 120 seconds remain in the half;
- `extreme_wp`: benchmark pre-play WP is below 0.01 or above 0.99;
- `must_score`: a rule-based score/clock check says a non-scoring action can
  only win through an exceptional return/turnover sequence;
- `clock_kill_available`: the leading offense may be able to end the game after
  a conversion; and
- `endgame_transition_uncertain`: runoff, kickoff, kneel-out, or no-next-snap
  logic cannot yet be reconstructed confidently.

The last tag makes a play non-scoreable in the MVP. The others do not. Extreme
states are excluded from coach ranking aggregates by default because tiny,
poorly calibrated probabilities can produce misleading comparisons; they stay
visible in an appendix. This rule must be applied without looking at the actual
play outcome.

### 2.7 Feasible actions and model support

Physical possibility and statistical support are different.

- `go` is physically available on every retained scrimmage fourth down.
- A field goal uses an alternative kick distance of `yardline_100 + 18` yards.
  This convention must be checked by season against actual `kick_distance`.
  The MVP will not value an attempt beyond 70 yards or outside the fitted
  model's observed support.
- `punt` is physically available outside pathological goal-line states, but it
  is valuable only where the punt transition model has adequate support.

Each action value therefore carries `available`, `in_support`, and
`support_reason`. A decision is auditable only if the chosen action and at least
one alternative are in support. Unsupported alternatives are not assigned zero
value. The support ranges will be learned from training data and stored with a
model artifact, not hard-coded after looking at a test season.

### 2.8 Meaningful decision labels

Do not filter the dataset based on estimated loss. Report all auditable plays,
then describe evidence using these categories:

- `close_call`: estimated best-to-chosen gap is under 1.0 percentage point or
  the uncertainty interval for the gap includes zero;
- `model_preference`: point estimate is at least 1.0 point but uncertainty does
  not support a stronger statement; and
- `clear_model_disagreement`: the 90% interval for decision loss is entirely
  above 1.0 point and the chosen action's probability of being optimal is below
  10%.

The 1.0-point communication threshold is a product convention, not a claim of
statistical or football significance. Sensitivity tables must also show 0.5,
1.5, and 2.0-point thresholds.

## 3. Data feasibility and contract

### 3.1 Source and acquisition

Use the official [`nflreadpy`](https://nflreadpy.nflverse.com/api/load_functions/)
loader as the first Python adapter. It returns Polars data frames and loads
nflverse play-by-play from 1999 onward. Keep the adapter thin so a direct
versioned parquet URL can replace it without changing downstream code.

Every ingestion run must write a manifest containing:

- requested and successfully loaded seasons;
- source URLs or nflreadpy version and resolved asset names;
- retrieval time, row count, column count, and file checksum where available;
- the upstream update timestamp when exposed;
- CoachIQ schema version and code commit; and
- per-season missingness and categorical-domain checks.

The cleaned data is updated after game days during the season, with stat
corrections commonly arriving through Thursday. The official
[`nflverse update schedule`](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html)
therefore supports next-day reports, not a promise of real-time in-game data.
For reproducible historical experiments, keep immutable local parquet snapshots
under ignored `data/raw/` and never train from a floating remote asset without
recording its manifest.

As of 2026-09-03, the conventional cleaned 2026 parquet release URL returned
404. The live-season milestone must discover availability and fail clearly; it
must not assume a season asset exists before nflverse publishes it.

The nflverse-data repository is published under CC BY 4.0, while its own terms
note that underlying NFL data remain subject to their owners' terms. Preserve
source/version attribution and review usage rights before a public or
commercial launch. See the
[`nflverse-data` repository](https://github.com/nflverse/nflverse-data).

### 3.2 Field availability

The canonical upstream reference is the 372-field
[`nflverse play-by-play dictionary`](https://nflreadr.nflverse.com/articles/dictionary_pbp.html).
"Direct" below means the field is present in current play-by-play, not that it
is raw observation. In particular, EP and WP columns are upstream model output.

| Need | Direct current fields | CoachIQ derivation or caveat |
|---|---|---|
| Season/game/play identity | `season`, `season_type`, `week`, `game_date`, `game_id`, `play_id`, `drive`, `order_sequence`, `nfl_api_id` | `decision_id = game_id + ":" + play_id`; validate uniqueness with drive/order |
| Down and distance | `down`, `ydstogo`, `goal_to_go` | Validate fourth-down state against adjacent valid rows |
| Field position | `yardline_100`, `yrdln`, `side_of_field`, `end_yard_line` | Normalize to possession-team perspective; reconstruct post-action spot from next valid state |
| Clock and period | `qtr`, `time`, `quarter_seconds_remaining`, `half_seconds_remaining`, `game_seconds_remaining`, `game_half` | Tag regulation/overtime, late-half, untimed, and runoff-sensitive states |
| Score | `posteam_score`, `defteam_score`, `score_differential` and post-play counterparts; home/away totals | Use pre-play fields as features; final winner from game result/scores |
| Timeouts | `home_timeouts_remaining`, `away_timeouts_remaining`, `posteam_timeouts_remaining`, `defteam_timeouts_remaining` | Recompute possession-relative values as a consistency check |
| Possession/home-away | `posteam`, `defteam`, `posteam_type`, `home_team`, `away_team`, `home_opening_kickoff` | Convert all state and value quantities to decision-team perspective |
| General action | `play_type`, `play_type_nfl`, `rush`, `pass`, `special`, `special_teams_play`, `st_play_type`, `aborted_play` | Apply versioned classification precedence; use text only for audited exceptions |
| Go outcome | `fourth_down_converted`, `fourth_down_failed`, `first_down`, `first_down_penalty`, `yards_gained`, turnover/TD fields | Reconstruct official next state; flags are checks, not the sole truth |
| Field goal | `field_goal_attempt`, `field_goal_result`, `kick_distance`, `kicker_player_id`, `kicker_player_name`, blocked-player and scoring fields | Derive alternative distance as field position + snap/hold depth; model make/miss/block and next state |
| Punt | `punt_attempt`, `kick_distance`, `return_yards`, `touchback`, punt result flags, `punt_blocked`, `return_touchdown`, fumble fields, punter/returner IDs | Derive opponent start state and exceptional outcomes; `kick_distance` is not FG-specific |
| Expected points | `ep`, `epa`, score-event probabilities | Upstream model estimates; benchmark/diagnostic only, never counterfactual truth |
| Win probability | `wp`, `def_wp`, `home_wp`, `away_wp`, post-play values, `vegas_wp`, `vegas_home_wp`, WPA fields | Upstream model estimates; use initially as a labeled benchmark/value plug-in, not an outcome feature in CoachIQ models |
| Venue/environment | `stadium`, `stadium_id`, `game_stadium`, `roof`, `surface`, `weather`, `temp`, `wind`, `location` | Normalize categories; raw weather text can be missing; indoor temp/wind nulls are structural |
| Personnel | kicker, punter, and returner IDs/names; passer/rusher/receiver IDs | Historical player effects need shrinkage and minimum history; never use future-season performance |
| Coach | `home_coach`, `away_coach` | Derive `decision_coach` from possession side; validate midseason changes |
| Pregame strength | `spread_line`, `total_line`, `div_game` | Lines are optional pregame information; record whether opening or closing and never substitute a postgame feature |
| Penalty/deletion | `penalty`, team/type/yards, `play_deleted`, `desc` | Apply the penalty table above and preserve an exclusion ledger |

Availability varies by season and upstream corrections can change past rows.
Milestone 1 must measure the contract separately for every season instead of
assuming the 2025 schema and completeness apply to 2014.

### 3.3 2025 feasibility probe

On 2026-09-03, the official
[`play_by_play_2025.csv.gz`](https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2025.csv.gz)
season asset was downloaded solely to check feasibility. It contained 48,771
rows and all 372 documented columns. There were 4,290 rows with `down == 4`:

| Check among fourth-down rows | Result |
|---|---:|
| Complete core IDs/state/clock/score/timeouts/possession | 4,290 / 4,290 |
| `punt` rows | 2,042 |
| `field_goal` rows | 1,024 |
| `pass` or `run` rows | 931 before policy exclusions |
| `no_play` rows | 289 |
| Aborted-play flag | 9 |
| Missing raw `weather` string | 305 (7.1%) |
| Missing `temp` and `wind` | 1,446 each (33.7%), largely structural for non-outdoor games |

These counts are a dated feasibility observation, not a golden test. The
published extraction count will differ after applying policy rules. Tests should
assert invariants and fixture behavior, not freeze a mutable upstream row count.

### 3.4 Known data risks

- Upstream rows receive corrections; identical URLs may not imply identical
  bytes over time.
- Play descriptions and categorical values change across eras.
- A fourth-down row records the realized action, so action datasets are highly
  selected: coaches attempt field goals and punts only in favorable states.
- Weather is coarse and stadium-level. It does not measure gusts at kick time.
- Player identity is present, but naive kicker/punter fixed effects badly
  overfit small samples and introduce survivor bias.
- Pregame betting lines may be unavailable or have ambiguous timing for a live
  product.
- Upstream EP/WP values are model estimates trained outside CoachIQ's temporal
  evaluation protocol. They are useful benchmarks but cannot certify CoachIQ's
  out-of-sample validity.
- Next-row logic fails around penalties, quarter ends, scoring tries, and game
  end. A transition reconstructor must search for the next valid game state and
  explicitly represent terminal states.

## 4. Statistical methodology

### 4.1 Decomposition

Use a modular transition/value approach:

```text
Q(s, go)  = sum_g P(gain = g | s, go) * V(transition(s, go, g))
Q(s, fg)   = sum_o P(FG outcome = o | s, fg) * V(transition(s, fg, o))
Q(s, punt) = sum_o P(punt outcome = o | s, punt) * V(transition(s, punt, o))
```

An outcome includes everything needed to construct the next state: yardage,
possession, score event, clock elapsed, in/out-of-bounds status where relevant,
and exceptional turnover/return events. The transition is deterministic only
after that complete outcome is sampled.

This is preferable to directly regressing eventual win on chosen action because
it makes assumptions inspectable, permits football-valid state transitions,
and exposes where uncertainty originates.

### 4.2 Go model

Do not model only conversion probability. A conversion at the line to gain and
a 50-yard touchdown lead to different states.

Baseline:

- empirically smoothed gain/outcome distributions by distance and coarse field
  position, including defensive first-down penalties;
- outcomes include touchdown, gain/loss yardage, turnover on downs, offensive
  turnover, first down by penalty, and elapsed time/inbounds status; and
- hierarchical backoff when a cell is sparse.

Stronger model:

- a calibrated conditional yardage distribution or ordered/discrete model;
- offense/defense strength based only on prior information;
- era and surface/roof effects if rolling tests support them; and
- explicit tail mass for return touchdowns and turnovers rather than silently
  folding them into ordinary failures.

Evaluate log loss/CRPS for the distribution, Brier score and calibration for
conversion, and calibration by yards-to-go and field-position bands.

### 4.3 Field-goal model

Baseline outcomes are make, ordinary miss/block with opponent possession, and
end-of-half terminal result. A later model separates blocks/returns.

Start with a monotonic distance effect plus roof and era. Add temperature/wind
only if missingness is handled explicitly and rolling out-of-time metrics
improve. A partially pooled kicker effect may use attempts strictly before the
decision date; unknown/new kickers shrink to league average.

The alternative field-goal distance is derived before action outcome is known.
Post-miss possession spot, score change, kickoff, clock runoff, and halftime
must be encoded in deterministic, unit-tested transitions.

After a make, the baseline uses the season-appropriate standard kickoff result
only as an explicit approximation. A later transition model integrates over
the empirical kickoff outcome distribution. Field-goal play duration is part
of the sampled outcome in clock-sensitive states.

Evaluate make-probability log loss, Brier score, calibration slope/intercept,
reliability curves by distance, and subgroup calibration by roof. Report
coverage separately for distances rarely attempted, where observational
selection is strongest.

### 4.4 Punt model

Baseline models a distribution over opponent starting field position plus
touchback, return touchdown, block, and receiving-team fumble/muff. It must use
net transition and elapsed time, not average gross punt distance.

A stronger version can condition on origin field position, roof/weather, era,
and shrinkage estimates for punter/return unit based only on past plays. Returner
effects are lower priority. Penalties are represented through the official next
state when possible.

Evaluate the full distribution with log score/CRPS, mean absolute error for
opponent start yard line as a secondary metric, and calibration of touchback,
block, return-TD, and muff probabilities. Sparse exceptional outcomes require
wide uncertainty rather than unstable point estimates.

### 4.5 State-value / win-probability model

Use a CoachIQ-owned, callable value model from the first integrated baseline.
The `wp` and `vegas_wp` columns only value observed upstream rows; they do not by
themselves provide a Python function for novel hypothetical states. Treat them
as observed-state calibration and sanity-check benchmarks, not as the
counterfactual value engine.

The first model is a regularized binomial or three-outcome logistic model
trained on nonterminal game states with final game value as the target; the
implementation must preserve the 0.5 tie utility rather than relabel ties as
wins or losses. Inputs may include possession,
score differential, game/half time, field position, down/distance, timeouts,
home field, opening-kickoff state, and an optional pregame strength estimate.
Use football-motivated transforms and a small declared interaction set. Weight
or sample states so games with more recorded plays do not dominate merely due
to length, and cluster all uncertainty/evaluation by game.

The next stage adds flexible interactions or gradient boosting only if they
improve rolling-origin calibration and proper scoring rules. Keep a no-betting-
line version so live and historical outputs have a consistent fallback.
nflverse WP and [`nfl4th`](https://github.com/nflverse/nfl4th) remain external
benchmarks.

### 4.6 Leakage controls

At scoring time every feature must have been knowable immediately before the
snap.

Forbidden inputs include:

- `yards_gained`, conversion/failure, kick result, return outcome, post-play
  score, `epa`, `wpa`, and next-play state;
- season-end player/team/coach aggregates for an earlier play in that season;
- future games in preprocessing encoders, imputers, calibration, hyperparameter
  selection, or support thresholds; and
- upstream `wp`/`ep` as features in an owned WP model.

Allowed pregame lines must have a documented timestamp. Team and player effects
are expanding-window features shifted by at least one play and preferably one
week. Any normalization or categorical vocabulary is fitted inside each
training fold.

### 4.7 Chronological evaluation

Never randomly split plays. Games, not rows, are the grouping unit.

Use rolling-origin folds such as:

| Training seasons | Validation/test season |
|---|---|
| 2014-2018 | 2019 |
| 2014-2019 | 2020 |
| 2014-2020 | 2021 |
| 2014-2021 | 2022 |
| 2014-2022 | 2023 |
| 2014-2023 | 2024 |

Use 2025 as the locked performance test after feature, model, and threshold
choices are frozen. The Milestone 0 schema/count probe is disclosed exposure to
that season, but no 2025 predictive outcome, calibration, or recommendation was
inspected. After the frozen report is written, refit through 2025 for 2026 use.
A model change during 2026 is a new version and must be backtested before
replacing the deployed artifact.

If older seasons improve the WP model, its fold-specific training window can
start earlier, but the action-model folds stay in the declared modern era.

### 4.8 Evaluation limits

Observed actions permit direct evaluation of factual components: field-goal
makes, conversion/gain distributions, punt transitions, and future game wins.
They do not reveal the unchosen action's result. Therefore:

- report proper scoring and calibration for each factual component;
- test deterministic transitions against reconstructed real post-play states;
- compare integrated recommendations with nfl4th as a disagreement analysis,
  not as ground truth;
- treat inverse-propensity or doubly robust policy evaluation as later
  sensitivity analysis, because it requires action overlap and no-unmeasured-
  confounding assumptions that are doubtful here; and
- never validate `decision_loss` against realized single-play WPA. Execution
  after the choice is not the quality of the pre-snap choice.

### 4.9 Calibration and uncertainty

For every probabilistic component report log loss, Brier score where
applicable, calibration intercept/slope, reliability diagrams, sample size, and
coverage/support. Expected calibration error may be included but never alone;
it depends strongly on bins.

Estimate uncertainty with a game-clustered bootstrap or model ensemble within
each temporal fold. For every action, propagate transition and value uncertainty
through Monte Carlo to produce:

- median and 5th/95th percentiles for `Q(s, a)`;
- the same interval for `decision_loss`;
- probability each action is optimal; and
- sensitivity to reasonable clock-runoff, FG spot, and pregame-strength
  assumptions.

These intervals primarily quantify sampling/model uncertainty, not all causal
uncertainty. Reports must say that unmeasured injuries, play-call quality,
personnel, wind, and coach information can still move the answer.

### 4.10 Causal interpretation and identifying assumptions

Each action is a stochastic policy, not a fully specified physical treatment.
For example, `go` averages over a modeled mix of run/pass concepts and execution;
`punt` averages over punt direction, coverage, and return behavior. The MVP
therefore estimates outcomes under the historical implementation policy for
similar states, optionally adjusted by prior-only team/player strength. It does
not estimate the result of a specific uncalled play.

Interpreting `Q(s, a)` causally requires:

- consistency: the labeled action corresponds to the modeled policy;
- no interference beyond the game state being modeled;
- conditional exchangeability: after included pre-snap state and prior-only
  strength variables, action outcome behavior transports to the alternative
  action at this state;
- positivity/overlap: sufficiently comparable historical examples exist; and
- correct transition and terminal-value specification.

These assumptions are only partially credible in observational football data.
Unobserved injuries, formation, personnel, kicker health, wind, and the planned
conversion play can affect both the choice and outcome. Support flags,
sensitivity analysis, and cautious language reduce overclaiming but do not
eliminate this limitation.

## 5. What CoachIQ owns

The existing nfl4th project is a valuable benchmark, not the product backend.
Its public methodology includes a yardage-distribution go model, a punt outcome
distribution, a distance/roof field-goal model, and a win-probability value
step. Its README also documents current edge-case limitations. Relevant source
is inspectable in
[`decision_functions.R`](https://github.com/nflverse/nfl4th/blob/master/R/decision_functions.R),
[`_go_for_it_and_2pt_models.R`](https://github.com/nflverse/nfl4th/blob/master/data-raw/_go_for_it_and_2pt_models.R),
and
[`_punt_and_fg_models.R`](https://github.com/nflverse/nfl4th/blob/master/data-raw/_punt_and_fg_models.R).

CoachIQ should learn from and benchmark against that decomposition while owning:

- reproducible Python ingestion, schema checks, and immutable manifests;
- the decision inclusion/exclusion policy and action classifier;
- pre- and post-action state reconstruction;
- all three action transition models and their temporal evaluation;
- an independent WP model and its calibration;
- integrated action valuation, uncertainty propagation, and decision scoring;
- versioned model/data cards and benchmark-disagreement analysis; and
- aggregation/reporting rules that avoid opportunity and sample-size traps.

Do not call nfl4th to generate production values or train CoachIQ against its
recommendation labels. A small offline comparison script may consume nfl4th
outputs as an external benchmark, with version recorded.

## 6. Minimal repository architecture

Create modules only when their milestone starts. The intended shape is:

```text
src/coachiq/
  data/
    source.py          # nflreadpy adapter, snapshot manifests
    schema.py          # canonical columns, domains, validation
    normalize.py       # types, team/field/clock perspective
    decisions.py       # inclusion policy and action classification
    transitions.py     # observed and hypothetical next-state construction
  models/
    win_probability.py
    go.py
    field_goal.py
    punt.py
    calibration.py
    artifacts.py       # versioned save/load metadata, not a registry service
  analysis/
    action_value.py    # compose transition probabilities with state value
    scoring.py         # loss, support, uncertainty, decision labels
    aggregation.py     # later game/week/coach summaries
tests/
  fixtures/            # tiny hand-curated play/state records, no season dumps
  data/
  models/
  analysis/
scripts/
  fetch_pbp.py         # thin reproducible entry points, no business logic
  build_decisions.py
  train_models.py
  evaluate_models.py
docs/
  milestone-0-foundation.md
  data-contract.md     # created when Milestone 1 freezes the actual schema
  model-cards/         # created with trained models
data/                  # gitignored: raw snapshots, derived tables, artifacts
```

`src/coachiq/api/` is not part of the planned architecture. No service,
frontend, database, workflow orchestrator, Docker image, or cloud layer is
justified by the MVP.

Initial dependencies should be added only with the code that uses them:

- `nflreadpy` and its Polars data frame for ingestion;
- `pytest` for executable policy and transition tests;
- a small modeling stack only in the modeling milestone, with scikit-learn as
  the likely baseline; and
- no plotting framework until an evaluation/report artifact needs it.

Notebooks may explore data, but no production transformation or metric may
exist only in a notebook.

## 7. Milestone roadmap

### Milestone 0 — methodology and feasibility

Primary objective: freeze a reviewable initial scope before implementation.

Deliverables:

- this decision policy, data feasibility matrix, statistical plan,
  architecture, and roadmap;
- a dated real-file schema/missingness probe; and
- explicit non-goals and external-vs-owned boundary.

Complete when each requested edge case has a deterministic include, exclude,
or tag rule and the plan identifies how every action value will be estimated
and evaluated.

### Milestone 1 — reproducible ingestion and normalization

Primary objective: turn nflverse seasons into a stable, validated local input.

Deliverables:

- season loader, immutable snapshot manifest, canonical schema, and normalized
  possession-relative state table;
- per-season schema, domain, duplicate, and missingness report for 2014-2025;
- minimal dependencies and packaging metadata; and
- unit tests using synthetic and tiny frozen records.

Complete when a clean checkout can reproduce the same derived checksum from a
pinned raw snapshot; all input rows are either normalized or rejected with a
reason; and no network is required for unit tests.

### Milestone 2 — fourth-down decisions and state reconstruction

Primary objective: reliably identify the decision and the observed next state.

Deliverables:

- executable inclusion/action rules and exclusion ledger;
- pre-state, observed action, observed transition, support tags, and coach
  mapping;
- a stratified hand-labeled gold set covering ordinary plays, each action,
  penalties, no-plays, fakes, blocks, aborted snaps, scores, half/game end, and
  overtime; and
- coverage/error report by season and edge-case class.

Complete when the classifier is 100% correct on the frozen policy gold set,
every mismatch is resolved by policy rather than an untracked exception, at
least 99% of non-no-play structured fourth-down rows are classified or have an
audited unknown reason, and reconstructed factual next states pass invariant
tests.

### Milestone 3 — transparent empirical action/value baseline

Primary objective: produce end-to-end values with simple, inspectable models.

Deliverables:

- smoothed go gain/conversion, FG outcome, and punt transition baselines;
- deterministic hypothetical state transitions;
- a simple, callable CoachIQ logistic state-value baseline, with nflverse WP
  used only as an observed-state benchmark;
- rolling-origin factual-component metrics, support tables, and a small set of
  worked play examples; and
- optional nfl4th disagreement comparison.

Complete when all transition distributions sum to one, toy-state values match
hand calculations, every output records model/data versions and support, and
the temporal evaluation report can be regenerated without using the locked
2025 test set for model selection.

### Milestone 4 — production-grade owned win-probability model

Primary objective: improve and validate the owned state-value model beyond the
first integration baseline.

Deliverables:

- regularized, interpretable WP baseline with and without pregame lines;
- rolling-origin discrimination, proper-score, and calibration report;
- recalibration fitted inside each temporal fold; and
- model card covering training population, features, known failures, and
  comparison with nflverse WP.

Complete when the owned model beats a preregistered score/time/home-field
baseline on aggregate rolling log loss and Brier score, has no unexplained
severe reliability failure in declared clock/WP bands, and can value all
post-transition states used by the action models. Failure to meet the bar is a
documented result, not a reason to hide metrics.

### Milestone 5 — integrated decision score and uncertainty

Primary objective: publish honest per-play model estimates.

Deliverables:

- action-value composition using the owned WP model;
- clustered uncertainty propagation, probability-best, decision-loss interval,
  and sensitivity analysis;
- `close_call`, `model_preference`, and `clear_model_disagreement` labels; and
- a machine-readable per-play output contract.

Complete when values reproduce from pinned artifacts, unsupported actions never
become zero-valued alternatives, intervals cover all reported estimates, and
golden worked examples pass.

### Milestone 6 — stronger action models and locked test

Primary objective: improve only components that demonstrate out-of-time value.

Deliverables:

- candidate distributional models, prior-only team/player effects, calibration,
  and subgroup diagnostics;
- ablation study and comparison to empirical baselines; and
- one frozen 2025 test report after all choices are locked.

Complete when each adopted component improves its preregistered proper scoring
rule in a majority of rolling folds without material calibration regression in
key subgroups. Keep the simpler model when it does not.

### Milestone 7 — game, week, and coach reporting

Primary objective: aggregate scores without disguising uncertainty or unequal
opportunity.

Deliverables:

- reproducible game report and weekly best/worst decision tables;
- coach total loss, per-opportunity loss, aggression profile, sample size, and
  shrinkage/uncertainty; and
- explicit exclusion and coverage summaries in every report.

Complete when aggregates reconcile exactly to included play records, ranking
eligibility has a declared minimum sample, and extreme/unsupported plays cannot
silently affect rankings.

### Milestone 8 — 2026 incremental operation

Primary objective: run the audited pipeline after game days with versioned
snapshots.

Deliverables:

- idempotent current-season fetch/build/score command;
- data-correction detection and rerun behavior;
- freshness, schema-drift, missingness, and model-support checks; and
- archived weekly artifacts plus Thursday corrected reruns.

Complete when replaying the same snapshot is byte-stable, an upstream
correction produces an explainable diff, schema drift fails loudly, and a full
week can be regenerated from manifests without manual data edits.

## 8. Reporting language

Preferred:

> CoachIQ estimated 61.8% win probability for going, 57.5% for punting,
> and 54.9% for attempting a field goal under model version X and the stated
> transition assumptions. The punt was 4.3 percentage points below the
> model-preferred action (90% interval: 1.7 to 6.8).

Avoid:

- "Going would have won the game."
- "The coach cost 4.3% win probability" without saying estimated/model-based.
- rankings without opportunity counts, intervals, and coverage.
- using realized WPA to retroactively grade the choice.

## 9. Open questions to resolve with data, not preference

These do not block Milestone 1, but each needs a preregistered experiment before
the relevant model is frozen:

- Is +18 yards the best season-stable alternative FG-distance convention?
- Which historical start season balances action sample size and era stability?
- Does pregame line information materially improve calibration, and can its
  timing be made reproducible for live use?
- Which support estimator is stable enough for rare long field goals and short
  field punts?
- Does structured weather improve rolling FG/punt metrics after missingness and
  roof are represented?
- Do prior-only kicker and punter effects improve proper scores after shrinkage?
- How should season-specific overtime rules enter a later scoring population?
