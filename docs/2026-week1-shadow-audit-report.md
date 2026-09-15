# CoachIQ 2026 Week 1 prospective shadow audit

Audit snapshot: `2026-09-15T05:52:14.904008+00:00`

## Decision

**READY WITH RESTRICTIONS**

This is the first completed-week prospective run of the frozen Milestone 9
system. All 16 expected Week 1 games were official finals, were present in the
same nflverse play-by-play snapshot, passed the frozen readiness checks, and
were processed without a validation or scoring failure. Two full command runs
produced byte-identical deterministic artifacts. The single-run readiness
runtime was below 60 seconds.

The only readiness restriction is the preregistered human-review gate. All 43
publication-v1-safe records passed an automated factual and policy precheck,
but the frozen protocol permits only a human to assign `approved`. They
therefore remain `pending_review`; none is currently authorized for external
use. External use is limited to records individually approved by a human after
a fresh source-correction check.

No result in this report changed a model, feature, threshold, transition cell,
bootstrap setting, overtime rule, publication rule, or readiness criterion.
Week 1 was not used for fitting, recalibration, model selection, or tuning.

## Preserved September 8 checkpoint

The historical `docs/2026-shadow-audit-report.md` `NOT READY` checkpoint was
not edited or overwritten. The preregistered protocol also remains unchanged
at SHA-256
`c62f5459d6bf0e71c377b4b6c543d94ac5c07a63bf070ec09a17d7b69300acf8`.
Its September 8 evidence remains:

| Historical artifact | SHA-256 |
|---|---|
| September 8 schedule snapshot | `eddb03f1c3c8c1ffd5e912b850caac344e0b14029f77fd1ef2eac1304872ca56` |
| `source-manifest.json` | `d23441fb2b7836d55bd2e95242224b991af4405c64a47539b31abd89b71f6f4f` |
| `operational-summary.json` | `9addc98ce8ee91edcef1e5387890d18e436b8fabac89e0f9238a9cad8c4bd16e` |
| `shadow-brief.md` | `14d6d8f3daee5afd0781a8266f78780e0727aef987f98162600afe00a57addef` |

The current run started from commit
`ed730a68eb5833a83223aad438d195e1983784b0`. The frozen versions are exactly
`coachiq-wp-v1`, `coachiq-action-transition-v1`, `coachiq-decision-v1`, and
`coachiq-publication-v1`; decision-v1 used 200 whole-training-game bootstrap
draws with seed 2505.

## Week completeness and source loading

The [official NFL Week 1 schedule](https://www.nfl.com/schedules/2026/by-week/week-1)
listed all 16 games as `FINAL` with the scores below. The independently loaded
nflverse schedule contained the same 16 IDs and scores, and the PBP snapshot
contained exactly the same 16 IDs. Completeness was established from the
official schedule before PBP scoring, not inferred from PBP availability.

| Game ID | Final score | Status |
|---|---|---|
| `2026_01_ARI_LAC` | ARI 26–14 LAC | final |
| `2026_01_ATL_PIT` | ATL 13–20 PIT | final |
| `2026_01_BAL_IND` | BAL 41–23 IND | final |
| `2026_01_BUF_HOU` | BUF 36–31 HOU | final |
| `2026_01_CHI_CAR` | CHI 59–37 CAR | final |
| `2026_01_CLE_JAX` | CLE 10–34 JAX | final |
| `2026_01_DAL_NYG` | DAL 20–28 NYG | final |
| `2026_01_DEN_KC` | DEN 10–31 KC | final |
| `2026_01_GB_MIN` | GB 22–39 MIN | final |
| `2026_01_MIA_LV` | MIA 13–27 LV | final |
| `2026_01_NE_SEA` | NE 10–13 SEA | final |
| `2026_01_NO_DET` | NO 30–31 DET | final |
| `2026_01_NYJ_TEN` | NYJ 23–10 TEN | final |
| `2026_01_SF_LA` | SF 27–7 LA | final |
| `2026_01_TB_CIN` | TB 27–33 CIN | final |
| `2026_01_WAS_PHI` | WAS 22–24 PHI | final |

The existing official loader path was retried unchanged. Installed
`nflreadpy 0.1.5` now reports 2026 as the current supported season, so both
`load_schedules([2026])` and `load_pbp([2026])` succeeded. No dependency
upgrade, validation bypass, package patch, or CoachIQ code change was needed.

The downloaded schedule had 272 rows and 46 columns. The 2026 PBP asset had
2,756 rows and 372 columns, all in Week 1 at this snapshot. Every game had a
terminal marker, unique play IDs, schedule/PBP team identity and score
agreement, 148–218 raw rows, and 5–20 fourth-down candidates. All counts were
inside the preregistered plausibility ranges.

## Frozen Week 1 scoring

| Metric | Result |
|---|---:|
| Games expected / available | 16 / 16 |
| Games processed / failed | 16 / 0 |
| Raw PBP rows | 2,756 |
| Normalized rows | 2,756 |
| Fourth-down candidates | 227 |
| Eligible decisions | 203 |
| Valued decisions | 200 |
| Clear model preferences | 62 |
| Publication-safe decisions | 43 |
| Publication-safe rate | 21.18% |
| Scoring failures | 0 |

Counts reconcile: 43 publication-safe plus 160 withheld equals 203 eligible;
the 62 clear preferences comprise 43 publication-safe and 19 withheld for
clipping. The three unvalued records were explicitly classified as
`insufficient_support`; no scoring record was silently dropped.

### Withholding distribution

Primary statuses are mutually exclusive:

| Primary status | Count | Eligible rate |
|---|---:|---:|
| `withhold_support` | 77 | 37.93% |
| `withhold_close_call` | 63 | 31.03% |
| `withhold_clipping` | 19 | 9.36% |
| `withhold_overtime_scope` | 1 | 0.49% |
| `withhold_uncertainty` | 0 | 0.00% |
| `withhold_model_form_risk` | 0 | 0.00% |

Overlapping reason counts were 78 not-clear, 67 field-clipping-above-policy,
36 known-heavy-field-clipping, 60 unavailable action, 20 sparse supported
action, one positive clock clipping, and one positive OT-boundary mass. There
were no actual-action-unsupported or incomplete-pairwise-evidence reasons.

## Historical-range comparison

The reference was regenerated from explicit 2014–2025 snapshots by the frozen
chronological publication study. Each evaluation season used only prior
seasons; 2026 was not accessed by that study. Its 23,664 decisions and 4,266
publication-safe records reproduce the committed pooled results. Reference
JSON SHA-256:
`ccf4e2e8a4bcb9928355410184a7f001bdb2eda3c91c14c2ce7823007d07169e`.

| Measure | Week 1 | Historical 2020–2025 range | Interpretation |
|---|---:|---:|---|
| Eligible decisions/game | 12.69 | 13.28–14.69 | 0.59 below the range; ordinary one-week volume |
| Clear-preference rate | 30.54% | 23.11%–30.70% | inside |
| Publication-safe rate | 21.18% | 14.07%–19.70% | 1.48 points above; below the five-point flag |
| Support-withholding rate | 37.93% | 38.35%–43.93% | 0.42 points below |
| Close-call withholding rate | 31.03% | 29.21%–32.82% | inside |
| Clipping-withholding rate | 9.36% | 9.04%–11.04% | inside |
| OT withholding rate | 0.49% | 0.50%–0.73% | rounding-level 0.01-point low |

No value is strong evidence of drift. The prospective sample is only 16 games
and 203 eligible decisions.

### Gap and clipping distributions

For the 200 available actual-action gaps, Week 1 median/P75/P90/P95/maximum
were 0.00% / 0.74% / 2.30% / 2.76% / 11.50%. Historical 2020–2025 references
were median 0.00%, P75 0.33%–0.73%, P90 1.81%–2.41%, P95 2.86%–3.84%, and
maximum 9.49%–12.22%. The small P75 and P95 crossings are descriptive sampling
variation; P90 and the maximum are inside their historical ranges.

Across all 203 decisions, maximum supported-action field clipping was nonzero
for 96.06%, above 10% for 33.00%, above 25% for 17.73%, and above 50% for
11.82%. The latter three are all inside the 2020–2025 envelopes of
30.04%–33.60%, 16.95%–18.73%, and 11.58%–12.99%. Median/P75/P90/P95/maximum
field mass were 3.31% / 17.77% / 57.35% / 81.28% / 91.12%.

Only one decision had positive clock clipping: Week 1 rates at any, above 10%,
above 25%, and above 50% were 0.49% / 0.49% / 0.49% / 0.00%, compared with
the 2025 reference of 2.72% / 1.66% / 0.88% / 0.35%. That same decision was
the only positive-OT case and was withheld.

Among the 43 publication-safe records, field clipping median/P90/maximum were
1.69% / 5.43% / 9.74%; the historical publication-safe ranges were
0.30%–0.92% / 5.60%–8.18% / 8.92%–9.79%. The higher median is not a policy
breach: every record remains below the frozen inclusive 10% ceiling, and the
one-week sample is small. Publication-safe actual-action gap median/P90/max
were 0.00% / 2.50% / 8.67%, versus historical ranges of 0.00% /
2.76%–4.26% / 7.63%–11.31%.

## Tactical-context warnings

The frozen warning mechanism flagged eight decisions. None was
publication-safe, so zero publication-safe records received an editorial
context warning and no otherwise-eligible case currently requires a contextual
human hold.

| Game/play | Warning | Publication-v1 status |
|---|---|---|
| `2026_01_ARI_LAC` 3223 | blocked-punt factual outcome | `withhold_support` |
| `2026_01_ARI_LAC` 4095 | final 120 seconds of regulation | `withhold_close_call` |
| `2026_01_ATL_PIT` 2194 | description says field-goal formation | `withhold_support` |
| `2026_01_GB_MIN` 4286 | final 120 seconds of regulation | `withhold_support` |
| `2026_01_NE_SEA` 3810 | final 120 seconds of regulation | `withhold_support` |
| `2026_01_NO_DET` 4427 | final 120 seconds of regulation | `withhold_close_call` |
| `2026_01_NO_DET` 4687 | final 120 seconds of regulation | `withhold_overtime_scope` |
| `2026_01_SF_LA` 3780 | final 120 seconds of regulation | `withhold_close_call` |

The mechanism inferred no hidden coaching intent.

## Editorial precheck and human-review queue

All 43 publication-safe records were cross-checked against the raw PBP row for
unique game/play identity, teams and possession, actual action, exact source
description, score differential, quarter and clocks, down/distance and field
position. Their publication status, support, clipping, OT mass, provenance,
neutral wording, and absence of causal/prohibited wording were also checked.
There were zero automated precheck failures.

This is not represented as human approval. Under the frozen protocol only a
human may assign `approved`, and no human reviewer supplied an approval record
during this run. Editorial outcomes therefore remain:

| Status | Count |
|---|---:|
| `approved` | 0 |
| `pending_review` | 43 |
| `hold_for_context` | 0 |
| `reject_data_issue` | 0 |
| `reject_model_form_risk` | 0 |

Human review may reduce the 43-record set. It may never promote any of the 160
publication-v1-withheld decisions.

## Internal notable decisions

These are the frozen deterministic top ten, ordered by descending
actual-action modeled gap, then pairwise evidence, game ID, and play ID. They
are internal model-disagreement examples, not grades or claims about known
counterfactual outcomes. `G/F/P` is go/field-goal/punt support; `--` is
unavailable. Every record has zero clock clipping, zero OT mass, no tactical
warning, and editorial status `pending_review`.

1. `2026_01_ARI_LAC` play 3127 — Q4 14:04, ARI +2, fourth-and-1 at its 40.
   Actual punt; CoachIQ favored go. EWPs G/F/P: 57.16%/--/48.48%; gap 8.67%;
   favored-over-actual probability 1.000, 90% difference interval
   7.91%–9.48%; support 664/--/17,007; maximum field clipping 3.55%.
   Source: “(14:04) 12-B.Gillikin punts 60 yards to end zone, Center-59-C.Kreiter,
   Touchback.” Neutral sentence: “On 4th-and-1 from their own 40, CoachIQ
   favored going for it. The model estimated going for it at 57.2% win
   probability and punting at 48.5%, a modeled advantage of 8.7 percentage
   points. The comparison met CoachIQ v1's frozen evidence threshold and
   publication-v1 safety checks.”

2. `2026_01_DEN_KC` play 1624 — Q2 4:50, tied, fourth-and-1 at DEN 32.
   Actual punt; favored go. EWPs: 45.49%/--/41.28%; gap 4.21%; probability
   1.000, 90% interval 3.66%–4.80%; support 664/--/17,007; field clipping
   0.35%. Neutral sentence: “On 4th-and-1 from their own 32, CoachIQ favored
   going for it. The model estimated going for it at 45.5% win probability and
   punting at 41.3%, a modeled advantage of 4.2 percentage points. The
   comparison met CoachIQ v1's frozen evidence threshold and publication-v1
   safety checks.”

3. `2026_01_BUF_HOU` play 3940 — Q4 3:24, HOU +1, fourth-and-9 at HOU 37.
   Actual punt; favored go. EWPs: 51.82%/--/48.94%; gap 2.88%; probability
   1.000, 90% interval 1.70%–4.26%; support 369/--/17,007; field clipping
   1.69%. Neutral sentence: “On 4th-and-9 from their own 37, CoachIQ favored
   going for it. The model estimated going for it at 51.8% win probability and
   punting at 48.9%, a modeled advantage of 2.9 percentage points. The
   comparison met CoachIQ v1's frozen evidence threshold and publication-v1
   safety checks.”

4. `2026_01_BUF_HOU` play 1808 — Q2 2:22, HOU -3, fourth-and-2 at HOU 39.
   Actual punt; favored go. EWPs: 34.17%/--/31.44%; gap 2.73%; probability
   1.000, 90% interval 1.64%–3.89%; support 187/--/17,007; field clipping
   2.92%. Neutral sentence: “On 4th-and-2 from their own 39, CoachIQ favored
   going for it. The model estimated going for it at 34.2% win probability and
   punting at 31.4%, a modeled advantage of 2.7 percentage points. The
   comparison met CoachIQ v1's frozen evidence threshold and publication-v1
   safety checks.”

5. `2026_01_ATL_PIT` play 3430 — Q3 0:13, PIT +3, fourth-and-3 at PIT 39.
   Actual punt; favored go. EWPs: 68.44%/--/65.93%; gap 2.51%; probability
   1.000, 90% interval 1.57%–3.56%; support 341/--/17,007; field clipping
   2.92%. Neutral sentence: “On 4th-and-3 from their own 39, CoachIQ favored
   going for it. The model estimated going for it at 68.4% win probability and
   punting at 65.9%, a modeled advantage of 2.5 percentage points. The
   comparison met CoachIQ v1's frozen evidence threshold and publication-v1
   safety checks.”

6. `2026_01_ARI_LAC` play 2154 — Q3 12:14, LAC -6, fourth-and-5 at LAC 42.
   Actual punt; favored go. EWPs: 42.56%/--/40.10%; gap 2.46%; probability
   1.000, 90% interval 1.52%–3.52%; support 341/--/17,007; field clipping
   5.43%. Neutral sentence: “On 4th-and-5 from their own 42, CoachIQ favored
   going for it. The model estimated going for it at 42.6% win probability and
   punting at 40.1%, a modeled advantage of 2.5 percentage points. The
   comparison met CoachIQ v1's frozen evidence threshold and publication-v1
   safety checks.”

7. `2026_01_CHI_CAR` play 2634 — Q3 13:08, CAR -7, fourth-and-5 at CAR 39.
   Actual punt; favored go. EWPs: 19.94%/--/17.75%; gap 2.19%; probability
   1.000, 90% interval 1.60%–2.86%; support 341/--/17,007; field clipping
   2.92%. Neutral sentence: “On 4th-and-5 from their own 39, CoachIQ favored
   going for it. The model estimated going for it at 19.9% win probability and
   punting at 17.7%, a modeled advantage of 2.2 percentage points. The
   comparison met CoachIQ v1's frozen evidence threshold and publication-v1
   safety checks.”

8. `2026_01_DEN_KC` play 2053 — Q2 0:58, DEN -7, fourth-and-5 at DEN 39.
   Actual punt; favored go. EWPs: 22.27%/--/20.31%; gap 1.95%; probability
   1.000, 90% interval 1.33%–2.66%; support 341/--/17,007; field clipping
   2.92%. Neutral sentence: “On 4th-and-5 from their own 39, CoachIQ favored
   going for it. The model estimated going for it at 22.3% win probability and
   punting at 20.3%, a modeled advantage of 2.0 percentage points. The
   comparison met CoachIQ v1's frozen evidence threshold and publication-v1
   safety checks.”

9. `2026_01_NYJ_TEN` play 2539 — Q3 8:51, TEN -14, fourth-and-3 at TEN 39.
   Actual punt; favored go. EWPs: 9.60%/--/8.05%; gap 1.55%; probability
   1.000, 90% interval 1.23%–1.94%; support 341/--/17,007; field clipping
   2.92%. Neutral sentence: “On 4th-and-3 from their own 39, CoachIQ favored
   going for it. The model estimated going for it at 9.6% win probability and
   punting at 8.0%, a modeled advantage of 1.6 percentage points. The
   comparison met CoachIQ v1's frozen evidence threshold and publication-v1
   safety checks.”

10. `2026_01_BAL_IND` play 2194 — Q2 0:59, IND -15, fourth-and-1 at IND 27.
    Actual punt; favored go. EWPs: 7.52%/--/6.03%; gap 1.49%; probability
    1.000, 90% interval 1.34%–1.65%; support 664/--/17,007; field clipping
    0.13%. Neutral sentence: “On 4th-and-1 from their own 27, CoachIQ favored
    going for it. The model estimated going for it at 7.5% win probability and
    punting at 6.0%, a modeled advantage of 1.5 percentage points. The
    comparison met CoachIQ v1's frozen evidence threshold and publication-v1
    safety checks.”

## Internal close-call examples

Publication-v1 emitted no public wording for these records. `G/F/P` gives the
available action EWPs.

| Game/play | Situation | Actual / favored | G/F/P EWP | Minimum gap | Pairwise probability | Status |
|---|---|---|---|---:|---:|---|
| `2026_01_WAS_PHI` 2064 | Q2 0:45, WAS +5, 4th-2 at WAS 47 | punt / go | 77.93%/--/76.96% | 0.97% | 0.945 | `withhold_close_call` |
| `2026_01_GB_MIN` 2440 | Q3 12:09, MIN +9, 4th-10 at MIN 38 | punt / punt | 76.47%/--/77.37% | 0.90% | 0.975 | `withhold_close_call` |
| `2026_01_NYJ_TEN` 1674 | Q2 2:44, NYJ +7, 4th-8 at TEN 36 | field goal / field goal | 72.91%/73.81%/72.92% | 0.90% | 0.995 | `withhold_close_call` |
| `2026_01_CHI_CAR` 2727 | Q3 11:39, CHI +7, 4th-9 at CHI 21 | punt / punt | 75.15%/--/76.04% | 0.88% | 0.955 | `withhold_close_call` |
| `2026_01_NYJ_TEN` 3135 | Q4 14:16, NYJ +17, 4th-1 at NYJ 29 | punt / go | 96.94%/--/96.10% | 0.84% | 1.000 | `withhold_close_call` |

These demonstrate the intended abstention: even strong pairwise bootstrap
evidence does not override the frozen one-percentage-point minimum gap.

## Suspicious-case review

- The largest publication-safe disagreement, ARI–LAC play 3127 at 8.67
  points, is classified as a valid model disagreement. Its source state and
  action are correct, pairwise evidence is complete, support is nonsparse,
  field clipping is 3.55%, clock and OT mass are zero, and its size is below
  prior observed maxima.
- Sixty-seven records had field clipping above the publication ceiling and 36
  entered the known heavy-clipping regime. This is the already disclosed
  coarse punt-transport model-form limitation. The frozen policy withheld
  them; it is not a newly discovered implementation defect.
- `2026_01_NO_DET` play 4687, tied with 37 seconds remaining on fourth-and-1,
  had an 11.50-point modeled actual-action gap, 29.67% maximum clock clipping,
  and 33.58% OT-boundary mass. It was correctly classified limited-support,
  warned for extreme late regulation, and withheld for OT scope. This is a
  tactical-context and scope case, not a publishable result.
- The blocked-punt and field-goal-formation records were warned and withheld.
  No source-data issue or silent action contradiction was found.

Final classification: zero implementation-correctness concerns, zero source
data issues, no unresolved model-form risk among publication-safe records,
eight tactical-context warnings, and one notable valid model disagreement.

## Determinism and provenance

Two independent full command invocations used the same schedule, PBP,
training files, and retrieval timestamp. A recursive byte comparison of all
deterministic artifacts found no difference. `run-metrics.json` is deliberately
excluded because wall-clock measurements are nondeterministic.

| Deterministic artifact | SHA-256 |
|---|---|
| `source-manifest.json` | `abce0cc66854623ebca6ce63c0515a305b10d22b1503d7ef8d28013017aa6d97` |
| `operational-summary.json` | `5536bdcf5043b3304bf3731856ee7ffe675652dc327daaec5cc37b9c18daa98d` |
| `weekly-report.json` | `896750ae164b68e3dc407300693cf94758030d68c7fd2977af10b57daf98db9c` |
| `shadow-brief.md` | `fff50246441dba4ee52bad95d39ac06c7c89e63956d3723c8f6d333f738d530f` |
| `hashes.json` | `0e83e6cd6efd9ca4eb9b6a6a2bc4b32535b341907b99cbd15b09fef13c3270e5` |

The schedule file SHA-256 is
`1a661c148d5cd2db3d7abe139af84ac2b910773edcdef46ac02a9b2a8ea577f0`;
its full-frame and Week 1 fingerprints are
`cfabd5929d6f672d889b57554c9162319dd231e22bd2dcca1256b565772cc7c7`
and `1bd667130b2a7bc4336013f5366dfff0bbbbd10eb10d2a39a216133e411b4e4c`.
The PBP file SHA-256 is
`ec4a0376ab2f869c826a400ddfeea1f0d7dcebb76cde85f9227fb3159f86396b`;
its full-frame and sorted Week 1 fingerprints are
`5f09608c40b453954254550fb0886e00a172aa02550c62749e7463b43fb24ad1`
and `ec237c65577b1cb882ff3611145aa6f248651d18e2e9028d687433840925bace`.

The frozen normalized 2014–2024 training fingerprint is
`5912982bb7071c2859de6ced61e6b10376b4d14beee7f8d670da78f3c4101559`.
It contains 531,234 normalized rows, 416,618 WP state rows, and 42,361 action
transitions from 3,010 games. Raw training snapshot SHA-256 values were:

| Season | SHA-256 |
|---:|---|
| 2014 | `c6910558e235dac664b1b7f02654d47ea8d51904ef9ace5d4f015165604e0b12` |
| 2015 | `b3314a52b781a00417528b2e3388d2596098cdbe7b565d3c962d7171a98ae70f` |
| 2016 | `75fde790db65a5e5765930e5780c1452e96a6a58d4d802c79f10f5842a387bbc` |
| 2017 | `0166785545b15de785075a154668996b8cb71294f7a7c3d9acbf4ae90a99f2dc` |
| 2018 | `152e44436368be4c253d14c0cb0f8335a53f3790ce5ebdbb7648551371d62d2b` |
| 2019 | `3878b8c99f5f3d977203b0e249b55ca913e59db3971420075ed35a0991610f6e` |
| 2020 | `d86d1e3f98b64bd839c8533a3867cb0f0e3d6216cd11bddd11efd5bc6c594a04` |
| 2021 | `d2fbf41c83c843e1c6db4ec117ef9b4b49b7730666f21005fc9951dce09d0e0a` |
| 2022 | `311971fb4404dc8759a9f77c50ef2f4933fbd2d24deb5a747987058d0b6788a8` |
| 2023 | `19fc2ce8abb85be47fad16ceff178c67d6581309e87d53bb70c4531373867b1e` |
| 2024 | `e332d33a0c83a33073cde85f8e8f1ac0caebcc552eda7e7c92612ff306bafa73` |

Per-game PBP fingerprints and deterministic game-report hashes are:

| Game ID | PBP fingerprint | Game report SHA-256 |
|---|---|---|
| `2026_01_ARI_LAC` | `edbe670be5bf6cbac90d839525b0b4cb345fd319564ffbbbe46b59f391bcee36` | `ddcee927bf222e34eae5855f70b3ee005f99d0ced8c6f3f95e1f7e4bf9d9eca3` |
| `2026_01_ATL_PIT` | `c6ee93b969a465de1f029d4307d7cbb961ec56183f4dfe6e591f80abb248c20d` | `504f7ee4a9fff8cbe5a4b0a91c15f63e86a1a1cafe1ceb65c4d4414dd9acdfea` |
| `2026_01_BAL_IND` | `420b65a3026d4858f19cf59b8dca47e68c6c17a8f97fdb7abc7c3f7e29142c5f` | `58cb4d8efd8340b2b5b803be45b31e84354770f5a19e31468a90a3d13dc8e5f5` |
| `2026_01_BUF_HOU` | `794808ec9b0f4f7fc92b46636a572c9350320f92d9d331f232b3896ecf68839a` | `3c6b024b7ee6927ed5d218b817c3c140b9cb492c950b8d2b3b8029857342e74c` |
| `2026_01_CHI_CAR` | `a2e993b33f22352eae558e5eb7f7b7d4c7e58ec36d5ca9f762e41b271ed88f01` | `d335e4faa6fbc2a2aee7ad1ea03d880450409f5028505dece24ada05efcd9055` |
| `2026_01_CLE_JAX` | `fcd4ad1cbace36aaaf12ec4bf7d8d2c68ed741482f782e7f35c07d51d59ff5b5` | `78b9879a5f4c0948daef6ffc606affaebc6845ac783441b780829e20dd95d04e` |
| `2026_01_DAL_NYG` | `a7b506a25b60726b5727de715ded5de376561a46a9507a6342e537c8e0d2cf6a` | `312bfde86fb4037c7ff797d2c8bcdcfd3d5aa00a04e91d29d65e9db0993dbac8` |
| `2026_01_DEN_KC` | `b40a2fad7e9f61751780cab690193d4da0192f12cdda998f383fc77e6ab13f67` | `c3cea90613b92ae1f7dafbbda177bcd2f6267252afd34ee03187a56bcc8df8b2` |
| `2026_01_GB_MIN` | `ffb23901568e59ed68b5eaa70fbc430fbdc9ce9511efc14a4bdc2b4b7fa9c0e6` | `4c08d4614ebc4870101e3c54607c03654f08eab43cbfaa518167d7a12938b528` |
| `2026_01_MIA_LV` | `e89b0b0165bf5ffc9098bd8cbb1cba70035511deb582671d60e44947c319fcaa` | `28fa22ef8900b26a78a6360ea29df7b47522fde919847966e84845c2479e537f` |
| `2026_01_NE_SEA` | `133ef85ca28c67000bff6ab75f7b6a698b067d8f2114b51446303a968720febe` | `471a47280d97ecd2e373d4c7a1a21eb540522c56207e2c8600c37b5fc2b5a480` |
| `2026_01_NO_DET` | `c604d2113f16d960707dd46d6021bc4c0e8da875bced2d19aab18239cd56d253` | `e120dab71337c762fe55154cabee54dec004d0f84bb62a047a64f79a18320718` |
| `2026_01_NYJ_TEN` | `fe23cb1a02f5ac7baad7ed0a25b7a23bc661a24d689a666cc8616b1081ecf392` | `b89105283e61d678a878e85e49ee2e3e16220a7396bc251e1478fb2807ae917b` |
| `2026_01_SF_LA` | `acb35f557da6b421b6926532b884bb0cbeb34be48cefd1bc5387471b58cde983` | `0748a558357e35ca4309ead13b3d697b0b9b822c8d7a7896817e275ed320c94e` |
| `2026_01_TB_CIN` | `532f36756232ab927c0d97d56a5cf182e03d91aee248765e5a1a744a890a2478` | `06daec93382f9c7c06e4e88f476e20dbed1db2df51cd2de2ae582c0b95e8bb50` |
| `2026_01_WAS_PHI` | `ac5545e61537e82b0f65d3c4b997722b3f34fb71e6cb1120b0a5a15c3c3ffa0e` | `034c457617f111a501111a85bb7db92d2ed821a4f8fc569c5d564c10d0f86d2a` |

The controlled correction self-check changed one game fingerprint, detected
only that game as changed, and left all others unchanged. There was no prior
legitimate live-game snapshot to compare with this completed-week snapshot;
no earlier live state was fabricated.

## Runtime

The two standard complete commands measured:

| Phase | Run A | Run B |
|---|---:|---:|
| Schedule and PBP snapshot load | 0.267 s | 0.061 s |
| Frozen training load, normalization, and component fit | 12.153 s | 7.570 s |
| Validation, Week 1 normalization, scoring, and publication | 20.501 s | 21.228 s |
| Single-run readiness workflow | 32.921 s | 28.859 s |
| Deterministic duplicate | 21.058 s | 20.241 s |
| Export | 0.085 s | 0.069 s |
| Full command total | 54.130 s | 49.229 s |

An instrumented warm-cache pass, which wrapped but did not change the frozen
functions, separated the combined phase: schedule/source readiness excluding
normalization 2.92 s, PBP load 0.02 s, Week 1 normalization 1.26 s, historical
snapshot load/normalization 4.41 s, frozen model fit 2.77 s, decision scoring
11.49 s, publication safety/record construction 0.05 s, and remaining manifest,
aggregation, and validation work 3.89 s. Its pre-export single pass was 26.81
seconds.

The like-for-like readiness workflows of 28.86–32.92 seconds are close to the
Milestone 8 29.60–31.08-second range. The 54.13/49.23-second command totals
include the newly required duplicate scoring pass and remain below 60 seconds.
There is no major operational regression.

## Verification and handoff

The final verification suite covered `pytest`, `ruff check .`,
`ruff format --check .`, `git diff --check`, `pip check`, the two full Week 1
commands, deterministic artifact comparison, protocol hashing, and all eight
frozen source hashes.

| Check | Result |
|---|---|
| `pytest` | PASS — 84 tests |
| `ruff check .` | PASS |
| `ruff format --check .` | PASS — 68 files already formatted |
| `git diff --check` | PASS |
| `pip check` | PASS — no broken requirements |
| Full Week 1 run A | PASS — 16/16 games, zero failures |
| Full Week 1 run B | PASS — 16/16 games, zero failures |
| Deterministic duplicate | PASS — all 20 indexed artifacts and `hashes.json` byte-identical |
| Shadow protocol hash | PASS — matched preregistration |
| Holdout protocol and eight frozen source hashes | PASS |

The run confirms:

- no model or publication-policy file changed;
- no scientific or publication version was created;
- training remained exactly 2014–2024 and Week 1 was evaluation-only;
- no coach grade, coach ranking, team ranking, cumulative leaderboard, or new
  publication rule was created;
- no result was externally published; and
- no commit or push was performed.

This completed Week 1 Milestone 9 report is safe to commit as an internal
operational record. The raw snapshots and generated machine artifacts remain
outside the repository, consistent with prior practice.

Milestone 10 may begin only as a separately authorized, restricted workflow:
obtain real human review for any proposed record, keep publication-v1
withholdings non-overridable, and recheck the source fingerprint immediately
before any external use. Milestone 10 was not implemented here.
