from __future__ import annotations

import json
from argparse import Namespace
from dataclasses import replace

import polars as pl
import pytest
from scripts.audit_decision_values import _load_normalized as load_decision_development
from scripts.audit_live_week import _write_outputs
from tests.data.test_normalize import raw_pbp

from coachiq.operations import (
    apply_editorial_review,
    assess_game_readiness,
    build_shadow_brief,
    build_source_manifest,
    compare_source_manifests,
    run_shadow_week,
    tactical_context_warnings,
    validate_live_shadow_request,
    validate_weekly_shadow_output,
)
from coachiq.operations.shadow import EDITORIAL_CHECKS
from coachiq.product import (
    AuditMode,
    DecisionPublicationRecord,
    GameAudit,
    SourceMetadata,
    WeeklyAudit,
    validate_audit_boundary,
    validate_policy_development_boundary,
)


def _schedule(*, final: bool = True, game_id: str = "2026_01_A_B") -> dict[str, object]:
    return {
        "season": 2026,
        "week": 1,
        "game_id": game_id,
        "game_type": "REG",
        "away_team": "A",
        "home_team": "B",
        "away_score": 7 if final else None,
        "home_score": 10 if final else None,
        "result": 3 if final else None,
    }


def _completed_raw(game_id: str = "2026_01_A_B") -> pl.DataFrame:
    return raw_pbp(
        season=[2026, 2026],
        season_type=["REG", "REG"],
        week=[1, 1],
        game_id=[game_id, game_id],
        play_id=[10, 20],
        home_team=["B", "B"],
        away_team=["A", "A"],
        posteam=["A", "B"],
        defteam=["B", "A"],
        down=[4, 1],
        ydstogo=[2, 10],
        yardline_100=[42.0, 70.0],
        qtr=[4, 4],
        quarter_seconds_remaining=[10, 0],
        half_seconds_remaining=[10, 0],
        game_seconds_remaining=[10, 0],
        score_differential=[-3, 3],
        home_timeouts_remaining=[2, 2],
        away_timeouts_remaining=[1, 1],
        posteam_timeouts_remaining=[1, 2],
        defteam_timeouts_remaining=[2, 1],
        play_type=["punt", "no_play"],
        play_type_nfl=["PUNT", "END_GAME"],
        result=[3, 3],
        punt_attempt=[1, 0],
        field_goal_attempt=[0, 0],
        penalty=[0, 0],
        play_deleted=[0, 0],
        desc=["A punts", "END GAME"],
    )


def _record(*, publishable: bool = True) -> DecisionPublicationRecord:
    return DecisionPublicationRecord(
        identity={"game_id": "2026_01_A_B", "play_id": 10},
        situation={
            "quarter": 4,
            "quarter_seconds_remaining": 60,
            "yards_to_goal": 30.0,
            "yards_to_go": 4.0,
        },
        actual_decision={
            "actual_action": "punt",
            "factual_outcome": "punt_blocked",
            "source_description": "Fake punt from field goal formation",
        },
        modeled_actions=(),
        comparison={
            "decision_v1_classification": "clear_model_preference",
            "minimum_preference_gap": 0.03,
            "minimum_pairwise_superiority": 0.98,
        },
        safety_diagnostics={
            "field_clipping_mass_by_action": {},
            "clock_clipping_mass_by_action": {},
            "maximum_field_clipping_mass": 0.0,
            "maximum_clock_clipping_mass": 0.0,
            "maximum_overtime_boundary_mass": 0.0,
            "sparse_supported_action": False,
            "unsupported_available_action": False,
            "actual_action_supported": True,
        },
        publication={
            "status": "publishable" if publishable else "withhold_clipping",
            "publishable": publishable,
            "withholding_reasons": ()
            if publishable
            else ("field_clipping_mass_above_policy",),
        },
        provenance={
            "wp_model_version": "coachiq-wp-v1",
            "action_transition_model_version": "coachiq-action-transition-v1",
            "decision_value_version": "coachiq-decision-v1",
            "publication_policy_version": "coachiq-publication-v1",
            "training_through_season": 2024,
            "source": {"sha256": "source"},
        },
        public_language="CoachIQ favored going for it." if publishable else None,
        internal_language=None if publishable else "Not publication eligible.",
    )


def _weekly(record: DecisionPublicationRecord) -> WeeklyAudit:
    source = SourceMetadata(
        source="fixture",
        retrieved_at_utc="2026-09-08T00:00:00+00:00",
        seasons=(2026,),
        weeks=(1,),
        row_count=2,
        sha256="source",
    )
    game = GameAudit(
        game_id="2026_01_A_B",
        season=2026,
        week=1,
        home_team="B",
        away_team="A",
        total_fourth_down_candidates=1,
        eligible_decisions=1,
        valued_decisions=1,
        publishable_decisions=int(record.publication["publishable"]),
        withheld_decisions=int(not record.publication["publishable"]),
        withheld_by_status={},
        withheld_by_reason={},
        decisions=(record,),
        provenance={"source": source.to_dict()},
    )
    return WeeklyAudit(
        season=2026,
        week=1,
        games_processed=1,
        total_fourth_down_candidates=1,
        eligible_decisions=1,
        valued_decisions=1,
        clear_model_preferences=1,
        publication_eligible=int(record.publication["publishable"]),
        withheld_by_status={},
        withheld_by_reason={},
        notable_decisions=(
            ({"identity": record.identity, "public_language": record.public_language},)
            if record.publication["publishable"]
            else ()
        ),
        strongest_pairwise_evidence=(),
        games=(game,),
        provenance={"source": source.to_dict()},
    )


def test_final_game_is_ready_and_incomplete_or_missing_games_are_rejected() -> None:
    ready, normalized = assess_game_readiness(_schedule(), _completed_raw())
    incomplete, _ = assess_game_readiness(
        _schedule(), _completed_raw().with_columns(pl.lit(None).alias("result"))
    )
    missing, _ = assess_game_readiness(_schedule(), None)
    nonfinal, _ = assess_game_readiness(_schedule(final=False), None)

    assert ready.status == "ready"
    assert normalized is not None
    assert ready.fourth_down_candidates == 1
    assert "raw_play_count_outside_preregistered_plausibility_range" in ready.warnings
    assert incomplete.status == "incomplete_source"
    assert missing.status == "source_missing"
    assert nonfinal.status == "game_not_final"


def test_manifest_fingerprints_and_correction_detection_are_per_game() -> None:
    schedule = pl.DataFrame([_schedule(game_id="g1"), _schedule(game_id="g2")])
    raw = pl.DataFrame(
        {
            "season": [2026, 2026],
            "week": [1, 1],
            "game_id": ["g1", "g2"],
            "play_id": [1, 1],
            "description": ["unchanged", "before"],
        }
    )
    first = build_source_manifest(
        schedule,
        raw,
        raw,
        season=2026,
        week=1,
        retrieved_at_utc="fixed",
        schedule_source="fixture",
        pbp_source="fixture",
    )
    changed_raw = raw.with_columns(
        pl.when(pl.col("game_id") == "g2")
        .then(pl.lit("after"))
        .otherwise(pl.col("description"))
        .alias("description")
    )
    second = build_source_manifest(
        schedule,
        changed_raw,
        changed_raw,
        season=2026,
        week=1,
        retrieved_at_utc="fixed",
        schedule_source="fixture",
        pbp_source="fixture",
    )
    correction = compare_source_manifests(first, second)

    assert correction.source_changed
    assert correction.changed_game_ids == ("g2",)
    assert correction.unchanged_game_ids == ("g1",)
    assert correction.added_game_ids == correction.removed_game_ids == ()


def test_output_correction_requires_acceptance_and_preserves_predecessor(
    tmp_path,
) -> None:
    schedule = pl.DataFrame([_schedule(game_id="g1"), _schedule(game_id="g2")])
    raw = pl.DataFrame(
        {
            "season": [2026, 2026],
            "week": [1, 1],
            "game_id": ["g1", "g2"],
            "play_id": [1, 1],
            "description": ["same", "before"],
        }
    )
    first_manifest = build_source_manifest(
        schedule,
        raw,
        raw,
        season=2026,
        week=1,
        retrieved_at_utc="fixed",
        schedule_source="fixture",
        pbp_source="fixture",
    )
    second_raw = raw.with_columns(
        pl.when(pl.col("game_id") == "g2")
        .then(pl.lit("after"))
        .otherwise(pl.col("description"))
        .alias("description")
    )
    second_manifest = build_source_manifest(
        schedule,
        second_raw,
        second_raw,
        season=2026,
        week=1,
        retrieved_at_utc="fixed",
        schedule_source="fixture",
        pbp_source="fixture",
    )
    base, _ = run_shadow_week(
        pl.DataFrame([_schedule(final=False)]),
        None,
        None,
        season=2026,
        week=1,
        retrieved_at_utc="fixed",
        schedule_source="fixture",
        pbp_source=None,
    )
    output_dir = tmp_path / "output"
    _write_outputs(
        Namespace(output_dir=output_dir, accept_source_correction=False),
        replace(base, source_manifest=first_manifest),
        first_manifest,
        None,
    )
    original = (output_dir / "source-manifest.json").read_bytes()

    with pytest.raises(SystemExit, match="source correction detected"):
        _write_outputs(
            Namespace(output_dir=output_dir, accept_source_correction=False),
            replace(base, source_manifest=second_manifest),
            second_manifest,
            None,
        )
    assert (output_dir / "source-manifest.json").read_bytes() == original

    corrected = _write_outputs(
        Namespace(output_dir=output_dir, accept_source_correction=True),
        replace(base, source_manifest=second_manifest),
        second_manifest,
        None,
    )
    assert corrected.source_correction_events == 1
    assert (output_dir / "source-manifest.previous.json").read_bytes() == original
    correction = json.loads(
        (output_dir / "correction-report.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (output_dir / "operational-summary.json").read_text(encoding="utf-8")
    )
    assert summary["source_correction_events"] == 1
    assert correction["changed_game_ids"] == ["g2"]
    assert correction["unchanged_game_ids"] == ["g1"]


def test_tactical_warnings_route_to_review_without_overriding_withholding() -> None:
    publishable = _record()
    withheld = _record(publishable=False)
    warnings = tactical_context_warnings(publishable)

    assert "description_term:fake" in warnings
    assert "description_term:field goal formation" in warnings
    assert "extreme_late_regulation" in warnings
    assert "unusual_punt_field_position" in warnings
    assert "unusual_factual_outcome:punt_blocked" in warnings

    with pytest.raises(ValueError, match="cannot approve"):
        apply_editorial_review(
            withheld,
            "approved",
            checklist={name: True for name in EDITORIAL_CHECKS},
        )
    with pytest.raises(ValueError, match="complete passing checklist"):
        apply_editorial_review(publishable, "approved", checklist={"one": True})
    approved = apply_editorial_review(
        publishable,
        "approved",
        reviewer="human-reviewer",
        checklist={name: True for name in EDITORIAL_CHECKS},
    )
    assert approved.status == "approved"
    assert approved.tactical_warnings == warnings


def test_missing_safety_or_version_metadata_fails_weekly_validation() -> None:
    record = _record()
    validate_weekly_shadow_output(_weekly(record))

    with pytest.raises(ValueError, match="missing safety metadata"):
        validate_weekly_shadow_output(_weekly(replace(record, safety_diagnostics={})))
    with pytest.raises(ValueError, match="version mismatch"):
        validate_weekly_shadow_output(
            _weekly(
                replace(
                    record,
                    provenance={**record.provenance, "wp_model_version": "wrong"},
                )
            )
        )


def test_no_completed_games_fails_safely_and_is_deterministic() -> None:
    schedule = pl.DataFrame([_schedule(final=False)])
    first, first_week = run_shadow_week(
        schedule,
        None,
        None,
        season=2026,
        week=1,
        retrieved_at_utc="fixed",
        schedule_source="fixture",
        pbp_source=None,
    )
    second, second_week = run_shadow_week(
        schedule,
        None,
        None,
        season=2026,
        week=1,
        retrieved_at_utc="fixed",
        schedule_source="fixture",
        pbp_source=None,
    )

    assert first.readiness_status == "NOT READY"
    assert first.readiness_reasons == ("no_completed_2026_games_available",)
    assert first_week is second_week is None
    assert first == second
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        second.to_dict(), sort_keys=True
    )
    assert "No scored decisions" in build_shadow_brief(first)


def test_weekly_exports_are_byte_identical(tmp_path) -> None:
    schedule = pl.DataFrame([_schedule(final=False)])
    report, _ = run_shadow_week(
        schedule,
        None,
        None,
        season=2026,
        week=1,
        retrieved_at_utc="fixed",
        schedule_source="fixture",
        pbp_source=None,
    )
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    _write_outputs(
        Namespace(output_dir=first_dir, accept_source_correction=False),
        report,
        report.source_manifest,
        None,
    )
    _write_outputs(
        Namespace(output_dir=second_dir, accept_source_correction=False),
        report,
        report.source_manifest,
        None,
    )

    first_files = {path.name: path.read_bytes() for path in first_dir.iterdir()}
    second_files = {path.name: path.read_bytes() for path in second_dir.iterdir()}
    assert first_files == second_files
    assert set(first_files) == {
        "hashes.json",
        "operational-summary.json",
        "shadow-brief.md",
        "source-manifest.json",
    }


def test_2026_is_allowed_only_in_the_explicit_live_shadow_path() -> None:
    validate_live_shadow_request(2026, 1)
    assert validate_audit_boundary((2026,), AuditMode.LIVE_SHADOW_2026) == (2026,)

    with pytest.raises(ValueError, match="exactly season 2026"):
        validate_live_shadow_request(2025, 1)
    with pytest.raises(ValueError, match="within 1-22"):
        validate_live_shadow_request(2026, 23)
    with pytest.raises(ValueError, match="2026 data is blocked"):
        validate_policy_development_boundary((2026,))
    with pytest.raises(SystemExit, match="2014-2024"):
        load_decision_development([2026], None)
