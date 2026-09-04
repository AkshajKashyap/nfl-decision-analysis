"""Chronological evaluation and calibration helpers for baseline models."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

LATEST_DEVELOPMENT_SEASON = 2024


@dataclass(frozen=True)
class ExpandingSeasonSplit:
    """One train-through-N, evaluate-N+1 split."""

    training_seasons: tuple[int, ...]
    evaluation_season: int


@dataclass(frozen=True)
class ProbabilityMetrics:
    """Proper scoring metrics for probability predictions."""

    observations: int
    log_loss: float
    brier_score: float


def expanding_season_splits(
    seasons: list[int] | tuple[int, ...], *, first_evaluation_season: int = 2020
) -> tuple[ExpandingSeasonSplit, ...]:
    """Build deterministic expanding windows and reject protected seasons."""

    canonical = tuple(sorted(set(int(season) for season in seasons)))
    if not canonical:
        raise ValueError("at least one season is required")
    if canonical[-1] > LATEST_DEVELOPMENT_SEASON:
        raise ValueError("2025 and later seasons are protected from development")
    splits = []
    for evaluation_season in canonical:
        if evaluation_season < first_evaluation_season:
            continue
        training = tuple(season for season in canonical if season < evaluation_season)
        if training:
            splits.append(ExpandingSeasonSplit(training, evaluation_season))
    if not splits:
        raise ValueError("no chronological split can be constructed")
    return tuple(splits)


def probability_metrics(
    targets: np.ndarray | list[float], predictions: np.ndarray | list[float]
) -> ProbabilityMetrics:
    """Calculate log loss and Brier score, accepting 0.5 tie targets."""

    observed = np.asarray(targets, dtype=float)
    predicted = np.asarray(predictions, dtype=float)
    if observed.shape != predicted.shape or not observed.size:
        raise ValueError("targets and predictions must have equal nonzero length")
    if np.any((observed < 0) | (observed > 1)):
        raise ValueError("targets must be within [0, 1]")
    if np.any((predicted < 0) | (predicted > 1)):
        raise ValueError("predictions must be within [0, 1]")
    numerical = np.clip(predicted, 1e-15, 1.0 - 1e-15)
    log_loss = -np.mean(
        observed * np.log(numerical) + (1.0 - observed) * np.log(1.0 - numerical)
    )
    return ProbabilityMetrics(
        observations=int(observed.size),
        log_loss=float(log_loss),
        brier_score=float(np.mean((predicted - observed) ** 2)),
    )


def calibration_table(
    targets: np.ndarray | list[float],
    predictions: np.ndarray | list[float],
    *,
    bins: int = 10,
) -> pl.DataFrame:
    """Return fixed-width reliability bins without fitting on evaluation data."""

    if bins < 2:
        raise ValueError("calibration bins must be at least two")
    observed = np.asarray(targets, dtype=float)
    predicted = np.asarray(predictions, dtype=float)
    probability_metrics(observed, predicted)
    indexes = np.minimum((predicted * bins).astype(int), bins - 1)
    rows = []
    for index in range(bins):
        selected = indexes == index
        if not selected.any():
            continue
        mean_prediction = float(predicted[selected].mean())
        observed_rate = float(observed[selected].mean())
        rows.append(
            {
                "bin": index,
                "lower": index / bins,
                "upper": (index + 1) / bins,
                "observations": int(selected.sum()),
                "mean_prediction": mean_prediction,
                "observed_rate": observed_rate,
                "absolute_gap": abs(mean_prediction - observed_rate),
            }
        )
    return pl.DataFrame(rows)


def expected_calibration_error(table: pl.DataFrame) -> float:
    """Return count-weighted absolute reliability gap."""

    total = table["observations"].sum()
    return float((table["observations"] * table["absolute_gap"]).sum() / total)


__all__ = [
    "LATEST_DEVELOPMENT_SEASON",
    "ExpandingSeasonSplit",
    "ProbabilityMetrics",
    "calibration_table",
    "expanding_season_splits",
    "expected_calibration_error",
    "probability_metrics",
]
