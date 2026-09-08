"""Deterministic game and weekly audits using the frozen CoachIQ v1 stack."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from coachiq.analysis.decision_value import (
    DECISION_BOOTSTRAP_REPLICATES,
    DECISION_BOOTSTRAP_SEED,
    DECISION_THRESHOLD_POLICY_V1,
    DecisionBootstrapContext,
    DecisionValueAudit,
    audit_decision_value,
    build_decision_bootstrap_context,
)
from coachiq.analysis.fourth_down import extract_fourth_down_candidates
from coachiq.analysis.holdout import HISTORICAL_SEASONS, frozen_artifact_identity
from coachiq.models.action_baselines import (
    ActionBaselineSet,
    canonical_state_from_candidate,
    fit_action_baselines,
)
from coachiq.models.state import build_state_value_rows
from coachiq.models.state_value import StateValueModel
from coachiq.models.wp_selection import fit_locked_wp_model
from coachiq.product.publication import (
    PUBLICATION_POLICY_V1,
    PublicationPolicy,
    SafetyDiagnostics,
    apply_publication_policy,
    attach_overtime_diagnostic,
    transition_clipping_diagnostics,
)

LATEST_POLICY_DEVELOPMENT_SEASON = 2025


class AuditMode(StrEnum):
    """Explicit data boundary for historical and prospective audit paths."""

    HISTORICAL = "historical"
    LIVE_SHADOW_2026 = "live_shadow_2026"


@dataclass(frozen=True)
class SourceMetadata:
    """Lightweight source identity retained with every report."""

    source: str
    retrieved_at_utc: str
    seasons: tuple[int, ...]
    weeks: tuple[int, ...]
    row_count: int
    sha256: str
    resolved_assets: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FrozenModels:
    """In-memory fitted v1 components reused across all games in a run."""

    action_models: ActionBaselineSet
    state_value_model: StateValueModel
    bootstrap_context: DecisionBootstrapContext
    manifest: dict[str, Any]


@dataclass(frozen=True)
class CandidateEvaluation:
    """Transient scientific output plus product safety diagnostics."""

    audit: DecisionValueAudit
    diagnostics: SafetyDiagnostics


@dataclass(frozen=True)
class DecisionPublicationRecord:
    """Canonical product-facing record for one eligible fourth down."""

    identity: dict[str, Any]
    situation: dict[str, Any]
    actual_decision: dict[str, Any]
    modeled_actions: tuple[dict[str, Any], ...]
    comparison: dict[str, Any]
    safety_diagnostics: dict[str, Any]
    publication: dict[str, Any]
    provenance: dict[str, Any]
    public_language: str | None
    internal_language: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GameAudit:
    """Neutral audit summary and decision records for one completed game."""

    game_id: str
    season: int
    week: int
    home_team: str
    away_team: str
    total_fourth_down_candidates: int
    eligible_decisions: int
    valued_decisions: int
    publishable_decisions: int
    withheld_decisions: int
    withheld_by_status: dict[str, int]
    withheld_by_reason: dict[str, int]
    decisions: tuple[DecisionPublicationRecord, ...]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WeeklyAudit:
    """Internal content-discovery report with no coach aggregation."""

    season: int
    week: int
    games_processed: int
    total_fourth_down_candidates: int
    eligible_decisions: int
    valued_decisions: int
    clear_model_preferences: int
    publication_eligible: int
    withheld_by_status: dict[str, int]
    withheld_by_reason: dict[str, int]
    notable_decisions: tuple[dict[str, Any], ...]
    strongest_pairwise_evidence: tuple[dict[str, Any], ...]
    games: tuple[GameAudit, ...]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_policy_development_boundary(seasons: Iterable[int]) -> tuple[int, ...]:
    """Block all 2026 access while publication-v1 is being developed."""

    values = tuple(sorted(set(int(value) for value in seasons)))
    if not values:
        raise ValueError("at least one source season is required")
    if max(values) > LATEST_POLICY_DEVELOPMENT_SEASON:
        raise ValueError("2026 data is blocked during publication-v1 development")
    return values


def validate_audit_boundary(
    seasons: Iterable[int], mode: AuditMode = AuditMode.HISTORICAL
) -> tuple[int, ...]:
    """Allow 2026 only through the explicit prospective shadow mode."""

    values = tuple(sorted(set(int(value) for value in seasons)))
    if mode == AuditMode.HISTORICAL:
        return validate_policy_development_boundary(values)
    if mode == AuditMode.LIVE_SHADOW_2026 and values == (2026,):
        return values
    raise ValueError("live shadow mode requires exactly season 2026")


def fit_frozen_models(
    historical_pbp: pl.DataFrame, *, project_root: Path
) -> FrozenModels:
    """Fit frozen v1 once from exactly 2014-2024 and return an audit manifest."""

    seasons = tuple(sorted(int(value) for value in historical_pbp["season"].unique()))
    if seasons != HISTORICAL_SEASONS:
        raise ValueError("frozen live models require exactly 2014-2024 training data")
    return fit_chronological_models(historical_pbp, project_root=project_root)


def fit_chronological_models(
    historical_pbp: pl.DataFrame, *, project_root: Path
) -> FrozenModels:
    """Fit the unchanged v1 specification for a historical chronological fold."""

    seasons = tuple(sorted(int(value) for value in historical_pbp["season"].unique()))
    expected = tuple(range(2014, max(seasons) + 1)) if seasons else ()
    if seasons != expected or not seasons or max(seasons) > 2024:
        raise ValueError(
            "v1 fitting requires consecutive 2014-through-2024-or-earlier data"
        )
    identity = frozen_artifact_identity(project_root)
    candidates = extract_fourth_down_candidates(historical_pbp)
    state_rows = build_state_value_rows(historical_pbp)
    action_models = fit_action_baselines(candidates)
    state_model = fit_locked_wp_model(state_rows)
    context = build_decision_bootstrap_context(
        action_models,
        bootstrap_replicates=DECISION_BOOTSTRAP_REPLICATES,
        random_seed=DECISION_BOOTSTRAP_SEED,
    )
    manifest = {
        "training_seasons": list(seasons),
        "training_through_season": max(seasons),
        "normalized_training_rows": historical_pbp.height,
        "state_training_rows": state_rows.height,
        "action_training_transitions": action_models.training_rows.height,
        "action_training_games": action_models.training_rows["game_id"].n_unique(),
        "normalized_training_fingerprint": fingerprint_frame(historical_pbp),
        "wp_fitted_parameters": state_model.to_dict(),
        "frozen_artifact": identity,
        "bootstrap_replicates": DECISION_BOOTSTRAP_REPLICATES,
        "bootstrap_seed": DECISION_BOOTSTRAP_SEED,
        "loading_strategy": (
            "deterministic in-memory fit once per run; reuse fitted models and "
            "bootstrap weights for every game"
        ),
    }
    return FrozenModels(action_models, state_model, context, manifest)


def audit_game(
    game_pbp: pl.DataFrame,
    trained_models: FrozenModels,
    publication_policy: PublicationPolicy = PUBLICATION_POLICY_V1,
    *,
    source: SourceMetadata,
    mode: AuditMode = AuditMode.HISTORICAL,
) -> GameAudit:
    """Audit one completed game with no fitting or mutable global state."""

    seasons = validate_audit_boundary(game_pbp["season"].unique(), mode)
    if len(seasons) != 1:
        raise ValueError("audit_game requires exactly one season")
    game_ids = tuple(str(value) for value in game_pbp["game_id"].unique())
    if len(game_ids) != 1:
        raise ValueError("audit_game requires exactly one game")
    candidates = extract_fourth_down_candidates(game_pbp)
    eligible = candidates.filter(pl.col("disposition") == "eligible")
    decisions = tuple(
        build_publication_record(
            row,
            trained_models,
            publication_policy,
            source=source,
            mode=mode,
        )
        for row in eligible.iter_rows(named=True)
    )
    return assemble_game_audit(
        game_pbp,
        candidates.height,
        decisions,
        trained_models,
        publication_policy,
        source=source,
    )


def assemble_game_audit(
    game_pbp: pl.DataFrame,
    total_fourth_down_candidates: int,
    decisions: tuple[DecisionPublicationRecord, ...],
    trained_models: FrozenModels,
    publication_policy: PublicationPolicy = PUBLICATION_POLICY_V1,
    *,
    source: SourceMetadata,
) -> GameAudit:
    """Aggregate already-valued records into the deterministic game contract."""

    game_ids = tuple(str(value) for value in game_pbp["game_id"].unique())
    seasons = tuple(int(value) for value in game_pbp["season"].unique())
    if len(game_ids) != 1 or len(seasons) != 1:
        raise ValueError("game aggregation requires exactly one game and season")
    statuses = Counter(
        str(record.publication["status"])
        for record in decisions
        if not bool(record.publication["publishable"])
    )
    reasons = Counter(
        reason
        for record in decisions
        for reason in record.publication["withholding_reasons"]
    )
    first = game_pbp.row(0, named=True)
    valued = sum(
        record.comparison["actual_action_modeled_gap"] is not None
        for record in decisions
    )
    publishable = sum(bool(record.publication["publishable"]) for record in decisions)
    return GameAudit(
        game_id=game_ids[0],
        season=seasons[0],
        week=int(first["week"]),
        home_team=str(first["home_team"]),
        away_team=str(first["away_team"]),
        total_fourth_down_candidates=total_fourth_down_candidates,
        eligible_decisions=len(decisions),
        valued_decisions=valued,
        publishable_decisions=publishable,
        withheld_decisions=len(decisions) - publishable,
        withheld_by_status=dict(sorted(statuses.items())),
        withheld_by_reason=dict(sorted(reasons.items())),
        decisions=decisions,
        provenance={
            "source": source.to_dict(),
            "models": trained_models.manifest,
            "publication_policy": asdict(publication_policy),
        },
    )


def audit_week(
    week_pbp: pl.DataFrame,
    trained_models: FrozenModels,
    publication_policy: PublicationPolicy = PUBLICATION_POLICY_V1,
    *,
    source: SourceMetadata,
    notable_limit: int = 10,
    mode: AuditMode = AuditMode.HISTORICAL,
) -> WeeklyAudit:
    """Aggregate games by decisions, never by coach."""

    seasons = validate_audit_boundary(week_pbp["season"].unique(), mode)
    weeks = tuple(sorted(int(value) for value in week_pbp["week"].unique()))
    if len(seasons) != 1 or len(weeks) != 1:
        raise ValueError("audit_week requires exactly one season and week")
    games = tuple(
        audit_game(
            week_pbp.filter(pl.col("game_id") == game_id),
            trained_models,
            publication_policy,
            source=source,
            mode=mode,
        )
        for game_id in sorted(str(value) for value in week_pbp["game_id"].unique())
    )
    return aggregate_week_audits(
        games,
        source=source,
        models_manifest=trained_models.manifest,
        publication_policy=publication_policy,
        notable_limit=notable_limit,
    )


def aggregate_week_audits(
    games: tuple[GameAudit, ...],
    *,
    source: SourceMetadata,
    models_manifest: dict[str, Any],
    publication_policy: PublicationPolicy = PUBLICATION_POLICY_V1,
    notable_limit: int = 10,
) -> WeeklyAudit:
    """Aggregate completed game audits without coach grades or rankings."""

    if not games:
        raise ValueError("weekly aggregation requires at least one game")
    seasons = {game.season for game in games}
    weeks = {game.week for game in games}
    if len(seasons) != 1 or len(weeks) != 1:
        raise ValueError("weekly aggregation requires one season and week")
    records = [record for game in games for record in game.decisions]
    publishable = [
        record for record in records if bool(record.publication["publishable"])
    ]
    notable = sorted(
        publishable,
        key=lambda record: (
            -float(record.comparison["actual_action_modeled_gap"] or 0.0),
            str(record.identity["game_id"]),
            int(record.identity["play_id"]),
        ),
    )[:notable_limit]
    strongest = sorted(
        publishable,
        key=lambda record: (
            -float(record.comparison["minimum_pairwise_superiority"] or 0.0),
            str(record.identity["game_id"]),
            int(record.identity["play_id"]),
        ),
    )[:notable_limit]
    statuses = Counter(
        str(record.publication["status"])
        for record in records
        if not bool(record.publication["publishable"])
    )
    reasons = Counter(
        reason
        for record in records
        for reason in record.publication["withholding_reasons"]
    )
    return WeeklyAudit(
        season=next(iter(seasons)),
        week=next(iter(weeks)),
        games_processed=len(games),
        total_fourth_down_candidates=sum(
            game.total_fourth_down_candidates for game in games
        ),
        eligible_decisions=len(records),
        valued_decisions=sum(
            record.comparison["actual_action_modeled_gap"] is not None
            for record in records
        ),
        clear_model_preferences=sum(
            record.comparison["decision_v1_classification"] == "clear_model_preference"
            for record in records
        ),
        publication_eligible=len(publishable),
        withheld_by_status=dict(sorted(statuses.items())),
        withheld_by_reason=dict(sorted(reasons.items())),
        notable_decisions=tuple(_notable_summary(record) for record in notable),
        strongest_pairwise_evidence=tuple(
            _notable_summary(record) for record in strongest
        ),
        games=games,
        provenance={
            "source": source.to_dict(),
            "models": models_manifest,
            "publication_policy": asdict(publication_policy),
        },
    )


def build_publication_record(
    row: dict[str, Any],
    trained_models: FrozenModels,
    publication_policy: PublicationPolicy = PUBLICATION_POLICY_V1,
    *,
    source: SourceMetadata,
    mode: AuditMode = AuditMode.HISTORICAL,
) -> DecisionPublicationRecord:
    """Create the canonical publication record for one eligible candidate."""

    evaluation = evaluate_candidate(row, trained_models, mode=mode)
    return publication_record_from_evaluation(
        row,
        trained_models,
        evaluation,
        publication_policy,
        source=source,
        mode=mode,
    )


def evaluate_candidate(
    row: dict[str, Any],
    trained_models: FrozenModels,
    *,
    mode: AuditMode = AuditMode.HISTORICAL,
) -> CandidateEvaluation:
    """Run frozen decision-v1 and exact pre-clip diagnostics once."""

    validate_audit_boundary((int(row["season"]),), mode)
    state = canonical_state_from_candidate(row)
    audit = audit_decision_value(
        state,
        str(row["actual_action"]),
        trained_models.action_models,
        trained_models.state_value_model,
        threshold_policy=DECISION_THRESHOLD_POLICY_V1,
        bootstrap_replicates=DECISION_BOOTSTRAP_REPLICATES,
        confidence_level=0.90,
        random_seed=DECISION_BOOTSTRAP_SEED,
        bootstrap_context=trained_models.bootstrap_context,
    )
    clipping = transition_clipping_diagnostics(
        state, audit.actual_action, trained_models.action_models
    )
    diagnostics = attach_overtime_diagnostic(clipping, audit)
    return CandidateEvaluation(audit=audit, diagnostics=diagnostics)


def publication_record_from_evaluation(
    row: dict[str, Any],
    trained_models: FrozenModels,
    evaluation: CandidateEvaluation,
    publication_policy: PublicationPolicy = PUBLICATION_POLICY_V1,
    *,
    source: SourceMetadata,
    mode: AuditMode = AuditMode.HISTORICAL,
) -> DecisionPublicationRecord:
    """Apply a policy to an already-scored candidate without rerunning bootstrap."""

    validate_audit_boundary((int(row["season"]),), mode)
    audit = evaluation.audit
    diagnostics = evaluation.diagnostics
    publication = apply_publication_policy(audit, diagnostics, publication_policy)
    comparison_action, comparison_gap = _claimed_comparison(audit)
    if publication.publishable:
        if comparison_action is None or comparison_gap is None:
            raise ValueError("publishable decision lacks a claimed comparison")
        public_language = publication_safe_language(
            publication, row, audit, comparison_action, comparison_gap
        )
    else:
        public_language = None
    return DecisionPublicationRecord(
        identity={
            "season": int(row["season"]),
            "week": int(row["week"]),
            "game_id": str(row["game_id"]),
            "play_id": int(row["play_id"]),
            "home_team": str(row["home_team"]),
            "away_team": str(row["away_team"]),
            "possession_team": str(row["possession_team"]),
        },
        situation={
            "quarter": int(row["quarter"]),
            "quarter_seconds_remaining": int(row["quarter_seconds_remaining"]),
            "game_seconds_remaining": int(row["game_seconds_remaining"]),
            "score_differential": int(row["score_differential"]),
            "yards_to_goal": float(row["yards_to_goal"]),
            "yards_to_go": float(row["yards_to_go"]),
            "posteam_timeouts_remaining": int(row["posteam_timeouts_remaining"]),
            "defteam_timeouts_remaining": int(row["defteam_timeouts_remaining"]),
        },
        actual_decision={
            "actual_action": audit.actual_action,
            "factual_outcome": str(row["factual_outcome"]),
            "source_description": row.get("description"),
        },
        modeled_actions=tuple(value.to_dict() for value in audit.actions),
        comparison={
            "model_preferred_supported_action": audit.model_preferred_action,
            "claimed_comparison_action": comparison_action,
            "claimed_comparison_gap": comparison_gap,
            "actual_action_modeled_gap": audit.raw_action_value_gap,
            "minimum_preference_gap": audit.model_preferred_minimum_gap,
            "minimum_pairwise_superiority": (audit.model_preferred_minimum_superiority),
            "pairwise_evidence": tuple(
                pair.to_dict() for pair in audit.pairwise_differences
            ),
            "decision_v1_classification": audit.classification,
            "decision_v1_classification_reason": audit.classification_reason,
        },
        safety_diagnostics=diagnostics.to_dict(),
        publication=publication.to_dict(),
        provenance={
            "wp_model_version": audit.wp_model_version,
            "action_transition_model_version": (audit.action_transition_model_version),
            "decision_value_version": audit.decision_value_version,
            "publication_policy_version": publication_policy.version,
            "training_through_season": max(
                trained_models.state_value_model.training_seasons
            ),
            "training_seasons": list(trained_models.state_value_model.training_seasons),
            "bootstrap_replicates": DECISION_BOOTSTRAP_REPLICATES,
            "bootstrap_seed": DECISION_BOOTSTRAP_SEED,
            "source": source.to_dict(),
        },
        public_language=public_language,
        internal_language=publication.internal_explanation,
    )


def neutral_public_language(
    row: dict[str, Any],
    audit: DecisionValueAudit,
    comparison_action: str,
    modeled_gap: float,
) -> str:
    """Render deterministic non-causal wording for a publication-safe record."""

    values = {value.action: value.expected_win_probability for value in audit.actions}
    preferred = str(audit.model_preferred_action)
    preferred_value = float(values[preferred])
    comparison_value = float(values[comparison_action])
    return (
        f"On 4th-and-{_format_yards(float(row['yards_to_go']))} from "
        f"{_field_position(float(row['yards_to_goal']))}, CoachIQ favored "
        f"{_action_phrase(preferred)}. The model estimated "
        f"{_action_phrase(preferred)} at {preferred_value:.1%} win probability "
        f"and {_action_phrase(comparison_action)} at {comparison_value:.1%}, "
        f"a modeled advantage of {modeled_gap * 100:.1f} percentage points. "
        "The comparison met CoachIQ v1's frozen evidence threshold and "
        "publication-v1 safety checks."
    )


def publication_safe_language(
    publication: Any,
    row: dict[str, Any],
    audit: DecisionValueAudit,
    comparison_action: str,
    modeled_gap: float,
) -> str | None:
    """Return neutral wording only when the separate policy permits it."""

    if not publication.publishable:
        return None
    return neutral_public_language(row, audit, comparison_action, modeled_gap)


def fingerprint_frame(frame: pl.DataFrame) -> str:
    """Return a deterministic fingerprint of values, schema, order, and shape."""

    digest = hashlib.sha256()
    digest.update(
        json.dumps({name: str(kind) for name, kind in frame.schema.items()}).encode()
    )
    digest.update(str(frame.shape).encode())
    hashes = frame.hash_rows(seed=2508, seed_1=2508, seed_2=2508, seed_3=2508)
    digest.update(hashes.to_numpy().tobytes())
    return digest.hexdigest()


def stable_json_dumps(report: GameAudit | WeeklyAudit | dict[str, Any]) -> str:
    """Serialize report output deterministically."""

    payload = report if isinstance(report, dict) else report.to_dict()
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _claimed_comparison(audit: DecisionValueAudit) -> tuple[str | None, float | None]:
    preferred = audit.model_preferred_action
    if preferred is None:
        return None, None
    values = {
        value.action: value.expected_win_probability
        for value in audit.actions
        if value.expected_win_probability is not None
    }
    if preferred not in values:
        return None, None
    if audit.actual_action != preferred:
        if audit.actual_action not in values:
            return None, None
        comparison = audit.actual_action
    else:
        alternatives = [action for action in values if action != preferred]
        if not alternatives:
            return None, None
        comparison = max(
            alternatives,
            key=lambda action: (float(values[action]), action),
        )
    return comparison, float(values[preferred]) - float(values[comparison])


def _notable_summary(record: DecisionPublicationRecord) -> dict[str, Any]:
    return {
        "identity": record.identity,
        "situation": record.situation,
        "actual_action": record.actual_decision["actual_action"],
        "model_preferred_supported_action": record.comparison[
            "model_preferred_supported_action"
        ],
        "actual_action_modeled_gap": record.comparison["actual_action_modeled_gap"],
        "minimum_pairwise_superiority": record.comparison[
            "minimum_pairwise_superiority"
        ],
        "public_language": record.public_language,
    }


def _action_phrase(action: str) -> str:
    return {
        "go": "going for it",
        "field_goal": "attempting a field goal",
        "punt": "punting",
    }[action]


def _field_position(yards_to_goal: float) -> str:
    yard = int(round(yards_to_goal if yards_to_goal <= 50 else 100 - yards_to_goal))
    return (
        "the 50"
        if yard == 50
        else (f"the opponent {yard}" if yards_to_goal < 50 else f"their own {yard}")
    )


def _format_yards(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


__all__ = [
    "AuditMode",
    "CandidateEvaluation",
    "LATEST_POLICY_DEVELOPMENT_SEASON",
    "DecisionPublicationRecord",
    "FrozenModels",
    "GameAudit",
    "SourceMetadata",
    "WeeklyAudit",
    "audit_game",
    "audit_week",
    "aggregate_week_audits",
    "assemble_game_audit",
    "build_publication_record",
    "evaluate_candidate",
    "fingerprint_frame",
    "fit_frozen_models",
    "fit_chronological_models",
    "neutral_public_language",
    "publication_safe_language",
    "publication_record_from_evaluation",
    "stable_json_dumps",
    "validate_policy_development_boundary",
    "validate_audit_boundary",
]
