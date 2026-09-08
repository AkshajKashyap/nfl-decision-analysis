# CoachIQ 2026 live shadow audit protocol

Status: **frozen before substantive 2026 play-by-play inspection**

Frozen on: 2026-09-08

Milestone 9 is a prospective operational evaluation. It does not reselect,
refit, recalibrate, or revise the scientific or publication policies. The
permitted stack is exactly:

- `coachiq-wp-v1`, trained on 2014–2024
- `coachiq-action-transition-v1`, trained on 2014–2024
- `coachiq-decision-v1`, 200 training-game bootstrap draws with seed 2505
- `coachiq-publication-v1`, including field clipping at most 10%, zero clock
  clipping, and zero OT-boundary mass

No observed 2026 output may change a feature, coefficient, cell, support
threshold, decision threshold, bootstrap setting, clipping threshold, OT rule,
language rule, or model/policy version. Unexpected results are operational
evidence to investigate, not tuning data.

## Scope and source opening rule

Only the dedicated live-shadow path may request season 2026. All model
development, holdout, historical audit, model-selection, and publication-policy
study commands must continue to reject it. The shadow path may inspect only
games the authoritative schedule marks final. It must not score live,
scheduled, postponed, cancelled, or source-incomplete games.

The normal play-by-play source is nflverse through nflreadpy. Completed-game
expectations should be compared with an official NFL schedule where practical.
The retrieval time, source asset, whole-source fingerprint, game fingerprints,
row counts, and report fingerprints must be retained.

If no complete 2026 regular-season or postseason week is available, the
Milestone 9 readiness result is `NOT READY` because prospective operational
evidence is absent. Pipeline fixtures may still be tested, but cannot substitute
for completed live games.

## Game readiness

Every expected game receives exactly one status:

| Status | Definition |
|---|---|
| `ready` | Schedule says final, teams/week match, PBP exists, final-score and terminal-play checks pass, normalization succeeds, and identity/order checks pass. |
| `incomplete_source` | PBP exists but terminal state, final score, teams, row coverage, or required fields are incomplete/inconsistent. |
| `game_not_final` | Schedule does not mark the game final. |
| `source_missing` | A schedule-final game has no matching PBP rows. |
| `validation_failed` | Schema, normalization, duplicate/order, or identity validation fails. |

Hard checks for `ready` are one season/week/game ID, schedule/PBP team match,
non-null final scores, schedule/PBP final-score agreement, at least one row,
unique play IDs, monotonically sortable play sequence, a terminal/end-game
source row or an equivalent final-state marker, and successful normalized-schema
validation. Games outside `REG` and `POST` are not scored.

For plausibility, raw rows outside 100–250 or fourth-down candidates outside
1–30 generate a manual-review warning. These broad ranges do not silently
exclude a final game; an analyst must resolve whether the game is unusual or
incomplete. Eligible count must never exceed candidate count.

One non-`ready` expected completed game prevents a complete weekly report and
therefore prevents `READY`.

## Fixed operational checks

For each ready game and complete week, verify:

1. Frozen artifact and publication-policy versions match exactly.
2. Every expected final game is present once and only once.
3. Candidate, eligible, valued, clear-preference, publication-safe, and
   withholding counts reconcile.
4. Scoring finishes without silently dropped decisions.
5. Every publication-safe notable record is publication-v1 `publishable` and
   contains complete safety metadata, provenance, and neutral wording.
6. Withheld decisions have no public sentence.
7. Same-snapshot reruns are byte-identical.
8. Source and generated-report fingerprints are present and verifiable.
9. Source correction detection identifies only affected games as stale.
10. End-to-end weekly runtime is at most 60 seconds for `READY`. A 60–120
    second runtime is a restriction; above 120 seconds is `NOT READY` unless a
    documented environmental cause is resolved and the fixed rerun passes.
11. Apparent state/action contradictions and tactical warnings receive human
    review before any external use.

The 60-second target is approximately twice the slower 31.08-second Milestone
8 historical weekly run. No scientific setting may be weakened to meet it.

## Safe failure rules

- Missing or nonfinal games: do not create a complete weekly publication set.
- Schema or normalized-contract mismatch: fail the affected game explicitly.
- Frozen model or publication version mismatch: fail the run.
- Missing source or model provenance: fail the run.
- Missing publication safety metadata: withhold the decision and fail its game
  readiness review.
- Unknown/unhandled action: withhold and record an explicit scoring failure.
- Decision scoring exception: mark the decision and game failed; never silently
  omit it.
- Output-path collision with a different source fingerprint: preserve the old
  manifest, mark stale, and require an explicit corrected rerun.

No output is preferable to a potentially incorrect complete report.

## Source correction protocol

Each run writes JSON manifests containing season/week, expected and observed
game IDs, source retrieval time, raw and normalized counts, full-source SHA-256,
per-game fingerprints, frozen versions, publication version, and report hashes.

On rerun, compare game fingerprints. A changed game is `stale_source`; a
removed expected game is `source_missing`; unchanged games remain current. A
corrected report is written separately, its predecessor hash is retained, and
the correction event lists affected IDs. Replacement must be explicit. If no
natural correction occurs, a controlled metadata/fixture mutation must prove
this behavior without fabricating a football result.

## Tactical-context warnings

Warnings route records to review and never infer intent. The fixed rules are:

- description terms: `fake`, `direct snap`, `pooch`, `quick kick`,
  `field goal formation`, `intentional safety`, `takes a safety`, `deliberate`,
  or `runs out of the back`;
- any fourth down in the final 120 seconds of regulation;
- a punt from the opponent 40 or closer;
- a field-goal attempt whose derived kick distance exceeds 65 yards;
- factual outcomes involving a blocked punt, blocked field goal, safety, or
  return touchdown.

A warning does not change publication-v1. It makes human approval necessary
and may lead a reviewer to withhold a case.

## Human editorial review

Publication eligibility is necessary, never sufficient. Every potentially
external decision starts as `pending_review`. A human reviewer verifies the
factual state, actual action, score/clock/down/distance, description/context,
publication-v1 status, support/clipping/OT diagnostics, provenance, and neutral
non-causal wording.

Allowed review statuses are:

- `pending_review`
- `approved`
- `hold_for_context`
- `reject_data_issue`
- `reject_model_form_risk`

Only a human may assign `approved`. A human may withhold any publishable case.
No review action may override a publication-v1 withholding or create public
wording for it.

## Prospective monitoring, not tuning

Each week reports games attempted/succeeded/failed, decisions attempted,
scoring failures, publication-safe decisions, human approvals/holds, tactical
warnings, source-correction events, deterministic-run failures, and phase
runtime.

Descriptive 2026 support, decision classification, clipping, OT mass, and gap
distributions may be compared with historical results. The historical
publication-safe rate was 14.07%–19.70% by season. A 2026 value more than five
percentage points outside that range is a monitoring flag only. Small samples
and ordinary variation must not be labeled drift. No monitoring result changes
the frozen stack.

No output may aggregate gaps by coach or team. There will be no cumulative
gap, average coach gap, coach/team leaderboard, grade, “mistake,” “bad call,”
or “failure” label. `notable_decisions` is a deterministic internal ordering of
publication-safe individual decisions by descending actual-action modeled gap,
then pairwise evidence, game ID, and play ID.

## Preregistered readiness decision

Assign exactly one status after the shadow run.

### `READY`

Requires at least one fully completed 2026 `REG`/`POST` week; all expected final
games `ready`; zero validation/scoring/version/provenance failures; reconciled
counts; byte-identical reruns; passing correction detection; runtime at most 60
seconds; no unresolved suspicious case; and completed human review of every
candidate selected for possible external publication.

### `READY WITH RESTRICTIONS`

Requires at least one fully completed week, deterministic correct output, no
frozen-stack or safety breach, and no unresolved data/scoring failure, but one
or more nonblocking restrictions remain: 60–120 second runtime, source-final
status requiring documented manual confirmation, tactical/context review still
pending, or not all otherwise-publishable cases human-approved. Restrictions
must be explicit and external use remains limited to individually approved
records.

### `NOT READY`

Required when no complete 2026 week exists; an expected completed game is
missing/incomplete/failed; source identity cannot be established; frozen
versions differ; counts do not reconcile; a scoring error is silently dropped;
same-source output differs; correction tracking fails; a withheld decision can
be promoted; a substantive correctness issue remains unresolved; or runtime
exceeds 120 seconds without a resolved environmental explanation and passing
rerun.

Football intuition, low publication volume, team concentration, an awkward
example, or a withheld high-gap play are never by themselves readiness failures
and never authorize tuning.
