# CoachIQ live shadow operations

Milestone 9 adds a prospective-only orchestration layer around the four frozen
v1 artifacts. It does not alter model fitting, action transitions, decision
thresholds, or publication-v1. Read the frozen
[2026 shadow protocol](2026-shadow-audit-protocol.md) before operating it.

## Weekly workflow

Use an immutable schedule snapshot and, once games are final, a matching
play-by-play snapshot. Frozen model fitting still uses only explicit 2014–2024
snapshots.

```bash
PYTHONPATH=src:. .venv/bin/python scripts/audit_live_week.py \
  --season 2026 \
  --week 1 \
  --schedule-parquet /tmp/coachiq-2026/schedules_2026.parquet \
  --pbp-parquet /tmp/coachiq-2026/play_by_play_2026.parquet \
  --training-parquet-dir /tmp/coachiq-training \
  --output-dir /tmp/coachiq-2026-week1
```

The command accepts exactly season 2026 and weeks 1–22. Historical model and
publication-development commands continue to reject 2026. When a selected week
contains no final games, the command deliberately does not request PBP or fit
the frozen components; it writes a `NOT READY` source-readiness result instead.

## Game and source readiness

Schedule rows are limited to `REG` and `POST`. A game is scored only when its
schedule scores and result are final and its PBP passes identity, team, final
margin, unique-play, terminal-state, normalization, and candidate extraction
checks. Every scheduled game is retained with one of `ready`,
`incomplete_source`, `game_not_final`, `source_missing`, or
`validation_failed`.

Raw play counts outside 100–250 and fourth-down candidate counts outside 1–30
are warnings for human investigation, not automatic exclusions. Any expected
completed game that is not `ready` prevents a complete weekly report. Scoring
is all-or-nothing at the week boundary, so a partial collection cannot look
complete.

The source manifest records retrieval time, full supplied-snapshot and selected
week fingerprints, per-game fingerprints, scheduled/final/observed game IDs,
raw and normalized counts, the frozen versions, the protocol hash, and the
weekly report fingerprint when scoring occurs.

## Output contract

Every run writes:

- `source-manifest.json`: deterministic source and version identity;
- `operational-summary.json`: readiness, game states, reconciled counts,
  warnings, editorial queue, monitoring values, and failures;
- `shadow-brief.md`: deterministic internal summary;
- `hashes.json`: SHA-256 values for every deterministic artifact;
- `run-metrics.json`: measured phase and command runtimes, intentionally
  excluded from deterministic hashes.

A fully scored week also writes `weekly-report.json` and one
`game-GAME_ID.json` per processed game. These preserve complete decision
records. Operational `notable_decisions` contain only publication-v1-safe
records, ordered by modeled actual-action gap, pairwise evidence, game ID, and
play ID. They retain the complete safety, support, clipping, OT, provenance,
and frozen-language fields. No coach or team aggregation is produced.

## Corrections and deterministic reruns

The command runs the same in-memory snapshot twice and compares the structured
reports and weekly JSON. Separate invocations with the same retrieval timestamp
must reproduce the deterministic hashes.

When an output directory already contains a manifest, per-game fingerprints
are compared before replacement. A mismatch writes
`source-manifest.candidate.json` and `correction-report.json`, preserves the
existing output, and stops. After analyst review, rerun with
`--accept-source-correction`; the command then retains the prior manifest,
hashes, and operational summary with `.previous` in their names, records one
correction event, and deterministically replaces the active artifacts.
Unchanged games remain explicitly unchanged in the correction report.

## Editorial review and tactical warnings

Every publication-safe record begins `pending_review`. Human approval requires
all eight checks from the frozen protocol: factual state, actual action,
score/clock/down/distance, tactical context, publication status, safety
diagnostics, neutral wording, and absence of a causal claim. A reviewer may
hold or reject an otherwise publishable case. Approval of a publication-v1
withheld case raises an error.

Fixed factual warnings cover unusual description terms, the last 120 seconds
of regulation, punts from the opponent 40 or closer, derived field-goal
distance above 65 yards, and specified unusual outcomes. They route a record to
review and never infer intent or alter publication-v1.

## Failure behavior and limitations

Missing final-game PBP, schema drift, identity/final-score disagreement,
normalization failure, frozen-version drift, incomplete provenance or safety
metadata, and scoring exceptions are explicit failures. Withheld records cannot
carry public language. Prefer no weekly report to an apparently complete
partial report.

The local command refits the frozen 2014–2024 estimators once per invocation;
there is no serialized production artifact yet. Phase metrics combine
validation, normalization, scoring, and publication because those operations
share the fail-safe game boundary, while source loading, frozen fitting,
deterministic rerun, export, and total command time are reported separately.
The readiness runtime excludes the deliberate second determinism run.

As of 2026-09-08, no 2026 game was final, so completed-week scoring runtime,
publication volume, drift comparisons, and human decision review remain
unobserved. See the [Milestone 9 report](2026-shadow-audit-report.md).
