"""Chronological development and pre-lock evaluation for CoachIQ WP."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import polars as pl

from coachiq.models.evaluation import probability_metrics
from coachiq.models.wp_selection import (
    DEVELOPMENT_EVALUATION_SEASONS,
    LATEST_ALLOWED_SEASON,
    PRELOCK_VALIDATION_SEASON,
    WP_CANDIDATES,
    WpCandidateSpec,
    candidate_by_id,
    clustered_metric_difference,
    fit_fold_recalibrator,
    fit_wp_candidate,
    probability_report,
    property_grid_report,
)


def evaluate_wp_development(
    state_rows: pl.DataFrame, *, bootstrap_replicates: int = 1000
) -> dict[str, object]:
    """Evaluate declared candidates using only the 2020-2023 development folds."""

    _validate_state_seasons(state_rows, maximum=2024)
    development_rows = state_rows.filter(pl.col("season") <= 2023)
    available = set(int(value) for value in development_rows["season"].unique())
    required = set(range(2014, 2024))
    if not required.issubset(available):
        raise ValueError("WP development requires complete 2014-2023 seasons")

    fold_reports: list[dict[str, object]] = []
    scored_folds: list[pl.DataFrame] = []
    for evaluation_season in DEVELOPMENT_EVALUATION_SEASONS:
        training = development_rows.filter(pl.col("season") < evaluation_season)
        evaluation = development_rows.filter(pl.col("season") == evaluation_season)
        candidate_reports: dict[str, object] = {}
        prediction_columns: list[pl.Series] = []
        for candidate in WP_CANDIDATES:
            model = fit_wp_candidate(training, candidate)
            raw = model.predict_proba(evaluation)
            recalibrator = fit_fold_recalibrator(training, candidate)
            recalibrated = recalibrator.predict(raw)
            candidate_reports[candidate.candidate_id] = {
                "raw": probability_report(evaluation, raw),
                "recalibrated": probability_report(evaluation, recalibrated),
                "recalibrator": recalibrator.to_dict(),
            }
            prediction_columns.extend(
                (
                    pl.Series(f"{candidate.candidate_id}_raw", raw),
                    pl.Series(f"{candidate.candidate_id}_recalibrated", recalibrated),
                )
            )

        constant = np.full(
            evaluation.height,
            float(training["eventual_win_equivalent"].mean()),
        )
        nflverse_mask = evaluation["nflverse_win_probability"].is_not_null().to_numpy()
        nflverse_report = None
        if nflverse_mask.any():
            nflverse_rows = evaluation.filter(
                pl.col("nflverse_win_probability").is_not_null()
            )
            nflverse_report = probability_report(
                nflverse_rows,
                nflverse_rows["nflverse_win_probability"].to_numpy(),
            )
        fold_reports.append(
            {
                "training_seasons": list(range(2014, evaluation_season)),
                "evaluation_season": evaluation_season,
                "constant_prevalence": probability_report(evaluation, constant),
                "nflverse_wp_reference": nflverse_report,
                "candidates": candidate_reports,
            }
        )
        scored_folds.append(
            evaluation.select(
                "season",
                "game_id",
                "play_id",
                "eventual_win_equivalent",
                "nflverse_win_probability",
                "nflverse_vegas_win_probability",
                "score_differential",
                "game_seconds_remaining",
                "yards_to_goal",
                "yards_to_go",
                "team_pregame_spread",
            ).with_columns(*prediction_columns)
        )

    scored = pl.concat(scored_folds)
    pooled: dict[str, object] = {}
    properties: dict[str, object] = {}
    all_training = development_rows.filter(pl.col("season") <= 2023)
    for candidate in WP_CANDIDATES:
        raw = scored[f"{candidate.candidate_id}_raw"].to_numpy()
        recalibrated = scored[f"{candidate.candidate_id}_recalibrated"].to_numpy()
        pooled[candidate.candidate_id] = {
            "raw": probability_report(scored, raw),
            "recalibrated": probability_report(scored, recalibrated),
            "recalibration_comparison": clustered_metric_difference(
                scored["eventual_win_equivalent"].to_numpy(),
                recalibrated,
                raw,
                scored["game_id"].to_numpy(),
                replicates=bootstrap_replicates,
                seed=4200 + ord(candidate.candidate_id),
            ),
        }
        property_model = fit_wp_candidate(all_training, candidate)
        property_recalibrator = fit_fold_recalibrator(all_training, candidate)
        properties[candidate.candidate_id] = {
            "raw": property_grid_report(property_model),
            "recalibrated": property_grid_report(property_model, property_recalibrator),
        }

    comparisons = {
        "B_minus_A": _comparison(
            scored, "B_raw", "A_raw", bootstrap_replicates, seed=4301
        ),
        "C_minus_B": _comparison(
            scored, "C_raw", "B_raw", bootstrap_replicates, seed=4302
        ),
        "C_minus_A": _comparison(
            scored, "C_raw", "A_raw", bootstrap_replicates, seed=4303
        ),
        "D_minus_A": _comparison(
            scored, "D_raw", "A_raw", bootstrap_replicates, seed=4304
        ),
        "D_minus_C": _comparison(
            scored, "D_raw", "C_raw", bootstrap_replicates, seed=4305
        ),
    }
    return {
        "protocol": {
            "training_start_season": 2014,
            "development_evaluation_seasons": list(DEVELOPMENT_EVALUATION_SEASONS),
            "prelock_validation_season": PRELOCK_VALIDATION_SEASON,
            "protected_holdout": 2025,
            "selection_uses_2024": False,
            "bootstrap_unit": "game_id",
            "bootstrap_replicates": bootstrap_replicates,
            "recalibration_policy": (
                "fit base on all outer-training seasons except the latest; "
                "fit intercept/slope on the latest outer-training season; "
                "refit base on the full outer-training window"
            ),
        },
        "candidates": [_candidate_payload(candidate) for candidate in WP_CANDIDATES],
        "folds": fold_reports,
        "pooled_development": pooled,
        "clustered_comparisons": comparisons,
        "pregame_incremental_value": _pregame_incremental_value(scored),
        "property_checks": properties,
        "season_diagnostics": _season_diagnostics(scored),
        "2022_investigation": _year_investigation(scored, 2022),
        "external_reference": _external_reference_report(scored),
    }


def evaluate_wp_prelock_validation(
    state_rows: pl.DataFrame,
    *,
    candidate_id: str,
    use_recalibration: bool,
) -> dict[str, object]:
    """Evaluate one already-selected specification once on 2024."""

    _validate_state_seasons(state_rows, maximum=LATEST_ALLOWED_SEASON)
    candidate = candidate_by_id(candidate_id)
    training = state_rows.filter(pl.col("season") < PRELOCK_VALIDATION_SEASON)
    validation = state_rows.filter(pl.col("season") == PRELOCK_VALIDATION_SEASON)
    training_seasons = sorted(int(value) for value in training["season"].unique())
    if training_seasons != list(range(2014, 2024)):
        raise ValueError(
            "2024 pre-lock validation requires complete 2014-2023 training"
        )
    if not validation.height:
        raise ValueError("2024 pre-lock validation rows are required")
    model = fit_wp_candidate(training, candidate)
    raw = model.predict_proba(validation)
    recalibrator = fit_fold_recalibrator(training, candidate)
    selected = recalibrator.predict(raw) if use_recalibration else raw
    constant = np.full(
        validation.height,
        float(training["eventual_win_equivalent"].mean()),
    )
    nflverse_rows = validation.filter(pl.col("nflverse_win_probability").is_not_null())
    vegas_rows = validation.filter(
        pl.col("nflverse_vegas_win_probability").is_not_null()
    )
    return {
        "candidate_id": candidate_id,
        "use_recalibration": use_recalibration,
        "training_seasons": training_seasons,
        "evaluation_season": 2024,
        "selected": probability_report(validation, selected),
        "raw": probability_report(validation, raw),
        "recalibrator": recalibrator.to_dict(),
        "constant_prevalence": probability_report(validation, constant),
        "nflverse_wp_reference": probability_report(
            nflverse_rows,
            nflverse_rows["nflverse_win_probability"].to_numpy(),
        ),
        "nflverse_vegas_wp_reference": probability_report(
            vegas_rows,
            vegas_rows["nflverse_vegas_win_probability"].to_numpy(),
        ),
        "property_checks": property_grid_report(
            model, recalibrator if use_recalibration else None
        ),
    }


def _comparison(
    scored: pl.DataFrame,
    candidate_column: str,
    reference_column: str,
    replicates: int,
    *,
    seed: int,
) -> dict[str, object]:
    return clustered_metric_difference(
        scored["eventual_win_equivalent"].to_numpy(),
        scored[candidate_column].to_numpy(),
        scored[reference_column].to_numpy(),
        scored["game_id"].to_numpy(),
        replicates=replicates,
        seed=seed,
    )


def _pregame_incremental_value(scored: pl.DataFrame) -> dict[str, object]:
    seconds = scored["game_seconds_remaining"].to_numpy()
    margin = np.abs(scored["score_differential"].to_numpy())
    masks = {
        "all_development_states": np.ones(scored.height, dtype=bool),
        "first_half": seconds > 1800,
        "tied": margin == 0,
        "within_7": margin <= 7,
        "final_5_minutes": seconds <= 300,
        "final_2_minutes": seconds <= 120,
    }
    targets = scored["eventual_win_equivalent"].to_numpy()
    b = scored["B_raw"].to_numpy()
    c = scored["C_raw"].to_numpy()
    reports: dict[str, object] = {}
    for name, mask in masks.items():
        b_metrics = probability_metrics(targets[mask], b[mask])
        c_metrics = probability_metrics(targets[mask], c[mask])
        b_report = probability_report(scored.filter(pl.Series(mask)), b[mask])
        c_report = probability_report(scored.filter(pl.Series(mask)), c[mask])
        b_ece = float(b_report["expected_calibration_error"])
        c_ece = float(c_report["expected_calibration_error"])
        reports[name] = {
            "observations": int(mask.sum()),
            "delta_log_loss_C_minus_B": c_metrics.log_loss - b_metrics.log_loss,
            "delta_brier_C_minus_B": c_metrics.brier_score - b_metrics.brier_score,
            "delta_ece_C_minus_B": c_ece - b_ece,
            "B_expected_calibration_error": b_ece,
            "C_expected_calibration_error": c_ece,
        }
    return reports


def _season_diagnostics(scored: pl.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for season in (2020, 2021, 2022, 2023):
        frame = scored.filter(pl.col("season") == season)
        margin = frame["score_differential"].abs()
        seconds = frame["game_seconds_remaining"]
        rows.append(
            {
                "season": season,
                "observations": frame.height,
                "games": frame["game_id"].n_unique(),
                "target_mean": float(frame["eventual_win_equivalent"].mean()),
                "tied_state_rate": float((margin == 0).mean()),
                "within_7_state_rate": float((margin <= 7).mean()),
                "mean_absolute_score_margin": float(margin.mean()),
                "first_half_rate": float((seconds > 1800).mean()),
                "final_5_minutes_rate": float((seconds <= 300).mean()),
                "mean_absolute_pregame_spread": float(
                    frame["team_pregame_spread"].abs().mean()
                ),
                "missing_pregame_spread_rate": float(
                    frame["team_pregame_spread"].is_null().mean()
                ),
            }
        )
    return rows


def _external_reference_report(scored: pl.DataFrame) -> dict[str, object]:
    """Report nflverse probabilities as diagnostics, never as model features."""

    reports: dict[str, object] = {}
    for column in ("nflverse_win_probability", "nflverse_vegas_win_probability"):
        available = scored.filter(pl.col(column).is_not_null())
        reports[column] = (
            probability_report(available, available[column].to_numpy())
            if available.height
            else None
        )
    return reports


def _year_investigation(scored: pl.DataFrame, season: int) -> dict[str, object]:
    adjacent = scored.filter(pl.col("season").is_in((season - 1, season, season + 1)))
    reports: dict[str, object] = {}
    for year in (season - 1, season, season + 1):
        frame = adjacent.filter(pl.col("season") == year)
        targets = frame["eventual_win_equivalent"].to_numpy()
        candidate = frame["A_raw"].to_numpy()
        numerical = np.clip(candidate, 1e-15, 1.0 - 1e-15)
        losses = -(
            targets * np.log(numerical) + (1.0 - targets) * np.log(1.0 - numerical)
        )
        game_losses = (
            frame.select("game_id")
            .with_columns(pl.Series("row_loss", losses))
            .group_by("game_id")
            .agg(
                pl.len().alias("observations"),
                pl.col("row_loss").sum().alias("total_log_loss"),
                pl.col("row_loss").mean().alias("mean_log_loss"),
            )
            .sort("total_log_loss", descending=True)
        )
        top_five = game_losses.head(5)
        retained_loss = float(losses.sum() - top_five["total_log_loss"].sum())
        retained_rows = int(frame.height - top_five["observations"].sum())
        reports[str(year)] = {
            "overall_log_loss": float(losses.mean()),
            "log_loss_excluding_five_largest_game_contributors": (
                retained_loss / retained_rows
            ),
            "five_largest_game_contributors": top_five.to_dicts(),
            "top_five_share_of_total_loss": float(
                top_five["total_log_loss"].sum() / losses.sum()
            ),
            "clock_regimes": probability_report(frame, candidate)["clock_regimes"],
            "score_regimes": probability_report(frame, candidate)["score_regimes"],
        }
    return reports


def _candidate_payload(candidate: WpCandidateSpec) -> dict[str, object]:
    return {
        **asdict(candidate),
        "feature_names": list(candidate.feature_names),
    }


def _validate_state_seasons(states: pl.DataFrame, *, maximum: int) -> None:
    if not states.height:
        raise ValueError("state rows cannot be empty")
    seasons = states["season"].unique()
    if int(seasons.max()) > maximum:
        raise ValueError(f"seasons after {maximum} are protected")


__all__ = ["evaluate_wp_development", "evaluate_wp_prelock_validation"]
