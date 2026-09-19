# CoachIQ 2026 Week 1 human-review cards

Internal only. Denver–Kansas City is quarantined and absent. Every card below remains `pending_review`; automation has assigned no approval.

For each card, return exactly one status: `approved`, `hold_for_context`, `reject_data_issue`, or `reject_model_form_risk`, plus a short reviewer note. Do not edit the evidence fields.

## 2026_01_ARI_LAC:3127

### Factual play

- Matchup / play: ARI at LAC, play `3127`
- Quarter / clock: Q4 14:04
- Score: ARI 16, LAC 14
- Possession: `ARI`
- Down / distance: fourth-and-1
- Field position: ARI 40
- Raw description: (14:04) 12-B.Gillikin punts 60 yards to end zone, Center-59-C.Kreiter, Touchback.
- Actual action: `punt`
- Factual outcome: `punted`

### Model evidence and safety

- CoachIQ-favored action: `go`
- Actual-action EWP: 48.48%
- Favored-action EWP: 57.16%
- Modeled gap: 8.67% over `punt`
- Pairwise superiority: 1.000
- 90% paired difference interval: 7.91% to 9.48%
- Field clipping maximum: 3.546%; clock clipping maximum: 0.000%
- OT-boundary mass: 0.000%
- Tactical-context warnings: none
- Source correction state: `pbp_fingerprint_unchanged_current_source_verified`
- Game source fingerprint: `edbe670be5bf6cbac90d839525b0b4cb345fd319564ffbbbe46b59f391bcee36`
- Versions: `coachiq-wp-v1`, `coachiq-action-transition-v1`, `coachiq-decision-v1`, `coachiq-publication-v1`

| Action | EWP | 90% interval | Support observations/games | Field / clock clipping |
|---|---:|---:|---:|---:|
| go | 57.2% | 56.4%–58.0% | 664 / 580 | 0.30% / 0.00% |
| field_goal | unavailable | unavailable | 0 / 0 | unavailable |
| punt | 48.5% | 48.4%–48.5% | 17007 / 2988 | 3.55% / 0.00% |

Proposed neutral public sentence: On 4th-and-1 from their own 40, CoachIQ favored going for it. The model estimated going for it at 57.2% win probability and punting at 48.5%, a modeled advantage of 8.7 percentage points. The comparison met CoachIQ v1's frozen evidence threshold and publication-v1 safety checks.

### Human response

- Status: `pending_review`
- Allowed final status: `approved` / `hold_for_context` / `reject_data_issue` / `reject_model_form_risk`
- Reviewer notes: _

## 2026_01_NE_SEA:3657

### Factual play

- Matchup / play: NE at SEA, play `3657`
- Quarter / clock: Q4 3:49
- Score: NE 10, SEA 13
- Possession: `NE`
- Down / distance: fourth-and-2
- Field position: NE 35
- Raw description: (3:49) (Shotgun) 10-D.Maye scrambles right end ran ob at NE 40 for 5 yards (32-D.Thomas).
- Actual action: `go`
- Factual outcome: `converted`

### Model evidence and safety

- CoachIQ-favored action: `go`
- Actual-action EWP: 31.12%
- Favored-action EWP: 31.12%
- Modeled gap: 6.99% over `punt`
- Pairwise superiority: 1.000
- 90% paired difference interval: 5.55% to 8.47%
- Field clipping maximum: 0.900%; clock clipping maximum: 0.000%
- OT-boundary mass: 0.000%
- Tactical-context warnings: none
- Source correction state: `pbp_fingerprint_unchanged_current_source_verified`
- Game source fingerprint: `133ef85ca28c67000bff6ab75f7b6a698b067d8f2114b51446303a968720febe`
- Versions: `coachiq-wp-v1`, `coachiq-action-transition-v1`, `coachiq-decision-v1`, `coachiq-publication-v1`

| Action | EWP | 90% interval | Support observations/games | Field / clock clipping |
|---|---:|---:|---:|---:|
| go | 31.1% | 29.7%–32.6% | 187 / 180 | 0.53% / 0.00% |
| field_goal | unavailable | unavailable | 0 / 0 | unavailable |
| punt | 24.1% | 24.1%–24.2% | 17007 / 2988 | 0.90% / 0.00% |

Proposed neutral public sentence: On 4th-and-2 from their own 35, CoachIQ favored going for it. The model estimated going for it at 31.1% win probability and punting at 24.1%, a modeled advantage of 7.0 percentage points. The comparison met CoachIQ v1's frozen evidence threshold and publication-v1 safety checks.

### Human response

- Status: `pending_review`
- Allowed final status: `approved` / `hold_for_context` / `reject_data_issue` / `reject_model_form_risk`
- Reviewer notes: _

## 2026_01_WAS_PHI:649

### Factual play

- Matchup / play: WAS at PHI, play `649`
- Quarter / clock: Q1 5:09
- Score: PHI 0, WAS 3
- Possession: `PHI`
- Down / distance: fourth-and-21
- Field position: PHI 28
- Raw description: (5:09) 10-B.Mann punts 64 yards to WAS 8, Center-41-R.Underwood. 83-J.Lane to WAS 22 for 14 yards (80-D.Cooper).
- Actual action: `punt`
- Factual outcome: `punted`

### Model evidence and safety

- CoachIQ-favored action: `punt`
- Actual-action EWP: 62.65%
- Favored-action EWP: 62.65%
- Modeled gap: 4.42% over `go`
- Pairwise superiority: 1.000
- 90% paired difference interval: 3.59% to 5.30%
- Field clipping maximum: 0.118%; clock clipping maximum: 0.000%
- OT-boundary mass: 0.000%
- Tactical-context warnings: none
- Source correction state: `pbp_fingerprint_unchanged_current_source_verified`
- Game source fingerprint: `ac5545e61537e82b0f65d3c4b997722b3f34fb71e6cb1120b0a5a15c3c3ffa0e`
- Versions: `coachiq-wp-v1`, `coachiq-action-transition-v1`, `coachiq-decision-v1`, `coachiq-publication-v1`

| Action | EWP | 90% interval | Support observations/games | Field / clock clipping |
|---|---:|---:|---:|---:|
| go | 58.2% | 57.3%–59.1% | 212 / 206 | 0.00% / 0.00% |
| field_goal | unavailable | unavailable | 0 / 0 | unavailable |
| punt | 62.7% | 62.6%–62.7% | 17007 / 2988 | 0.12% / 0.00% |

Proposed neutral public sentence: On 4th-and-21 from their own 28, CoachIQ favored punting. The model estimated punting at 62.7% win probability and going for it at 58.2%, a modeled advantage of 4.4 percentage points. The comparison met CoachIQ v1's frozen evidence threshold and publication-v1 safety checks.

### Human response

- Status: `pending_review`
- Allowed final status: `approved` / `hold_for_context` / `reject_data_issue` / `reject_model_form_risk`
- Reviewer notes: _

## 2026_01_BUF_HOU:3022

### Factual play

- Matchup / play: BUF at HOU, play `3022`
- Quarter / clock: Q3 2:50
- Score: HOU 21, BUF 27
- Possession: `HOU`
- Down / distance: fourth-and-1
- Field position: HOU 37
- Raw description: (2:50) 57-B.Fisher reported in as eligible. 32-D.Montgomery right tackle to HOU 39 for 2 yards (47-C.Benford; 56-J.Solomon).
- Actual action: `go`
- Factual outcome: `converted`

### Model evidence and safety

- CoachIQ-favored action: `go`
- Actual-action EWP: 24.78%
- Favored-action EWP: 24.78%
- Modeled gap: 6.02% over `punt`
- Pairwise superiority: 1.000
- 90% paired difference interval: 5.55% to 6.53%
- Field clipping maximum: 1.688%; clock clipping maximum: 0.000%
- OT-boundary mass: 0.000%
- Tactical-context warnings: none
- Source correction state: `pbp_fingerprint_unchanged_current_source_verified`
- Game source fingerprint: `794808ec9b0f4f7fc92b46636a572c9350320f92d9d331f232b3896ecf68839a`
- Versions: `coachiq-wp-v1`, `coachiq-action-transition-v1`, `coachiq-decision-v1`, `coachiq-publication-v1`

| Action | EWP | 90% interval | Support observations/games | Field / clock clipping |
|---|---:|---:|---:|---:|
| go | 24.8% | 24.3%–25.3% | 664 / 580 | 0.00% / 0.00% |
| field_goal | unavailable | unavailable | 0 / 0 | unavailable |
| punt | 18.8% | 18.7%–18.8% | 17007 / 2988 | 1.69% / 0.00% |

Proposed neutral public sentence: On 4th-and-1 from their own 37, CoachIQ favored going for it. The model estimated going for it at 24.8% win probability and punting at 18.8%, a modeled advantage of 6.0 percentage points. The comparison met CoachIQ v1's frozen evidence threshold and publication-v1 safety checks.

### Human response

- Status: `pending_review`
- Allowed final status: `approved` / `hold_for_context` / `reject_data_issue` / `reject_model_form_risk`
- Reviewer notes: _

## 2026_01_CHI_CAR:832

### Factual play

- Matchup / play: CHI at CAR, play `832`
- Quarter / clock: Q1 4:22
- Score: CAR 7, CHI 7
- Possession: `CAR`
- Down / distance: fourth-and-13
- Field position: CAR 37
- Raw description: (4:22) 6-S.Martin punts 30 yards to CHI 33, Center-44-J.Jansen, out of bounds.
- Actual action: `punt`
- Factual outcome: `punted`

### Model evidence and safety

- CoachIQ-favored action: `punt`
- Actual-action EWP: 36.94%
- Favored-action EWP: 36.94%
- Modeled gap: 3.54% over `go`
- Pairwise superiority: 1.000
- 90% paired difference interval: 2.72% to 4.44%
- Field clipping maximum: 1.688%; clock clipping maximum: 0.000%
- OT-boundary mass: 0.000%
- Tactical-context warnings: none
- Source correction state: `pbp_fingerprint_unchanged_current_source_verified`
- Game source fingerprint: `a2e993b33f22352eae558e5eb7f7b7d4c7e58ec36d5ca9f762e41b271ed88f01`
- Versions: `coachiq-wp-v1`, `coachiq-action-transition-v1`, `coachiq-decision-v1`, `coachiq-publication-v1`

| Action | EWP | 90% interval | Support observations/games | Field / clock clipping |
|---|---:|---:|---:|---:|
| go | 33.4% | 32.5%–34.2% | 212 / 206 | 0.47% / 0.00% |
| field_goal | unavailable | unavailable | 0 / 0 | unavailable |
| punt | 36.9% | 36.9%–37.0% | 17007 / 2988 | 1.69% / 0.00% |

Proposed neutral public sentence: On 4th-and-13 from their own 37, CoachIQ favored punting. The model estimated punting at 36.9% win probability and going for it at 33.4%, a modeled advantage of 3.5 percentage points. The comparison met CoachIQ v1's frozen evidence threshold and publication-v1 safety checks.

### Human response

- Status: `pending_review`
- Allowed final status: `approved` / `hold_for_context` / `reject_data_issue` / `reject_model_form_risk`
- Reviewer notes: _

## 2026_01_ATL_PIT:3430

### Factual play

- Matchup / play: ATL at PIT, play `3430`
- Quarter / clock: Q3 0:13
- Score: PIT 13, ATL 10
- Possession: `PIT`
- Down / distance: fourth-and-3
- Field position: PIT 39
- Raw description: (:13) 19-C.Johnston punts 50 yards to ATL 11, Center-46-C.Kuntz. 17-Z.Branch to ATL 24 for 13 yards (44-C.Bruener).
- Actual action: `punt`
- Factual outcome: `punted`

### Model evidence and safety

- CoachIQ-favored action: `go`
- Actual-action EWP: 65.93%
- Favored-action EWP: 68.44%
- Modeled gap: 2.51% over `punt`
- Pairwise superiority: 1.000
- 90% paired difference interval: 1.57% to 3.56%
- Field clipping maximum: 2.916%; clock clipping maximum: 0.000%
- OT-boundary mass: 0.000%
- Tactical-context warnings: none
- Source correction state: `pbp_fingerprint_unchanged_current_source_verified`
- Game source fingerprint: `c6ee93b969a465de1f029d4307d7cbb961ec56183f4dfe6e591f80abb248c20d`
- Versions: `coachiq-wp-v1`, `coachiq-action-transition-v1`, `coachiq-decision-v1`, `coachiq-publication-v1`

| Action | EWP | 90% interval | Support observations/games | Field / clock clipping |
|---|---:|---:|---:|---:|
| go | 68.4% | 67.5%–69.5% | 341 / 321 | 0.00% / 0.00% |
| field_goal | unavailable | unavailable | 0 / 0 | unavailable |
| punt | 65.9% | 65.9%–66.0% | 17007 / 2988 | 2.92% / 0.00% |

Proposed neutral public sentence: On 4th-and-3 from their own 39, CoachIQ favored going for it. The model estimated going for it at 68.4% win probability and punting at 65.9%, a modeled advantage of 2.5 percentage points. The comparison met CoachIQ v1's frozen evidence threshold and publication-v1 safety checks.

### Human response

- Status: `pending_review`
- Allowed final status: `approved` / `hold_for_context` / `reject_data_issue` / `reject_model_form_risk`
- Reviewer notes: _

## 2026_01_TB_CIN:460

### Factual play

- Matchup / play: TB at CIN, play `460`
- Quarter / clock: Q1 7:49
- Score: CIN 0, TB 3
- Possession: `CIN`
- Down / distance: fourth-and-6
- Field position: CIN 30
- Raw description: (7:49) 8-R.Rehkow punts 51 yards to TB 19, Center-46-W.Wagner. 15-T.Johnson pushed ob at TB 32 for 13 yards (47-S.Bozeman).
- Actual action: `punt`
- Factual outcome: `punted`

### Model evidence and safety

- CoachIQ-favored action: `punt`
- Actual-action EWP: 55.91%
- Favored-action EWP: 55.91%
- Modeled gap: 3.11% over `go`
- Pairwise superiority: 1.000
- 90% paired difference interval: 2.34% to 3.72%
- Field clipping maximum: 0.153%; clock clipping maximum: 0.000%
- OT-boundary mass: 0.000%
- Tactical-context warnings: none
- Source correction state: `pbp_fingerprint_unchanged_current_source_verified`
- Game source fingerprint: `532f36756232ab927c0d97d56a5cf182e03d91aee248765e5a1a744a890a2478`
- Versions: `coachiq-wp-v1`, `coachiq-action-transition-v1`, `coachiq-decision-v1`, `coachiq-publication-v1`

| Action | EWP | 90% interval | Support observations/games | Field / clock clipping |
|---|---:|---:|---:|---:|
| go | 52.8% | 52.2%–53.6% | 369 / 349 | 0.00% / 0.00% |
| field_goal | unavailable | unavailable | 0 / 0 | unavailable |
| punt | 55.9% | 55.9%–55.9% | 17007 / 2988 | 0.15% / 0.00% |

Proposed neutral public sentence: On 4th-and-6 from their own 30, CoachIQ favored punting. The model estimated punting at 55.9% win probability and going for it at 52.8%, a modeled advantage of 3.1 percentage points. The comparison met CoachIQ v1's frozen evidence threshold and publication-v1 safety checks.

### Human response

- Status: `pending_review`
- Allowed final status: `approved` / `hold_for_context` / `reject_data_issue` / `reject_model_form_risk`
- Reviewer notes: _

## 2026_01_NYJ_TEN:2539

### Factual play

- Matchup / play: NYJ at TEN, play `2539`
- Quarter / clock: Q3 8:51
- Score: TEN 3, NYJ 17
- Possession: `TEN`
- Down / distance: fourth-and-3
- Field position: TEN 39
- Raw description: (8:51) 3-T.Townsend punts 54 yards to NYJ 7, Center-46-M.Cox. 18-I.Williams to NYJ 22 for 15 yards (21-M.Robinson; 44-M.Diabate).
- Actual action: `punt`
- Factual outcome: `punted`

### Model evidence and safety

- CoachIQ-favored action: `go`
- Actual-action EWP: 8.05%
- Favored-action EWP: 9.60%
- Modeled gap: 1.55% over `punt`
- Pairwise superiority: 1.000
- 90% paired difference interval: 1.23% to 1.94%
- Field clipping maximum: 2.916%; clock clipping maximum: 0.000%
- OT-boundary mass: 0.000%
- Tactical-context warnings: none
- Source correction state: `pbp_fingerprint_unchanged_current_source_verified`
- Game source fingerprint: `fe23cb1a02f5ac7baad7ed0a25b7a23bc661a24d689a666cc8616b1081ecf392`
- Versions: `coachiq-wp-v1`, `coachiq-action-transition-v1`, `coachiq-decision-v1`, `coachiq-publication-v1`

| Action | EWP | 90% interval | Support observations/games | Field / clock clipping |
|---|---:|---:|---:|---:|
| go | 9.6% | 9.3%–10.0% | 341 / 321 | 0.00% / 0.00% |
| field_goal | unavailable | unavailable | 0 / 0 | unavailable |
| punt | 8.0% | 8.0%–8.1% | 17007 / 2988 | 2.92% / 0.00% |

Proposed neutral public sentence: On 4th-and-3 from their own 39, CoachIQ favored going for it. The model estimated going for it at 9.6% win probability and punting at 8.0%, a modeled advantage of 1.6 percentage points. The comparison met CoachIQ v1's frozen evidence threshold and publication-v1 safety checks.

### Human response

- Status: `pending_review`
- Allowed final status: `approved` / `hold_for_context` / `reject_data_issue` / `reject_model_form_risk`
- Reviewer notes: _

## 2026_01_GB_MIN:479

### Factual play

- Matchup / play: GB at MIN, play `479`
- Quarter / clock: Q1 8:13
- Score: MIN 0, GB 3
- Possession: `MIN`
- Down / distance: fourth-and-10
- Field position: MIN 45
- Raw description: (8:13) 19-B.Thorson punts 36 yards to GB 19, Center-42-A.DePaola, fair catch by 23-S.Moore.
- Actual action: `punt`
- Factual outcome: `punted`

### Model evidence and safety

- CoachIQ-favored action: `punt`
- Actual-action EWP: 49.77%
- Favored-action EWP: 49.77%
- Modeled gap: 2.94% over `go`
- Pairwise superiority: 1.000
- 90% paired difference interval: 2.18% to 3.57%
- Field clipping maximum: 9.743%; clock clipping maximum: 0.000%
- OT-boundary mass: 0.000%
- Tactical-context warnings: none
- Source correction state: `pbp_fingerprint_unchanged_current_source_verified`
- Game source fingerprint: `ffb23901568e59ed68b5eaa70fbc430fbdc9ce9511efc14a4bdc2b4b7fa9c0e6`
- Versions: `coachiq-wp-v1`, `coachiq-action-transition-v1`, `coachiq-decision-v1`, `coachiq-publication-v1`

| Action | EWP | 90% interval | Support observations/games | Field / clock clipping |
|---|---:|---:|---:|---:|
| go | 46.8% | 46.2%–47.6% | 369 / 349 | 0.27% / 0.00% |
| field_goal | unavailable | unavailable | 0 / 0 | unavailable |
| punt | 49.8% | 49.7%–49.8% | 17007 / 2988 | 9.74% / 0.00% |

Proposed neutral public sentence: On 4th-and-10 from their own 45, CoachIQ favored punting. The model estimated punting at 49.8% win probability and going for it at 46.8%, a modeled advantage of 2.9 percentage points. The comparison met CoachIQ v1's frozen evidence threshold and publication-v1 safety checks.

### Human response

- Status: `pending_review`
- Allowed final status: `approved` / `hold_for_context` / `reject_data_issue` / `reject_model_form_risk`
- Reviewer notes: _
