"""End-to-end chronological evaluation of the Milestone 3 baselines."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import polars as pl

from coachiq.analysis.fourth_down import extract_fourth_down_candidates
from coachiq.models.action_baselines import (
    ActionBaselineSet,
    canonical_state_from_candidate,
    fit_action_baselines,
)
from coachiq.models.evaluation import (
    calibration_table,
    expanding_season_splits,
    expected_calibration_error,
    probability_metrics,
)
from coachiq.models.state import build_state_value_rows
from coachiq.models.state_value import fit_state_value_model


def audit_reconstruction_invariants(candidates: pl.DataFrame) -> dict[str, int]:
    """Raise on Milestone 2 violations before any model fitting."""

    eligible = candidates.filter(pl.col("disposition") == "eligible")
    core = (
        "possession_team",
        "defense_team",
        "score_differential",
        "quarter",
        "game_seconds_remaining",
        "yards_to_goal",
        "yards_to_go",
        "posteam_timeouts_remaining",
        "defteam_timeouts_remaining",
    )
    unknown = eligible.filter(pl.col("actual_action") == "unknown").height
    missing = eligible.filter(
        pl.any_horizontal(pl.col(column).is_null() for column in core)
    ).height
    duplicates = candidates.select(
        pl.struct("game_id", "play_id").is_duplicated().sum()
    ).item()
    action_total = eligible.group_by("actual_action").len()["len"].sum()
    inconsistent_perspective = candidates.filter(
        (pl.col("next_state_status") == "reconstructed")
        & (
            (
                (pl.col("next_possession_team") == pl.col("possession_team"))
                & (
                    pl.col("decision_team_score_differential_next")
                    != pl.col("next_score_differential")
                )
            )
            | (
                (pl.col("next_defense_team") == pl.col("possession_team"))
                & (
                    pl.col("decision_team_score_differential_next")
                    != -pl.col("next_score_differential")
                )
            )
        )
    ).height
    failures = {
        "eligible_unknown_actions": unknown,
        "eligible_missing_core_state": missing,
        "duplicate_decision_ids": int(duplicates),
        "eligible_action_count_difference": int(action_total - eligible.height),
        "inconsistent_next_state_perspective": inconsistent_perspective,
    }
    if any(failures.values()):
        raise ValueError(f"Milestone 2 invariant failure: {failures}")
    return {
        **failures,
        "candidate_rows": candidates.height,
        "eligible_rows": eligible.height,
        "linked_repeated_fourth_downs": candidates.filter(
            pl.col("repeated_from_play_id").is_not_null()
        ).height,
    }


def evaluate_baseline(
    normalized_pbp: pl.DataFrame, *, first_evaluation_season: int = 2020
) -> dict[str, object]:
    """Evaluate every model using expanding pre-2025 season splits."""

    candidates = extract_fourth_down_candidates(normalized_pbp)
    invariants = audit_reconstruction_invariants(candidates)
    state_rows = build_state_value_rows(normalized_pbp)
    seasons = sorted(int(value) for value in normalized_pbp["season"].unique())
    splits = expanding_season_splits(
        seasons, first_evaluation_season=first_evaluation_season
    )
    reports = []
    for split in splits:
        train_states = state_rows.filter(pl.col("season").is_in(split.training_seasons))
        test_states = state_rows.filter(pl.col("season") == split.evaluation_season)
        state_model = fit_state_value_model(train_states)
        state_predictions = state_model.predict_proba(test_states)
        targets = test_states["eventual_win_equivalent"].to_numpy()
        state_metrics = probability_metrics(targets, state_predictions)
        calibration = calibration_table(targets, state_predictions)
        constant_predictions = np.full(
            test_states.height, float(train_states["eventual_win_equivalent"].mean())
        )

        nflverse = test_states.filter(pl.col("nflverse_win_probability").is_not_null())
        nflverse_metrics = None
        if nflverse.height:
            nflverse_metrics = asdict(
                probability_metrics(
                    nflverse["eventual_win_equivalent"].to_numpy(),
                    nflverse["nflverse_win_probability"].to_numpy(),
                )
            )

        train_candidates = candidates.filter(
            pl.col("season").is_in(split.training_seasons)
        )
        test_candidates = candidates.filter(pl.col("season") == split.evaluation_season)
        action_models = fit_action_baselines(train_candidates)
        reports.append(
            {
                "training_seasons": list(split.training_seasons),
                "evaluation_season": split.evaluation_season,
                "state_value": {
                    **asdict(state_metrics),
                    "constant_benchmark": asdict(
                        probability_metrics(targets, constant_predictions)
                    ),
                    "nflverse_wp_reference": nflverse_metrics,
                    "expected_calibration_error": expected_calibration_error(
                        calibration
                    ),
                    "calibration": calibration.to_dicts(),
                },
                "go": _evaluate_binary_action(action_models, test_candidates, "go"),
                "field_goal": _evaluate_binary_action(
                    action_models, test_candidates, "field_goal"
                ),
                "punt": _evaluate_punts(action_models, test_candidates),
                "support": _evaluate_support(action_models, test_candidates),
            }
        )
    return {
        "policy": {
            "first_evaluation_season": first_evaluation_season,
            "latest_allowed_season": 2024,
            "support_minimum_observations": 30,
            "state_model_ridge_penalty": 1.0,
        },
        "invariants": invariants,
        "field_goal_distance_validation": _field_goal_distance_validation(candidates),
        "splits": reports,
    }


def _field_goal_distance_validation(
    candidates: pl.DataFrame,
) -> list[dict[str, object]]:
    attempts = candidates.filter(
        (pl.col("actual_action") == "field_goal")
        & pl.col("kick_distance").is_not_null()
        & pl.col("yards_to_goal").is_not_null()
    ).with_columns(
        (pl.col("kick_distance") - (pl.col("yards_to_goal") + 18.0)).alias(
            "distance_difference"
        )
    )
    return (
        attempts.group_by("season")
        .agg(
            pl.len().alias("attempts"),
            pl.col("distance_difference").abs().mean().alias("mean_absolute_error"),
            (pl.col("distance_difference") == 0).mean().alias("exact_match_rate"),
            pl.col("distance_difference").min().alias("minimum_difference"),
            pl.col("distance_difference").max().alias("maximum_difference"),
        )
        .sort("season")
        .to_dicts()
    )


def _evaluate_binary_action(
    model: ActionBaselineSet, candidates: pl.DataFrame, action: str
) -> dict[str, object]:
    valid_outcomes = (
        (
            "converted",
            "converted_by_penalty",
            "touchdown",
            "failed",
            "interception",
            "fumble_lost",
        )
        if action == "go"
        else ("field_goal_made", "field_goal_missed", "field_goal_blocked")
    )
    rows = candidates.filter(
        (pl.col("disposition") == "eligible")
        & (pl.col("actual_action") == action)
        & pl.col("factual_outcome").is_in(valid_outcomes)
    )
    predictions: list[float] = []
    targets: list[float] = []
    for row in rows.iter_rows(named=True):
        probability, support = model.empirical_binary_probability(
            action, canonical_state_from_candidate(row)
        )
        if probability is None or not support.in_support:
            continue
        predictions.append(probability)
        if action == "go":
            targets.append(
                float(
                    row["factual_outcome"]
                    in {"converted", "converted_by_penalty", "touchdown"}
                )
            )
        else:
            targets.append(float(row["factual_outcome"] == "field_goal_made"))
    metrics = probability_metrics(targets, predictions) if predictions else None
    return {
        "eligible_observed_outcomes": rows.height,
        "supported_observations": len(predictions),
        "unsupported_rate": 1.0 - len(predictions) / rows.height
        if rows.height
        else 0.0,
        "metrics": asdict(metrics) if metrics else None,
    }


def _evaluate_punts(
    model: ActionBaselineSet, candidates: pl.DataFrame
) -> dict[str, object]:
    rows = candidates.filter(
        (pl.col("disposition") == "eligible")
        & (pl.col("actual_action") == "punt")
        & (pl.col("next_state_status") == "reconstructed")
        & pl.col("next_yards_to_goal").is_not_null()
    )
    predictions: list[float] = []
    targets: list[float] = []
    for row in rows.iter_rows(named=True):
        prediction, support = model.punt_expected_opponent_yards_to_goal(
            canonical_state_from_candidate(row)
        )
        if prediction is None or not support.in_support:
            continue
        predictions.append(prediction)
        targets.append(float(row["next_yards_to_goal"]))
    if predictions:
        errors = np.asarray(predictions) - np.asarray(targets)
        mae = float(np.mean(np.abs(errors)))
        rmse = float(np.sqrt(np.mean(errors**2)))
    else:
        mae = rmse = None
    return {
        "eligible_observed_outcomes": rows.height,
        "supported_observations": len(predictions),
        "unsupported_rate": 1.0 - len(predictions) / rows.height
        if rows.height
        else 0.0,
        "mean_absolute_error_yards_to_goal": mae,
        "root_mean_squared_error_yards_to_goal": rmse,
    }


def _evaluate_support(
    model: ActionBaselineSet, candidates: pl.DataFrame
) -> dict[str, object]:
    rows = candidates.filter(pl.col("disposition") == "eligible")
    results: dict[str, object] = {}
    for action in ("go", "field_goal", "punt"):
        supported = 0
        available = 0
        counts: list[int] = []
        for row in rows.iter_rows(named=True):
            support = model.support(action, canonical_state_from_candidate(row))
            available += int(support.available)
            supported += int(support.in_support)
            counts.append(support.observation_count)
        results[action] = {
            "queries": rows.height,
            "available": available,
            "supported": supported,
            "unsupported_rate": 1.0 - supported / rows.height if rows.height else 0.0,
            "median_comparable_observations": float(np.median(counts))
            if counts
            else 0.0,
        }
    return results


__all__ = ["audit_reconstruction_invariants", "evaluate_baseline"]
