"""Compose empirical transitions with state value from the original-team view."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from coachiq.models.action_baselines import ActionBaselineSet, ActionSupport
from coachiq.models.state import CanonicalState
from coachiq.models.state_value import StateValueModel


@dataclass(frozen=True)
class ActionValueEstimate:
    """One model-based action estimate with finite-support uncertainty."""

    action: str
    expected_win_probability: float | None
    interval_lower: float | None
    interval_upper: float | None
    confidence_level: float
    support: ActionSupport
    transition_samples: int
    uncertainty_method: str = "training-game cluster bootstrap"


def estimate_action_value(
    state: CanonicalState,
    action: str,
    action_models: ActionBaselineSet,
    state_value_model: StateValueModel,
    *,
    bootstrap_replicates: int = 400,
    confidence_level: float = 0.90,
    random_seed: int = 1729,
) -> ActionValueEstimate:
    """Estimate baseline EWP without treating it as a known counterfactual."""

    if bootstrap_replicates < 1:
        raise ValueError("bootstrap_replicates must be positive")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between zero and one")
    distribution = action_models.transition_distribution(action, state)
    if not distribution.support.in_support:
        return ActionValueEstimate(
            action=action,
            expected_win_probability=None,
            interval_lower=None,
            interval_upper=None,
            confidence_level=confidence_level,
            support=distribution.support,
            transition_samples=0,
        )

    possession_values = state_value_model.predict_proba(distribution.states)
    next_teams = distribution.states["evaluation_team"].to_list()
    original_team_values = np.asarray(
        [
            value if team == state.evaluation_team else 1.0 - value
            for value, team in zip(possession_values, next_teams, strict=True)
        ]
    )
    estimate = float(original_team_values.mean())
    lower, upper = _cluster_bootstrap_interval(
        original_team_values,
        distribution.game_clusters,
        replicates=bootstrap_replicates,
        confidence_level=confidence_level,
        seed=random_seed,
    )
    return ActionValueEstimate(
        action=action,
        expected_win_probability=estimate,
        interval_lower=lower,
        interval_upper=upper,
        confidence_level=confidence_level,
        support=distribution.support,
        transition_samples=len(original_team_values),
    )


def estimate_all_actions(
    state: CanonicalState,
    action_models: ActionBaselineSet,
    state_value_model: StateValueModel,
    **kwargs: object,
) -> tuple[ActionValueEstimate, ...]:
    """Estimate go, field-goal, and punt values without choosing a winner."""

    return tuple(
        estimate_action_value(
            state,
            action,
            action_models,
            state_value_model,
            **kwargs,
        )
        for action in ("go", "field_goal", "punt")
    )


def _cluster_bootstrap_interval(
    values: np.ndarray,
    clusters: tuple[str, ...],
    *,
    replicates: int,
    confidence_level: float,
    seed: int,
) -> tuple[float, float]:
    unique_clusters = tuple(sorted(set(clusters)))
    cluster_array = np.asarray(clusters)
    grouped = {cluster: values[cluster_array == cluster] for cluster in unique_clusters}
    rng = np.random.default_rng(seed)
    bootstrap_means = np.empty(replicates)
    for index in range(replicates):
        sampled = rng.choice(unique_clusters, size=len(unique_clusters), replace=True)
        bootstrap_means[index] = np.concatenate(
            [grouped[str(cluster)] for cluster in sampled]
        ).mean()
    tail = (1.0 - confidence_level) / 2.0
    return (
        float(np.quantile(bootstrap_means, tail)),
        float(np.quantile(bootstrap_means, 1.0 - tail)),
    )


__all__ = ["ActionValueEstimate", "estimate_action_value", "estimate_all_actions"]
