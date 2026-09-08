# CoachIQ game audit pipeline

Milestone 8 introduces an internal product-facing pipeline around the frozen
v1 research stack. It reconstructs completed-game fourth downs, values them,
attaches safety diagnostics and provenance, applies
`coachiq-publication-v1`, and emits deterministic JSON. It does not grade or
rank coaches.

## Pipeline

The core entry points are:

```python
fit_frozen_models(historical_pbp, project_root=project_root) -> FrozenModels
audit_game(game_pbp, trained_models, publication_policy, source=source) -> GameAudit
audit_week(week_pbp, trained_models, publication_policy, source=source) -> WeeklyAudit
```

`fit_frozen_models` requires exactly 2014–2024. It verifies the already-frozen
holdout source hashes, fits `coachiq-wp-v1` and
`coachiq-action-transition-v1` once, and builds the frozen 200-replicate,
seed-2505 decision bootstrap context once. Every game in the run reuses these
objects. It never fits on 2025 outcomes.

The current minimal artifact approach is a deterministic in-memory fit plus a
versioned manifest, rather than a Python pickle. The manifest records training
seasons, through-season, normalized-source fingerprint, state-row and
transition counts, training-game count, fitted WP parameters, source hashes,
model versions, bootstrap settings, and frozen protocol identity. This avoids
a brittle executable artifact while keeping fitting to about four seconds in
the measured weekly run. A future serialized artifact must have a stable,
language-independent format and reproduce this manifest before replacing the
current approach.

## Canonical decision record

Each eligible decision contains these top-level objects:

- `identity`: season, week, game/play IDs, teams, and possession team.
- `situation`: quarter, clocks, score differential, field position, yards to
  go, and timeouts.
- `actual_decision`: observed action, factual outcome, and source description.
- `modeled_actions`: all actions with EWP, 90% interval, bootstrap metadata,
  support counts/status, OT mass, and scientific versions. Unsupported actions
  remain present with null estimates.
- `comparison`: preferred supported action, claimed comparison, actual-action
  gap, minimum gap and pairwise superiority, full paired comparisons, and the
  unchanged decision-v1 classification/reason.
- `safety_diagnostics`: field and clock clipping by action and maxima, OT mass,
  sparse support, unsupported alternatives, and actual-action support.
- `publication`: status, boolean eligibility, all reason codes, internal
  explanation, and policy version.
- `provenance`: scientific/policy versions, 2014–2024 training window,
  bootstrap settings, retrieval timestamp, source scope, row count, filename,
  and SHA-256.
- `public_language`: deterministic neutral wording only for publishable rows.
- `internal_language`: deterministic withholding explanation for internal use.

An unsupported actual action has no claimed comparison and cannot generate
public wording. Technical metadata is retained even when it is inconvenient
for presentation.

## Game and weekly reports

A `GameAudit` reports total fourth-down candidates, eligible decisions, valued
decisions, publishable/withheld totals, primary statuses, all reason counts,
the canonical records, and provenance.

A `WeeklyAudit` combines game reports and adds the number of games, clear model
preferences, publication-eligible count, `notable_decisions` sorted by modeled
actual-action gap, and `strongest_pairwise_evidence`. Both lists contain only
publication-safe decisions. They are content-discovery lists, not causal
rankings. There is no coach field in an aggregation key and no season
leaderboard.

## Historical dry-run

The 2020–2025 chronological study evaluated 23,664 eligible decisions. At the
selected policy, 4,266 (18.03%) were publication eligible. Representative
2024–2025 behavior includes:

- Publication safe: 2025 Week 6, Denver at the New York Jets, play 3352. On
  fourth-and-1 from the Jets' 30, v1 favored going over the observed punt by
  9.8 percentage points; maximum field clipping was 0.15%, clock clipping was
  zero, support was nonsparse, and pairwise superiority was 1.0.
- Clipping withheld despite a clear preference: 2025 wild-card San Francisco
  at Philadelphia, play 4063. The modeled actual-action gap was 12.2 points,
  but maximum field clipping was 92.9% and clock clipping was positive. No
  public wording was emitted.
- Close call withheld: 2025 Week 18 Cleveland at Cincinnati, play 3043.
  Decision-v1's minimum gap was only 0.06 points and minimum superiority 0.56.
- Sparse support withheld: 2024 Week 5 Miami at New England, play 4291.
- OT risk withheld: 2024 Week 9 Tampa Bay at Kansas City, play 4214; tied-
  expiration mass was 67.5%.
- Unsupported comparison withheld: 2024 Week 1 Las Vegas at the Los Angeles
  Chargers, play 3319.

These are model audits, not statements about known counterfactual outcomes.

## Reproducible command

With explicit nflverse snapshots named `play_by_play_YEAR.parquet`:

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_games.py \
  --season 2025 \
  --week 10 \
  --parquet-dir /tmp/coachiq-m8 \
  --json-output /tmp/coachiq-week10.json
```

The source retrieval timestamp defaults to the target snapshot's file mtime
and can be supplied explicitly. This makes the JSON stable for the same source
snapshot. In validation, two Week 10 runs were byte-identical with SHA-256
`dbac64ef6f232a11f2a6c1a46acc798ab2466fae7e9da59c405271f34c6b68ed`.

The 2025 Week 10 report covered 14 games, 223 fourth-down candidates, 203
eligible decisions, 200 valued decisions, 72 clear model preferences, and 48
publication-eligible decisions. Primary withholding totals were 78 support,
52 close call, 24 clipping, and one OT-scope decision.

## Runtime

On the Milestone 8 development environment, the two final full Week 10 runs
took 29.60 and 31.08 seconds:

| Phase | Run 1 | Run 2 |
|---|---:|---:|
| Load and normalize 2014–2025 explicit snapshots | 7.23 s | 8.09 s |
| Fit frozen 2014–2024 components once | 3.83 s | 3.87 s |
| Audit 14 games with 200 bootstrap draws | 18.54 s | 19.13 s |

The complete six-fold policy study took 786.37 seconds. The operational weekly
path is practical after games complete without distributed infrastructure or a
weaker uncertainty specification.

## Freshness and correction handling

Every output stores the target source filename, retrieval timestamp, row
count, season/week, and full-file SHA-256. The model manifest stores a
deterministic fingerprint of normalized training data. A later run can compare
these values before replacing a report. A changed source fingerprint requires
regeneration; it does not silently merge corrected and stale decisions.

## 2026 boundary

The Milestone 8 CLI and library guard reject seasons after 2025. No 2026 data
were used to select the policy or inspect notable decisions. Milestone 9 may
deliberately introduce a separate live-season orchestration path only after
this policy is committed and frozen; it must continue to use the frozen v1
scientific stack and publication-v1 without threshold tuning.
