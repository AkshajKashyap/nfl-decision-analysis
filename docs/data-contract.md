# CoachIQ play-by-play data contract

This document freezes the Milestone 1 internal play representation. It is a
normalization contract, not a fourth-down decision filter: all rows are retained
unless the raw source is structurally invalid.

## Source boundary

`coachiq.data.load_pbp(seasons)` loads nflverse play-by-play through
`nflreadpy`, validates requested years, and returns raw data sorted by season,
game ID, play ID, and upstream `order_sequence` when present. It neither caches
nor writes data in the repository.

`coachiq.data.normalize_pbp(raw)` is the separate transformation boundary. It
selects only the fields below, gives them stable CoachIQ names/types, and sorts
them by `season`, `game_id`, `play_id`, and `play_sequence`.

`build_manifest(raw, seasons)` returns source/version, resolved asset names,
row/schema metadata, retrieval time, and the current git revision when
available, including whether its worktree was dirty. A manifest is persisted only through explicit
`write_manifest(manifest, path)`; callers must select the destination. This
makes retrieval provenance recordable without introducing a hidden CoachIQ cache
or a repository-local data store. nflreadpy's own external cache behavior, if
configured, remains outside this repository.

## Raw schema expectations

The following nflverse columns must exist because CoachIQ cannot preserve a
reliable play-level audit record without them:

```text
season, game_id, play_id, home_team, away_team, posteam, defteam,
down, ydstogo, yardline_100, qtr, quarter_seconds_remaining,
half_seconds_remaining, game_seconds_remaining, score_differential,
home_timeouts_remaining, away_timeouts_remaining,
posteam_timeouts_remaining, defteam_timeouts_remaining, play_type,
play_type_nfl
```

Presence is different from non-nullness. For example, kickoff,
administrative, and no-play rows legitimately have null possession or down.
Fields outside this required set are optional across upstream historical
schemas. If an optional source field is absent, CoachIQ emits its normalized
column as typed nulls rather than changing the output schema.

## Normalized schema

All column names and Polars dtypes are defined in
`coachiq.data.schema.NORMALIZED_SCHEMA`. The 91 columns are grouped below for
readability.

| Group | Normalized columns |
|---|---|
| Identity/order | `season`, `season_type`, `week`, `game_date`, `game_id`, `play_id`, `drive`, `play_sequence`, `nfl_api_id` |
| Teams/context | `home_team`, `away_team`, `possession_team`, `defense_team`, `possession_side`, `home_opening_kickoff`, `home_coach`, `away_coach` |
| Pre-play situation | `down`, `yards_to_go`, `goal_to_go`, `yards_to_goal`, `quarter`, `game_half`, `quarter_seconds_remaining`, `half_seconds_remaining`, `game_seconds_remaining`, `posteam_score`, `defteam_score`, `score_differential`, `home_timeouts_remaining`, `away_timeouts_remaining`, `posteam_timeouts_remaining`, `defteam_timeouts_remaining` |
| Play/action audit | `play_type`, `nfl_play_type`, `description`, `is_special_teams_play`, `special_teams_play_type`, `is_rush`, `is_pass`, `is_qb_kneel`, `is_qb_spike`, `is_field_goal_attempt`, `is_punt_attempt`, `has_penalty`, `is_no_play`, `is_play_deleted`, `is_aborted_play`, `is_timeout`, `timeout_team`, `penalty_team`, `penalty_type`, `penalty_yards` |
| Factual transition audit | `yards_gained`, `is_first_down`, `is_first_down_by_penalty`, `is_fourth_down_converted`, `is_fourth_down_failed`, `field_goal_result`, `kick_distance`, `return_yards`, `is_touchback`, `is_punt_blocked`, `is_fumble_lost`, `is_interception`, `is_touchdown`, `is_safety`, `is_return_touchdown`, `posteam_score_after`, `defteam_score_after`, `score_differential_after`, `end_yard_line`, `series_result`, `fixed_drive_result` |
| Personnel/environment | `kicker_player_id`, `kicker_player_name`, `punter_player_id`, `punter_player_name`, `punt_returner_player_id`, `punt_returner_player_name`, `roof`, `surface`, `weather`, `temperature`, `wind` |
| Pregame/upstream diagnostics | `spread_line`, `total_line`, `is_division_game`, `expected_points`, `win_probability`, `vegas_win_probability` |

Naming changes isolate downstream CoachIQ code from nflverse terminology. The
key mappings are `posteam -> possession_team`, `defteam -> defense_team`,
`ydstogo -> yards_to_go`, `yardline_100 -> yards_to_goal`,
`qtr -> quarter`, `order_sequence -> play_sequence`, `desc -> description`,
and binary 0/1 flags to nullable `is_*` / `has_*` booleans.

The output includes upstream `expected_points`, `win_probability`, and
`vegas_win_probability` only for the benchmark/diagnostic purpose specified in
Milestone 0. Their presence does not authorize their use as CoachIQ model
features.

## Validation rules

- The normalized schema is exact: no missing, extra, or type-drift columns.
- `season`, `game_id`, and `play_id` are non-null.
- `(game_id, play_id)` is unique.
- Non-null `down` values must be 1 through 4; null down is preserved.
- Non-null `quarter` values must be 1 through 5; null quarter is preserved.
- Present raw binary indicators must be 0/1 (or boolean); null is preserved.
- Ordering is deterministic by `season`, `game_id`, `play_id`, and
  `play_sequence`.

This layer intentionally does not reject plays because they are penalties,
no-plays, overtime, kneels, aborted snaps, or otherwise unusual. Those are
Milestone 2 decision-policy concerns.

## Observed development-season behavior

The 2024 nflverse asset was validated on 2026-09-03. It produced 49,492 rows,
285 games, and 4,279 rows with raw `down == 4`; normalization preserved all
49,492 rows and emitted 91 columns.

Administrative/non-play rows account for legitimate nulls: 2,713 rows had null
possession/defense team and score differential, 8,009 had null down, and 3,542
had null `yardline_100`. Five rows had null game seconds remaining. This is
expected upstream behavior, not a contract failure. Candidate-row requirements
in the Milestone 0 foundation will be applied only during Milestone 2.
