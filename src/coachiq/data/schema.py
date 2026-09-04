"""Schema constants and validation for CoachIQ play-by-play data."""

from __future__ import annotations

from collections.abc import Iterable

import polars as pl


class SchemaValidationError(ValueError):
    """Raised when raw or normalized play-by-play violates CoachIQ's contract."""


# These are the fields without which CoachIQ cannot retain a reliable play-level
# audit record. Other fields in the normalized table are optional upstream fields
# and become typed null columns if a historical schema does not provide them.
REQUIRED_RAW_COLUMNS = frozenset(
    {
        "season",
        "game_id",
        "play_id",
        "home_team",
        "away_team",
        "posteam",
        "defteam",
        "down",
        "ydstogo",
        "yardline_100",
        "qtr",
        "quarter_seconds_remaining",
        "half_seconds_remaining",
        "game_seconds_remaining",
        "score_differential",
        "home_timeouts_remaining",
        "away_timeouts_remaining",
        "posteam_timeouts_remaining",
        "defteam_timeouts_remaining",
        "play_type",
        "play_type_nfl",
        "result",
    }
)

CORE_IDENTIFIER_COLUMNS = ("season", "game_id", "play_id")
SORT_COLUMNS = ("season", "game_id", "play_id", "play_sequence")
VALID_DOWNS = frozenset({1, 2, 3, 4})
VALID_QUARTERS = frozenset({1, 2, 3, 4, 5})


# This is the stable, deliberately narrow CoachIQ internal representation. Types
# are enforced by normalize_pbp, even when nflverse's source type changes.
NORMALIZED_SCHEMA: dict[str, pl.DataType] = {
    # Identity and ordering
    "season": pl.Int16,
    "season_type": pl.String,
    "week": pl.Int16,
    "game_date": pl.String,
    "game_id": pl.String,
    "play_id": pl.Int64,
    "drive": pl.Int32,
    "play_sequence": pl.Int64,
    "nfl_api_id": pl.String,
    # Teams and possession context
    "home_team": pl.String,
    "away_team": pl.String,
    "possession_team": pl.String,
    "defense_team": pl.String,
    "possession_side": pl.String,
    "home_opening_kickoff": pl.Boolean,
    "home_coach": pl.String,
    "away_coach": pl.String,
    # Pre-play situation
    "down": pl.Int8,
    "yards_to_go": pl.Int16,
    "goal_to_go": pl.Boolean,
    "yards_to_goal": pl.Float64,
    "quarter": pl.Int8,
    "game_half": pl.String,
    "quarter_seconds_remaining": pl.Int32,
    "half_seconds_remaining": pl.Int32,
    "game_seconds_remaining": pl.Int32,
    "posteam_score": pl.Int16,
    "defteam_score": pl.Int16,
    "score_differential": pl.Int16,
    "home_timeouts_remaining": pl.Int8,
    "away_timeouts_remaining": pl.Int8,
    "posteam_timeouts_remaining": pl.Int8,
    "defteam_timeouts_remaining": pl.Int8,
    # Final observed result used only as the state-value target
    "home_score_differential_final": pl.Int16,
    # Play/action audit fields
    "play_type": pl.String,
    "nfl_play_type": pl.String,
    "description": pl.String,
    "is_special_teams_play": pl.Boolean,
    "special_teams_play_type": pl.String,
    "is_rush": pl.Boolean,
    "is_pass": pl.Boolean,
    "is_qb_kneel": pl.Boolean,
    "is_qb_spike": pl.Boolean,
    "is_field_goal_attempt": pl.Boolean,
    "is_punt_attempt": pl.Boolean,
    "has_penalty": pl.Boolean,
    "is_no_play": pl.Boolean,
    "is_play_deleted": pl.Boolean,
    "is_aborted_play": pl.Boolean,
    "is_timeout": pl.Boolean,
    "timeout_team": pl.String,
    "penalty_team": pl.String,
    "penalty_type": pl.String,
    "penalty_yards": pl.Int16,
    # Factual outcome / transition audit fields
    "yards_gained": pl.Int16,
    "is_first_down": pl.Boolean,
    "is_first_down_by_penalty": pl.Boolean,
    "is_fourth_down_converted": pl.Boolean,
    "is_fourth_down_failed": pl.Boolean,
    "field_goal_result": pl.String,
    "kick_distance": pl.Int16,
    "return_yards": pl.Int16,
    "is_touchback": pl.Boolean,
    "is_punt_blocked": pl.Boolean,
    "is_fumble_lost": pl.Boolean,
    "is_interception": pl.Boolean,
    "is_touchdown": pl.Boolean,
    "is_safety": pl.Boolean,
    "is_return_touchdown": pl.Boolean,
    "posteam_score_after": pl.Int16,
    "defteam_score_after": pl.Int16,
    "score_differential_after": pl.Int16,
    "end_yard_line": pl.String,
    "series_result": pl.String,
    "fixed_drive_result": pl.String,
    # Personnel and environment used by later transition models
    "kicker_player_id": pl.String,
    "kicker_player_name": pl.String,
    "punter_player_id": pl.String,
    "punter_player_name": pl.String,
    "punt_returner_player_id": pl.String,
    "punt_returner_player_name": pl.String,
    "roof": pl.String,
    "surface": pl.String,
    "weather": pl.String,
    "temperature": pl.Float64,
    "wind": pl.Float64,
    # Pre-game and externally modeled diagnostic fields
    "spread_line": pl.Float64,
    "total_line": pl.Float64,
    "is_division_game": pl.Boolean,
    "expected_points": pl.Float64,
    "win_probability": pl.Float64,
    "vegas_win_probability": pl.Float64,
}


def require_raw_columns(raw: pl.DataFrame) -> None:
    """Raise a clear error when required nflverse columns are absent."""

    missing = sorted(REQUIRED_RAW_COLUMNS.difference(raw.columns))
    if missing:
        joined = ", ".join(missing)
        raise SchemaValidationError(f"Raw PBP is missing required columns: {joined}")


def validate_normalized_pbp(frame: pl.DataFrame) -> None:
    """Validate CoachIQ's fixed normalized representation without filtering rows."""

    expected = list(NORMALIZED_SCHEMA)
    missing = [column for column in expected if column not in frame.columns]
    extra = [column for column in frame.columns if column not in NORMALIZED_SCHEMA]
    if missing or extra:
        details: list[str] = []
        if missing:
            details.append(f"missing columns: {', '.join(missing)}")
        if extra:
            details.append(f"unexpected columns: {', '.join(extra)}")
        raise SchemaValidationError(
            "Normalized schema mismatch (" + "; ".join(details) + ")"
        )

    incorrect_types = {
        column: (frame.schema[column], expected_type)
        for column, expected_type in NORMALIZED_SCHEMA.items()
        if frame.schema[column] != expected_type
    }
    if incorrect_types:
        details = ", ".join(
            f"{column}: {actual} (expected {expected_type})"
            for column, (actual, expected_type) in incorrect_types.items()
        )
        raise SchemaValidationError(f"Normalized column types are invalid: {details}")

    null_identifiers = frame.select(
        [
            pl.col(column).is_null().sum().alias(column)
            for column in CORE_IDENTIFIER_COLUMNS
        ]
    ).row(0, named=True)
    invalid_identifiers = {
        column: count for column, count in null_identifiers.items() if count > 0
    }
    if invalid_identifiers:
        details = ", ".join(
            f"{column}={count}" for column, count in invalid_identifiers.items()
        )
        raise SchemaValidationError(f"Normalized identifiers cannot be null: {details}")

    duplicate_count = frame.select(
        pl.struct(["game_id", "play_id"]).is_duplicated().sum().alias("count")
    ).item()
    if duplicate_count:
        raise SchemaValidationError(
            "Normalized PBP has "
            f"{duplicate_count} duplicate (game_id, play_id) identifiers"
        )

    _validate_domain(frame, "down", VALID_DOWNS)
    _validate_domain(frame, "quarter", VALID_QUARTERS)

    sorted_frame = frame.sort(SORT_COLUMNS, nulls_last=True)
    if not frame.equals(sorted_frame):
        raise SchemaValidationError(
            "Normalized PBP must be sorted by season, game_id, play_id, play_sequence"
        )


def _validate_domain(frame: pl.DataFrame, column: str, allowed: Iterable[int]) -> None:
    invalid = frame.filter(
        pl.col(column).is_not_null() & ~pl.col(column).is_in(list(allowed))
    )
    if invalid.height:
        values = invalid.select(pl.col(column).unique().sort()).to_series().to_list()
        raise SchemaValidationError(f"Invalid {column} values: {values}")
