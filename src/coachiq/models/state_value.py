"""Transparent ridge-logistic baseline for possession-team game value."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import polars as pl

STATE_VALUE_MODEL_VERSION = "state-value-logistic-v1"
FEATURE_NAMES = (
    "score_differential",
    "time_fraction",
    "late_score_interaction",
    "score_pressure",
    "field_progress",
    "yards_to_go_scaled",
    "timeout_differential",
    "is_home",
    "down_2",
    "down_3",
    "down_4",
)


@dataclass(frozen=True)
class StateValueModel:
    """Fitted deterministic model and training-only preprocessing metadata."""

    coefficients: tuple[float, ...]
    feature_means: tuple[float, ...]
    feature_scales: tuple[float, ...]
    training_seasons: tuple[int, ...]
    training_observations: int
    ridge_penalty: float
    iterations: int
    version: str = STATE_VALUE_MODEL_VERSION

    def predict_proba(self, states: pl.DataFrame) -> np.ndarray:
        """Predict possession-team eventual win-equivalent probabilities."""

        raw = state_feature_matrix(states)
        means = np.asarray(self.feature_means)
        scales = np.asarray(self.feature_scales)
        standardized = (raw - means) / scales
        design = np.column_stack((np.ones(len(standardized)), standardized))
        logits = design @ np.asarray(self.coefficients)
        return _sigmoid(logits)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable model metadata and parameters."""

        payload = asdict(self)
        payload["feature_names"] = list(FEATURE_NAMES)
        return payload


def fit_state_value_model(
    states: pl.DataFrame,
    *,
    ridge_penalty: float = 1.0,
    max_iterations: int = 50,
    tolerance: float = 1e-8,
) -> StateValueModel:
    """Fit ridge logistic regression with soft 0.5 targets for tied games."""

    if ridge_penalty < 0:
        raise ValueError("ridge_penalty cannot be negative")
    if not states.height:
        raise ValueError("state-value training data cannot be empty")
    targets = states.get_column("eventual_win_equivalent").to_numpy().astype(float)
    if np.any((targets < 0) | (targets > 1) | ~np.isfinite(targets)):
        raise ValueError("eventual_win_equivalent targets must be within [0, 1]")

    raw = state_feature_matrix(states)
    means = raw.mean(axis=0)
    scales = raw.std(axis=0)
    scales[scales < 1e-12] = 1.0
    standardized = (raw - means) / scales
    design = np.column_stack((np.ones(len(standardized)), standardized))
    coefficients = np.zeros(design.shape[1], dtype=float)
    penalty = np.eye(design.shape[1]) * ridge_penalty
    penalty[0, 0] = 0.0

    completed_iterations = 0
    for iteration in range(1, max_iterations + 1):
        probabilities = _sigmoid(design @ coefficients)
        weights = np.clip(probabilities * (1.0 - probabilities), 1e-8, None)
        gradient = design.T @ (probabilities - targets) + penalty @ coefficients
        hessian = design.T @ (design * weights[:, None]) + penalty
        step = np.linalg.solve(hessian, gradient)
        coefficients -= step
        completed_iterations = iteration
        if float(np.max(np.abs(step))) < tolerance:
            break

    seasons = tuple(sorted(int(value) for value in states["season"].unique()))
    return StateValueModel(
        coefficients=tuple(float(value) for value in coefficients),
        feature_means=tuple(float(value) for value in means),
        feature_scales=tuple(float(value) for value in scales),
        training_seasons=seasons,
        training_observations=states.height,
        ridge_penalty=ridge_penalty,
        iterations=completed_iterations,
    )


def state_feature_matrix(states: pl.DataFrame) -> np.ndarray:
    """Apply the fixed, interpretable Milestone 3 feature transformations."""

    required = (
        "score_differential",
        "game_seconds_remaining",
        "yards_to_goal",
        "yards_to_go",
        "team_timeouts_remaining",
        "opponent_timeouts_remaining",
        "is_home",
        "down",
    )
    missing = [column for column in required if column not in states.columns]
    if missing:
        raise ValueError(f"state rows are missing columns: {', '.join(missing)}")
    if states.select(pl.any_horizontal(pl.col(required).is_null()).any()).item():
        raise ValueError("state-value features cannot contain null values")

    score = states["score_differential"].to_numpy().astype(float)
    seconds = states["game_seconds_remaining"].to_numpy().astype(float)
    yards_to_goal = states["yards_to_goal"].to_numpy().astype(float)
    yards_to_go = states["yards_to_go"].to_numpy().astype(float)
    timeouts = states["team_timeouts_remaining"].to_numpy().astype(float)
    opponent_timeouts = states["opponent_timeouts_remaining"].to_numpy().astype(float)
    home = states["is_home"].cast(pl.Float64).to_numpy()
    down = states["down"].to_numpy()

    time_fraction = np.clip(seconds, 0, 3600) / 3600.0
    late_fraction = 1.0 - time_fraction
    score_pressure = score / np.sqrt(np.maximum(seconds / 60.0, 1.0))
    return np.column_stack(
        (
            score,
            time_fraction,
            score * late_fraction,
            score_pressure,
            (100.0 - yards_to_goal) / 100.0,
            np.clip(yards_to_go, 0, 30) / 10.0,
            timeouts - opponent_timeouts,
            home,
            (down == 2).astype(float),
            (down == 3).astype(float),
            (down == 4).astype(float),
        )
    )


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -35.0, 35.0)))


__all__ = [
    "FEATURE_NAMES",
    "STATE_VALUE_MODEL_VERSION",
    "StateValueModel",
    "fit_state_value_model",
    "state_feature_matrix",
]
