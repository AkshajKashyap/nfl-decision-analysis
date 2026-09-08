# CoachIQ 2026 shadow audit report

## Decision

**NOT READY**

As of 2026-09-08, no 2026 regular-season game had been completed. The frozen
protocol requires at least one fully completed `REG` or `POST` week for either
readiness category. The operational framework fails safely, but prospective
scoring evidence, completed-game runtime, publication volume, human review, and
drift observations do not yet exist.

This is a source-availability result, not a scientific failure and not evidence
for changing any v1 model or policy.

## Preregistration and frozen stack

`docs/2026-shadow-audit-protocol.md` was frozen before the 2026 schedule or PBP
source was opened. Its SHA-256 is
`c62f5459d6bf0e71c377b4b6c543d94ac5c07a63bf070ec09a17d7b69300acf8`.
The `READY`, `READY WITH RESTRICTIONS`, and `NOT READY` gates remain unchanged.

The run identifies exactly `coachiq-wp-v1`,
`coachiq-action-transition-v1`, `coachiq-decision-v1`, and
`coachiq-publication-v1`, with training through 2024. No feature, fitted
parameter, support threshold, clipping threshold, decision threshold,
bootstrap setting, OT rule, wording rule, or publication rule changed. No new
model or policy version was created.

## Available 2026 source

The normal nflreadpy schedule source returned 272 2026 rows, all regular
season, with zero non-null final results. The saved schedule snapshot contains
16 Week 1 games; all received `game_not_final`. The
[official NFL Week 1 schedule](https://www.nfl.com/schedules/2026/by-week/reg-1)
also places the opening games after this audit date. The schedule snapshot was
retrieved at `2026-09-08T08:30:40.236074+00:00` and has file SHA-256
`eddb03f1c3c8c1ffd5e912b850caac344e0b14029f77fd1ef2eac1304872ca56`.

No 2026 PBP snapshot was available. nflreadpy 0.1.5 rejected a season-2026 PBP
request because its current accepted PBP range ends at 2025. Because the
schedule had no final games, the final command correctly skipped PBP loading
and did not treat this as a missing completed game.

## Shadow run results

| Metric | Result |
|---|---:|
| Weeks inspected | 1 |
| Scheduled games | 16 |
| Final games / games attempted | 0 / 0 |
| Games successfully processed / failed | 0 / 0 |
| Fourth-down candidates | 0 |
| Eligible / valued decisions | 0 / 0 |
| Clear model preferences | 0 |
| Publication-safe decisions | 0 |
| Scoring failures | 0 |
| Human approved / held / pending | 0 / 0 / 0 |
| Tactical warnings | 0 |
| Source-correction events in live run | 0 |
| Deterministic-run failures | 0 |

There are no withholding reasons, publication-safe notable examples, close
calls, suspicious football cases, or editorial outcomes to report because no
decision was scored. A zero publication-safe count is not a measured zero rate;
the rate is unavailable.

## Determinism, corrections, and runtime

Two independent Week 1 command invocations from the same snapshot produced
byte-identical deterministic artifacts. The final hashes are:

| Artifact | SHA-256 |
|---|---|
| `source-manifest.json` | `d23441fb2b7836d55bd2e95242224b991af4405c64a47539b31abd89b71f6f4f` |
| `operational-summary.json` | `9addc98ce8ee91edcef1e5387890d18e436b8fabac89e0f9238a9cad8c4bd16e` |
| `shadow-brief.md` | `14d6d8f3daee5afd0781a8266f78780e0727aef987f98162600afe00a57addef` |

The manifest preserves the protocol hash, source retrieval timestamp, all 16
scheduled IDs, full-snapshot and week fingerprints, frozen versions, and null
PBP/report fingerprints. No machine-readable weekly or game report is emitted
when there is no completed week.

Focused correction tests changed one controlled fixture game fingerprint. The
comparison marked only that game changed and the other game unchanged. Output
collision tests preserve the active manifest until explicit correction
acceptance; accepted replacement retains predecessor artifacts and increments
the correction event count. No football outcome was fabricated.

The two source-readiness invocations took 0.158 and 0.170 seconds end to end.
In the first measured run, source loading took 0.026 seconds, readiness
validation took 0.061 seconds, the deterministic rerun took 0.069 seconds, and
export took 0.002 seconds. Frozen fitting took zero seconds because no
game was final. These timings do not answer the required completed-week runtime
question and are not compared with the Milestone 8 30-second baseline.

## Monitoring and operational interpretation

The historical publication-safe range remains 14.07%–19.70% by season, with a
preregistered five-percentage-point monitoring band. There is no 2026 rate,
support distribution, classification distribution, clipping distribution, OT
mass, or gap distribution to compare. Calling this drift would be invalid.

The implemented safeguards are ready for the first completed-week rerun:
explicit game readiness, all-or-nothing weekly scoring, complete frozen audit
records, publication-safe-only notable ordering, tactical warnings, a
non-overridable human checklist, source correction handling, deterministic
hashes, phase metrics, and explicit safe failures. The unobserved completed-game
path prevents public use now.

## Readiness rationale and next gate

The exact failed preregistered condition is: **at least one fully completed 2026
`REG`/`POST` week must exist and be audited**. Therefore `READY` and
`READY WITH RESTRICTIONS` are unavailable, irrespective of passing fixture
tests or the small source-readiness runtime.

The code and report are safe to commit as a truthful `NOT READY` operational
checkpoint, but Milestone 9 is not a completed live-game audit. After the first
week is final and nflverse PBP is available, rerun this same frozen command,
resolve every game and tactical warning, complete editorial review, and apply
the unchanged readiness gates.

Milestone 10 is deferred until that blocking evidence exists. Its intended
scope is the first carefully human-reviewed public-facing CoachIQ output: select
only individually approved publication-v1-safe decisions, recheck source
corrections immediately before release, publish frozen neutral wording with
provenance and limitations, and retain an approval record. It must not add
model development, threshold changes, coach grades, or rankings.
