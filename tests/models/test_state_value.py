from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from coachiq.data import NORMALIZED_SCHEMA
from coachiq.models import (
    build_state_value_rows,
    calibration_table,
    expanding_season_splits,
    fit_state_value_model,
    probability_for_team,
    probability_metrics,
    state_feature_matrix,
)


def _state_rows(size: int = 200) -> pl.DataFrame:
    indexes = np.arange(size)
    score = (indexes % 21) - 10
    seconds = 60 + (indexes * 137) % 3540
    return pl.DataFrame(
        {
            "season": np.where(indexes < size // 2, 2022, 2023),
            "score_differential": score,
            "game_seconds_remaining": seconds,
            "yards_to_goal": 5 + (indexes * 11) % 91,
            "yards_to_go": 1 + indexes % 15,
            "team_timeouts_remaining": indexes % 4,
            "opponent_timeouts_remaining": (indexes + 2) % 4,
            "is_home": indexes % 2 == 0,
            "down": 1 + indexes % 4,
            "eventual_win_equivalent": (score + (indexes % 3) > 0).astype(float),
        }
    )


def _normalized_result_fixture() -> pl.DataFrame:
    rows = []
    for play_id, possession, defense in ((10, "H", "A"), (20, "A", "H")):
        row = {
            column: False if dtype == pl.Boolean else None
            for column, dtype in NORMALIZED_SCHEMA.items()
        }
        row.update(
            {
                "season": 2024,
                "season_type": "REG",
                "game_id": "2024_01_A_H",
                "play_id": play_id,
                "play_sequence": play_id,
                "home_team": "H",
                "away_team": "A",
                "possession_team": possession,
                "defense_team": defense,
                "down": 1,
                "yards_to_go": 10,
                "yards_to_goal": 75.0,
                "quarter": 1,
                "game_seconds_remaining": 3500,
                "score_differential": 0,
                "posteam_timeouts_remaining": 3,
                "defteam_timeouts_remaining": 3,
                "spread_line": 7.0,
                "play_type": "run",
                "nfl_play_type": "RUSH",
                "home_score_differential_final": 7,
            }
        )
        rows.append(row)
    return pl.DataFrame(rows, schema=NORMALIZED_SCHEMA)


def test_state_target_and_probability_perspective_are_team_relative() -> None:
    rows = build_state_value_rows(_normalized_result_fixture())

    assert rows.select(
        "evaluation_team", "team_pregame_spread", "eventual_win_equivalent"
    ).rows() == [
        ("H", 7.0, 1.0),
        ("A", -7.0, 0.0),
    ]
    assert probability_for_team(0.72, "A", "A") == 0.72
    assert probability_for_team(0.72, "A", "H") == pytest.approx(0.28)


def test_state_value_fit_is_deterministic_and_probabilities_are_bounded() -> None:
    rows = _state_rows()

    first = fit_state_value_model(rows)
    second = fit_state_value_model(rows)
    predictions = first.predict_proba(rows)

    assert first.coefficients == second.coefficients
    assert np.array_equal(predictions, second.predict_proba(rows))
    assert np.all((predictions >= 0) & (predictions <= 1))
    assert first.predict_proba(
        rows.filter(pl.col("score_differential") == 10)
    ).mean() > (
        first.predict_proba(rows.filter(pl.col("score_differential") == -10)).mean()
    )


def test_target_and_external_probabilities_cannot_enter_feature_matrix() -> None:
    rows = _state_rows().with_columns(
        pl.lit(0.01).alias("nflverse_win_probability"),
        pl.lit(0.02).alias("nflverse_vegas_win_probability"),
        pl.lit(99.0).alias("expected_points"),
    )
    altered = rows.with_columns(
        (1.0 - pl.col("eventual_win_equivalent")).alias("eventual_win_equivalent"),
        pl.lit(0.99).alias("nflverse_win_probability"),
        pl.lit(0.98).alias("nflverse_vegas_win_probability"),
        pl.lit(-99.0).alias("expected_points"),
    )

    assert np.array_equal(state_feature_matrix(rows), state_feature_matrix(altered))


def test_expanding_splits_are_chronological_and_protect_2025() -> None:
    splits = expanding_season_splits(list(range(2014, 2025)))

    assert splits[0].training_seasons == tuple(range(2014, 2020))
    assert splits[0].evaluation_season == 2020
    assert splits[-1].training_seasons == tuple(range(2014, 2024))
    assert splits[-1].evaluation_season == 2024
    assert all(
        max(split.training_seasons) < split.evaluation_season for split in splits
    )

    with pytest.raises(ValueError, match="2025"):
        expanding_season_splits([2014, 2025])


def test_probability_metrics_and_fixed_calibration_bins_are_bounded() -> None:
    metrics = probability_metrics([0.0, 0.5, 1.0], [0.1, 0.5, 0.9])
    calibration = calibration_table([0.0, 0.5, 1.0], [0.1, 0.5, 0.9])

    assert metrics.observations == 3
    assert 0 <= metrics.brier_score <= 1
    assert calibration["observations"].sum() == 3
    assert calibration["mean_prediction"].is_between(0, 1).all()
