# CoachIQ decision-value methodology

## Status and purpose

`coachiq-decision-v1` is the frozen pre-2025 specification for comparing the
modeled values of supported fourth-down actions. It answers a narrow question:

> Under the frozen CoachIQ state-value model and empirical transition
> assumptions, how large is the estimated difference between the supported
> actions?

It is a model-based decision audit. It is not a coach grade, a claim that an
action was right or wrong, or an estimate of what would certainly have happened
under an unobserved choice. No coach aggregation belongs to this version.

## Frozen dependencies

Decision v1 requires:

- `coachiq-wp-v1`, the locked Candidate D ridge-logistic state-value model;
- `coachiq-action-transition-v1`, the unchanged Milestone 3 empirical
  go/field-goal/punt transition specification;
- regulation fourth-down decisions from 2014 through 2024 only; and
- expanding chronological evaluation in 2020--2024, with every evaluation
  season fit only on earlier seasons.

The action models use the existing cells and thresholds without widening them:

- go: yards-to-go bucket crossed with field-position zone;
- field goal: attempted-kick-distance bucket, with attempts above 70 yards
  unavailable;
- punt: field-position zone;
- fewer than 30 comparable observations: unsupported; and
- 30--99 observations: supported but sparse.

## Canonical output

For each of `go`, `field_goal`, and `punt`, the audit records availability,
support label and reason, observation and game counts, expected win probability
(EWP), a 90% transition-bootstrap interval, valid bootstrap-draw count, model
versions, and empirical mass transported to a tied 0:00 regulation boundary.

The decision record contains the actual action and its EWP, the highest-valued
supported action and EWP, all pairwise comparisons, the number of supported
actions, the raw actual-action gap, the classification and reason, the v1
threshold policy, and version metadata.

The raw action-value gap is

```text
max(EWP over supported actions) - EWP(actual action)
```

It is unavailable when the actual action is unsupported or fewer than two
actions are supported. A zero gap says only that the observed action tied for
or had the highest estimate under this model.

## Transition values and possession perspective

Each fixed empirical action cell supplies equally weighted observed transition
rows. Its clock, score, field position, possession, timeouts, home indicator,
and pregame spread are transported to the query's possession-relative state by
the unchanged action-transition model. `coachiq-wp-v1` values each resulting
state from the next possession's perspective; the decision layer inverts that
probability when possession changed and averages from the original decision
team's perspective.

This transports observational outcomes from actions selected in historically
similar cells. It does not remove selection bias or hidden confounding.

## Paired whole-game bootstrap

Decision v1 uses 200 deterministic whole-game cluster draws with seed 2505. On
each draw, one multinomial resample is taken over the common universe of
training games. Every action uses those same game weights while retaining its
own transition rows and its own weighted denominator.

For each supported pair, the action values are subtracted within bootstrap
draw. The output reports the point difference, central 90% interval, the strict
empirical probability that the first action exceeds the second, the reverse
probability, and the probability of a tied draw. Numerically negligible
differences within `1e-12` are ties. Sharing game weights preserves covariance
arising from common games without pairing unrelated action rows or inventing
row-level correlation.

Two hundred draws are a computational compromise for scoring roughly 20,000
development decisions. Strict superiority probabilities therefore move in
0.5-point increments. The report prints the binomial Monte Carlo standard error
at the selected 95% cutoff and the classification change from moving that
cutoff by one draw. The intervals do not include uncertainty from refitting
`coachiq-wp-v1`.

## Classification policy

The presentation policy is `decision-threshold-v1`:

1. `insufficient_support` when the actual action is unsupported or fewer than
   two actions can be valued;
2. `limited_support` when any supported action is sparse, an otherwise
   available action is unsupported, pairwise uncertainty is unavailable, or a
   supported action has positive tied-regulation-expiration transition mass;
3. `clear_model_preference` only when complete non-sparse support remains, the
   highest-valued supported action exceeds every supported alternative by at
   least 1.0 percentage point, and every corresponding paired superiority
   probability is at least 95%; and
4. `close_call` for the remaining fully supported comparisons.

The 1-point/95% combination is a conservative presentation rule, not a claim
about a universal football threshold. It jointly avoids presenting tiny point
differences or bootstrap-unstable ordering as clear. The final diagnostics
compare all nine combinations of 0.5, 1.0, and 2.0 percentage-point gaps with
90%, 95%, and 97.5% superiority requirements. The selected rule is not chosen
to maximize the number of clear preferences.

## Regulation-to-overtime safeguard

The locked state-value and transition specifications do not model overtime.
Decision v1 therefore examines each supported action's transported successors.
If a positive empirical share reaches 0:00 of the fourth quarter with a tied
score, that share is recorded as `overtime_boundary_mass` and the comparison is
limited. This is more precise than limiting every tied state in the final two
minutes: a query remains eligible for the ordinary policy when none of its
supported empirical transitions crosses that boundary.

The EWP and pairwise numbers are retained for audit visibility, but the system
will not present a clear preference when any supported alternative includes
such out-of-scope mass. This is a scope/presentation safeguard, not a football
assertion and not an overtime model.

## Validation protocol

The reproducible diagnostic fits on 2014 through the season before evaluation
and scores eligible regulation decisions in each of 2020 through 2024. It
reports support by season, action count, field zone, yards-to-go, and late-game
regime; sparse support; classifications; gap distributions; threshold
sensitivity; temporal stability; deterministic stress cases; worked examples;
and a transport audit of the twenty largest actual-action gaps.

Factual-action validation compares the modeled EWP for the observed action with
the eventual win-equivalent target using log loss, Brier score, expected
calibration error, and ten fixed calibration bands. It also validates observed
go/field-goal success probabilities and punt destination predictions against
their reconstructed factual outcomes. This is necessary evidence about model
behavior, but it is not sufficient evidence for unobserved alternative-action
values.

The largest-gap audit retains the source description and factual next state. It
checks support cells, possession and score perspective, query-relative clock,
field position and timeout transport, scoring-restart samples, regulation/OT
mass, bounds, and pre-transport clipping counts. Boundary clipping is reported
rather than hidden; a boundary count is not automatically a data error.

## Uncertainty and known failure modes

The reported intervals principally capture finite empirical transition
sampling at the game-cluster level. They omit:

- fitted WP coefficient uncertainty;
- WP and transition model-form uncertainty;
- uncertainty about cell definitions and support thresholds;
- player, injury, weather, formation, and play-call information;
- hidden confounding and historical action-selection bias;
- within-game dependence beyond the game-cluster resampling design; and
- overtime value.

Coarse empirical cells can mix strategically different situations. Examples
include clock-management punts, punts from field-goal formation, desperation
states, and transitions whose elapsed time or field movement clips at a valid
boundary when transported. Large estimates are review targets, not grounds for
silently dropping observations. Factual calibration cannot establish the
validity of an unobserved alternative.

The final largest-gap review found no mismatch between the implemented
query-relative transport and its documented formula, but it did expose large
pre-clip boundary mass in some coarse punt cells (as high as 3,251 of 3,500
transitions for a query at the opponent 21) and large clock-expiration mass in
some end-game go cells. These are model-form warnings, not reconstruction
errors. The overtime safeguard limits tied-expiration cases; other clipping
remains visible in the audit and should be studied before any public coach-level
reporting.

## Reproduction and versioning

With explicit local snapshots named `play_by_play_YEAR.parquet`:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_decision_values.py diagnostics \
  --parquet-dir /tmp --bootstrap-replicates 200 \
  --json-output /tmp/coachiq-decision-v1.json
PYTHONPATH=src .venv/bin/python scripts/audit_decision_values.py worked \
  --input-report /tmp/coachiq-decision-v1.json
PYTHONPATH=src .venv/bin/python scripts/audit_decision_values.py largest \
  --input-report /tmp/coachiq-decision-v1.json
```

The loader requires exactly 2014--2024 and rejects 2025 and later. Changing the
WP model, empirical transition rules, support thresholds, resampling design,
gap definition, classification rule, overtime safeguard, or interpretation
requires a new decision-value version.
