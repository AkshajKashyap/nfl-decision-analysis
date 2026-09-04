"""Conversion from nflverse PBP columns to CoachIQ's fixed internal schema."""

from __future__ import annotations

import polars as pl

from coachiq.data.schema import (
    NORMALIZED_SCHEMA,
    SORT_COLUMNS,
    SchemaValidationError,
    require_raw_columns,
    validate_normalized_pbp,
)

_RAW_TO_NORMALIZED = {
    "season": "season",
    "season_type": "season_type",
    "week": "week",
    "game_date": "game_date",
    "game_id": "game_id",
    "play_id": "play_id",
    "drive": "drive",
    "order_sequence": "play_sequence",
    "nfl_api_id": "nfl_api_id",
    "home_team": "home_team",
    "away_team": "away_team",
    "posteam": "possession_team",
    "defteam": "defense_team",
    "posteam_type": "possession_side",
    "home_opening_kickoff": "home_opening_kickoff",
    "home_coach": "home_coach",
    "away_coach": "away_coach",
    "down": "down",
    "ydstogo": "yards_to_go",
    "goal_to_go": "goal_to_go",
    "yardline_100": "yards_to_goal",
    "qtr": "quarter",
    "game_half": "game_half",
    "quarter_seconds_remaining": "quarter_seconds_remaining",
    "half_seconds_remaining": "half_seconds_remaining",
    "game_seconds_remaining": "game_seconds_remaining",
    "posteam_score": "posteam_score",
    "defteam_score": "defteam_score",
    "score_differential": "score_differential",
    "home_timeouts_remaining": "home_timeouts_remaining",
    "away_timeouts_remaining": "away_timeouts_remaining",
    "posteam_timeouts_remaining": "posteam_timeouts_remaining",
    "defteam_timeouts_remaining": "defteam_timeouts_remaining",
    "play_type": "play_type",
    "play_type_nfl": "nfl_play_type",
    "desc": "description",
    "special_teams_play": "is_special_teams_play",
    "st_play_type": "special_teams_play_type",
    "rush": "is_rush",
    "pass": "is_pass",
    "qb_kneel": "is_qb_kneel",
    "qb_spike": "is_qb_spike",
    "field_goal_attempt": "is_field_goal_attempt",
    "punt_attempt": "is_punt_attempt",
    "penalty": "has_penalty",
    "play_deleted": "is_play_deleted",
    "aborted_play": "is_aborted_play",
    "timeout": "is_timeout",
    "timeout_team": "timeout_team",
    "penalty_team": "penalty_team",
    "penalty_type": "penalty_type",
    "penalty_yards": "penalty_yards",
    "yards_gained": "yards_gained",
    "first_down": "is_first_down",
    "first_down_penalty": "is_first_down_by_penalty",
    "fourth_down_converted": "is_fourth_down_converted",
    "fourth_down_failed": "is_fourth_down_failed",
    "field_goal_result": "field_goal_result",
    "kick_distance": "kick_distance",
    "return_yards": "return_yards",
    "touchback": "is_touchback",
    "punt_blocked": "is_punt_blocked",
    "fumble_lost": "is_fumble_lost",
    "interception": "is_interception",
    "touchdown": "is_touchdown",
    "safety": "is_safety",
    "return_touchdown": "is_return_touchdown",
    "posteam_score_post": "posteam_score_after",
    "defteam_score_post": "defteam_score_after",
    "score_differential_post": "score_differential_after",
    "end_yard_line": "end_yard_line",
    "series_result": "series_result",
    "fixed_drive_result": "fixed_drive_result",
    "kicker_player_id": "kicker_player_id",
    "kicker_player_name": "kicker_player_name",
    "punter_player_id": "punter_player_id",
    "punter_player_name": "punter_player_name",
    "punt_returner_player_id": "punt_returner_player_id",
    "punt_returner_player_name": "punt_returner_player_name",
    "roof": "roof",
    "surface": "surface",
    "weather": "weather",
    "temp": "temperature",
    "wind": "wind",
    "spread_line": "spread_line",
    "total_line": "total_line",
    "div_game": "is_division_game",
    "ep": "expected_points",
    "wp": "win_probability",
    "vegas_wp": "vegas_win_probability",
}

_BINARY_COLUMNS = frozenset(
    {
        "home_opening_kickoff",
        "goal_to_go",
        "is_special_teams_play",
        "is_rush",
        "is_pass",
        "is_qb_kneel",
        "is_qb_spike",
        "is_field_goal_attempt",
        "is_punt_attempt",
        "has_penalty",
        "is_play_deleted",
        "is_aborted_play",
        "is_timeout",
        "is_first_down",
        "is_first_down_by_penalty",
        "is_fourth_down_converted",
        "is_fourth_down_failed",
        "is_touchback",
        "is_punt_blocked",
        "is_fumble_lost",
        "is_interception",
        "is_touchdown",
        "is_safety",
        "is_return_touchdown",
        "is_division_game",
    }
)


def normalize_pbp(raw: pl.DataFrame) -> pl.DataFrame:
    """Return a typed, sorted CoachIQ PBP table without applying decision policy."""

    require_raw_columns(raw)
    _validate_integral_raw_column(raw, "down")
    _validate_integral_raw_column(raw, "qtr")
    _validate_binary_columns(raw)

    expressions: list[pl.Expr] = []
    for raw_column, normalized_column in _RAW_TO_NORMALIZED.items():
        expected_type = NORMALIZED_SCHEMA[normalized_column]
        if raw_column not in raw.columns:
            expressions.append(
                pl.lit(None, dtype=expected_type).alias(normalized_column)
            )
        elif normalized_column in _BINARY_COLUMNS:
            expressions.append(_binary_expression(raw_column, normalized_column))
        else:
            expressions.append(
                pl.col(raw_column)
                .cast(expected_type, strict=False)
                .alias(normalized_column)
            )

    expressions.append(
        pl.col("play_type").eq("no_play").fill_null(False).alias("is_no_play")
    )
    normalized = raw.select(expressions).select(list(NORMALIZED_SCHEMA))
    normalized = normalized.sort(SORT_COLUMNS, nulls_last=True)
    validate_normalized_pbp(normalized)
    return normalized


def _binary_expression(raw_column: str, normalized_column: str) -> pl.Expr:
    numeric = pl.col(raw_column).cast(pl.Float64, strict=False)
    return (
        pl.when(pl.col(raw_column).is_null())
        .then(pl.lit(None, dtype=pl.Boolean))
        .otherwise(numeric.eq(1))
        .cast(pl.Boolean)
        .alias(normalized_column)
    )


def _validate_integral_raw_column(raw: pl.DataFrame, column: str) -> None:
    numeric = pl.col(column).cast(pl.Float64, strict=False)
    malformed_count = raw.select(
        (
            pl.col(column).is_not_null()
            & (numeric.is_null() | numeric.ne(numeric.floor()))
        )
        .sum()
        .alias("count")
    ).item()
    if malformed_count:
        raise SchemaValidationError(
            f"Raw PBP column {column!r} has {malformed_count} non-integral values"
        )


def _validate_binary_columns(raw: pl.DataFrame) -> None:
    raw_binary_columns = {
        raw_column: normalized_column
        for raw_column, normalized_column in _RAW_TO_NORMALIZED.items()
        if normalized_column in _BINARY_COLUMNS and raw_column in raw.columns
    }
    for raw_column, normalized_column in raw_binary_columns.items():
        numeric = pl.col(raw_column).cast(pl.Float64, strict=False)
        invalid_count = raw.select(
            (
                pl.col(raw_column).is_not_null()
                & (numeric.is_null() | ~numeric.is_in([0, 1]))
            )
            .sum()
            .alias("count")
        ).item()
        if invalid_count:
            raise SchemaValidationError(
                f"Raw PBP column {raw_column!r} has {invalid_count} invalid "
                f"binary values for {normalized_column!r}"
            )
