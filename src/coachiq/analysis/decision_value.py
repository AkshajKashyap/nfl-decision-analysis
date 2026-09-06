"""Auditable comparisons of frozen CoachIQ fourth-down action values."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

import numpy as np
import polars as pl

from coachiq.models.action_baselines import ActionBaselineSet, ActionSupport
from coachiq.models.state import CanonicalState
from coachiq.models.state_value import StateValueModel
from coachiq.models.wp_selection import LOCKED_WP_MODEL_VERSION

ACTIONS = ("go", "field_goal", "punt")
PAIRWISE_ACTIONS = (
    ("go", "punt"),
    ("go", "field_goal"),
    ("field_goal", "punt"),
)
ACTION_TRANSITION_MODEL_VERSION = "coachiq-action-transition-v1"
DECISION_VALUE_VERSION = "coachiq-decision-v1"
LATEST_DECISION_DATA_SEASON = 2024
DECISION_BOOTSTRAP_REPLICATES = 200
DECISION_BOOTSTRAP_SEED = 2505


@dataclass(frozen=True)
class DecisionThresholdPolicy:
    """Conservative evidence requirements for a model preference."""

    minimum_gap: float = 0.01
    superiority_probability: float = 0.95
    require_complete_available_support: bool = True
    version: str = "decision-threshold-v1"
    require_zero_overtime_boundary_mass: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_gap <= 1:
            raise ValueError("minimum_gap must be within [0, 1]")
        if not 0.5 <= self.superiority_probability <= 1:
            raise ValueError("superiority_probability must be within [0.5, 1]")


DECISION_THRESHOLD_POLICY_V1 = DecisionThresholdPolicy()


@dataclass(frozen=True, eq=False)
class DecisionBootstrapContext:
    """Reusable shared game weights for many decisions under one fitted model."""

    training_games: tuple[str, ...]
    weights: np.ndarray
    replicates: int
    random_seed: int


@dataclass(frozen=True)
class CanonicalActionValue:
    """One action's modeled value, support, and coherent uncertainty."""

    action: str
    expected_win_probability: float | None
    interval_lower: float | None
    interval_upper: float | None
    confidence_level: float
    bootstrap_replicates: int
    bootstrap_valid_replicates: int
    support_status: str
    support_observations: int
    support_games: int
    available: bool
    sparse: bool
    support_reason: str | None
    overtime_boundary_mass: float
    wp_model_version: str
    action_transition_model_version: str
    uncertainty_method: str = "paired training-game cluster bootstrap"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True)
class PairwiseActionDifference:
    """Bootstrap comparison of two modeled action values."""

    action_a: str
    action_b: str
    available: bool
    difference: float | None
    interval_lower: float | None
    interval_upper: float | None
    probability_a_exceeds_b: float | None
    probability_b_exceeds_a: float | None
    probability_tied: float | None
    confidence_level: float
    bootstrap_replicates: int
    bootstrap_valid_replicates: int
    unavailable_reason: str | None
    uncertainty_method: str = "paired training-game cluster bootstrap"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        return asdict(self)


@dataclass(frozen=True)
class DecisionValueAudit:
    """Canonical model-based audit for one observed fourth-down decision."""

    actual_action: str
    actions: tuple[CanonicalActionValue, ...]
    pairwise_differences: tuple[PairwiseActionDifference, ...]
    supported_action_count: int
    actual_action_ewp: float | None
    highest_supported_action: str | None
    highest_supported_action_ewp: float | None
    raw_action_value_gap: float | None
    classification: str
    classification_reason: str
    model_preferred_action: str | None
    model_preferred_minimum_gap: float | None
    model_preferred_minimum_superiority: float | None
    maximum_overtime_boundary_mass: float
    threshold_policy: DecisionThresholdPolicy
    wp_model_version: str
    action_transition_model_version: str
    decision_value_version: str = DECISION_VALUE_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return the nested audit contract as JSON-serializable values."""

        payload = asdict(self)
        return payload


def audit_decision_value(
    state: CanonicalState,
    actual_action: str,
    action_models: ActionBaselineSet,
    state_value_model: StateValueModel,
    *,
    threshold_policy: DecisionThresholdPolicy = DECISION_THRESHOLD_POLICY_V1,
    bootstrap_replicates: int = DECISION_BOOTSTRAP_REPLICATES,
    confidence_level: float = 0.90,
    random_seed: int = DECISION_BOOTSTRAP_SEED,
    bootstrap_context: DecisionBootstrapContext | None = None,
) -> DecisionValueAudit:
    """Compare supported actions without interpreting differences causally."""

    _validate_inputs(
        state,
        actual_action,
        action_models,
        state_value_model,
        bootstrap_replicates,
        confidence_level,
    )
    distributions = {
        action: action_models.transition_distribution(action, state)
        for action in ACTIONS
    }
    samples: dict[str, np.ndarray] = {}
    overtime_boundary_mass = {
        action: _overtime_boundary_mass(state, distribution.states)
        for action, distribution in distributions.items()
    }
    for action, distribution in distributions.items():
        if not distribution.support.in_support:
            continue
        possession_values = state_value_model.predict_proba(distribution.states)
        next_teams = distribution.states["evaluation_team"].to_numpy()
        samples[action] = np.where(
            next_teams == state.evaluation_team,
            possession_values,
            1.0 - possession_values,
        )

    context = bootstrap_context or build_decision_bootstrap_context(
        action_models,
        bootstrap_replicates=bootstrap_replicates,
        random_seed=random_seed,
    )
    if context.replicates != bootstrap_replicates:
        raise ValueError("bootstrap context replicate count does not match")
    expected_training_games = tuple(
        sorted(str(value) for value in action_models.training_rows["game_id"].unique())
    )
    if context.training_games != expected_training_games:
        raise ValueError("bootstrap context training games do not match action model")
    training_games = context.training_games
    weights = context.weights
    draws = {
        action: _action_bootstrap_draws(
            values,
            distributions[action].game_clusters,
            training_games,
            weights,
        )
        for action, values in samples.items()
    }

    action_values = tuple(
        _action_value_output(
            action,
            distributions[action].support,
            samples.get(action),
            draws.get(action),
            state_value_model.version,
            bootstrap_replicates,
            confidence_level,
            overtime_boundary_mass[action],
        )
        for action in ACTIONS
    )
    pairs = tuple(
        _pairwise_output(
            action_a,
            action_b,
            samples,
            draws,
            bootstrap_replicates,
            confidence_level,
        )
        for action_a, action_b in PAIRWISE_ACTIONS
    )
    return _decision_output(
        actual_action,
        action_values,
        pairs,
        threshold_policy,
        state_value_model.version,
    )


def support_status(support: ActionSupport) -> str:
    """Map detailed action support to the canonical decision-layer label."""

    if not support.available:
        return "unavailable"
    if not support.in_support:
        return "unsupported"
    if support.sparse:
        return "sparse"
    return "supported"


def format_decision_value_audit(audit: DecisionValueAudit) -> str:
    """Return a stable, terminology-safe text rendering of one audit."""

    lines = [
        f"actual action: {audit.actual_action}",
        f"classification: {audit.classification} ({audit.classification_reason})",
    ]
    for value in audit.actions:
        if value.expected_win_probability is None:
            lines.append(
                f"{value.action}: {value.support_status}; "
                f"n={value.support_observations}, games={value.support_games}, "
                f"reason={value.support_reason}"
            )
        else:
            lines.append(
                f"{value.action}: EWP={value.expected_win_probability:.4f}, "
                f"interval=[{value.interval_lower:.4f}, {value.interval_upper:.4f}], "
                f"support={value.support_status}, n={value.support_observations}, "
                f"games={value.support_games}, "
                f"OT-boundary-mass={value.overtime_boundary_mass:.3f}"
            )
    for pair in audit.pairwise_differences:
        if not pair.available:
            lines.append(
                f"{pair.action_a} minus {pair.action_b}: unavailable "
                f"({pair.unavailable_reason})"
            )
        else:
            lines.append(
                f"{pair.action_a} minus {pair.action_b}: "
                f"difference={pair.difference:+.4f}, "
                f"interval=[{pair.interval_lower:+.4f}, {pair.interval_upper:+.4f}], "
                f"P(A>B)={pair.probability_a_exceeds_b:.3f}, "
                f"P(B>A)={pair.probability_b_exceeds_a:.3f}, "
                f"P(tie)={pair.probability_tied:.3f}"
            )
    gap = (
        "unavailable"
        if audit.raw_action_value_gap is None
        else f"{audit.raw_action_value_gap:.4f}"
    )
    lines.extend(
        (
            f"actual-action value gap: {gap}",
            f"versions: decision={audit.decision_value_version}, "
            f"WP={audit.wp_model_version}, "
            f"transitions={audit.action_transition_model_version}",
        )
    )
    return "\n".join(lines)


def build_decision_bootstrap_context(
    action_models: ActionBaselineSet,
    *,
    bootstrap_replicates: int = DECISION_BOOTSTRAP_REPLICATES,
    random_seed: int = DECISION_BOOTSTRAP_SEED,
) -> DecisionBootstrapContext:
    """Build reusable paired weights over the chronological training games."""

    if bootstrap_replicates < 1:
        raise ValueError("bootstrap_replicates must be positive")
    training_games = tuple(
        sorted(str(value) for value in action_models.training_rows["game_id"].unique())
    )
    return DecisionBootstrapContext(
        training_games=training_games,
        weights=_bootstrap_game_weights(
            training_games, bootstrap_replicates, random_seed
        ),
        replicates=bootstrap_replicates,
        random_seed=random_seed,
    )


def _action_value_output(
    action: str,
    support: ActionSupport,
    values: np.ndarray | None,
    draws: np.ndarray | None,
    wp_version: str,
    replicates: int,
    confidence_level: float,
    overtime_boundary_mass: float,
) -> CanonicalActionValue:
    if values is None or draws is None:
        estimate = lower = upper = None
        valid = 0
    else:
        estimate = float(values.mean())
        finite = draws[np.isfinite(draws)]
        valid = int(finite.size)
        if not valid:
            lower = upper = None
        else:
            tail = (1.0 - confidence_level) / 2.0
            lower = float(np.quantile(finite, tail))
            upper = float(np.quantile(finite, 1.0 - tail))
    return CanonicalActionValue(
        action=action,
        expected_win_probability=estimate,
        interval_lower=lower,
        interval_upper=upper,
        confidence_level=confidence_level,
        bootstrap_replicates=replicates,
        bootstrap_valid_replicates=valid,
        support_status=support_status(support),
        support_observations=support.observation_count,
        support_games=support.game_count,
        available=support.available,
        sparse=support.sparse,
        support_reason=support.reason,
        overtime_boundary_mass=overtime_boundary_mass,
        wp_model_version=wp_version,
        action_transition_model_version=ACTION_TRANSITION_MODEL_VERSION,
    )


def _pairwise_output(
    action_a: str,
    action_b: str,
    samples: dict[str, np.ndarray],
    draws: dict[str, np.ndarray],
    replicates: int,
    confidence_level: float,
) -> PairwiseActionDifference:
    if action_a not in samples or action_b not in samples:
        return PairwiseActionDifference(
            action_a=action_a,
            action_b=action_b,
            available=False,
            difference=None,
            interval_lower=None,
            interval_upper=None,
            probability_a_exceeds_b=None,
            probability_b_exceeds_a=None,
            probability_tied=None,
            confidence_level=confidence_level,
            bootstrap_replicates=replicates,
            bootstrap_valid_replicates=0,
            unavailable_reason="one_or_both_actions_unsupported",
        )
    differences = draws[action_a] - draws[action_b]
    finite = differences[np.isfinite(differences)]
    if not finite.size:
        return PairwiseActionDifference(
            action_a=action_a,
            action_b=action_b,
            available=False,
            difference=float(samples[action_a].mean() - samples[action_b].mean()),
            interval_lower=None,
            interval_upper=None,
            probability_a_exceeds_b=None,
            probability_b_exceeds_a=None,
            probability_tied=None,
            confidence_level=confidence_level,
            bootstrap_replicates=replicates,
            bootstrap_valid_replicates=0,
            unavailable_reason="no_jointly_valid_bootstrap_draws",
        )
    tail = (1.0 - confidence_level) / 2.0
    tied = np.isclose(finite, 0.0, rtol=0.0, atol=1e-12)
    return PairwiseActionDifference(
        action_a=action_a,
        action_b=action_b,
        available=True,
        difference=float(samples[action_a].mean() - samples[action_b].mean()),
        interval_lower=float(np.quantile(finite, tail)),
        interval_upper=float(np.quantile(finite, 1.0 - tail)),
        probability_a_exceeds_b=float(np.mean((finite > 0) & ~tied)),
        probability_b_exceeds_a=float(np.mean((finite < 0) & ~tied)),
        probability_tied=float(np.mean(tied)),
        confidence_level=confidence_level,
        bootstrap_replicates=replicates,
        bootstrap_valid_replicates=int(finite.size),
        unavailable_reason=None,
    )


def _decision_output(
    actual_action: str,
    actions: tuple[CanonicalActionValue, ...],
    pairs: tuple[PairwiseActionDifference, ...],
    policy: DecisionThresholdPolicy,
    wp_version: str,
) -> DecisionValueAudit:
    by_action = {value.action: value for value in actions}
    supported = [
        value for value in actions if value.expected_win_probability is not None
    ]
    actual = by_action[actual_action]
    ranked = sorted(
        supported,
        key=lambda value: (
            -float(value.expected_win_probability),
            ACTIONS.index(value.action),
        ),
    )
    highest = ranked[0] if ranked else None
    meaningful_comparison = actual in supported and len(supported) >= 2
    gap = (
        float(highest.expected_win_probability - actual.expected_win_probability)
        if highest is not None and meaningful_comparison
        else None
    )
    classification, reason, minimum_gap, minimum_superiority = _classify(
        actual,
        actions,
        pairs,
        ranked,
        policy,
    )
    return DecisionValueAudit(
        actual_action=actual_action,
        actions=actions,
        pairwise_differences=pairs,
        supported_action_count=len(supported),
        actual_action_ewp=actual.expected_win_probability,
        highest_supported_action=highest.action if highest else None,
        highest_supported_action_ewp=(
            highest.expected_win_probability if highest else None
        ),
        raw_action_value_gap=gap,
        classification=classification,
        classification_reason=reason,
        model_preferred_action=highest.action if highest else None,
        model_preferred_minimum_gap=minimum_gap,
        model_preferred_minimum_superiority=minimum_superiority,
        maximum_overtime_boundary_mass=max(
            value.overtime_boundary_mass for value in supported
        )
        if supported
        else 0.0,
        threshold_policy=policy,
        wp_model_version=wp_version,
        action_transition_model_version=ACTION_TRANSITION_MODEL_VERSION,
    )


def _classify(
    actual: CanonicalActionValue,
    actions: tuple[CanonicalActionValue, ...],
    pairs: tuple[PairwiseActionDifference, ...],
    ranked: list[CanonicalActionValue],
    policy: DecisionThresholdPolicy,
) -> tuple[str, str, float | None, float | None]:
    if actual.expected_win_probability is None:
        return "insufficient_support", "actual_action_unsupported", None, None
    if len(ranked) < 2:
        return "insufficient_support", "fewer_than_two_supported_actions", None, None
    if policy.require_zero_overtime_boundary_mass and any(
        value.overtime_boundary_mass > 0 for value in ranked
    ):
        return (
            "limited_support",
            "supported_action_has_unmodeled_overtime_transition_mass",
            None,
            None,
        )
    relevant = [value for value in actions if value.available]
    if any(value.sparse for value in ranked):
        return "limited_support", "one_or_more_supported_actions_are_sparse", None, None
    if policy.require_complete_available_support and any(
        value.expected_win_probability is None for value in relevant
    ):
        return "limited_support", "available_action_lacks_support", None, None

    preferred = ranked[0]
    minimum_gap = min(
        float(preferred.expected_win_probability - other.expected_win_probability)
        for other in ranked[1:]
    )
    superiority = [
        _probability_first_exceeds_second(preferred.action, other.action, pairs)
        for other in ranked[1:]
    ]
    if any(value is None for value in superiority):
        return (
            "limited_support",
            "pairwise_uncertainty_unavailable",
            minimum_gap,
            None,
        )
    minimum_superiority = min(
        float(value) for value in superiority if value is not None
    )
    if (
        minimum_gap >= policy.minimum_gap
        and minimum_superiority >= policy.superiority_probability
    ):
        return (
            "clear_model_preference",
            "gap_and_pairwise_evidence_meet_policy",
            minimum_gap,
            minimum_superiority,
        )
    return (
        "close_call",
        "gap_or_pairwise_evidence_below_policy",
        minimum_gap,
        minimum_superiority,
    )


def _probability_first_exceeds_second(
    first: str,
    second: str,
    pairs: tuple[PairwiseActionDifference, ...],
) -> float | None:
    for pair in pairs:
        if pair.action_a == first and pair.action_b == second:
            return pair.probability_a_exceeds_b
        if pair.action_a == second and pair.action_b == first:
            return pair.probability_b_exceeds_a
    return None


def _action_bootstrap_draws(
    values: np.ndarray,
    clusters: tuple[str, ...],
    training_games: tuple[str, ...],
    weights: np.ndarray,
) -> np.ndarray:
    game_indexes = {game: index for index, game in enumerate(training_games)}
    indexes = np.fromiter(
        (game_indexes[str(cluster)] for cluster in clusters),
        dtype=np.int64,
        count=len(clusters),
    )
    counts = np.bincount(indexes, minlength=len(training_games)).astype(float)
    sums = np.bincount(indexes, weights=values, minlength=len(training_games))
    occupied = counts > 0
    selected_weights = weights[:, occupied]
    denominators = selected_weights @ counts[occupied]
    numerators = selected_weights @ sums[occupied]
    return np.divide(
        numerators,
        denominators,
        out=np.full(weights.shape[0], np.nan),
        where=denominators > 0,
    )


def _overtime_boundary_mass(state: CanonicalState, states: pl.DataFrame) -> float:
    """Return empirical mass transported to a tied regulation-expiration state."""

    if state.quarter != 4 or not states.height:
        return 0.0
    boundary = states.select(
        (
            (pl.col("game_seconds_remaining") <= 0)
            & (pl.col("score_differential") == 0)
        ).sum()
    ).item()
    return float(boundary) / states.height


@lru_cache(maxsize=16)
def _bootstrap_game_weights(
    training_games: tuple[str, ...], replicates: int, seed: int
) -> np.ndarray:
    game_count = len(training_games)
    if not game_count:
        raise ValueError("action baseline has no training games")
    rng = np.random.default_rng(seed)
    probabilities = np.full(game_count, 1.0 / game_count)
    return rng.multinomial(game_count, probabilities, size=replicates)


def _validate_inputs(
    state: CanonicalState,
    actual_action: str,
    action_models: ActionBaselineSet,
    state_value_model: StateValueModel,
    bootstrap_replicates: int,
    confidence_level: float,
) -> None:
    if state.quarter not in (1, 2, 3, 4):
        raise ValueError("decision v1 supports regulation quarters 1-4 only")
    if actual_action not in ACTIONS:
        raise ValueError(f"unsupported actual action: {actual_action}")
    if state_value_model.version != LOCKED_WP_MODEL_VERSION:
        raise ValueError(f"decision v1 requires {LOCKED_WP_MODEL_VERSION}")
    if (
        state_value_model.training_seasons
        and max(state_value_model.training_seasons) > 2024
    ):
        raise ValueError("2025 and later seasons are protected")
    if action_models.training_seasons and max(action_models.training_seasons) > 2024:
        raise ValueError("2025 and later seasons are protected")
    if bootstrap_replicates < 1:
        raise ValueError("bootstrap_replicates must be positive")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between zero and one")


__all__ = [
    "ACTIONS",
    "ACTION_TRANSITION_MODEL_VERSION",
    "DECISION_THRESHOLD_POLICY_V1",
    "DECISION_BOOTSTRAP_REPLICATES",
    "DECISION_BOOTSTRAP_SEED",
    "DECISION_VALUE_VERSION",
    "LATEST_DECISION_DATA_SEASON",
    "PAIRWISE_ACTIONS",
    "CanonicalActionValue",
    "DecisionBootstrapContext",
    "DecisionThresholdPolicy",
    "DecisionValueAudit",
    "PairwiseActionDifference",
    "audit_decision_value",
    "build_decision_bootstrap_context",
    "format_decision_value_audit",
    "support_status",
]
