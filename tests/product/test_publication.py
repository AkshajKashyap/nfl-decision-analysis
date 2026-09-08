from __future__ import annotations

from dataclasses import replace

import numpy as np
import polars as pl
import pytest

from coachiq.analysis.decision_value import (
    ACTION_TRANSITION_MODEL_VERSION,
    DECISION_THRESHOLD_POLICY_V1,
    DECISION_VALUE_VERSION,
    CanonicalActionValue,
    DecisionValueAudit,
    PairwiseActionDifference,
)
from coachiq.product import (
    PUBLICATION_POLICY_VERSION,
    DecisionPublicationRecord,
    FrozenModels,
    SafetyDiagnostics,
    SourceMetadata,
    aggregate_week_audits,
    apply_publication_policy,
    assemble_game_audit,
    publication_safe_language,
    stable_json_dumps,
    validate_policy_development_boundary,
)
from coachiq.product.audit import _claimed_comparison


def _action(action: str, value: float) -> CanonicalActionValue:
    return CanonicalActionValue(
        action=action,
        expected_win_probability=value,
        interval_lower=value - 0.01,
        interval_upper=value + 0.01,
        confidence_level=0.90,
        bootstrap_replicates=200,
        bootstrap_valid_replicates=200,
        support_status="supported",
        support_observations=500,
        support_games=200,
        available=True,
        sparse=False,
        support_reason=None,
        overtime_boundary_mass=0.0,
        wp_model_version="coachiq-wp-v1",
        action_transition_model_version=ACTION_TRANSITION_MODEL_VERSION,
    )


def _pair(first: str, second: str, difference: float) -> PairwiseActionDifference:
    return PairwiseActionDifference(
        action_a=first,
        action_b=second,
        available=True,
        difference=difference,
        interval_lower=difference - 0.01,
        interval_upper=difference + 0.01,
        probability_a_exceeds_b=0.98 if difference > 0 else 0.02,
        probability_b_exceeds_a=0.02 if difference > 0 else 0.98,
        probability_tied=0.0,
        confidence_level=0.90,
        bootstrap_replicates=200,
        bootstrap_valid_replicates=200,
        unavailable_reason=None,
    )


def _audit(classification: str = "clear_model_preference") -> DecisionValueAudit:
    return DecisionValueAudit(
        actual_action="punt",
        actions=(
            _action("go", 0.60),
            _action("field_goal", 0.50),
            _action("punt", 0.55),
        ),
        pairwise_differences=(
            _pair("go", "punt", 0.05),
            _pair("go", "field_goal", 0.10),
            _pair("field_goal", "punt", -0.05),
        ),
        supported_action_count=3,
        actual_action_ewp=0.55,
        highest_supported_action="go",
        highest_supported_action_ewp=0.60,
        raw_action_value_gap=0.05,
        classification=classification,
        classification_reason=(
            "gap_and_pairwise_evidence_meet_policy"
            if classification == "clear_model_preference"
            else "gap_or_pairwise_evidence_below_policy"
        ),
        model_preferred_action="go",
        model_preferred_minimum_gap=0.05,
        model_preferred_minimum_superiority=0.98,
        maximum_overtime_boundary_mass=0.0,
        threshold_policy=DECISION_THRESHOLD_POLICY_V1,
        wp_model_version="coachiq-wp-v1",
        action_transition_model_version=ACTION_TRANSITION_MODEL_VERSION,
        decision_value_version=DECISION_VALUE_VERSION,
    )


def _diagnostics(**overrides: object) -> SafetyDiagnostics:
    values: dict[str, object] = {
        "field_clipping_mass_by_action": {
            "go": 0.0,
            "field_goal": 0.0,
            "punt": 0.0,
        },
        "clock_clipping_mass_by_action": {
            "go": 0.0,
            "field_goal": 0.0,
            "punt": 0.0,
        },
        "maximum_field_clipping_mass": 0.0,
        "maximum_clock_clipping_mass": 0.0,
        "maximum_overtime_boundary_mass": 0.0,
        "sparse_supported_action": False,
        "unsupported_available_action": False,
        "actual_action_supported": True,
    }
    values.update(overrides)
    return SafetyDiagnostics(**values)


def _record(
    play_id: int, *, publishable: bool, gap: float = 0.05
) -> DecisionPublicationRecord:
    status = "publishable" if publishable else "withhold_clipping"
    reasons = () if publishable else ("field_clipping_mass_above_policy",)
    return DecisionPublicationRecord(
        identity={"game_id": "g1", "play_id": play_id},
        situation={"yards_to_go": 1},
        actual_decision={"actual_action": "punt"},
        modeled_actions=(),
        comparison={
            "decision_v1_classification": "clear_model_preference",
            "model_preferred_supported_action": "go",
            "actual_action_modeled_gap": gap,
            "minimum_pairwise_superiority": 0.98,
        },
        safety_diagnostics={"maximum_field_clipping_mass": 0.2},
        publication={
            "status": status,
            "publishable": publishable,
            "withholding_reasons": reasons,
        },
        provenance={
            "wp_model_version": "coachiq-wp-v1",
            "action_transition_model_version": "coachiq-action-transition-v1",
            "decision_value_version": "coachiq-decision-v1",
            "publication_policy_version": PUBLICATION_POLICY_VERSION,
        },
        public_language="CoachIQ favored going for it." if publishable else None,
        internal_language=None if publishable else "Not publication eligible.",
    )


def _source() -> SourceMetadata:
    return SourceMetadata(
        source="test snapshot",
        retrieved_at_utc="2026-01-01T00:00:00+00:00",
        seasons=(2025,),
        weeks=(1,),
        row_count=10,
        sha256="abc123",
    )


def test_publication_is_separate_and_uses_frozen_decision_evidence() -> None:
    audit = _audit()
    before = audit.classification
    result = apply_publication_policy(audit, _diagnostics())

    assert result.publishable
    assert result.status == "publishable"
    assert audit.classification == before == "clear_model_preference"
    assert result.policy_version == "coachiq-publication-v1"

    drifted = replace(
        audit, threshold_policy=replace(DECISION_THRESHOLD_POLICY_V1, minimum_gap=0.0)
    )
    with pytest.raises(ValueError, match="frozen decision-v1 policy"):
        apply_publication_policy(drifted, _diagnostics())


def test_field_clipping_policy_boundary_is_inclusive_and_conservative() -> None:
    at_limit = apply_publication_policy(
        _audit(), _diagnostics(maximum_field_clipping_mass=0.10)
    )
    above_limit = apply_publication_policy(
        _audit(),
        _diagnostics(maximum_field_clipping_mass=float(np.nextafter(0.10, 1.0))),
    )

    assert at_limit.publishable
    assert not above_limit.publishable
    assert above_limit.status == "withhold_clipping"
    assert "field_clipping_mass_above_policy" in above_limit.withholding_reasons


def test_any_clock_clipping_and_incomplete_clear_evidence_withhold() -> None:
    clock = apply_publication_policy(
        _audit(), _diagnostics(maximum_clock_clipping_mass=np.nextafter(0.0, 1.0))
    )
    incomplete = apply_publication_policy(
        replace(_audit(), model_preferred_minimum_superiority=None), _diagnostics()
    )

    assert clock.status == "withhold_clipping"
    assert "clock_clipping_mass_above_policy" in clock.withholding_reasons
    assert incomplete.status == "withhold_uncertainty"
    assert "decision_v1_pairwise_evidence_incomplete" in incomplete.withholding_reasons


@pytest.mark.parametrize(
    ("diagnostics", "expected_status"),
    (
        (
            _diagnostics(maximum_overtime_boundary_mass=0.01),
            "withhold_overtime_scope",
        ),
        (_diagnostics(sparse_supported_action=True), "withhold_support"),
        (_diagnostics(actual_action_supported=False), "withhold_support"),
        (_diagnostics(unsupported_available_action=True), "withhold_support"),
    ),
)
def test_ot_and_support_risks_withhold(
    diagnostics: SafetyDiagnostics, expected_status: str
) -> None:
    result = apply_publication_policy(_audit(), diagnostics)

    assert not result.publishable
    assert result.status == expected_status


def test_close_call_withholds_and_cannot_generate_public_claim() -> None:
    result = apply_publication_policy(_audit("close_call"), _diagnostics())

    assert result.status == "withhold_close_call"
    assert publication_safe_language(result, {}, None, "go", 0.05) is None


def test_unsupported_actual_action_cannot_form_a_claimed_comparison() -> None:
    audit = _audit("insufficient_support")
    unsupported_punt = replace(
        audit.actions[2],
        expected_win_probability=None,
        interval_lower=None,
        interval_upper=None,
        support_status="unsupported",
    )
    audit = replace(
        audit,
        actions=(*audit.actions[:2], unsupported_punt),
        actual_action_ewp=None,
        raw_action_value_gap=None,
    )
    result = apply_publication_policy(
        audit, _diagnostics(actual_action_supported=False)
    )

    assert not result.publishable
    assert _claimed_comparison(audit) == (None, None)
    assert publication_safe_language(result, {}, None, "go", 0.05) is None


def test_neutral_wording_is_deterministic_and_avoids_causal_claims() -> None:
    publication = apply_publication_policy(_audit(), _diagnostics())
    row = {"yards_to_go": 1, "yards_to_goal": 43.0}
    first = publication_safe_language(publication, row, _audit(), "punt", 0.05)
    second = publication_safe_language(publication, row, _audit(), "punt", 0.05)

    assert first == second
    assert "CoachIQ favored" in first
    assert "modeled advantage" in first
    for prohibited in ("mistake", "cost their team", "objectively correct", "optimal"):
        assert prohibited not in first.lower()


def test_game_week_provenance_aggregation_and_json_are_deterministic() -> None:
    source = _source()
    models = FrozenModels(None, None, None, {"training_through_season": 2024})
    game_frame = pl.DataFrame(
        {
            "season": [2025],
            "week": [1],
            "game_id": ["g1"],
            "home_team": ["A"],
            "away_team": ["B"],
        }
    )
    game = assemble_game_audit(
        game_frame,
        3,
        (_record(10, publishable=True), _record(20, publishable=False)),
        models,
        source=source,
    )
    week = aggregate_week_audits(
        (game,), source=source, models_manifest=models.manifest
    )

    assert game.eligible_decisions == 2
    assert game.publishable_decisions == 1
    assert game.withheld_by_reason == {"field_clipping_mass_above_policy": 1}
    assert week.games_processed == 1
    assert week.publication_eligible == 1
    assert week.notable_decisions[0]["identity"]["play_id"] == 10
    assert "coach" not in json_keys(week.to_dict())
    assert stable_json_dumps(week) == stable_json_dumps(week)
    assert week.provenance["source"]["sha256"] == "abc123"


def test_2026_guard_blocks_policy_development_access() -> None:
    assert validate_policy_development_boundary((2024, 2025)) == (2024, 2025)
    with pytest.raises(ValueError, match="2026 data is blocked"):
        validate_policy_development_boundary((2026,))


def json_keys(value: object) -> str:
    if isinstance(value, dict):
        return (
            " ".join(str(key) for key in value)
            + " "
            + " ".join(json_keys(item) for item in value.values())
        )
    if isinstance(value, (list, tuple)):
        return " ".join(json_keys(item) for item in value)
    return ""
