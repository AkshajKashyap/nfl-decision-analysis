"""Conservative publication eligibility around frozen decision-v1 outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from coachiq.analysis.decision_value import (
    ACTIONS,
    DECISION_THRESHOLD_POLICY_V1,
    DecisionValueAudit,
)
from coachiq.models.action_baselines import ActionBaselineSet
from coachiq.models.state import CanonicalState

PUBLICATION_POLICY_VERSION = "coachiq-publication-v1"
PUBLICATION_FIELD_CLIPPING_LIMIT = 0.10
PUBLICATION_CLOCK_CLIPPING_LIMIT = 0.0


@dataclass(frozen=True)
class PublicationPolicy:
    """Safety gates that do not alter scientific decision classification."""

    maximum_field_clipping_mass: float
    maximum_clock_clipping_mass: float
    require_clear_model_preference: bool = True
    require_actual_action_supported: bool = True
    require_all_available_actions_supported: bool = True
    withhold_any_sparse_supported_action: bool = True
    require_zero_overtime_boundary_mass: bool = True
    version: str = PUBLICATION_POLICY_VERSION

    def __post_init__(self) -> None:
        if not 0 <= self.maximum_field_clipping_mass <= 1:
            raise ValueError("maximum field clipping mass must be within [0, 1]")
        if not 0 <= self.maximum_clock_clipping_mass <= 1:
            raise ValueError("maximum clock clipping mass must be within [0, 1]")


PUBLICATION_POLICY_V1 = PublicationPolicy(
    maximum_field_clipping_mass=PUBLICATION_FIELD_CLIPPING_LIMIT,
    maximum_clock_clipping_mass=PUBLICATION_CLOCK_CLIPPING_LIMIT,
)


@dataclass(frozen=True)
class SafetyDiagnostics:
    """Pre-clip transport mass and other model-form publication diagnostics."""

    field_clipping_mass_by_action: dict[str, float | None]
    clock_clipping_mass_by_action: dict[str, float | None]
    maximum_field_clipping_mass: float
    maximum_clock_clipping_mass: float
    maximum_overtime_boundary_mass: float
    sparse_supported_action: bool
    unsupported_available_action: bool
    actual_action_supported: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PublicationDecision:
    """Publication result kept separate from decision-v1 classification."""

    status: str
    publishable: bool
    withholding_reasons: tuple[str, ...]
    internal_explanation: str | None
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def transition_clipping_diagnostics(
    state: CanonicalState,
    actual_action: str,
    action_models: ActionBaselineSet,
) -> SafetyDiagnostics:
    """Measure mass v1 clips before its field and clock boundary transport."""

    field: dict[str, float | None] = {}
    clock: dict[str, float | None] = {}
    support_by_action = {
        action: action_models.support(action, state) for action in ACTIONS
    }
    for action in ACTIONS:
        support = support_by_action[action]
        if not support.in_support:
            field[action] = None
            clock[action] = None
            continue
        # This deliberately diagnoses the exact empirical cell consumed by frozen
        # action-transition-v1 without changing that model's public contract.
        rows = action_models._comparable_rows(action, state)  # noqa: SLF001
        raw_field = state.yards_to_goal + rows["decision_yards_to_goal_delta"]
        field_clipped = ~rows["field_position_resets"] & (
            (raw_field < 1.0) | (raw_field > 99.0)
        )
        raw_clock = state.game_seconds_remaining - rows["elapsed_seconds"]
        field[action] = float(field_clipped.sum()) / rows.height
        clock[action] = float((raw_clock < 0.0).sum()) / rows.height

    supported_actions = [
        action for action, support in support_by_action.items() if support.in_support
    ]
    maximum_field = max(
        (float(field[action]) for action in supported_actions), default=0.0
    )
    maximum_clock = max(
        (float(clock[action]) for action in supported_actions), default=0.0
    )
    return SafetyDiagnostics(
        field_clipping_mass_by_action=field,
        clock_clipping_mass_by_action=clock,
        maximum_field_clipping_mass=maximum_field,
        maximum_clock_clipping_mass=maximum_clock,
        maximum_overtime_boundary_mass=0.0,
        sparse_supported_action=any(
            support.sparse and support.in_support
            for support in support_by_action.values()
        ),
        unsupported_available_action=any(
            support.available and not support.in_support
            for support in support_by_action.values()
        ),
        actual_action_supported=support_by_action[actual_action].in_support,
    )


def attach_overtime_diagnostic(
    diagnostics: SafetyDiagnostics, audit: DecisionValueAudit
) -> SafetyDiagnostics:
    """Return clipping diagnostics with decision-v1 OT mass attached."""

    values = diagnostics.to_dict()
    values["maximum_overtime_boundary_mass"] = audit.maximum_overtime_boundary_mass
    return SafetyDiagnostics(**values)


def apply_publication_policy(
    audit: DecisionValueAudit,
    diagnostics: SafetyDiagnostics,
    policy: PublicationPolicy = PUBLICATION_POLICY_V1,
) -> PublicationDecision:
    """Apply safety gates without modifying the supplied decision-v1 result."""

    _validate_frozen_decision_contract(audit)
    reasons: list[str] = []
    if policy.require_clear_model_preference:
        if audit.classification == "close_call":
            reasons.append("decision_v1_close_call")
        elif audit.classification != "clear_model_preference":
            reasons.append("decision_v1_not_clear_model_preference")

    if (
        policy.require_actual_action_supported
        and not diagnostics.actual_action_supported
    ):
        reasons.append("actual_action_unsupported")
    if (
        policy.require_all_available_actions_supported
        and diagnostics.unsupported_available_action
    ):
        reasons.append("available_action_unsupported")
    if (
        policy.withhold_any_sparse_supported_action
        and diagnostics.sparse_supported_action
    ):
        reasons.append("supported_action_sparse")
    if (
        policy.require_zero_overtime_boundary_mass
        and diagnostics.maximum_overtime_boundary_mass > 0.0
    ):
        reasons.append("overtime_boundary_mass_nonzero")

    if audit.classification == "clear_model_preference" and (
        audit.model_preferred_minimum_gap is None
        or audit.model_preferred_minimum_superiority is None
        or audit.model_preferred_minimum_gap < DECISION_THRESHOLD_POLICY_V1.minimum_gap
        or audit.model_preferred_minimum_superiority
        < DECISION_THRESHOLD_POLICY_V1.superiority_probability
    ):
        reasons.append("decision_v1_pairwise_evidence_incomplete")

    if diagnostics.maximum_field_clipping_mass > policy.maximum_field_clipping_mass:
        reasons.append("field_clipping_mass_above_policy")
    if diagnostics.maximum_clock_clipping_mass > policy.maximum_clock_clipping_mass:
        reasons.append("clock_clipping_mass_above_policy")
    if diagnostics.maximum_field_clipping_mass > 0.25:
        reasons.append("known_heavy_field_clipping_regime")

    unique_reasons = tuple(dict.fromkeys(reasons))
    if not unique_reasons:
        return PublicationDecision(
            status="publishable",
            publishable=True,
            withholding_reasons=(),
            internal_explanation=None,
            policy_version=policy.version,
        )
    status = _withholding_status(unique_reasons)
    return PublicationDecision(
        status=status,
        publishable=False,
        withholding_reasons=unique_reasons,
        internal_explanation=_internal_explanation(unique_reasons, diagnostics, policy),
        policy_version=policy.version,
    )


def _validate_frozen_decision_contract(audit: DecisionValueAudit) -> None:
    if audit.decision_value_version != "coachiq-decision-v1":
        raise ValueError("publication-v1 requires coachiq-decision-v1")
    if audit.wp_model_version != "coachiq-wp-v1":
        raise ValueError("publication-v1 requires coachiq-wp-v1")
    if audit.action_transition_model_version != "coachiq-action-transition-v1":
        raise ValueError("publication-v1 requires coachiq-action-transition-v1")
    if audit.threshold_policy != DECISION_THRESHOLD_POLICY_V1:
        raise ValueError("publication-v1 requires the frozen decision-v1 policy")


def _withholding_status(reasons: tuple[str, ...]) -> str:
    reason_set = set(reasons)
    if "overtime_boundary_mass_nonzero" in reason_set:
        return "withhold_overtime_scope"
    if reason_set & {
        "actual_action_unsupported",
        "available_action_unsupported",
        "supported_action_sparse",
        "decision_v1_not_clear_model_preference",
    }:
        return "withhold_support"
    if "decision_v1_close_call" in reason_set:
        return "withhold_close_call"
    if "decision_v1_pairwise_evidence_incomplete" in reason_set:
        return "withhold_uncertainty"
    if reason_set & {
        "field_clipping_mass_above_policy",
        "clock_clipping_mass_above_policy",
        "known_heavy_field_clipping_regime",
    }:
        return "withhold_clipping"
    return "withhold_model_form_risk"


def _internal_explanation(
    reasons: tuple[str, ...],
    diagnostics: SafetyDiagnostics,
    policy: PublicationPolicy,
) -> str:
    if "overtime_boundary_mass_nonzero" in reasons:
        return (
            "Not publication eligible: modeled transitions include "
            f"{diagnostics.maximum_overtime_boundary_mass:.1%} unmodeled "
            "tied-regulation-expiration mass."
        )
    if "field_clipping_mass_above_policy" in reasons:
        return (
            "Not publication eligible: a hypothetical transition has "
            f"{diagnostics.maximum_field_clipping_mass:.1%} field-boundary "
            f"clipping, above the {policy.maximum_field_clipping_mass:.0%} policy."
        )
    if "clock_clipping_mass_above_policy" in reasons:
        return (
            "Not publication eligible: a hypothetical transition has "
            f"{diagnostics.maximum_clock_clipping_mass:.1%} clock-boundary "
            "clipping."
        )
    if "decision_v1_close_call" in reasons:
        return "Not publication eligible: decision-v1 classified this as a close call."
    if "supported_action_sparse" in reasons:
        return "Not publication eligible: at least one supported action is sparse."
    if "actual_action_unsupported" in reasons:
        return "Not publication eligible: the actual action lacks empirical support."
    if "available_action_unsupported" in reasons:
        return "Not publication eligible: an available comparison lacks support."
    return "Not publication eligible under coachiq-publication-v1."


__all__ = [
    "PUBLICATION_CLOCK_CLIPPING_LIMIT",
    "PUBLICATION_FIELD_CLIPPING_LIMIT",
    "PUBLICATION_POLICY_V1",
    "PUBLICATION_POLICY_VERSION",
    "PublicationDecision",
    "PublicationPolicy",
    "SafetyDiagnostics",
    "apply_publication_policy",
    "attach_overtime_diagnostic",
    "transition_clipping_diagnostics",
]
