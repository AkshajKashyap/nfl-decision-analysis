"""Explicit, one-time evaluation path for the protected 2025 holdout."""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from coachiq.analysis.decision_diagnostics import (
    _aggregate_report,
    _largest_gap_sort_key,
    _public_summary,
    _score_decisions,
    _situation,
    _support_cell,
    _transition_audit,
)
from coachiq.analysis.decision_value import (
    ACTION_TRANSITION_MODEL_VERSION,
    ACTIONS,
    DECISION_BOOTSTRAP_REPLICATES,
    DECISION_BOOTSTRAP_SEED,
    DECISION_THRESHOLD_POLICY_V1,
    DECISION_VALUE_VERSION,
    build_decision_bootstrap_context,
)
from coachiq.analysis.fourth_down import extract_fourth_down_candidates
from coachiq.models.action_baselines import (
    MAX_FIELD_GOAL_DISTANCE,
    MIN_SUPPORT_OBSERVATIONS,
    SPARSE_SUPPORT_OBSERVATIONS,
    ActionBaselineSet,
    canonical_state_from_candidate,
    fit_action_baselines,
)
from coachiq.models.state import build_state_value_rows
from coachiq.models.wp_selection import (
    LOCKED_WP_CANDIDATE_ID,
    LOCKED_WP_MODEL_VERSION,
    LOCKED_WP_USES_RECALIBRATION,
    fit_locked_wp_model,
    probability_report,
    property_grid_report,
)

HISTORICAL_SEASONS = tuple(range(2014, 2025))
HOLDOUT_SEASON = 2025
PROTOCOL_SHA256 = "a98c5817a90926f5fe207493f2b7670048d1f2b0fb32c8e802266b47a485034b"
FROZEN_SOURCE_HASHES = {
    "src/coachiq/models/state_value.py": (
        "b5a757f513baf04e1ac0bdf37cf34947257cee9b040a1891adf57e634cfb3307"
    ),
    "src/coachiq/models/wp_selection.py": (
        "0e683d6a2e23989ca1fb840d42255be4e6bcee5669599847d8802a18e75548f2"
    ),
    "src/coachiq/models/action_baselines.py": (
        "d03391f3ad8dce97ef44e458870453f732321e11cb23ec67c2721a85616a9a97"
    ),
    "src/coachiq/analysis/decision_value.py": (
        "6709cf7f960dbb53240ed81dc5ab5530ebff0a5a7c48e5bbdbfd2edf6d3da9fe"
    ),
    "src/coachiq/analysis/decision_diagnostics.py": (
        "bbe816c577c5b9f45b674bbfcfc84ca874dc373c3dd21a80cf842918bc6d9fe2"
    ),
    "src/coachiq/analysis/fourth_down.py": (
        "0ebec62d5dad9b034c5377aa8be04ee3147f8b7231d2e0bbf53bf771e29a3f9b"
    ),
    "src/coachiq/data/normalize.py": (
        "22dd09c20f0973f82fba5b514566ac4a7249603094c415c896758b0417418c4f"
    ),
    "src/coachiq/data/schema.py": (
        "4a940b260d6afd1ddf3fe0ff20c6c9945dcf22773e7db7d0cd4c89d1daaf52d9"
    ),
}
CLIP_THRESHOLDS = (0.0, 0.10, 0.25, 0.50)


def validate_holdout_boundary(
    historical_seasons: list[int] | tuple[int, ...],
    holdout_seasons: list[int] | tuple[int, ...],
) -> None:
    """Require the exact frozen training window and the single holdout season."""

    if tuple(sorted(set(historical_seasons))) != HISTORICAL_SEASONS:
        raise ValueError("holdout training requires exactly 2014-2024")
    if tuple(sorted(set(holdout_seasons))) != (HOLDOUT_SEASON,):
        raise ValueError("explicit holdout evaluation requires exactly 2025")


def frozen_artifact_identity(project_root: Path) -> dict[str, object]:
    """Verify and return preregistered v1 source and policy metadata."""

    actual = {
        relative: _sha256(project_root / relative) for relative in FROZEN_SOURCE_HASHES
    }
    mismatches = {
        path: {"expected": FROZEN_SOURCE_HASHES[path], "actual": digest}
        for path, digest in actual.items()
        if digest != FROZEN_SOURCE_HASHES[path]
    }
    protocol = project_root / "docs/2025-holdout-protocol.md"
    protocol_hash = _sha256(protocol)
    if protocol_hash != PROTOCOL_SHA256:
        mismatches[str(protocol.relative_to(project_root))] = {
            "expected": PROTOCOL_SHA256,
            "actual": protocol_hash,
        }
    if mismatches:
        raise ValueError(f"frozen holdout artifact mismatch: {mismatches}")
    return {
        "wp_model_version": LOCKED_WP_MODEL_VERSION,
        "wp_candidate_id": LOCKED_WP_CANDIDATE_ID,
        "wp_uses_recalibration": LOCKED_WP_USES_RECALIBRATION,
        "wp_ridge_penalty": 1.0,
        "wp_feature_count": 13,
        "action_transition_model_version": ACTION_TRANSITION_MODEL_VERSION,
        "decision_value_version": DECISION_VALUE_VERSION,
        "support_policy": {
            "minimum_observations": MIN_SUPPORT_OBSERVATIONS,
            "sparse_below_observations": SPARSE_SUPPORT_OBSERVATIONS,
            "maximum_field_goal_distance": MAX_FIELD_GOAL_DISTANCE,
        },
        "classification_policy": asdict(DECISION_THRESHOLD_POLICY_V1),
        "bootstrap_replicates": DECISION_BOOTSTRAP_REPLICATES,
        "bootstrap_seed": DECISION_BOOTSTRAP_SEED,
        "training_seasons": list(HISTORICAL_SEASONS),
        "holdout_season": HOLDOUT_SEASON,
        "protocol_sha256": protocol_hash,
        "source_sha256": actual,
    }


def holdout_run_policy() -> dict[str, object]:
    """Return the deterministic evaluation-only boundary recorded in reports."""

    return {
        "evaluation_only": True,
        "fit_seasons": list(HISTORICAL_SEASONS),
        "evaluation_season": HOLDOUT_SEASON,
        "recalibration_on_holdout": False,
        "model_selection_on_holdout": False,
        "threshold_or_cell_tuning_on_holdout": False,
    }


def evaluate_2025_holdout(
    historical_pbp: pl.DataFrame,
    holdout_pbp: pl.DataFrame,
    historical_decision_report: dict[str, object],
    *,
    project_root: Path,
    progress: Any = None,
) -> dict[str, object]:
    """Evaluate frozen v1 on 2025 without fitting or recalibrating on 2025."""

    historical = sorted(int(value) for value in historical_pbp["season"].unique())
    holdout = sorted(int(value) for value in holdout_pbp["season"].unique())
    validate_holdout_boundary(historical, holdout)
    identity = frozen_artifact_identity(project_root)
    _validate_historical_report(historical_decision_report)

    historical_states = build_state_value_rows(historical_pbp)
    holdout_states = build_state_value_rows(holdout_pbp)
    historical_candidates = extract_fourth_down_candidates(historical_pbp)
    holdout_candidates = extract_fourth_down_candidates(holdout_pbp)
    evaluation_candidates = holdout_candidates.filter(
        pl.col("disposition") == "eligible"
    )

    if progress:
        progress("fit frozen WP and action transitions on 2014-2024 only")
    wp_model = fit_locked_wp_model(historical_states)
    action_models = fit_action_baselines(historical_candidates)
    if wp_model.training_seasons != HISTORICAL_SEASONS:
        raise ValueError("WP model training seasons crossed the holdout boundary")
    if action_models.training_seasons != HISTORICAL_SEASONS:
        raise ValueError("action model training seasons crossed the holdout boundary")

    wp_holdout = _wp_holdout_report(historical_states, holdout_states, wp_model)
    wp_history = _historical_wp_reports(historical_states)

    if progress:
        progress(f"score {evaluation_candidates.height:,} eligible 2025 decisions")
    context = build_decision_bootstrap_context(
        action_models,
        bootstrap_replicates=DECISION_BOOTSTRAP_REPLICATES,
        random_seed=DECISION_BOOTSTRAP_SEED,
    )
    summaries = _score_decisions(
        evaluation_candidates,
        action_models,
        wp_model,
        context,
        DECISION_THRESHOLD_POLICY_V1,
        DECISION_BOOTSTRAP_REPLICATES,
        0.90,
    )
    decision_report = _aggregate_report(summaries)

    if progress:
        progress("quantify pre-clip transition mass and audit largest gaps")
    clipping = _clipping_report(evaluation_candidates, action_models, summaries)
    historical_clipping = _historical_clipping_reports(historical_pbp)
    largest = _largest_gap_audits(summaries, action_models, clipping["records"])
    overtime = _action_overtime_report(summaries)
    acceptance = _acceptance_report(
        wp_holdout,
        wp_history,
        decision_report,
        historical_decision_report,
        clipping,
        historical_clipping,
        largest,
    )
    return {
        "protocol": holdout_run_policy(),
        "frozen_artifact": identity,
        "sample_counts": {
            "historical_normalized_rows": historical_pbp.height,
            "holdout_normalized_rows": holdout_pbp.height,
            "holdout_games": holdout_pbp["game_id"].n_unique(),
            "holdout_state_rows": holdout_states.height,
            "holdout_fourth_down_candidates": holdout_candidates.height,
            "holdout_eligible_decisions": evaluation_candidates.height,
        },
        "fitted_metadata": {
            "wp": wp_model.to_dict(),
            "action_training_seasons": list(action_models.training_seasons),
            "action_training_transitions": action_models.training_rows.height,
            "action_training_games": action_models.training_rows["game_id"].n_unique(),
        },
        "wp_holdout": wp_holdout,
        "wp_historical_seasons": wp_history,
        "decision_holdout": decision_report,
        "decision_historical_seasons": historical_decision_report["folds"],
        "overtime_holdout": overtime,
        "clipping_holdout": {
            key: value for key, value in clipping.items() if key != "records"
        },
        "clipping_historical_seasons": historical_clipping,
        "largest_gap_audit": largest,
        "acceptance": acceptance,
    }


def _wp_holdout_report(
    training: pl.DataFrame, holdout: pl.DataFrame, model: Any
) -> dict[str, object]:
    selected = probability_report(holdout, model.predict_proba(holdout))
    constant = np.full(
        holdout.height, float(training["eventual_win_equivalent"].mean())
    )
    report: dict[str, object] = {
        "training_seasons": list(HISTORICAL_SEASONS),
        "evaluation_season": HOLDOUT_SEASON,
        "selected": selected,
        "constant_prevalence": probability_report(holdout, constant),
        "property_checks": property_grid_report(model),
    }
    for label, column in (
        ("nflverse_wp_reference", "nflverse_win_probability"),
        ("nflverse_vegas_wp_reference", "nflverse_vegas_win_probability"),
    ):
        available = holdout.filter(pl.col(column).is_not_null())
        report[label] = (
            probability_report(available, available[column].to_numpy())
            if available.height
            else None
        )
    return report


def _historical_wp_reports(states: pl.DataFrame) -> list[dict[str, object]]:
    reports = []
    for season in range(2020, 2025):
        training = states.filter(pl.col("season") < season)
        evaluation = states.filter(pl.col("season") == season)
        model = fit_locked_wp_model(training)
        reports.append(
            {
                "season": season,
                "training_seasons": list(model.training_seasons),
                **probability_report(evaluation, model.predict_proba(evaluation)),
            }
        )
    return reports


def _clipping_report(
    candidates: pl.DataFrame,
    action_models: ActionBaselineSet,
    summaries: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    summary_by_id = {(row["game_id"], row["play_id"]): row for row in summaries or []}
    cells = _cell_arrays(action_models)
    action_records: list[dict[str, Any]] = []
    decision_records: list[dict[str, Any]] = []
    for row in candidates.filter(pl.col("disposition") == "eligible").iter_rows(
        named=True
    ):
        state = canonical_state_from_candidate(row)
        situation = _situation(row)
        summary = summary_by_id.get((str(row["game_id"]), int(row["play_id"])))
        values = []
        for action in ACTIONS:
            support = action_models.support(action, state)
            if not support.in_support:
                continue
            arrays = cells[_cell_key(action, state)]
            raw_clock = state.game_seconds_remaining - arrays["elapsed"]
            raw_field = state.yards_to_goal + arrays["field_delta"]
            field = (~arrays["reset"]) & ((raw_field < 1) | (raw_field > 99))
            clock = raw_clock < 0
            combined = field | clock
            count = len(raw_clock)
            record = {
                "season": int(row["season"]),
                "game_id": str(row["game_id"]),
                "play_id": int(row["play_id"]),
                "action": action,
                "samples": count,
                "field_clipped_samples": int(field.sum()),
                "field_clipping_mass": float(field.mean()),
                "clock_clipped_samples": int(clock.sum()),
                "clock_clipping_mass": float(clock.mean()),
                "combined_clipped_samples": int(combined.sum()),
                "combined_clipping_mass": float(combined.mean()),
                "maximum_field_underflow_yards": float(
                    np.maximum(1 - raw_field[field & (raw_field < 1)], 0).max(initial=0)
                ),
                "maximum_field_overflow_yards": float(
                    np.maximum(raw_field[field & (raw_field > 99)] - 99, 0).max(
                        initial=0
                    )
                ),
                "maximum_clock_underflow_seconds": float(
                    np.maximum(-raw_clock[clock], 0).max(initial=0)
                ),
            }
            action_records.append(record)
            values.append(record)
        decision_records.append(
            {
                "season": int(row["season"]),
                "game_id": str(row["game_id"]),
                "play_id": int(row["play_id"]),
                "field_zone": situation["field_zone"],
                "time_regime": situation["late_game_regime"],
                "actual_action": str(row["actual_action"]),
                "classification": summary["classification"] if summary else None,
                "raw_action_value_gap": summary["raw_action_value_gap"]
                if summary
                else None,
                "supported_actions": len(values),
                "field_clipping_mass": max(
                    (value["field_clipping_mass"] for value in values), default=None
                ),
                "clock_clipping_mass": max(
                    (value["clock_clipping_mass"] for value in values), default=None
                ),
                "combined_clipping_mass": max(
                    (value["combined_clipping_mass"] for value in values),
                    default=None,
                ),
            }
        )
    _assign_gap_groups(decision_records)
    largest_ids = {
        (row["game_id"], row["play_id"])
        for row in sorted(
            (row for row in summaries or [] if row["raw_action_value_gap"] is not None),
            key=_largest_gap_sort_key,
        )[:20]
    }
    clear = [
        row
        for row in decision_records
        if row["classification"] == "clear_model_preference"
    ]
    largest = [
        row
        for row in decision_records
        if (row["game_id"], row["play_id"]) in largest_ids
    ]
    return {
        "definition": {
            "thresholds": ["any", ">10%", ">25%", ">50%"],
            "decision_mass": "maximum among supported actions",
            "field": "non-reset raw query-relative field position outside 1-99",
            "clock": "raw query-relative successor clock below zero",
        },
        "supported_action_decision_pairs": len(action_records),
        "decisions": len(decision_records),
        "decisions_without_supported_action": sum(
            row["supported_actions"] == 0 for row in decision_records
        ),
        "overall": _two_measure_summary(decision_records),
        "by_action": _group_clipping(action_records, "action"),
        "severity_by_action": _severity_by_action(action_records),
        "by_field_zone": _group_clipping(decision_records, "field_zone"),
        "by_time_regime": _group_clipping(decision_records, "time_regime"),
        "by_classification": _group_clipping(decision_records, "classification"),
        "by_actual_action": _group_clipping(decision_records, "actual_action"),
        "by_gap_percentile": _group_clipping(decision_records, "gap_percentile"),
        "clear_model_preference": _two_measure_summary(clear),
        "largest_20_gaps": _two_measure_summary(largest),
        "records": {
            "action": action_records,
            "decision": decision_records,
        },
    }


def _cell_arrays(model: ActionBaselineSet) -> dict[tuple[str, ...], dict[str, Any]]:
    output: dict[tuple[str, ...], dict[str, Any]] = {}
    rows = model.training_rows
    for action in ACTIONS:
        subset = rows.filter(pl.col("actual_action") == action)
        columns = (
            ["distance_bin", "field_bin"]
            if action == "go"
            else ["action_bin"]
            if action == "field_goal"
            else ["field_bin"]
        )
        for raw_key, cell in subset.partition_by(columns, as_dict=True).items():
            key = raw_key if isinstance(raw_key, tuple) else (raw_key,)
            output[(action, *map(str, key))] = {
                "elapsed": cell["elapsed_seconds"].to_numpy(),
                "field_delta": cell["decision_yards_to_goal_delta"].to_numpy(),
                "reset": cell["field_position_resets"].to_numpy(),
            }
    return output


def _cell_key(action: str, state: Any) -> tuple[str, ...]:
    cell = _support_cell(action, state)
    if action == "go":
        return (action, str(cell["distance_bin"]), str(cell["field_bin"]))
    if action == "field_goal":
        return (action, str(cell["field_goal_distance_bin"]))
    return (action, str(cell["field_bin"]))


def _assign_gap_groups(records: list[dict[str, Any]]) -> None:
    gaps = [
        float(row["raw_action_value_gap"])
        for row in records
        if row["raw_action_value_gap"] is not None
    ]
    if not gaps:
        for row in records:
            row["gap_percentile"] = "unavailable"
        return
    p50, p75, p90, p95 = np.quantile(gaps, (0.50, 0.75, 0.90, 0.95))
    for row in records:
        gap = row["raw_action_value_gap"]
        row["gap_percentile"] = (
            "unavailable"
            if gap is None
            else "0-50"
            if gap <= p50
            else "50-75"
            if gap <= p75
            else "75-90"
            if gap <= p90
            else "90-95"
            if gap <= p95
            else "top-5"
        )


def _two_measure_summary(records: list[dict[str, Any]]) -> dict[str, object]:
    return {
        "field": _mass_summary(records, "field_clipping_mass"),
        "clock": _mass_summary(records, "clock_clipping_mass"),
        "combined": _mass_summary(records, "combined_clipping_mass"),
    }


def _mass_summary(records: list[dict[str, Any]], field: str) -> dict[str, object]:
    values = [float(row[field]) for row in records if row.get(field) is not None]
    labels = ("any", "above_10_percent", "above_25_percent", "above_50_percent")
    return {
        "observations": len(values),
        "thresholds": {
            label: {
                "count": int(sum(value > threshold for value in values)),
                "rate": float(np.mean([value > threshold for value in values]))
                if values
                else 0.0,
            }
            for label, threshold in zip(labels, CLIP_THRESHOLDS, strict=True)
        },
        "mass_distribution": _distribution(values),
    }


def _group_clipping(records: list[dict[str, Any]], field: str) -> dict[str, object]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        groups.setdefault(str(row.get(field)), []).append(row)
    return {key: _two_measure_summary(group) for key, group in sorted(groups.items())}


def _severity_by_action(records: list[dict[str, Any]]) -> dict[str, object]:
    """Summarize how far raw transitions crossed each physical boundary."""

    report: dict[str, object] = {}
    for action in ACTIONS:
        selected = [row for row in records if row["action"] == action]
        report[action] = {
            "maximum_field_underflow_yards": max(
                (row["maximum_field_underflow_yards"] for row in selected),
                default=0.0,
            ),
            "maximum_field_overflow_yards": max(
                (row["maximum_field_overflow_yards"] for row in selected),
                default=0.0,
            ),
            "maximum_clock_underflow_seconds": max(
                (row["maximum_clock_underflow_seconds"] for row in selected),
                default=0.0,
            ),
            "field_underflow_distribution_among_affected_pairs": _distribution(
                [
                    float(row["maximum_field_underflow_yards"])
                    for row in selected
                    if row["maximum_field_underflow_yards"] > 0
                ]
            ),
            "field_overflow_distribution_among_affected_pairs": _distribution(
                [
                    float(row["maximum_field_overflow_yards"])
                    for row in selected
                    if row["maximum_field_overflow_yards"] > 0
                ]
            ),
            "clock_underflow_distribution_among_affected_pairs": _distribution(
                [
                    float(row["maximum_clock_underflow_seconds"])
                    for row in selected
                    if row["maximum_clock_underflow_seconds"] > 0
                ]
            ),
        }
    return report


def _historical_clipping_reports(pbp: pl.DataFrame) -> list[dict[str, object]]:
    candidates = extract_fourth_down_candidates(pbp)
    reports = []
    for season in range(2020, 2025):
        model = fit_action_baselines(candidates.filter(pl.col("season") < season))
        evaluation = candidates.filter(pl.col("season") == season)
        clipping = _clipping_report(evaluation, model)
        reports.append(
            {
                "season": season,
                "decisions": clipping["decisions"],
                "overall": clipping["overall"],
                "by_action": clipping["by_action"],
            }
        )
    return reports


def _largest_gap_audits(
    summaries: list[dict[str, Any]],
    action_models: ActionBaselineSet,
    clipping_records: dict[str, list[dict[str, Any]]],
) -> list[dict[str, object]]:
    action_clips = {
        (row["game_id"], row["play_id"], row["action"]): row
        for row in clipping_records["action"]
    }
    selected = sorted(
        (row for row in summaries if row["raw_action_value_gap"] is not None),
        key=_largest_gap_sort_key,
    )[:20]
    output = []
    for row in selected:
        transport = _transition_audit(row["state"], action_models)
        clips = {
            action: action_clips.get((row["game_id"], row["play_id"], action))
            for action in ACTIONS
        }
        structural = any(
            count
            for action in transport.values()
            for count in action.get("structural_flags", {}).values()
        )
        heavy = any(
            clip
            and (
                clip["field_clipping_mass"] > 0.25 or clip["clock_clipping_mass"] > 0.25
            )
            for clip in clips.values()
        )
        overtime = row["maximum_overtime_boundary_mass"] > 0
        label = (
            "potential_correctness_bug"
            if structural
            else "model_form_warning"
            if heavy or overtime
            else "structurally_clean"
        )
        public = _public_summary({**row, "transition_audit": transport})
        public["clipping_audit"] = clips
        public["review_label"] = label
        public["review_basis"] = (
            "one or more structural transport invariants failed"
            if structural
            else "heavy pre-clip mass or overtime scope in a supported action"
            if heavy or overtime
            else "all recorded reconstruction and transport checks pass"
        )
        output.append(public)
    return output


def _action_overtime_report(rows: list[dict[str, Any]]) -> dict[str, object]:
    by_action: dict[str, object] = {}
    for action in ACTIONS:
        masses = []
        for row in rows:
            value = next(item for item in row["audit"].actions if item.action == action)
            if value.expected_win_probability is not None:
                masses.append(float(value.overtime_boundary_mass))
        affected = [mass for mass in masses if mass > 0]
        by_action[action] = {
            "supported_decisions": len(masses),
            "affected_decisions": len(affected),
            "affected_rate": len(affected) / len(masses) if masses else 0.0,
            "mass_distribution_among_affected": _distribution(affected),
        }
    maximum = [float(row["maximum_overtime_boundary_mass"]) for row in rows]
    affected_maximum = [mass for mass in maximum if mass > 0]
    return {
        "decisions": len(rows),
        "affected_decisions": len(affected_maximum),
        "affected_rate": len(affected_maximum) / len(rows) if rows else 0.0,
        "maximum_mass_distribution_among_affected": _distribution(affected_maximum),
        "by_action": by_action,
    }


def _acceptance_report(
    wp: dict[str, object],
    wp_history: list[dict[str, object]],
    decision: dict[str, object],
    decision_history: dict[str, object],
    clipping: dict[str, object],
    clipping_history: list[dict[str, object]],
    largest: list[dict[str, object]],
) -> dict[str, object]:
    warnings: list[str] = []
    failures: list[str] = []
    selected = wp["selected"]
    if selected["log_loss"] > 0.5532:
        warnings.append("WP overall log loss exceeds preregistered warning level")
    if selected["brier_score"] > 0.1875:
        warnings.append("WP overall Brier exceeds preregistered warning level")
    if selected["expected_calibration_error"] > 0.0518:
        warnings.append("WP overall ECE exceeds preregistered warning level")
    constant = wp["constant_prevalence"]
    if (
        selected["log_loss"] > 0.6232
        or selected["brier_score"] > 0.2225
        or selected["expected_calibration_error"] > 0.08
        or (
            selected["log_loss"] > constant["log_loss"]
            and selected["brier_score"] > constant["brier_score"]
        )
    ):
        failures.append("WP catastrophic criterion fired")
    for band in selected["calibration"]:
        gap = band["calibration_gap"]
        if not band["sparse"] and gap is not None and gap > 0.08:
            warnings.append(f"WP calibration warning in {band['band']} band")
        if (
            band["band"] in {"0-10%", "90-100%"}
            and not band["sparse"]
            and gap is not None
            and gap > 0.06
        ):
            warnings.append(f"WP extreme-band warning in {band['band']} band")
        if not band["sparse"] and gap is not None and gap >= 0.15:
            failures.append(f"WP catastrophic calibration gap in {band['band']}")
    if (
        any(values["violations"] for values in wp["property_checks"]["checks"].values())
        or wp["property_checks"]["late_game_dominance"]["violations"]
    ):
        failures.append("WP property-grid sanity check failed")
    _append_regime_warnings(warnings, selected, wp_history)

    factual = decision["factual_action_value_validation"]["overall"]
    if factual["log_loss"] > 0.5497:
        warnings.append("factual EWP log loss exceeds warning level")
    if factual["brier_score"] > 0.1913:
        warnings.append("factual EWP Brier exceeds warning level")
    if factual["expected_calibration_error"] > 0.0567:
        warnings.append("factual EWP ECE exceeds warning level")
    if factual["log_loss"] > 0.6197 and factual["brier_score"] > 0.2213:
        failures.append("factual EWP catastrophic criterion fired")
    _append_factual_action_warnings(warnings, decision, decision_history)
    _append_drift_warnings(warnings, decision, decision_history)
    _append_gap_warnings(warnings, decision, decision_history)
    _append_overtime_warnings(warnings, decision, decision_history)
    _append_clipping_findings(warnings, failures, clipping, clipping_history)

    bugs = [
        row for row in largest if row["review_label"] == "potential_correctness_bug"
    ]
    model_warnings = [
        row for row in largest if row["review_label"] == "model_form_warning"
    ]
    if bugs:
        failures.append("largest-gap audit contains a potential correctness bug")
    if model_warnings:
        warnings.append("largest-gap audit contains model-form warnings")
    warnings = sorted(set(warnings))
    failures = sorted(set(failures))
    status = (
        "FAIL — NEW VERSION REQUIRED"
        if failures
        else "PASS WITH LIMITATIONS"
        if warnings
        else "PASS"
    )
    return {
        "status": status,
        "material_warnings": warnings,
        "failure_findings": failures,
        "historical_wp_ranges": _metric_ranges(wp_history),
        "rule": "preregistered in docs/2025-holdout-protocol.md",
    }


def _append_regime_warnings(
    warnings: list[str], selected: dict[str, Any], history: list[dict[str, Any]]
) -> None:
    for category in ("clock_regimes", "score_regimes"):
        for name, values in selected[category].items():
            if values["observations"] < 500:
                continue
            prior = [row[category][name] for row in history if name in row[category]]
            if values["log_loss"] > max(row["log_loss"] for row in prior) + 0.05:
                warnings.append(f"WP regime log-loss warning: {category}/{name}")
            if values["expected_calibration_error"] > (
                max(row["expected_calibration_error"] for row in prior) + 0.03
            ):
                warnings.append(f"WP regime ECE warning: {category}/{name}")


def _append_factual_action_warnings(
    warnings: list[str], current: dict[str, Any], history: dict[str, Any]
) -> None:
    folds = history["folds"]
    for action, values in current["factual_action_value_validation"][
        "by_actual_action"
    ].items():
        if values is None or values["observations"] < 100:
            continue
        prior = [
            fold["factual_action_value_validation"]["by_actual_action"][action]
            for fold in folds
        ]
        for metric, margin in (
            ("log_loss", 0.05),
            ("brier_score", 0.03),
            ("expected_calibration_error", 0.03),
        ):
            if values[metric] > max(row[metric] for row in prior) + margin:
                warnings.append(f"factual {action} EWP {metric} warning")
    transitions = current["factual_transition_validation"]
    for action in ("go", "field_goal"):
        values = transitions[action]
        if values is None or values["observations"] < 100:
            continue
        prior = [fold["factual_transition_validation"][action] for fold in folds]
        if values["log_loss"] > max(row["log_loss"] for row in prior) + 0.05:
            warnings.append(f"{action} transition log-loss warning")
        if values["brier_score"] > max(row["brier_score"] for row in prior) + 0.03:
            warnings.append(f"{action} transition Brier warning")
    punt = transitions["punt"]
    if punt and punt["observations"] >= 100:
        if punt["mean_absolute_error_yards_to_goal"] > 10.06:
            warnings.append("punt destination MAE warning")
        if punt["root_mean_squared_error_yards_to_goal"] > 14.87:
            warnings.append("punt destination RMSE warning")


def _append_drift_warnings(
    warnings: list[str], current: dict[str, Any], history: dict[str, Any]
) -> None:
    folds = history["folds"]
    for count, values in current["supported_action_counts"].items():
        prior = [fold["supported_action_counts"][count]["rate"] for fold in folds]
        if _outside_range(values["rate"], prior, 0.03):
            warnings.append(f"supported-action-count drift warning: {count}")
    sparse = current["sparse_support_frequency"]["rate"]
    prior_sparse = [fold["sparse_support_frequency"]["rate"] for fold in folds]
    if _outside_range(sparse, prior_sparse, 0.03):
        warnings.append("sparse-support drift warning")
    for label, values in current["classification"].items():
        prior = [
            fold["classification"].get(label, {"rate": 0.0})["rate"] for fold in folds
        ]
        if _outside_range(values["rate"], prior, 0.03):
            warnings.append(f"classification drift warning: {label}")
    if current["supported_action_counts"]["0"]["decisions"]:
        warnings.append("one or more decisions have zero supported actions")
    for action, values in current["actual_action_support"].items():
        prior = [
            fold["actual_action_support"][action]["unsupported_rate"] for fold in folds
        ]
        if _outside_range(values["unsupported_rate"], prior, 0.02):
            warnings.append(f"unsupported actual-action drift warning: {action}")


def _append_gap_warnings(
    warnings: list[str], current: dict[str, Any], history: dict[str, Any]
) -> None:
    gaps = current["action_gap_distribution"]["overall"]
    folds = [fold["action_gap_distribution"]["overall"] for fold in history["folds"]]
    for metric in ("p75", "p90", "p95"):
        values = [float(fold[metric]) for fold in folds]
        value = float(gaps[metric])
        endpoint = min(values) if value < min(values) else max(values)
        if value < min(values) or value > max(values):
            if (
                abs(value - endpoint) > 0.005
                and abs(value - endpoint) > 0.25 * endpoint
            ):
                warnings.append(f"action-gap {metric} drift warning")
    if gaps["maximum"] > 0.1720:
        warnings.append("action-gap maximum warning")


def _append_overtime_warnings(
    warnings: list[str], current: dict[str, Any], history: dict[str, Any]
) -> None:
    overtime = current["overtime_boundary_frequency"]
    prior = [fold["overtime_boundary_frequency"] for fold in history["folds"]]
    if _outside_range(overtime["rate"], [row["rate"] for row in prior], 0.03):
        warnings.append("OT-boundary frequency drift warning")
    mass = overtime["mass_distribution_among_affected"]
    for metric in ("median", "p75", "p90", "p95"):
        if mass[metric] is None:
            continue
        maximum = max(
            float(row["mass_distribution_among_affected"][metric]) for row in prior
        )
        if mass[metric] > maximum + 0.10:
            warnings.append(f"OT-boundary {metric} mass warning")


def _append_clipping_findings(
    warnings: list[str],
    failures: list[str],
    clipping: dict[str, Any],
    history: list[dict[str, Any]],
) -> None:
    overall = clipping["overall"]
    clear = clipping["clear_model_preference"]
    largest = clipping["largest_20_gaps"]
    for measure in ("field", "clock"):
        if overall[measure]["thresholds"]["above_25_percent"]["rate"] >= 0.05:
            warnings.append(f"material {measure} clipping affects >=5% of decisions")
        if clear[measure]["thresholds"]["above_25_percent"]["rate"] >= 0.10:
            warnings.append(f"material {measure} clipping affects >=10% of clear cases")
        if overall[measure]["thresholds"]["above_50_percent"]["rate"] >= 0.01:
            warnings.append(f"heavy {measure} clipping affects >=1% of decisions")
        if largest[measure]["thresholds"]["above_25_percent"]["count"] >= 5:
            warnings.append(f"material {measure} clipping affects >=5 largest gaps")
        if overall[measure]["thresholds"]["above_50_percent"]["rate"] >= 0.20:
            failures.append(f"severe {measure} clipping affects >=20% of decisions")
        if clear[measure]["thresholds"]["above_50_percent"]["rate"] >= 0.33:
            failures.append(f"severe {measure} clipping affects >=33% of clear cases")
        if largest[measure]["thresholds"]["above_50_percent"]["count"] >= 10:
            failures.append(f"severe {measure} clipping affects >=10 largest gaps")
        for threshold in (
            "any",
            "above_10_percent",
            "above_25_percent",
            "above_50_percent",
        ):
            rate = overall[measure]["thresholds"][threshold]["rate"]
            prior_max = max(
                row["overall"][measure]["thresholds"][threshold]["rate"]
                for row in history
            )
            if rate > prior_max + 0.05 and rate > prior_max * 1.5:
                warnings.append(f"historical clipping drift: {measure}/{threshold}")


def _validate_historical_report(report: dict[str, object]) -> None:
    protocol = report.get("protocol", {})
    if protocol.get("decision_value_version") != DECISION_VALUE_VERSION:
        raise ValueError("historical report decision version mismatch")
    if protocol.get("bootstrap_replicates") != DECISION_BOOTSTRAP_REPLICATES:
        raise ValueError("historical report bootstrap count mismatch")
    if protocol.get("bootstrap_seed") != DECISION_BOOTSTRAP_SEED:
        raise ValueError("historical report bootstrap seed mismatch")
    seasons = [fold["evaluation_season"] for fold in report.get("folds", [])]
    if seasons != list(range(2020, 2025)):
        raise ValueError("historical report requires evaluation seasons 2020-2024")


def _metric_ranges(rows: list[dict[str, Any]]) -> dict[str, list[float]]:
    return {
        metric: [min(row[metric] for row in rows), max(row[metric] for row in rows)]
        for metric in ("log_loss", "brier_score", "expected_calibration_error")
    }


def _outside_range(value: float, prior: list[float], margin: float) -> bool:
    return value < min(prior) - margin or value > max(prior) + margin


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "observations": 0,
            "median": None,
            "p75": None,
            "p90": None,
            "p95": None,
            "maximum": None,
        }
    array = np.asarray(values)
    return {
        "observations": len(values),
        "median": float(np.quantile(array, 0.50)),
        "p75": float(np.quantile(array, 0.75)),
        "p90": float(np.quantile(array, 0.90)),
        "p95": float(np.quantile(array, 0.95)),
        "maximum": float(array.max()),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = [
    "FROZEN_SOURCE_HASHES",
    "HISTORICAL_SEASONS",
    "HOLDOUT_SEASON",
    "PROTOCOL_SHA256",
    "evaluate_2025_holdout",
    "frozen_artifact_identity",
    "holdout_run_policy",
    "validate_holdout_boundary",
]
