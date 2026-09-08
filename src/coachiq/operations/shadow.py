"""Fail-safe 2026 shadow auditing around the frozen CoachIQ stack."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from typing import Any

import polars as pl

from coachiq.analysis.fourth_down import extract_fourth_down_candidates
from coachiq.data import normalize_pbp
from coachiq.product import (
    PUBLICATION_POLICY_VERSION,
    AuditMode,
    DecisionPublicationRecord,
    FrozenModels,
    SourceMetadata,
    WeeklyAudit,
    audit_week,
    fingerprint_frame,
    stable_json_dumps,
)

SHADOW_PROTOCOL_SHA256 = (
    "c62f5459d6bf0e71c377b4b6c543d94ac5c07a63bf070ec09a17d7b69300acf8"
)
LIVE_SEASON = 2026
PLAUSIBLE_RAW_ROWS = (100, 250)
PLAUSIBLE_CANDIDATES = (1, 30)
EDITORIAL_STATUSES = {
    "pending_review",
    "approved",
    "hold_for_context",
    "reject_data_issue",
    "reject_model_form_risk",
}
EDITORIAL_CHECKS = (
    "factual_game_state",
    "actual_action",
    "score_clock_down_distance",
    "tactical_context",
    "publication_status",
    "safety_diagnostics",
    "neutral_wording",
    "no_causal_claim",
)
TACTICAL_TERMS = (
    "fake",
    "direct snap",
    "pooch",
    "quick kick",
    "field goal formation",
    "intentional safety",
    "takes a safety",
    "deliberate",
    "runs out of the back",
)
TACTICAL_OUTCOMES = {
    "punt_blocked",
    "field_goal_blocked",
    "safety",
    "return_touchdown",
}


@dataclass(frozen=True)
class GameReadiness:
    """Source and validation readiness for one scheduled game."""

    game_id: str
    season: int
    week: int
    game_type: str
    away_team: str
    home_team: str
    schedule_final: bool
    status: str
    raw_rows: int
    normalized_rows: int
    fourth_down_candidates: int
    eligible_decisions: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    source_fingerprint: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceManifest:
    """Deterministic source identity for one shadow week."""

    season: int
    week: int
    retrieved_at_utc: str
    schedule_source: str
    pbp_source: str | None
    schedule_snapshot_fingerprint: str
    pbp_snapshot_fingerprint: str | None
    schedule_fingerprint: str
    pbp_fingerprint: str | None
    schedule_rows: int
    source_rows: int
    normalized_rows: int
    scheduled_game_ids: tuple[str, ...]
    final_game_ids: tuple[str, ...]
    observed_game_ids: tuple[str, ...]
    per_game_schedule_fingerprints: dict[str, str]
    per_game_fingerprints: dict[str, str]
    model_versions: tuple[str, ...]
    publication_version: str
    generated_report_fingerprint: str | None
    protocol_sha256: str = SHADOW_PROTOCOL_SHA256

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CorrectionReport:
    """Per-game source changes between two deterministic manifests."""

    source_changed: bool
    changed_game_ids: tuple[str, ...]
    added_game_ids: tuple[str, ...]
    removed_game_ids: tuple[str, ...]
    unchanged_game_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EditorialReview:
    """Human review state that can only further withhold a decision."""

    game_id: str
    play_id: int
    status: str
    reviewer: str | None
    checklist: dict[str, bool]
    tactical_warnings: tuple[str, ...]
    note: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ShadowOperationalReport:
    """Deterministic counts and readiness result for one prospective week."""

    season: int
    week: int
    readiness_status: str
    readiness_reasons: tuple[str, ...]
    games_scheduled: int
    games_final: int
    games_attempted: int
    games_successfully_processed: int
    failed_games: int
    fourth_down_candidates: int
    eligible_decisions: int
    valued_decisions: int
    clear_model_preferences: int
    decisions_attempted: int
    scoring_failures: int
    publication_safe_decisions: int
    human_approved_decisions: int
    human_held_decisions: int
    pending_human_review: int
    tactical_warning_decisions: int
    source_correction_events: int
    deterministic_run_failures: int
    publication_safe_rate: float | None
    historical_publication_safe_rate_range: tuple[float, float]
    historical_range_flag: bool
    withhold_by_status: dict[str, int]
    withhold_by_reason: dict[str, int]
    game_readiness: tuple[GameReadiness, ...]
    notable_decisions: tuple[dict[str, Any], ...]
    close_calls: tuple[dict[str, Any], ...]
    tactical_warnings: tuple[dict[str, Any], ...]
    editorial_reviews: tuple[EditorialReview, ...]
    source_manifest: SourceManifest
    weekly_report_fingerprint: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_live_shadow_request(season: int, week: int) -> None:
    """Require the one deliberate prospective season and a valid NFL week."""

    if season != LIVE_SEASON:
        raise ValueError("live shadow auditing requires exactly season 2026")
    if not 1 <= week <= 22:
        raise ValueError("live shadow week must be within 1-22")


def assess_game_readiness(
    schedule_row: dict[str, Any], raw_game: pl.DataFrame | None
) -> tuple[GameReadiness, pl.DataFrame | None]:
    """Validate one scheduled game and return normalized rows only when ready."""

    game_id = str(schedule_row["game_id"])
    season = int(schedule_row["season"])
    week = int(schedule_row["week"])
    game_type = str(schedule_row["game_type"])
    final = _schedule_final(schedule_row)
    base = {
        "game_id": game_id,
        "season": season,
        "week": week,
        "game_type": game_type,
        "away_team": str(schedule_row["away_team"]),
        "home_team": str(schedule_row["home_team"]),
        "schedule_final": final,
    }
    if not final:
        return (
            GameReadiness(
                **base,
                status="game_not_final",
                raw_rows=0 if raw_game is None else raw_game.height,
                normalized_rows=0,
                fourth_down_candidates=0,
                eligible_decisions=0,
                warnings=(),
                errors=(),
                source_fingerprint=None,
            ),
            None,
        )
    if raw_game is None or not raw_game.height:
        return (
            GameReadiness(
                **base,
                status="source_missing",
                raw_rows=0,
                normalized_rows=0,
                fourth_down_candidates=0,
                eligible_decisions=0,
                warnings=(),
                errors=("schedule-final game has no PBP rows",),
                source_fingerprint=None,
            ),
            None,
        )

    errors = _raw_game_errors(schedule_row, raw_game)
    if errors:
        return (
            GameReadiness(
                **base,
                status="incomplete_source",
                raw_rows=raw_game.height,
                normalized_rows=0,
                fourth_down_candidates=0,
                eligible_decisions=0,
                warnings=(),
                errors=tuple(errors),
                source_fingerprint=fingerprint_frame(raw_game),
            ),
            None,
        )
    try:
        normalized = normalize_pbp(raw_game)
        candidates = extract_fourth_down_candidates(normalized)
    except Exception as error:
        return (
            GameReadiness(
                **base,
                status="validation_failed",
                raw_rows=raw_game.height,
                normalized_rows=0,
                fourth_down_candidates=0,
                eligible_decisions=0,
                warnings=(),
                errors=(f"{type(error).__name__}: {error}",),
                source_fingerprint=fingerprint_frame(raw_game),
            ),
            None,
        )
    eligible = candidates.filter(pl.col("disposition") == "eligible").height
    warnings = []
    if not PLAUSIBLE_RAW_ROWS[0] <= raw_game.height <= PLAUSIBLE_RAW_ROWS[1]:
        warnings.append("raw_play_count_outside_preregistered_plausibility_range")
    if not PLAUSIBLE_CANDIDATES[0] <= candidates.height <= PLAUSIBLE_CANDIDATES[1]:
        warnings.append("fourth_down_count_outside_preregistered_plausibility_range")
    if eligible > candidates.height:
        raise RuntimeError("eligible decision count exceeds candidate count")
    return (
        GameReadiness(
            **base,
            status="ready",
            raw_rows=raw_game.height,
            normalized_rows=normalized.height,
            fourth_down_candidates=candidates.height,
            eligible_decisions=eligible,
            warnings=tuple(warnings),
            errors=(),
            source_fingerprint=fingerprint_frame(raw_game),
        ),
        normalized,
    )


def build_source_manifest(
    schedule: pl.DataFrame,
    raw_pbp: pl.DataFrame | None,
    normalized_pbp: pl.DataFrame | None,
    *,
    season: int,
    week: int,
    retrieved_at_utc: str,
    schedule_source: str,
    pbp_source: str | None,
) -> SourceManifest:
    """Build a lightweight deterministic manifest with per-game hashes."""

    validate_live_shadow_request(season, week)
    selected_schedule = _select_schedule(schedule, season, week)
    selected_raw = _select_pbp(raw_pbp, season, week)
    selected_normalized = _select_pbp(normalized_pbp, season, week)
    per_game_schedule = {
        str(game_id): fingerprint_frame(
            selected_schedule.filter(pl.col("game_id") == game_id)
        )
        for game_id in sorted(selected_schedule["game_id"].unique())
    }
    per_game = (
        {
            str(game_id): fingerprint_frame(
                selected_raw.filter(pl.col("game_id") == game_id)
            )
            for game_id in sorted(selected_raw["game_id"].unique())
        }
        if selected_raw is not None and selected_raw.height
        else {}
    )
    final_ids = tuple(
        sorted(
            str(row["game_id"])
            for row in selected_schedule.iter_rows(named=True)
            if _schedule_final(row)
        )
    )
    return SourceManifest(
        season=season,
        week=week,
        retrieved_at_utc=retrieved_at_utc,
        schedule_source=schedule_source,
        pbp_source=pbp_source,
        schedule_snapshot_fingerprint=fingerprint_frame(schedule),
        pbp_snapshot_fingerprint=(
            fingerprint_frame(raw_pbp)
            if raw_pbp is not None and raw_pbp.height
            else None
        ),
        schedule_fingerprint=fingerprint_frame(selected_schedule),
        pbp_fingerprint=(
            fingerprint_frame(selected_raw)
            if selected_raw is not None and selected_raw.height
            else None
        ),
        schedule_rows=selected_schedule.height,
        source_rows=0 if selected_raw is None else selected_raw.height,
        normalized_rows=(
            0 if selected_normalized is None else selected_normalized.height
        ),
        scheduled_game_ids=tuple(
            sorted(str(value) for value in selected_schedule["game_id"].unique())
        ),
        final_game_ids=final_ids,
        observed_game_ids=tuple(sorted(per_game)),
        per_game_schedule_fingerprints=per_game_schedule,
        per_game_fingerprints=per_game,
        model_versions=(
            "coachiq-wp-v1",
            "coachiq-action-transition-v1",
            "coachiq-decision-v1",
        ),
        publication_version=PUBLICATION_POLICY_VERSION,
        generated_report_fingerprint=None,
    )


def compare_source_manifests(
    previous: SourceManifest, current: SourceManifest
) -> CorrectionReport:
    """Identify only games whose source fingerprint changed."""

    if (previous.season, previous.week) != (current.season, current.week):
        raise ValueError("source correction comparison requires one season/week")
    old_ids = set(previous.per_game_schedule_fingerprints) | set(
        previous.per_game_fingerprints
    )
    new_ids = set(current.per_game_schedule_fingerprints) | set(
        current.per_game_fingerprints
    )
    shared = old_ids & new_ids

    def identity(
        manifest: SourceManifest, game_id: str
    ) -> tuple[str | None, str | None]:
        return (
            manifest.per_game_schedule_fingerprints.get(game_id),
            manifest.per_game_fingerprints.get(game_id),
        )

    changed = tuple(
        sorted(
            game
            for game in shared
            if identity(previous, game) != identity(current, game)
        )
    )
    added = tuple(sorted(new_ids - old_ids))
    removed = tuple(sorted(old_ids - new_ids))
    unchanged = tuple(
        sorted(
            game
            for game in shared
            if identity(previous, game) == identity(current, game)
        )
    )
    return CorrectionReport(
        source_changed=bool(changed or added or removed),
        changed_game_ids=changed,
        added_game_ids=added,
        removed_game_ids=removed,
        unchanged_game_ids=unchanged,
    )


def tactical_context_warnings(
    record: DecisionPublicationRecord,
) -> tuple[str, ...]:
    """Flag fixed factual patterns for review without inferring hidden intent."""

    description = str(record.actual_decision.get("source_description") or "").lower()
    action = str(record.actual_decision.get("actual_action"))
    outcome = str(record.actual_decision.get("factual_outcome"))
    situation = record.situation
    warnings = [
        f"description_term:{term}" for term in TACTICAL_TERMS if term in description
    ]
    if (
        int(situation["quarter"]) == 4
        and int(situation["quarter_seconds_remaining"]) <= 120
    ):
        warnings.append("extreme_late_regulation")
    if action == "punt" and float(situation["yards_to_goal"]) <= 40:
        warnings.append("unusual_punt_field_position")
    if action == "field_goal" and float(situation["yards_to_goal"]) + 18 > 65:
        warnings.append("field_goal_distance_above_65")
    if outcome in TACTICAL_OUTCOMES:
        warnings.append(f"unusual_factual_outcome:{outcome}")
    return tuple(warnings)


def apply_editorial_review(
    record: DecisionPublicationRecord,
    status: str,
    *,
    reviewer: str | None = None,
    checklist: dict[str, bool] | None = None,
    note: str | None = None,
) -> EditorialReview:
    """Apply human state without permitting an override of model withholding."""

    if status not in EDITORIAL_STATUSES:
        raise ValueError(f"unknown editorial status: {status}")
    publishable = bool(record.publication.get("publishable"))
    if status == "approved" and not publishable:
        raise ValueError("human review cannot approve a publication-withheld decision")
    checks = dict(checklist or {})
    if status == "approved" and (
        set(checks) != set(EDITORIAL_CHECKS) or not all(checks.values())
    ):
        raise ValueError("approval requires a complete passing checklist")
    return EditorialReview(
        game_id=str(record.identity["game_id"]),
        play_id=int(record.identity["play_id"]),
        status=status,
        reviewer=reviewer,
        checklist=checks,
        tactical_warnings=tactical_context_warnings(record),
        note=note,
    )


def run_shadow_week(
    schedule: pl.DataFrame,
    raw_pbp: pl.DataFrame | None,
    trained_models: FrozenModels | None,
    *,
    season: int,
    week: int,
    retrieved_at_utc: str,
    schedule_source: str,
    pbp_source: str | None,
    determinism_verified: bool = False,
    correction_detection_verified: bool = False,
    runtime_seconds: float | None = None,
) -> tuple[ShadowOperationalReport, WeeklyAudit | None]:
    """Validate, optionally score, and assign preregistered operational status."""

    validate_live_shadow_request(season, week)
    selected_schedule = _select_schedule(schedule, season, week)
    raw_selected = _select_pbp(raw_pbp, season, week)
    readiness: list[GameReadiness] = []
    ready_frames: list[pl.DataFrame] = []
    for schedule_row in selected_schedule.iter_rows(named=True):
        game_id = str(schedule_row["game_id"])
        raw_game = (
            None
            if raw_selected is None
            else raw_selected.filter(pl.col("game_id") == game_id)
        )
        result, normalized = assess_game_readiness(schedule_row, raw_game)
        readiness.append(result)
        if normalized is not None:
            ready_frames.append(normalized)
    normalized_week = pl.concat(ready_frames) if ready_frames else None
    manifest = build_source_manifest(
        schedule,
        raw_pbp,
        normalized_week,
        season=season,
        week=week,
        retrieved_at_utc=retrieved_at_utc,
        schedule_source=schedule_source,
        pbp_source=pbp_source,
    )
    final_games = [game for game in readiness if game.schedule_final]
    ready_final_games = [game for game in final_games if game.status == "ready"]
    weekly: WeeklyAudit | None = None
    scoring_failures = 0
    readiness_reasons: list[str] = []
    if not final_games:
        readiness_reasons.append("no_completed_2026_games_available")
    elif len(ready_final_games) != len(final_games):
        readiness_reasons.append("one_or_more_completed_games_not_ready")
    elif trained_models is None or normalized_week is None:
        readiness_reasons.append("frozen_models_or_normalized_source_missing")
    else:
        try:
            _validate_model_manifest(trained_models.manifest)
            source = SourceMetadata(
                source=pbp_source or "2026 live shadow source",
                retrieved_at_utc=retrieved_at_utc,
                seasons=(season,),
                weeks=(week,),
                row_count=raw_selected.height if raw_selected is not None else 0,
                sha256=manifest.pbp_fingerprint or "missing",
            )
            candidate_weekly = audit_week(
                normalized_week,
                trained_models,
                source=source,
                mode=AuditMode.LIVE_SHADOW_2026,
            )
            validate_weekly_shadow_output(candidate_weekly)
            weekly = candidate_weekly
        except Exception as error:
            scoring_failures = 1
            diagnostic = f"weekly_scoring_failed:{type(error).__name__}:{error}"
            readiness_reasons.append(diagnostic)
            readiness = [
                replace(
                    game,
                    status="validation_failed",
                    errors=(*game.errors, diagnostic),
                )
                if game.status == "ready"
                else game
                for game in readiness
            ]
            ready_final_games = [
                game
                for game in readiness
                if game.schedule_final and game.status == "ready"
            ]

    tactical = _weekly_tactical_warnings(weekly)
    reviews = _pending_reviews(weekly, tactical)
    if weekly is not None and not determinism_verified:
        readiness_reasons.append("deterministic_rerun_not_verified")
    if weekly is not None and not correction_detection_verified:
        readiness_reasons.append("correction_detection_not_verified")
    if weekly is not None and runtime_seconds is not None and runtime_seconds > 60:
        readiness_reasons.append("runtime_above_ready_limit")
    if reviews:
        readiness_reasons.append("human_review_pending")
    status = _readiness_status(
        final_games=final_games,
        ready_final_games=ready_final_games,
        weekly=weekly,
        scoring_failures=scoring_failures,
        determinism_verified=determinism_verified,
        correction_detection_verified=correction_detection_verified,
        runtime_seconds=runtime_seconds,
        pending_reviews=len(reviews),
    )
    safe_count = 0 if weekly is None else weekly.publication_eligible
    attempted = 0 if weekly is None else weekly.eligible_decisions
    rate = safe_count / attempted if attempted else None
    historical_flag = bool(rate is not None and (rate < 0.0907 or rate > 0.2470))
    report_fingerprint = (
        hashlib.sha256(stable_json_dumps(weekly).encode()).hexdigest()
        if weekly is not None
        else None
    )
    manifest = replace(
        manifest,
        generated_report_fingerprint=report_fingerprint,
    )
    close_calls = _close_call_summaries(weekly)
    notable = _notable_full_records(weekly)
    return (
        ShadowOperationalReport(
            season=season,
            week=week,
            readiness_status=status,
            readiness_reasons=tuple(dict.fromkeys(readiness_reasons)),
            games_scheduled=selected_schedule.height,
            games_final=len(final_games),
            games_attempted=len(final_games),
            games_successfully_processed=(
                0 if weekly is None else len(ready_final_games)
            ),
            failed_games=len(final_games) - len(ready_final_games),
            fourth_down_candidates=(
                0 if weekly is None else weekly.total_fourth_down_candidates
            ),
            eligible_decisions=attempted,
            valued_decisions=0 if weekly is None else weekly.valued_decisions,
            clear_model_preferences=(
                0 if weekly is None else weekly.clear_model_preferences
            ),
            decisions_attempted=attempted,
            scoring_failures=scoring_failures,
            publication_safe_decisions=safe_count,
            human_approved_decisions=0,
            human_held_decisions=0,
            pending_human_review=len(reviews),
            tactical_warning_decisions=len(tactical),
            source_correction_events=0,
            deterministic_run_failures=(
                0 if weekly is None or determinism_verified else 1
            ),
            publication_safe_rate=rate,
            historical_publication_safe_rate_range=(0.1407, 0.1970),
            historical_range_flag=historical_flag,
            withhold_by_status=({} if weekly is None else weekly.withheld_by_status),
            withhold_by_reason=({} if weekly is None else weekly.withheld_by_reason),
            game_readiness=tuple(readiness),
            notable_decisions=notable,
            close_calls=close_calls,
            tactical_warnings=tuple(tactical),
            editorial_reviews=tuple(reviews),
            source_manifest=manifest,
            weekly_report_fingerprint=report_fingerprint,
        ),
        weekly,
    )


def build_shadow_brief(report: ShadowOperationalReport) -> str:
    """Render a deterministic internal brief without new public prose."""

    rate = (
        "unavailable"
        if report.publication_safe_rate is None
        else f"{report.publication_safe_rate:.1%}"
    )
    lines = [
        f"# CoachIQ {report.season} Week {report.week} shadow brief",
        "",
        "## Week summary",
        "",
        f"- Readiness: `{report.readiness_status}`",
        f"- Scheduled games: {report.games_scheduled}",
        f"- Final games: {report.games_final}",
        f"- Successfully processed games: {report.games_successfully_processed}",
        f"- Fourth-down candidates: {report.fourth_down_candidates}",
        f"- Eligible decisions: {report.eligible_decisions}",
        f"- Valued decisions: {report.valued_decisions}",
        f"- Clear model preferences: {report.clear_model_preferences}",
        f"- Decisions evaluated: {report.decisions_attempted}",
        f"- Publication-safe decisions: {report.publication_safe_decisions} ({rate})",
        f"- Readiness reasons: {', '.join(report.readiness_reasons) or 'none'}",
        "",
        "## Withholding distribution",
        "",
    ]
    if report.withhold_by_status:
        lines.extend(
            f"- `{name}`: {count}"
            for name, count in sorted(report.withhold_by_status.items())
        )
    else:
        lines.append("- No scored decisions.")
    lines.extend(("", "## Notable model disagreements", ""))
    if report.notable_decisions:
        lines.extend(
            f"- {item['public_language']}" for item in report.notable_decisions
        )
    else:
        lines.append("- None available.")
    lines.extend(("", "## Close calls", ""))
    if report.close_calls:
        lines.extend(
            f"- {item['game_id']} play {item['play_id']}: "
            "decision-v1 classified the comparison as close."
            for item in report.close_calls
        )
    else:
        lines.append("- None available.")
    lines.append("")
    return "\n".join(lines)


def finalize_operational_evidence(
    report: ShadowOperationalReport,
    *,
    determinism_verified: bool,
    correction_detection_verified: bool,
    runtime_seconds: float | None,
) -> ShadowOperationalReport:
    """Attach rerun/runtime evidence without rescoring a completed week."""

    evidence_reasons = {
        "deterministic_rerun_not_verified",
        "correction_detection_not_verified",
        "runtime_above_ready_limit",
    }
    reasons = [
        reason for reason in report.readiness_reasons if reason not in evidence_reasons
    ]
    has_scored_week = report.weekly_report_fingerprint is not None
    if has_scored_week and not determinism_verified:
        reasons.append("deterministic_rerun_not_verified")
    if has_scored_week and not correction_detection_verified:
        reasons.append("correction_detection_not_verified")
    if has_scored_week and runtime_seconds is not None and runtime_seconds > 60:
        reasons.append("runtime_above_ready_limit")

    if (
        not report.games_final
        or report.failed_games
        or not has_scored_week
        or report.scoring_failures
        or (runtime_seconds is not None and runtime_seconds > 120)
    ):
        status = "NOT READY"
    elif (
        not determinism_verified
        or not correction_detection_verified
        or report.pending_human_review
        or (runtime_seconds is not None and runtime_seconds > 60)
        or any(game.warnings for game in report.game_readiness if game.schedule_final)
    ):
        status = "READY WITH RESTRICTIONS"
    else:
        status = "READY"
    return replace(
        report,
        readiness_status=status,
        readiness_reasons=tuple(dict.fromkeys(reasons)),
        deterministic_run_failures=(
            0 if determinism_verified or not has_scored_week else 1
        ),
    )


def validate_weekly_shadow_output(weekly: WeeklyAudit) -> None:
    """Fail when safety, provenance, withholding, or notable contracts drift."""

    required_safety = {
        "field_clipping_mass_by_action",
        "clock_clipping_mass_by_action",
        "maximum_field_clipping_mass",
        "maximum_clock_clipping_mass",
        "maximum_overtime_boundary_mass",
        "sparse_supported_action",
        "unsupported_available_action",
        "actual_action_supported",
    }
    required_provenance = {
        "wp_model_version",
        "action_transition_model_version",
        "decision_value_version",
        "publication_policy_version",
        "training_through_season",
        "source",
    }
    notable_ids = {
        (str(item["identity"]["game_id"]), int(item["identity"]["play_id"]))
        for item in weekly.notable_decisions
    }
    records = {
        (str(record.identity["game_id"]), int(record.identity["play_id"])): record
        for game in weekly.games
        for record in game.decisions
    }
    for key, record in records.items():
        if not required_safety <= set(record.safety_diagnostics):
            raise ValueError(f"publication decision missing safety metadata: {key}")
        if not required_provenance <= set(record.provenance):
            raise ValueError(f"publication decision missing provenance: {key}")
        if (
            record.provenance["wp_model_version"] != "coachiq-wp-v1"
            or record.provenance["action_transition_model_version"]
            != "coachiq-action-transition-v1"
            or record.provenance["decision_value_version"] != "coachiq-decision-v1"
            or record.provenance["publication_policy_version"]
            != "coachiq-publication-v1"
            or record.provenance["training_through_season"] != 2024
        ):
            raise ValueError(f"publication decision version mismatch: {key}")
        if not record.publication.get("publishable") and record.public_language:
            raise ValueError(f"withheld decision contains public language: {key}")
    for key in notable_ids:
        if key not in records or not records[key].publication.get("publishable"):
            raise ValueError(f"notable decision is not publication-safe: {key}")


def _schedule_final(row: dict[str, Any]) -> bool:
    return all(
        row.get(field) is not None for field in ("away_score", "home_score", "result")
    )


def _raw_game_errors(schedule_row: dict[str, Any], raw_game: pl.DataFrame) -> list[str]:
    errors: list[str] = []
    for field in ("season", "week", "game_id", "home_team", "away_team", "play_id"):
        if field not in raw_game.columns:
            errors.append(f"missing_required_identity_column:{field}")
    if errors:
        return errors
    if raw_game["game_id"].n_unique() != 1:
        errors.append("multiple_game_ids")
    if raw_game["play_id"].n_unique() != raw_game.height:
        errors.append("duplicate_play_ids")
    for field in ("season", "week", "home_team", "away_team"):
        expected = schedule_row[field]
        if (
            raw_game[field].drop_nulls().n_unique() != 1
            or raw_game[field].drop_nulls()[0] != expected
        ):
            errors.append(f"schedule_pbp_mismatch:{field}")
    if "result" not in raw_game.columns or not raw_game["result"].drop_nulls().len():
        errors.append("missing_final_score_margin")
    elif float(raw_game["result"].drop_nulls()[0]) != float(schedule_row["result"]):
        errors.append("schedule_pbp_final_score_mismatch")
    terminal = False
    if "desc" in raw_game.columns:
        terminal = bool(
            raw_game.select(
                pl.col("desc")
                .cast(pl.String)
                .str.contains("END GAME", literal=True)
                .fill_null(False)
                .any()
            ).item()
        )
    if not terminal and "game_seconds_remaining" in raw_game.columns:
        terminal = bool(raw_game["game_seconds_remaining"].drop_nulls().min() <= 0)
    if not terminal:
        errors.append("missing_terminal_game_marker")
    return errors


def _select_schedule(schedule: pl.DataFrame, season: int, week: int) -> pl.DataFrame:
    required = {
        "season",
        "week",
        "game_id",
        "game_type",
        "away_team",
        "home_team",
        "away_score",
        "home_score",
        "result",
    }
    missing = sorted(required - set(schedule.columns))
    if missing:
        raise ValueError(f"schedule missing required columns: {', '.join(missing)}")
    return schedule.filter(
        (pl.col("season") == season)
        & (pl.col("week") == week)
        & pl.col("game_type").is_in(("REG", "POST"))
    ).sort("game_id")


def _select_pbp(
    frame: pl.DataFrame | None, season: int, week: int
) -> pl.DataFrame | None:
    if frame is None:
        return None
    if "season" not in frame.columns or "week" not in frame.columns:
        return frame
    return frame.filter((pl.col("season") == season) & (pl.col("week") == week)).sort(
        [column for column in ("game_id", "play_id") if column in frame.columns]
    )


def _validate_model_manifest(manifest: dict[str, Any]) -> None:
    frozen = manifest.get("frozen_artifact", {})
    expected = {
        "wp_model_version": "coachiq-wp-v1",
        "action_transition_model_version": "coachiq-action-transition-v1",
        "decision_value_version": "coachiq-decision-v1",
    }
    for field, value in expected.items():
        if frozen.get(field) != value:
            raise ValueError(f"frozen model version mismatch: {field}")
    if manifest.get("training_through_season") != 2024:
        raise ValueError("live shadow model must be trained through 2024")


def _weekly_tactical_warnings(weekly: WeeklyAudit | None) -> list[dict[str, Any]]:
    if weekly is None:
        return []
    warnings = []
    for game in weekly.games:
        for record in game.decisions:
            codes = tactical_context_warnings(record)
            if codes:
                warnings.append(
                    {
                        "game_id": record.identity["game_id"],
                        "play_id": record.identity["play_id"],
                        "publication_status": record.publication["status"],
                        "warnings": codes,
                    }
                )
    return warnings


def _pending_reviews(
    weekly: WeeklyAudit | None, warnings: list[dict[str, Any]]
) -> list[EditorialReview]:
    if weekly is None:
        return []
    warning_lookup = {
        (str(item["game_id"]), int(item["play_id"])): tuple(item["warnings"])
        for item in warnings
    }
    reviews = []
    for game in weekly.games:
        for record in game.decisions:
            if not record.publication["publishable"]:
                continue
            reviews.append(
                EditorialReview(
                    game_id=str(record.identity["game_id"]),
                    play_id=int(record.identity["play_id"]),
                    status="pending_review",
                    reviewer=None,
                    checklist={},
                    tactical_warnings=warning_lookup.get(
                        (
                            str(record.identity["game_id"]),
                            int(record.identity["play_id"]),
                        ),
                        (),
                    ),
                    note=None,
                )
            )
    return reviews


def _close_call_summaries(weekly: WeeklyAudit | None) -> tuple[dict[str, Any], ...]:
    if weekly is None:
        return ()
    rows = []
    for game in weekly.games:
        for record in game.decisions:
            if record.comparison["decision_v1_classification"] == "close_call":
                rows.append(
                    {
                        "game_id": record.identity["game_id"],
                        "play_id": record.identity["play_id"],
                        "situation": record.situation,
                        "actual_action": record.actual_decision["actual_action"],
                        "minimum_preference_gap": record.comparison[
                            "minimum_preference_gap"
                        ],
                        "minimum_pairwise_superiority": record.comparison[
                            "minimum_pairwise_superiority"
                        ],
                    }
                )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                -float(row["minimum_preference_gap"] or 0.0),
                -float(row["minimum_pairwise_superiority"] or 0.0),
                str(row["game_id"]),
                int(row["play_id"]),
            ),
        )[:10]
    )


def _notable_full_records(
    weekly: WeeklyAudit | None,
) -> tuple[dict[str, Any], ...]:
    if weekly is None:
        return ()
    records = [
        record
        for game in weekly.games
        for record in game.decisions
        if bool(record.publication["publishable"])
    ]
    ordered = sorted(
        records,
        key=lambda record: (
            -float(record.comparison["actual_action_modeled_gap"] or 0.0),
            -float(record.comparison["minimum_pairwise_superiority"] or 0.0),
            str(record.identity["game_id"]),
            int(record.identity["play_id"]),
        ),
    )[:10]
    return tuple(record.to_dict() for record in ordered)


def _readiness_status(
    *,
    final_games: list[GameReadiness],
    ready_final_games: list[GameReadiness],
    weekly: WeeklyAudit | None,
    scoring_failures: int,
    determinism_verified: bool,
    correction_detection_verified: bool,
    runtime_seconds: float | None,
    pending_reviews: int,
) -> str:
    if (
        not final_games
        or len(final_games) != len(ready_final_games)
        or weekly is None
        or scoring_failures
        or (runtime_seconds is not None and runtime_seconds > 120)
    ):
        return "NOT READY"
    if (
        not determinism_verified
        or not correction_detection_verified
        or pending_reviews
        or (runtime_seconds is not None and runtime_seconds > 60)
        or any(game.warnings for game in ready_final_games)
    ):
        return "READY WITH RESTRICTIONS"
    return "READY"


__all__ = [
    "SHADOW_PROTOCOL_SHA256",
    "CorrectionReport",
    "EditorialReview",
    "GameReadiness",
    "ShadowOperationalReport",
    "SourceManifest",
    "apply_editorial_review",
    "assess_game_readiness",
    "build_shadow_brief",
    "build_source_manifest",
    "compare_source_manifests",
    "finalize_operational_evidence",
    "run_shadow_week",
    "tactical_context_warnings",
    "validate_live_shadow_request",
    "validate_weekly_shadow_output",
]
