from __future__ import annotations

import polars as pl
import pytest

from coachiq.data import NORMALIZED_SCHEMA, SchemaValidationError, normalize_pbp


def raw_pbp(**overrides: object) -> pl.DataFrame:
    """Return intentionally unsorted, minimum-contract nflverse-like rows."""

    data: dict[str, object] = {
        "season": [2024, 2023],
        "game_id": ["2024_01_A_B", "2023_01_C_D"],
        "play_id": [55, 40],
        "home_team": ["B", "D"],
        "away_team": ["A", "C"],
        "posteam": ["A", None],
        "defteam": ["B", None],
        "down": [4, None],
        "ydstogo": [2, None],
        "yardline_100": [42.0, None],
        "qtr": [4, None],
        "quarter_seconds_remaining": [123, None],
        "half_seconds_remaining": [123, None],
        "game_seconds_remaining": [123, None],
        "score_differential": [-2, None],
        "home_timeouts_remaining": [2, None],
        "away_timeouts_remaining": [1, None],
        "posteam_timeouts_remaining": [1, None],
        "defteam_timeouts_remaining": [2, None],
        "play_type": ["punt", "no_play"],
        "play_type_nfl": ["PUNT", "PENALTY"],
        "punt_attempt": [1, None],
        "field_goal_attempt": [0, None],
        "penalty": [0, 1],
        "play_deleted": [0, 0],
    }
    data.update(overrides)
    return pl.DataFrame(data)


def test_normalize_has_fixed_schema_sorts_rows_and_preserves_identifiers() -> None:
    normalized = normalize_pbp(raw_pbp())

    assert normalized.columns == list(NORMALIZED_SCHEMA)
    assert normalized.schema == NORMALIZED_SCHEMA
    assert normalized.select("season").to_series().to_list() == [2023, 2024]
    assert normalized.select("game_id", "play_id").rows() == [
        ("2023_01_C_D", 40),
        ("2024_01_A_B", 55),
    ]


def test_normalize_retains_legitimate_null_play_context() -> None:
    normalized = normalize_pbp(raw_pbp())
    no_play = normalized.filter(pl.col("play_type") == "no_play").row(0, named=True)

    assert no_play["possession_team"] is None
    assert no_play["down"] is None
    assert no_play["is_no_play"] is True
    assert no_play["is_punt_attempt"] is None


def test_normalize_coerces_binary_flags_to_nullable_booleans() -> None:
    normalized = normalize_pbp(raw_pbp())
    punt_row = normalized.filter(pl.col("game_id") == "2024_01_A_B").row(0, named=True)

    assert normalized.schema["is_punt_attempt"] == pl.Boolean
    assert punt_row["is_punt_attempt"] is True
    assert punt_row["is_field_goal_attempt"] is False
    assert punt_row["has_penalty"] is False


def test_normalize_rejects_missing_required_raw_column() -> None:
    raw = raw_pbp().drop("yardline_100")

    with pytest.raises(SchemaValidationError, match="yardline_100"):
        normalize_pbp(raw)


def test_normalize_rejects_invalid_down_value() -> None:
    raw = raw_pbp(down=[5, None])

    with pytest.raises(SchemaValidationError, match="Invalid down values"):
        normalize_pbp(raw)


def test_normalize_rejects_non_integral_down_and_binary_values() -> None:
    with pytest.raises(SchemaValidationError, match="down.*non-integral"):
        normalize_pbp(raw_pbp(down=[4.5, None]))

    with pytest.raises(SchemaValidationError, match="punt_attempt.*invalid binary"):
        normalize_pbp(raw_pbp(punt_attempt=[0.5, None]))


def test_normalize_rejects_duplicate_game_play_identifier() -> None:
    raw = raw_pbp(
        season=[2024, 2024],
        game_id=["2024_01_A_B", "2024_01_A_B"],
        play_id=[55, 55],
    )

    with pytest.raises(SchemaValidationError, match="duplicate"):
        normalize_pbp(raw)
