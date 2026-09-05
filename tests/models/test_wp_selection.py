from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from tests.models.test_state_value import _state_rows

from coachiq.analysis import evaluate_wp_prelock_validation
from coachiq.models import (
    EXPANDED_FEATURE_SPEC,
    FEATURE_NAMES_BY_SPEC,
    LOCKED_WP_CANDIDATE_ID,
    LOCKED_WP_MODEL_VERSION,
    PREGAME_BASELINE_FEATURE_SPEC,
    PREGAME_FEATURE_SPEC,
    WP_CANDIDATES,
    calibration_band_report,
    clustered_metric_difference,
    fit_fold_recalibrator,
    fit_locked_wp_model,
    fit_wp_candidate,
    property_grid_report,
    state_feature_matrix,
)


def test_candidate_features_are_explicit_and_pregame_missingness_is_finite() -> None:
    rows = _state_rows().with_columns(
        pl.when(pl.int_range(pl.len()) % 2 == 0)
        .then(pl.lit(None, dtype=pl.Float64))
        .otherwise(pl.lit(7.0))
        .alias("team_pregame_spread")
    )

    expanded = state_feature_matrix(rows, feature_spec=EXPANDED_FEATURE_SPEC)
    pregame = state_feature_matrix(rows, feature_spec=PREGAME_FEATURE_SPEC)

    assert expanded.shape[1] == len(FEATURE_NAMES_BY_SPEC[EXPANDED_FEATURE_SPEC])
    assert pregame.shape[1] == len(FEATURE_NAMES_BY_SPEC[PREGAME_FEATURE_SPEC])
    assert np.isfinite(pregame).all()
    assert set(pregame[:, -1]) == {0.0, 1.0}


def test_candidate_fit_and_recalibration_are_deterministic_and_chronological() -> None:
    rows = _state_rows().with_columns(pl.lit(3.0).alias("team_pregame_spread"))
    candidate = next(item for item in WP_CANDIDATES if item.candidate_id == "C")

    first = fit_wp_candidate(rows, candidate)
    second = fit_wp_candidate(rows, candidate)
    first_recalibrator = fit_fold_recalibrator(rows, candidate)
    second_recalibrator = fit_fold_recalibrator(rows, candidate)

    assert first == second
    assert first.version == "state-value-logistic-pregame-dev"
    assert first_recalibrator == second_recalibrator
    assert first_recalibrator.training_seasons == (2022,)
    assert first_recalibrator.calibration_season == 2023
    assert max(first_recalibrator.training_seasons) < 2023


def test_game_clustered_comparison_is_reproducible() -> None:
    targets = [0.0, 0.0, 1.0, 1.0, 0.0, 1.0]
    candidate = [0.1, 0.2, 0.8, 0.9, 0.3, 0.7]
    reference = [0.4, 0.4, 0.6, 0.6, 0.5, 0.5]
    games = ["a", "a", "b", "b", "c", "c"]

    first = clustered_metric_difference(
        targets, candidate, reference, games, replicates=100, seed=4
    )
    second = clustered_metric_difference(
        targets, candidate, reference, games, replicates=100, seed=4
    )

    assert first == second
    assert first["games"] == 3
    assert first["log_loss"]["difference"] < 0
    assert first["brier_score"]["difference"] < 0


def test_calibration_bands_and_property_grid_are_complete_and_bounded() -> None:
    rows = _state_rows().with_columns(pl.lit(0.0).alias("team_pregame_spread"))
    model = fit_wp_candidate(rows, WP_CANDIDATES[1])

    bands = calibration_band_report([0.0, 0.5, 1.0], [0.05, 0.55, 0.95])
    properties = property_grid_report(model)

    assert len(bands) == 10
    assert sum(int(row["observations"]) for row in bands) == 3
    assert all("sparse" in row for row in bands)
    assert 0 <= properties["probability_minimum"]
    assert properties["probability_maximum"] <= 1
    assert set(properties["checks"]) == {
        "score",
        "lead_time",
        "deficit_time",
        "field_position",
        "pregame_strength",
    }


def test_unknown_feature_spec_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown"):
        state_feature_matrix(_state_rows(), feature_spec="future-model")


def test_locked_model_metadata_and_protected_season_boundary() -> None:
    rows = _state_rows().with_columns(pl.lit(3.0).alias("team_pregame_spread"))

    model = fit_locked_wp_model(rows)

    assert LOCKED_WP_CANDIDATE_ID == "D"
    assert model.version == LOCKED_WP_MODEL_VERSION == "coachiq-wp-v1"
    assert model.feature_spec == PREGAME_BASELINE_FEATURE_SPEC
    assert model.ridge_penalty == 1.0
    with pytest.raises(ValueError, match="2025"):
        fit_locked_wp_model(rows.with_columns(pl.lit(2025).alias("season")))


def test_prelock_validation_requires_the_complete_prior_window() -> None:
    rows = _state_rows().with_columns(pl.lit(3.0).alias("team_pregame_spread"))
    incomplete = pl.concat(
        [
            rows.head(1).with_columns(pl.lit(season).alias("season"))
            for season in range(2020, 2025)
        ]
    )

    with pytest.raises(ValueError, match="complete 2014-2023"):
        evaluate_wp_prelock_validation(
            incomplete,
            candidate_id="D",
            use_recalibration=False,
        )
