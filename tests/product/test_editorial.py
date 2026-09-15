from __future__ import annotations

import json

import pytest

from coachiq.product import (
    HUMAN_REVIEW_CHECKS,
    build_publication_package,
    build_review_card,
    deterministic_shortlist,
    methodology_note,
    prohibited_language_violations,
    provenance_footer,
    select_close_call_companion,
    validate_human_review,
)


def _record(
    play_id: int,
    *,
    game_id: str | None = None,
    actual: str = "punt",
    favored: str = "go",
    publishable: bool = True,
    classification: str = "clear_model_preference",
) -> dict[str, object]:
    game_id = game_id or f"2026_01_A{play_id}_B{play_id}"
    go = 0.55 + play_id / 10000
    punt = 0.52
    preferred = go if favored == "go" else punt
    comparison = punt if favored == "go" else go
    reasons = [] if publishable else ["decision_v1_close_call"]
    return {
        "identity": {
            "season": 2026,
            "week": 1,
            "game_id": game_id,
            "play_id": play_id,
            "home_team": f"B{play_id}",
            "away_team": f"A{play_id}",
            "possession_team": f"A{play_id}",
        },
        "situation": {
            "quarter": (play_id % 4) + 1,
            "quarter_seconds_remaining": 600,
            "game_seconds_remaining": 2400,
            "score_differential": -3,
            "yards_to_goal": 60.0,
            "yards_to_go": 2.0,
            "posteam_timeouts_remaining": 3,
            "defteam_timeouts_remaining": 3,
        },
        "actual_decision": {
            "actual_action": actual,
            "factual_outcome": actual,
            "source_description": f"Play {play_id}",
        },
        "modeled_actions": [
            {
                "action": "go",
                "expected_win_probability": go,
                "interval_lower": go - 0.01,
                "interval_upper": go + 0.01,
                "support_status": "supported",
                "support_observations": 500,
                "support_games": 200,
                "available": True,
                "sparse": False,
            },
            {
                "action": "punt",
                "expected_win_probability": punt,
                "interval_lower": punt - 0.01,
                "interval_upper": punt + 0.01,
                "support_status": "supported",
                "support_observations": 1000,
                "support_games": 400,
                "available": True,
                "sparse": False,
            },
        ],
        "comparison": {
            "model_preferred_supported_action": favored,
            "claimed_comparison_action": "punt" if favored == "go" else "go",
            "claimed_comparison_gap": preferred - comparison,
            "actual_action_modeled_gap": (
                0.0 if actual == favored else preferred - comparison
            ),
            "minimum_preference_gap": abs(preferred - comparison),
            "minimum_pairwise_superiority": 0.98,
            "pairwise_evidence": [],
            "decision_v1_classification": classification,
            "decision_v1_classification_reason": "fixture",
        },
        "safety_diagnostics": {
            "field_clipping_mass_by_action": {"go": 0.01, "punt": 0.02},
            "clock_clipping_mass_by_action": {"go": 0.0, "punt": 0.0},
            "maximum_field_clipping_mass": 0.02,
            "maximum_clock_clipping_mass": 0.0,
            "maximum_overtime_boundary_mass": 0.0,
            "sparse_supported_action": False,
            "unsupported_available_action": False,
            "actual_action_supported": True,
        },
        "publication": {
            "status": "publishable" if publishable else "withhold_close_call",
            "publishable": publishable,
            "withholding_reasons": reasons,
        },
        "provenance": {
            "wp_model_version": "coachiq-wp-v1",
            "action_transition_model_version": "coachiq-action-transition-v1",
            "decision_value_version": "coachiq-decision-v1",
            "publication_policy_version": "coachiq-publication-v1",
            "training_through_season": 2024,
            "source": {
                "retrieved_at_utc": "2026-09-15T17:29:29+00:00",
                "sha256": "current-week",
            },
        },
        "public_language": (
            f"On fourth-and-2, CoachIQ favored {favored}. The model estimated "
            "a modeled advantage under CoachIQ v1."
            if publishable
            else None
        ),
        "internal_language": None,
    }


def _weekly() -> dict[str, object]:
    safe = [
        _record(
            play,
            actual="go" if play in (3, 7) else "punt",
            favored=("go" if play % 3 else "punt"),
        )
        for play in range(1, 11)
    ]
    close = _record(90, publishable=False, classification="close_call")
    return {
        "season": 2026,
        "week": 1,
        "games": [{"decisions": [*safe, close]}],
        "provenance": {
            "source": {
                "retrieved_at_utc": "2026-09-15T17:29:29+00:00",
                "sha256": "current-week",
            }
        },
    }


def _facts(record: dict[str, object]) -> dict[str, object]:
    identity = record["identity"]
    situation = record["situation"]
    actual = record["actual_decision"]
    return {
        "game_id": identity["game_id"],
        "play_id": identity["play_id"],
        "possession_team": identity["possession_team"],
        "possession_team_score": 7,
        "defense_team_score": 10,
        "quarter": situation["quarter"],
        "quarter_seconds_remaining": situation["quarter_seconds_remaining"],
        "score_differential": situation["score_differential"],
        "yards_to_go": situation["yards_to_go"],
        "yards_to_goal": situation["yards_to_goal"],
        "actual_action": actual["actual_action"],
        "factual_outcome": actual["factual_outcome"],
        "description": actual["source_description"],
    }


def _correction(*, ready: bool = True) -> dict[str, object]:
    return {
        "checked_at_utc": "2026-09-15T18:00:00+00:00",
        "exact_diff_complete": ready,
        "current_audit_regenerated": True,
        "deterministic_rerun_passed": True,
        "ready_for_publication": ready,
        "current_week_fingerprint": "current-week",
    }


def _review(record: dict[str, object], status: str = "approved") -> dict[str, object]:
    return {
        "decision_id": (
            f"{record['identity']['game_id']}:{record['identity']['play_id']}"
        ),
        "status": status,
        "reviewer": "Human Reviewer",
        "reviewer_type": "human",
        "reviewed_at_utc": "2026-09-15T18:05:00+00:00",
        "checklist": {name: status == "approved" for name in HUMAN_REVIEW_CHECKS},
        "note": None,
    }


def test_shortlist_is_safe_varied_and_deterministic() -> None:
    weekly = _weekly()
    first = deterministic_shortlist(weekly, limit=8)
    second = deterministic_shortlist(weekly, limit=8)

    assert first == second
    assert len(first) == 8
    assert all(record["publication"]["publishable"] for record in first)
    assert (
        len(
            {
                (
                    record["actual_decision"]["actual_action"],
                    record["comparison"]["model_preferred_supported_action"],
                )
                for record in first
            }
        )
        >= 2
    )


def test_only_human_can_approve_and_withholding_cannot_be_overridden() -> None:
    safe = _record(1)
    withheld = _record(2, publishable=False, classification="close_call")
    approval = _review(safe)
    validate_human_review(safe, approval, correction_check=_correction())

    with pytest.raises(ValueError, match="cannot approve"):
        validate_human_review(
            withheld,
            {**approval, "decision_id": "2026_01_A2_B2:2"},
            correction_check=_correction(),
        )
    with pytest.raises(ValueError, match="reviewer_type='human'"):
        validate_human_review(
            safe,
            {**approval, "reviewer_type": "automation"},
            correction_check=_correction(),
        )
    with pytest.raises(ValueError, match="unknown or non-final"):
        validate_human_review(
            safe,
            {**approval, "status": "pending_review"},
            correction_check=_correction(),
        )


def test_language_close_call_and_provenance_are_conservative() -> None:
    assert prohibited_language_violations(methodology_note()) == ()
    assert prohibited_language_violations("The coach made a mistake and blew it.") == (
        "mistake",
        "blew_it",
    )
    close = select_close_call_companion(_weekly())
    assert close["classification"] == "close_call"
    assert "not a directional claim" in close["wording"]
    assert prohibited_language_violations(close["wording"]) == ()
    footer = provenance_footer(_weekly()["provenance"]["source"])
    assert "coachiq-wp-v1" in footer
    assert "current-week" in footer


def test_package_manifest_correction_gate_and_bytes_are_deterministic() -> None:
    weekly = _weekly()
    shortlist = deterministic_shortlist(weekly, limit=8)
    cards = [
        build_review_card(
            record,
            source_facts=_facts(record),
            correction_state="unchanged",
        )
        for record in shortlist
    ]
    reviews = [
        _review(record, "approved" if index < 3 else "hold_for_context")
        for index, record in enumerate(shortlist)
    ]
    selected = [review["decision_id"] for review in reviews[:3]]
    kwargs = {
        "weekly": weekly,
        "review_cards": cards,
        "reviews": reviews,
        "selected_decision_ids": selected,
        "correction_check": _correction(),
        "generated_at_utc": "2026-09-15T18:10:00+00:00",
    }
    first = build_publication_package(**kwargs)
    second = build_publication_package(**kwargs)

    assert first == second
    manifest = json.loads(first["publication-manifest.json"])
    assert manifest["selected_decision_ids"] == selected
    assert manifest["externally_published"] is False
    assert manifest["report_sha256"]
    assert "coachiq-publication-v1" in first["week-01.md"]
    assert not prohibited_language_violations(first["week-01.md"])

    with pytest.raises(ValueError, match="exact diff is incomplete"):
        build_publication_package(
            **{**kwargs, "correction_check": _correction(ready=False)}
        )
