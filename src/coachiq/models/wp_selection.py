"""Locked, chronological selection helpers for CoachIQ state value."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import polars as pl

from coachiq.models.evaluation import (
    calibration_table,
    expected_calibration_error,
    probability_metrics,
)
from coachiq.models.state_value import (
    BASELINE_FEATURE_SPEC,
    EXPANDED_FEATURE_SPEC,
    FEATURE_NAMES_BY_SPEC,
    PREGAME_BASELINE_FEATURE_SPEC,
    PREGAME_FEATURE_SPEC,
    StateValueModel,
    fit_state_value_model,
)

DEVELOPMENT_EVALUATION_SEASONS = (2020, 2021, 2022, 2023)
PRELOCK_VALIDATION_SEASON = 2024
LATEST_ALLOWED_SEASON = 2024
CLUSTER_BOOTSTRAP_REPLICATES = 1000
SPARSE_CALIBRATION_BAND_ROWS = 500
LOCKED_WP_CANDIDATE_ID = "D"
LOCKED_WP_MODEL_VERSION = "coachiq-wp-v1"
LOCKED_WP_USES_RECALIBRATION = False


@dataclass(frozen=True)
class WpCandidateSpec:
    """One deliberately bounded state-value candidate."""

    candidate_id: str
    description: str
    feature_spec: str
    ridge_penalty: float
    version: str

    @property
    def feature_names(self) -> tuple[str, ...]:
        return FEATURE_NAMES_BY_SPEC[self.feature_spec]


@dataclass(frozen=True)
class LogisticRecalibrator:
    """Intercept/slope recalibration fitted on prior-season predictions."""

    intercept: float
    slope: float
    training_seasons: tuple[int, ...]
    calibration_season: int
    observations: int

    def predict(self, probabilities: np.ndarray | list[float]) -> np.ndarray:
        values = np.asarray(probabilities, dtype=float)
        logits = _logit(values)
        return _sigmoid(self.intercept + self.slope * logits)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


WP_CANDIDATES = (
    WpCandidateSpec(
        candidate_id="A",
        description="Milestone 3 ridge-logistic baseline",
        feature_spec=BASELINE_FEATURE_SPEC,
        ridge_penalty=1.0,
        version="state-value-logistic-v1",
    ),
    WpCandidateSpec(
        candidate_id="B",
        description="Expanded interpretable ridge-logistic basis",
        feature_spec=EXPANDED_FEATURE_SPEC,
        ridge_penalty=1.0,
        version="state-value-logistic-expanded-dev",
    ),
    WpCandidateSpec(
        candidate_id="C",
        description="Expanded basis plus clock-decayed pregame strength",
        feature_spec=PREGAME_FEATURE_SPEC,
        ridge_penalty=1.0,
        version="state-value-logistic-pregame-dev",
    ),
    WpCandidateSpec(
        candidate_id="D",
        description="Complexity-pruned baseline plus pregame strength",
        feature_spec=PREGAME_BASELINE_FEATURE_SPEC,
        ridge_penalty=1.0,
        version="state-value-logistic-pregame-pruned-dev",
    ),
)


def candidate_by_id(candidate_id: str) -> WpCandidateSpec:
    """Return a declared candidate or raise for an unknown identifier."""

    for candidate in WP_CANDIDATES:
        if candidate.candidate_id == candidate_id:
            return candidate
    raise ValueError(f"unknown WP candidate: {candidate_id}")


def fit_wp_candidate(states: pl.DataFrame, spec: WpCandidateSpec) -> StateValueModel:
    """Fit one candidate with its frozen development specification."""

    return fit_state_value_model(
        states,
        ridge_penalty=spec.ridge_penalty,
        feature_spec=spec.feature_spec,
        version=spec.version,
    )


def fit_locked_wp_model(states: pl.DataFrame) -> StateValueModel:
    """Fit the frozen CoachIQ v1 specification on pre-2025 state rows."""

    if not states.height:
        raise ValueError("locked WP training rows cannot be empty")
    if int(states["season"].max()) > LATEST_ALLOWED_SEASON:
        raise ValueError("2025 and later seasons are protected")
    spec = candidate_by_id(LOCKED_WP_CANDIDATE_ID)
    return fit_state_value_model(
        states,
        ridge_penalty=spec.ridge_penalty,
        feature_spec=spec.feature_spec,
        version=LOCKED_WP_MODEL_VERSION,
    )


def fit_logistic_recalibrator(
    targets: np.ndarray | list[float],
    probabilities: np.ndarray | list[float],
    *,
    training_seasons: tuple[int, ...],
    calibration_season: int,
    max_iterations: int = 50,
    tolerance: float = 1e-10,
) -> LogisticRecalibrator:
    """Fit deterministic Platt-style intercept/slope recalibration."""

    observed = np.asarray(targets, dtype=float)
    predicted = np.asarray(probabilities, dtype=float)
    probability_metrics(observed, predicted)
    design = np.column_stack((np.ones(observed.size), _logit(predicted)))
    coefficients = np.array([0.0, 1.0])
    for _ in range(max_iterations):
        fitted = _sigmoid(design @ coefficients)
        weights = np.clip(fitted * (1.0 - fitted), 1e-8, None)
        gradient = design.T @ (fitted - observed)
        hessian = design.T @ (design * weights[:, None])
        step = np.linalg.solve(hessian, gradient)
        coefficients -= step
        if float(np.max(np.abs(step))) < tolerance:
            break
    return LogisticRecalibrator(
        intercept=float(coefficients[0]),
        slope=float(coefficients[1]),
        training_seasons=training_seasons,
        calibration_season=calibration_season,
        observations=int(observed.size),
    )


def fit_fold_recalibrator(
    training_states: pl.DataFrame, spec: WpCandidateSpec
) -> LogisticRecalibrator:
    """Fit recalibration on the latest training season using only earlier fit data."""

    seasons = tuple(sorted(int(value) for value in training_states["season"].unique()))
    if len(seasons) < 2:
        raise ValueError("recalibration requires at least two training seasons")
    calibration_season = seasons[-1]
    fitting_seasons = seasons[:-1]
    fitting_rows = training_states.filter(pl.col("season").is_in(fitting_seasons))
    calibration_rows = training_states.filter(pl.col("season") == calibration_season)
    base_model = fit_wp_candidate(fitting_rows, spec)
    probabilities = base_model.predict_proba(calibration_rows)
    return fit_logistic_recalibrator(
        calibration_rows["eventual_win_equivalent"].to_numpy(),
        probabilities,
        training_seasons=fitting_seasons,
        calibration_season=calibration_season,
    )


def probability_report(
    states: pl.DataFrame, probabilities: np.ndarray | list[float]
) -> dict[str, object]:
    """Return proper scores, fixed bands, and game-state regime diagnostics."""

    targets = states["eventual_win_equivalent"].to_numpy()
    predicted = np.asarray(probabilities, dtype=float)
    metrics = probability_metrics(targets, predicted)
    calibration = calibration_table(targets, predicted)
    return {
        **asdict(metrics),
        "expected_calibration_error": expected_calibration_error(calibration),
        "calibration": calibration_band_report(targets, predicted),
        "clock_regimes": _regime_reports(states, predicted, _clock_regimes(states)),
        "score_regimes": _regime_reports(states, predicted, _score_regimes(states)),
    }


def calibration_band_report(
    targets: np.ndarray | list[float],
    probabilities: np.ndarray | list[float],
    *,
    bins: int = 10,
) -> list[dict[str, object]]:
    """Return all fixed-width bands, explicitly marking sparse and empty bands."""

    observed = np.asarray(targets, dtype=float)
    predicted = np.asarray(probabilities, dtype=float)
    probability_metrics(observed, predicted)
    indexes = np.minimum((predicted * bins).astype(int), bins - 1)
    rows: list[dict[str, object]] = []
    for index in range(bins):
        selected = indexes == index
        count = int(selected.sum())
        mean_prediction = float(predicted[selected].mean()) if count else None
        observed_rate = float(observed[selected].mean()) if count else None
        gap = (
            float(abs(mean_prediction - observed_rate))
            if mean_prediction is not None and observed_rate is not None
            else None
        )
        rows.append(
            {
                "band": f"{index * 10}-{(index + 1) * 10}%",
                "lower": index / bins,
                "upper": (index + 1) / bins,
                "observations": count,
                "mean_prediction": mean_prediction,
                "observed_rate": observed_rate,
                "calibration_gap": gap,
                "sparse": count < SPARSE_CALIBRATION_BAND_ROWS,
            }
        )
    return rows


def clustered_metric_difference(
    targets: np.ndarray | list[float],
    candidate_probabilities: np.ndarray | list[float],
    reference_probabilities: np.ndarray | list[float],
    game_ids: np.ndarray | list[str],
    *,
    replicates: int = CLUSTER_BOOTSTRAP_REPLICATES,
    confidence_level: float = 0.90,
    seed: int = 4104,
) -> dict[str, object]:
    """Compare probabilities using a deterministic game-cluster bootstrap."""

    observed = np.asarray(targets, dtype=float)
    candidate = np.asarray(candidate_probabilities, dtype=float)
    reference = np.asarray(reference_probabilities, dtype=float)
    clusters = np.asarray(game_ids)
    probability_metrics(observed, candidate)
    probability_metrics(observed, reference)
    if clusters.shape != observed.shape:
        raise ValueError("game IDs must align with probability rows")
    if replicates < 1:
        raise ValueError("bootstrap replicates must be positive")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence level must be between zero and one")

    candidate_numerical = np.clip(candidate, 1e-15, 1.0 - 1e-15)
    reference_numerical = np.clip(reference, 1e-15, 1.0 - 1e-15)
    log_difference = -(
        observed * np.log(candidate_numerical)
        + (1.0 - observed) * np.log(1.0 - candidate_numerical)
    ) + (
        observed * np.log(reference_numerical)
        + (1.0 - observed) * np.log(1.0 - reference_numerical)
    )
    brier_difference = (candidate - observed) ** 2 - (reference - observed) ** 2
    unique_clusters, inverse = np.unique(clusters, return_inverse=True)
    counts = np.bincount(inverse).astype(float)
    log_sums = np.bincount(inverse, weights=log_difference)
    brier_sums = np.bincount(inverse, weights=brier_difference)
    rng = np.random.default_rng(seed)
    sampled = rng.integers(
        0, len(unique_clusters), size=(replicates, len(unique_clusters))
    )
    sampled_counts = counts[sampled].sum(axis=1)
    log_replicates = log_sums[sampled].sum(axis=1) / sampled_counts
    brier_replicates = brier_sums[sampled].sum(axis=1) / sampled_counts
    tail = (1.0 - confidence_level) / 2.0
    return {
        "candidate_minus_reference": True,
        "confidence_level": confidence_level,
        "replicates": replicates,
        "games": len(unique_clusters),
        "log_loss": {
            "difference": float(log_difference.mean()),
            "lower": float(np.quantile(log_replicates, tail)),
            "upper": float(np.quantile(log_replicates, 1.0 - tail)),
        },
        "brier_score": {
            "difference": float(brier_difference.mean()),
            "lower": float(np.quantile(brier_replicates, tail)),
            "upper": float(np.quantile(brier_replicates, 1.0 - tail)),
        },
    }


def property_grid_report(
    model: StateValueModel,
    recalibrator: LogisticRecalibrator | None = None,
) -> dict[str, object]:
    """Audit football directionality on a deterministic grid."""

    def predict(
        score: float,
        seconds: float,
        yards_to_goal: float,
        yards_to_go: float,
        is_home: bool,
        spread: float = 0.0,
    ) -> float:
        frame = pl.DataFrame(
            {
                "score_differential": [score],
                "game_seconds_remaining": [seconds],
                "yards_to_goal": [yards_to_goal],
                "yards_to_go": [yards_to_go],
                "team_timeouts_remaining": [3.0],
                "opponent_timeouts_remaining": [3.0],
                "is_home": [is_home],
                "down": [4],
                "team_pregame_spread": [spread],
            }
        )
        value = model.predict_proba(frame)
        if recalibrator is not None:
            value = recalibrator.predict(value)
        return float(value[0])

    checks: dict[str, dict[str, float | int]] = {}
    violation_sizes: dict[str, list[float]] = {
        "score": [],
        "lead_time": [],
        "deficit_time": [],
        "field_position": [],
        "pregame_strength": [],
    }
    totals = {name: 0 for name in violation_sizes}
    for is_home in (False, True):
        for yards_to_goal in (20.0, 50.0, 80.0):
            for yards_to_go in (1.0, 5.0, 12.0):
                score_values = [
                    predict(score, 900, yards_to_goal, yards_to_go, is_home)
                    for score in (-21, -14, -7, -3, 0, 3, 7, 14, 21)
                ]
                _record_direction(
                    score_values,
                    increasing=True,
                    name="score",
                    totals=totals,
                    violations=violation_sizes,
                )
                lead_values = [
                    predict(7, seconds, yards_to_goal, yards_to_go, is_home)
                    for seconds in (3600, 2700, 1800, 900, 300, 120, 30)
                ]
                _record_direction(
                    lead_values,
                    increasing=True,
                    name="lead_time",
                    totals=totals,
                    violations=violation_sizes,
                )
                deficit_values = [
                    predict(-7, seconds, yards_to_goal, yards_to_go, is_home)
                    for seconds in (3600, 2700, 1800, 900, 300, 120, 30)
                ]
                _record_direction(
                    deficit_values,
                    increasing=False,
                    name="deficit_time",
                    totals=totals,
                    violations=violation_sizes,
                )
                field_values = [
                    predict(0, 900, yard, yards_to_go, is_home)
                    for yard in (90, 70, 50, 30, 10)
                ]
                _record_direction(
                    field_values,
                    increasing=True,
                    name="field_position",
                    totals=totals,
                    violations=violation_sizes,
                )
                strength_values = [
                    predict(0, 1800, yards_to_goal, yards_to_go, is_home, spread)
                    for spread in (-14, -7, 0, 7, 14)
                ]
                _record_direction(
                    strength_values,
                    increasing=True,
                    name="pregame_strength",
                    totals=totals,
                    violations=violation_sizes,
                )
    for name, total in totals.items():
        values = violation_sizes[name]
        checks[name] = {
            "comparisons": total,
            "violations": len(values),
            "maximum_violation": max(values, default=0.0),
        }

    clocks = (3600, 900, 300, 120, 30, 0)
    spread_ranges = []
    score_ranges = []
    for seconds in clocks:
        spread_probabilities = [
            predict(0, seconds, 50, 2, True, spread) for spread in (-14, 14)
        ]
        score_probabilities = [
            predict(score, seconds, 50, 2, True, 0) for score in (-7, 7)
        ]
        spread_ranges.append(spread_probabilities[1] - spread_probabilities[0])
        score_ranges.append(score_probabilities[1] - score_probabilities[0])
    late_dominance_violations = int(
        (np.diff(spread_ranges) > 1e-12).sum() + (np.diff(score_ranges) < -1e-12).sum()
    )
    probabilities = [
        predict(score, seconds, yard, distance, home, spread)
        for score in (-28, -14, 0, 14, 28)
        for seconds in clocks
        for yard in (1, 20, 50, 80, 99)
        for distance in (1, 5, 15)
        for home in (False, True)
        for spread in (-14, 0, 14)
    ]
    return {
        "checks": checks,
        "late_game_dominance": {
            "clocks": list(clocks),
            "pregame_probability_range": spread_ranges,
            "score_probability_range": score_ranges,
            "violations": late_dominance_violations,
        },
        "probability_minimum": min(probabilities),
        "probability_maximum": max(probabilities),
    }


def _record_direction(
    values: list[float],
    *,
    increasing: bool,
    name: str,
    totals: dict[str, int],
    violations: dict[str, list[float]],
) -> None:
    differences = np.diff(values)
    bad = differences < -1e-12 if increasing else differences > 1e-12
    totals[name] += len(differences)
    violations[name].extend(float(abs(value)) for value in differences[bad])


def _regime_reports(
    states: pl.DataFrame,
    probabilities: np.ndarray,
    regimes: dict[str, np.ndarray],
) -> dict[str, object]:
    targets = states["eventual_win_equivalent"].to_numpy()
    reports: dict[str, object] = {}
    for name, selected in regimes.items():
        count = int(selected.sum())
        if not count:
            continue
        metrics = probability_metrics(targets[selected], probabilities[selected])
        calibration = calibration_table(targets[selected], probabilities[selected])
        reports[name] = {
            **asdict(metrics),
            "expected_calibration_error": expected_calibration_error(calibration),
            "calibration": calibration_band_report(
                targets[selected], probabilities[selected]
            ),
        }
    return reports


def _clock_regimes(states: pl.DataFrame) -> dict[str, np.ndarray]:
    seconds = states["game_seconds_remaining"].to_numpy()
    return {
        "first_half": seconds > 1800,
        "third_quarter": (seconds > 900) & (seconds <= 1800),
        "fourth_quarter_over_5_minutes": (seconds > 300) & (seconds <= 900),
        "final_5_minutes": seconds <= 300,
        "final_2_minutes": seconds <= 120,
    }


def _score_regimes(states: pl.DataFrame) -> dict[str, np.ndarray]:
    margin = np.abs(states["score_differential"].to_numpy())
    return {
        "tied": margin == 0,
        "within_3_not_tied": (margin > 0) & (margin <= 3),
        "within_7_over_3": (margin > 3) & (margin <= 7),
        "margin_over_7": margin > 7,
    }


def _logit(probabilities: np.ndarray) -> np.ndarray:
    values = np.clip(probabilities, 1e-12, 1.0 - 1e-12)
    return np.log(values / (1.0 - values))


def _sigmoid(values: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(values, -35.0, 35.0)))


__all__ = [
    "CLUSTER_BOOTSTRAP_REPLICATES",
    "DEVELOPMENT_EVALUATION_SEASONS",
    "LATEST_ALLOWED_SEASON",
    "LOCKED_WP_CANDIDATE_ID",
    "LOCKED_WP_MODEL_VERSION",
    "LOCKED_WP_USES_RECALIBRATION",
    "PRELOCK_VALIDATION_SEASON",
    "WP_CANDIDATES",
    "LogisticRecalibrator",
    "WpCandidateSpec",
    "calibration_band_report",
    "candidate_by_id",
    "clustered_metric_difference",
    "fit_fold_recalibrator",
    "fit_logistic_recalibrator",
    "fit_locked_wp_model",
    "fit_wp_candidate",
    "probability_report",
    "property_grid_report",
]
