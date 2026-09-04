"""Transparent CoachIQ statistical models."""

from coachiq.models.action_baselines import (
    ActionBaselineSet,
    ActionSupport,
    TransitionDistribution,
    canonical_state_from_candidate,
    derive_field_goal_distance,
    fit_action_baselines,
)
from coachiq.models.evaluation import (
    ExpandingSeasonSplit,
    ProbabilityMetrics,
    calibration_table,
    expanding_season_splits,
    expected_calibration_error,
    probability_metrics,
)
from coachiq.models.state import (
    CANONICAL_STATE_COLUMNS,
    CanonicalState,
    build_state_value_rows,
    probability_for_team,
    quarter_from_game_seconds,
)
from coachiq.models.state_value import (
    FEATURE_NAMES,
    StateValueModel,
    fit_state_value_model,
    state_feature_matrix,
)

__all__ = [
    "CANONICAL_STATE_COLUMNS",
    "FEATURE_NAMES",
    "CanonicalState",
    "ExpandingSeasonSplit",
    "ProbabilityMetrics",
    "ActionBaselineSet",
    "ActionSupport",
    "StateValueModel",
    "TransitionDistribution",
    "build_state_value_rows",
    "canonical_state_from_candidate",
    "calibration_table",
    "expanding_season_splits",
    "expected_calibration_error",
    "fit_state_value_model",
    "fit_action_baselines",
    "probability_for_team",
    "probability_metrics",
    "quarter_from_game_seconds",
    "state_feature_matrix",
    "derive_field_goal_distance",
]
