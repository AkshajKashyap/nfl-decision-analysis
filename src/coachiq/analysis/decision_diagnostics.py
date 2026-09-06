"""Chronological diagnostics for the CoachIQ decision-value layer."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any, Callable

import numpy as np
import polars as pl

from coachiq.analysis.decision_value import (
    ACTION_TRANSITION_MODEL_VERSION,
    ACTIONS,
    DECISION_BOOTSTRAP_REPLICATES,
    DECISION_BOOTSTRAP_SEED,
    DECISION_THRESHOLD_POLICY_V1,
    DECISION_VALUE_VERSION,
    DecisionThresholdPolicy,
    DecisionValueAudit,
    audit_decision_value,
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
from coachiq.models.evaluation import probability_metrics
from coachiq.models.state import CanonicalState, build_state_value_rows
from coachiq.models.wp_selection import LOCKED_WP_MODEL_VERSION, fit_locked_wp_model

DECISION_EVALUATION_SEASONS = (2020, 2021, 2022, 2023, 2024)


def evaluate_decision_diagnostics(
    pbp: pl.DataFrame,
    *,
    bootstrap_replicates: int = DECISION_BOOTSTRAP_REPLICATES,
    confidence_level: float = 0.90,
    threshold_policy: DecisionThresholdPolicy = DECISION_THRESHOLD_POLICY_V1,
    progress: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Run pre-2025 rolling decision audits and aggregate no coach results."""

    _validate_seasons(pbp)
    all_candidates = extract_fourth_down_candidates(pbp)
    all_states = build_state_value_rows(pbp)
    fold_reports: list[dict[str, object]] = []
    summaries: list[dict[str, Any]] = []
    large_gap_candidates: list[dict[str, Any]] = []
    final_models: tuple[ActionBaselineSet, Any] | None = None

    for season in DECISION_EVALUATION_SEASONS:
        if progress:
            progress(f"fit through {season - 1}; evaluate {season}")
        training_candidates = all_candidates.filter(pl.col("season") < season)
        evaluation = all_candidates.filter(
            (pl.col("season") == season) & (pl.col("disposition") == "eligible")
        )
        action_models = fit_action_baselines(training_candidates)
        state_model = fit_locked_wp_model(all_states.filter(pl.col("season") < season))
        context = build_decision_bootstrap_context(
            action_models,
            bootstrap_replicates=bootstrap_replicates,
            random_seed=DECISION_BOOTSTRAP_SEED,
        )
        fold_summaries = _score_decisions(
            evaluation,
            action_models,
            state_model,
            context,
            threshold_policy,
            bootstrap_replicates,
            confidence_level,
        )
        fold_reports.append(_fold_report(season, fold_summaries))
        if progress:
            progress(f"completed {season}: {len(fold_summaries):,} decisions")
        summaries.extend(fold_summaries)
        fold_largest = sorted(
            (row for row in fold_summaries if row["raw_action_value_gap"] is not None),
            key=_largest_gap_sort_key,
        )[:20]
        for item in fold_largest:
            item["transition_audit"] = _transition_audit(item["state"], action_models)
        large_gap_candidates.extend(fold_largest)
        if season == 2024:
            final_models = (action_models, state_model)

    largest = sorted(large_gap_candidates, key=_largest_gap_sort_key)[:20]
    worked = _select_worked_audits(summaries)
    if final_models is None:
        raise RuntimeError("2024 diagnostic models were not constructed")
    stress = _stress_tests(
        *final_models,
        threshold_policy=threshold_policy,
        bootstrap_replicates=bootstrap_replicates,
        confidence_level=confidence_level,
    )
    return {
        "protocol": {
            "training_start_season": 2014,
            "evaluation_seasons": list(DECISION_EVALUATION_SEASONS),
            "latest_allowed_season": 2024,
            "protected_season": 2025,
            "bootstrap_replicates": bootstrap_replicates,
            "bootstrap_seed": DECISION_BOOTSTRAP_SEED,
            "confidence_level": confidence_level,
            "bootstrap_unit": "training game",
            "bootstrap_design": (
                "one shared multinomial resample of the training-game universe; "
                "each action retains its own empirical transition rows and denominator"
            ),
            "wp_model_version": LOCKED_WP_MODEL_VERSION,
            "action_transition_model_version": ACTION_TRANSITION_MODEL_VERSION,
            "decision_value_version": DECISION_VALUE_VERSION,
            "support_thresholds": {
                "minimum_observations": MIN_SUPPORT_OBSERVATIONS,
                "sparse_below_observations": SPARSE_SUPPORT_OBSERVATIONS,
                "maximum_field_goal_distance": MAX_FIELD_GOAL_DISTANCE,
            },
            "threshold_policy": asdict(threshold_policy),
        },
        "folds": fold_reports,
        "pooled": _aggregate_report(summaries),
        "threshold_sensitivity": _threshold_sensitivity(summaries, threshold_policy),
        "monte_carlo_stability": _monte_carlo_stability(
            summaries, threshold_policy, bootstrap_replicates
        ),
        "temporal_stability": [_temporal_row(report) for report in fold_reports],
        "worked_audits": [_public_summary(row) for row in worked],
        "largest_gap_audit": [_public_summary(row) for row in largest],
        "stress_tests": stress,
        "largest_gap_structural_flags": _large_gap_flags(largest),
    }


def _score_decisions(
    candidates: pl.DataFrame,
    action_models: ActionBaselineSet,
    state_model: Any,
    context: Any,
    policy: DecisionThresholdPolicy,
    replicates: int,
    confidence_level: float,
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for row in candidates.iter_rows(named=True):
        state = canonical_state_from_candidate(row)
        audit = audit_decision_value(
            state,
            str(row["actual_action"]),
            action_models,
            state_model,
            threshold_policy=policy,
            bootstrap_replicates=replicates,
            confidence_level=confidence_level,
            bootstrap_context=context,
        )
        summaries.append(_decision_summary(row, state, audit, action_models))
    return summaries


def _decision_summary(
    row: dict[str, Any],
    state: CanonicalState,
    audit: DecisionValueAudit,
    action_models: ActionBaselineSet,
) -> dict[str, Any]:
    action_values = {value.action: value for value in audit.actions}
    available = [value for value in audit.actions if value.available]
    supported = [
        value for value in audit.actions if value.expected_win_probability is not None
    ]
    support_profile = (
        "insufficient"
        if len(supported) < 2 or audit.actual_action_ewp is None
        else "sparse"
        if any(value.sparse for value in supported)
        else "incomplete"
        if any(value.expected_win_probability is None for value in available)
        else "complete_nonsparse"
    )
    return {
        "season": int(row["season"]),
        "game_id": str(row["game_id"]),
        "play_id": int(row["play_id"]),
        "situation": _situation(row),
        "state": state,
        "actual_action": audit.actual_action,
        "target": _eventual_value(row),
        "audit": audit,
        "classification": audit.classification,
        "support_profile": support_profile,
        "supported_action_count": audit.supported_action_count,
        "raw_action_value_gap": audit.raw_action_value_gap,
        "minimum_preference_gap": audit.model_preferred_minimum_gap,
        "minimum_superiority": audit.model_preferred_minimum_superiority,
        "actual_action_ewp": audit.actual_action_ewp,
        "actual_support_status": action_values[audit.actual_action].support_status,
        "action_support": {
            action: action_values[action].support_status for action in ACTIONS
        },
        "maximum_overtime_boundary_mass": audit.maximum_overtime_boundary_mass,
        "play_audit": _play_audit(row),
        "factual_transition_validation": _factual_transition_prediction(
            row, state, action_models
        ),
    }


def _fold_report(season: int, rows: list[dict[str, Any]]) -> dict[str, object]:
    report = _aggregate_report(rows)
    return {
        "training_seasons": list(range(2014, season)),
        "evaluation_season": season,
        **report,
    }


def _aggregate_report(rows: list[dict[str, Any]]) -> dict[str, object]:
    return {
        "decisions": len(rows),
        "classification": _categorical_report(rows, "classification"),
        "support_profiles": _categorical_report(rows, "support_profile"),
        "supported_action_counts": _supported_count_report(rows),
        "support_by_field_zone": _support_breakdown(rows, "field_zone"),
        "support_by_yards_to_go": _support_breakdown(rows, "yards_to_go_bucket"),
        "support_by_quarter": _support_breakdown(rows, "quarter_bucket"),
        "support_by_late_game_regime": _support_breakdown(rows, "late_game_regime"),
        "sparse_support_frequency": _sparse_support_frequency(rows),
        "overtime_boundary_frequency": _overtime_boundary_frequency(rows),
        "actual_action_support": _actual_action_support(rows),
        "factual_action_value_validation": _factual_action_value_validation(rows),
        "factual_transition_validation": _factual_transition_validation(rows),
        "action_gap_distribution": _gap_report(rows),
    }


def _categorical_report(
    rows: list[dict[str, Any]], field: str
) -> dict[str, dict[str, float | int]]:
    counts = Counter(str(row[field]) for row in rows)
    total = len(rows)
    return {
        name: {"decisions": count, "rate": count / total if total else 0.0}
        for name, count in sorted(counts.items())
    }


def _supported_count_report(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    counts = Counter(int(row["supported_action_count"]) for row in rows)
    total = len(rows)
    return {
        str(count): {
            "decisions": counts.get(count, 0),
            "rate": counts.get(count, 0) / total if total else 0.0,
        }
        for count in (0, 1, 2, 3)
    }


def _support_breakdown(
    rows: list[dict[str, Any]], situation_field: str
) -> dict[str, object]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row["situation"][situation_field])
        groups.setdefault(key, []).append(row)
    return {
        key: {
            "decisions": len(group),
            "supported_action_counts": _supported_count_report(group),
            "classification": _categorical_report(group, "classification"),
        }
        for key, group in sorted(groups.items())
    }


def _actual_action_support(rows: list[dict[str, Any]]) -> dict[str, object]:
    report: dict[str, object] = {}
    for action in ACTIONS:
        selected = [row for row in rows if row["actual_action"] == action]
        counts = Counter(str(row["actual_support_status"]) for row in selected)
        unsupported = sum(
            count
            for status, count in counts.items()
            if status in {"unsupported", "unavailable"}
        )
        report[action] = {
            "decisions": len(selected),
            "unsupported": unsupported,
            "unsupported_rate": unsupported / len(selected) if selected else 0.0,
            "support_status": dict(sorted(counts.items())),
        }
    return report


def _sparse_support_frequency(rows: list[dict[str, Any]]) -> dict[str, object]:
    any_sparse = [
        row for row in rows if "sparse" in set(row["action_support"].values())
    ]
    return {
        "decisions": len(any_sparse),
        "rate": len(any_sparse) / len(rows) if rows else 0.0,
        "by_action": {
            action: {
                "decisions": sum(
                    row["action_support"][action] == "sparse" for row in rows
                ),
                "rate": (
                    sum(row["action_support"][action] == "sparse" for row in rows)
                    / len(rows)
                    if rows
                    else 0.0
                ),
            }
            for action in ACTIONS
        },
    }


def _overtime_boundary_frequency(rows: list[dict[str, Any]]) -> dict[str, object]:
    affected = [row for row in rows if row["maximum_overtime_boundary_mass"] > 0]
    masses = [float(row["maximum_overtime_boundary_mass"]) for row in affected]
    return {
        "decisions": len(affected),
        "rate": len(affected) / len(rows) if rows else 0.0,
        "mass_distribution_among_affected": _distribution(masses),
    }


def _factual_action_value_validation(rows: list[dict[str, Any]]) -> dict[str, object]:
    return {
        "interpretation": (
            "calibration of the modeled value for the action actually observed; "
            "necessary but not sufficient for unchosen-action validity"
        ),
        "overall": _probability_validation(rows),
        "by_actual_action": {
            action: _probability_validation(
                [row for row in rows if row["actual_action"] == action]
            )
            for action in ACTIONS
        },
    }


def _probability_validation(rows: list[dict[str, Any]]) -> dict[str, object] | None:
    selected = [
        row
        for row in rows
        if row["actual_action_ewp"] is not None and row["target"] is not None
    ]
    if not selected:
        return None
    targets = [float(row["target"]) for row in selected]
    probabilities = [float(row["actual_action_ewp"]) for row in selected]
    metrics = probability_metrics(targets, probabilities)
    calibration = _calibration_rows(targets, probabilities)
    ece = sum(
        int(row["observations"]) * float(row["calibration_gap"] or 0.0)
        for row in calibration
    ) / len(selected)
    return {
        **asdict(metrics),
        "expected_calibration_error": ece,
        "calibration": calibration,
    }


def _calibration_rows(
    targets: list[float], probabilities: list[float]
) -> list[dict[str, object]]:
    observed = np.asarray(targets)
    predicted = np.asarray(probabilities)
    indexes = np.minimum((predicted * 10).astype(int), 9)
    rows: list[dict[str, object]] = []
    for index in range(10):
        selected = indexes == index
        count = int(selected.sum())
        mean_prediction = float(predicted[selected].mean()) if count else None
        observed_rate = float(observed[selected].mean()) if count else None
        rows.append(
            {
                "band": f"{index * 10}-{(index + 1) * 10}%",
                "observations": count,
                "mean_prediction": mean_prediction,
                "observed_rate": observed_rate,
                "calibration_gap": (
                    abs(mean_prediction - observed_rate) if count else None
                ),
                "sparse": count < 100,
            }
        )
    return rows


def _factual_transition_prediction(
    row: dict[str, Any],
    state: CanonicalState,
    action_models: ActionBaselineSet,
) -> dict[str, Any] | None:
    action = str(row["actual_action"])
    if action in {"go", "field_goal"}:
        probability, support = action_models.empirical_binary_probability(action, state)
        valid = (
            {
                "converted",
                "converted_by_penalty",
                "touchdown",
                "failed",
                "interception",
                "fumble_lost",
            }
            if action == "go"
            else {"field_goal_made", "field_goal_missed", "field_goal_blocked"}
        )
        if probability is None or str(row["factual_outcome"]) not in valid:
            return None
        success = (
            str(row["factual_outcome"])
            in {"converted", "converted_by_penalty", "touchdown"}
            if action == "go"
            else str(row["factual_outcome"]) == "field_goal_made"
        )
        return {
            "kind": "binary",
            "action": action,
            "prediction": probability,
            "target": float(success),
            "support_observations": support.observation_count,
        }
    if row["next_state_status"] != "reconstructed" or row["next_yards_to_goal"] is None:
        return None
    prediction, support = action_models.punt_expected_opponent_yards_to_goal(state)
    if prediction is None:
        return None
    return {
        "kind": "continuous",
        "action": action,
        "prediction": prediction,
        "target": float(row["next_yards_to_goal"]),
        "support_observations": support.observation_count,
    }


def _factual_transition_validation(rows: list[dict[str, Any]]) -> dict[str, object]:
    report: dict[str, object] = {}
    for action in ACTIONS:
        values = [
            row["factual_transition_validation"]
            for row in rows
            if row["actual_action"] == action
            and row["factual_transition_validation"] is not None
        ]
        if action in {"go", "field_goal"} and values:
            metrics = probability_metrics(
                [float(value["target"]) for value in values],
                [float(value["prediction"]) for value in values],
            )
            report[action] = asdict(metrics)
        elif values:
            errors = np.asarray(
                [
                    float(value["prediction"]) - float(value["target"])
                    for value in values
                ]
            )
            report[action] = {
                "observations": len(values),
                "mean_absolute_error_yards_to_goal": float(np.abs(errors).mean()),
                "root_mean_squared_error_yards_to_goal": float(
                    np.sqrt(np.mean(errors**2))
                ),
            }
        else:
            report[action] = None
    return report


def _gap_report(rows: list[dict[str, Any]]) -> dict[str, object]:
    selected = [row for row in rows if row["raw_action_value_gap"] is not None]
    return {
        "overall": _distribution(
            [float(row["raw_action_value_gap"]) for row in selected]
        ),
        "by_classification": {
            name: _distribution(
                [
                    float(row["raw_action_value_gap"])
                    for row in selected
                    if row["classification"] == name
                ]
            )
            for name in sorted({str(row["classification"]) for row in rows})
        },
        "by_support_profile": {
            name: _distribution(
                [
                    float(row["raw_action_value_gap"])
                    for row in selected
                    if row["support_profile"] == name
                ]
            )
            for name in sorted({str(row["support_profile"]) for row in rows})
        },
        "by_actual_action": {
            action: _distribution(
                [
                    float(row["raw_action_value_gap"])
                    for row in selected
                    if row["actual_action"] == action
                ]
            )
            for action in ACTIONS
        },
    }


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


def _threshold_sensitivity(
    rows: list[dict[str, Any]], selected_policy: DecisionThresholdPolicy
) -> list[dict[str, object]]:
    selected_labels = [str(row["classification"]) for row in rows]
    reports: list[dict[str, object]] = []
    for gap in (0.005, 0.01, 0.02):
        for superiority in (0.90, 0.95, 0.975):
            labels = [_sensitivity_label(row, gap, superiority) for row in rows]
            counts = Counter(labels)
            changed = sum(a != b for a, b in zip(labels, selected_labels, strict=True))
            reports.append(
                {
                    "minimum_gap": gap,
                    "superiority_probability": superiority,
                    "is_selected_policy": (
                        gap == selected_policy.minimum_gap
                        and superiority == selected_policy.superiority_probability
                    ),
                    "classification": {
                        name: {
                            "decisions": counts.get(name, 0),
                            "rate": counts.get(name, 0) / len(rows) if rows else 0.0,
                        }
                        for name in (
                            "clear_model_preference",
                            "close_call",
                            "limited_support",
                            "insufficient_support",
                        )
                    },
                    "reclassification_rate_vs_selected": (
                        changed / len(rows) if rows else 0.0
                    ),
                }
            )
    return reports


def _sensitivity_label(row: dict[str, Any], gap: float, superiority: float) -> str:
    if row["classification"] not in {"clear_model_preference", "close_call"}:
        return str(row["classification"])
    return (
        "clear_model_preference"
        if float(row["minimum_preference_gap"]) >= gap
        and float(row["minimum_superiority"]) >= superiority
        else "close_call"
    )


def _monte_carlo_stability(
    rows: list[dict[str, Any]],
    policy: DecisionThresholdPolicy,
    replicates: int,
) -> dict[str, object]:
    """Quantify finite-draw resolution around the selected superiority cutoff."""

    one_draw = 1.0 / replicates
    lower = max(0.5, policy.superiority_probability - one_draw)
    upper = min(1.0, policy.superiority_probability + one_draw)
    selected = [
        _sensitivity_label(row, policy.minimum_gap, policy.superiority_probability)
        for row in rows
    ]
    lower_labels = [_sensitivity_label(row, policy.minimum_gap, lower) for row in rows]
    upper_labels = [_sensitivity_label(row, policy.minimum_gap, upper) for row in rows]

    def changed(labels: list[str]) -> dict[str, float | int]:
        count = sum(a != b for a, b in zip(labels, selected, strict=True))
        return {
            "decisions": count,
            "rate": count / len(rows) if rows else 0.0,
        }

    return {
        "replicates": replicates,
        "empirical_probability_resolution": one_draw,
        "binomial_standard_error_at_selected_cutoff": float(
            np.sqrt(
                policy.superiority_probability
                * (1.0 - policy.superiority_probability)
                / replicates
            )
        ),
        "one_draw_lower_threshold": lower,
        "one_draw_upper_threshold": upper,
        "reclassification_at_one_draw_lower": changed(lower_labels),
        "reclassification_at_one_draw_upper": changed(upper_labels),
        "interpretation": (
            "finite-draw diagnostic only; it does not measure transition-model, "
            "WP-parameter, model-form, or counterfactual uncertainty"
        ),
    }


def _temporal_row(report: dict[str, object]) -> dict[str, object]:
    gaps = report["action_gap_distribution"]["overall"]
    return {
        "season": report["evaluation_season"],
        "decisions": report["decisions"],
        "classification": report["classification"],
        "supported_action_counts": report["supported_action_counts"],
        "gap_median": gaps["median"],
        "gap_p90": gaps["p90"],
        "gap_p95": gaps["p95"],
        "gap_maximum": gaps["maximum"],
        "sparse_support_rate": report["sparse_support_frequency"]["rate"],
    }


def _select_worked_audits(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        rows, key=lambda row: (row["season"], row["game_id"], row["play_id"])
    )

    def pair_lookup(row: dict[str, Any], action_a: str, action_b: str) -> Any:
        return next(
            (
                pair
                for pair in row["audit"].pairwise_differences
                if {pair.action_a, pair.action_b} == {action_a, action_b}
                and pair.available
            ),
            None,
        )

    def is_nonsaturated_one_score(row: dict[str, Any]) -> bool:
        estimates = [
            value.expected_win_probability
            for value in row["audit"].actions
            if value.expected_win_probability is not None
        ]
        return (
            abs(row["situation"]["score_differential"]) <= 8
            and bool(estimates)
            and min(estimates) >= 0.05
            and max(estimates) <= 0.95
        )

    definitions: tuple[tuple[str, Callable[[dict[str, Any]], bool]], ...] = (
        (
            "obvious_punt",
            lambda row: (
                row["actual_action"] == "punt"
                and row["situation"]["yards_to_goal"] >= 75
                and row["situation"]["yards_to_go"] >= 8
            ),
        ),
        (
            "close_go_punt",
            lambda row: (
                row["classification"] == "close_call"
                and pair_lookup(row, "go", "punt") is not None
                and is_nonsaturated_one_score(row)
            ),
        ),
        (
            "clear_short_yardage_go_preference",
            lambda row: (
                row["classification"] == "clear_model_preference"
                and row["audit"].model_preferred_action == "go"
                and row["situation"]["yards_to_go"] <= 2
            ),
        ),
        (
            "field_goal_go_tradeoff",
            lambda row: (
                pair_lookup(row, "go", "field_goal") is not None
                and is_nonsaturated_one_score(row)
            ),
        ),
        (
            "late_high_leverage",
            lambda row: (
                row["situation"]["quarter"] == 4
                and row["situation"]["quarter_seconds_remaining"] <= 300
                and abs(row["situation"]["score_differential"]) <= 8
            ),
        ),
        (
            "tied_late_regulation_overtime_risk",
            lambda row: (
                row["situation"]["score_differential"] == 0
                and row["maximum_overtime_boundary_mass"] > 0
            ),
        ),
        (
            "sparse_or_unsupported",
            lambda row: (
                row["classification"] in {"limited_support", "insufficient_support"}
            ),
        ),
    )
    selected: list[dict[str, Any]] = []
    used: set[tuple[str, int]] = set()
    for label, predicate in definitions:
        matches = [
            row
            for row in ordered
            if predicate(row) and (row["game_id"], row["play_id"]) not in used
        ]
        if matches:
            chosen = (
                min(matches, key=_preference_gap_sort_key)
                if label in {"close_go_punt", "field_goal_go_tradeoff"}
                else matches[0]
            )
            chosen = {**chosen, "audit_label": label}
            selected.append(chosen)
            used.add((chosen["game_id"], chosen["play_id"]))
    close_calls = [
        row
        for row in ordered
        if row["classification"] == "close_call"
        and is_nonsaturated_one_score(row)
        and (row["game_id"], row["play_id"]) not in used
    ]
    if close_calls:
        chosen = min(close_calls, key=_preference_gap_sort_key)
        selected.append({**chosen, "audit_label": "true_close_call"})
    return selected


def _stress_tests(
    action_models: ActionBaselineSet,
    state_model: Any,
    *,
    threshold_policy: DecisionThresholdPolicy,
    bootstrap_replicates: int,
    confidence_level: float,
) -> list[dict[str, object]]:
    context = build_decision_bootstrap_context(
        action_models,
        bootstrap_replicates=bootstrap_replicates,
        random_seed=DECISION_BOOTSTRAP_SEED,
    )

    def state(
        score: int,
        quarter: int,
        seconds: int,
        yards_to_goal: int,
        yards_to_go: int,
        team_timeouts: int = 3,
        opponent_timeouts: int = 3,
    ) -> CanonicalState:
        return CanonicalState(
            "A",
            "B",
            True,
            score,
            quarter,
            seconds,
            yards_to_goal,
            4,
            yards_to_go,
            team_timeouts,
            opponent_timeouts,
        )

    cases = (
        ("fourth_and_1_midfield", state(0, 2, 1800, 50, 1), "go"),
        ("fourth_and_long_backed_up", state(0, 2, 1800, 90, 12), "punt"),
        ("short_opponent_territory", state(0, 3, 900, 28, 1), "go"),
        ("late_tie_field_goal_range", state(0, 4, 90, 22, 4, 2, 2), "field_goal"),
        ("late_trailing_near_goal", state(-8, 4, 120, 15, 3, 1, 2), "go"),
        ("late_trailing_midrange", state(-5, 4, 120, 35, 3, 1, 2), "go"),
        ("large_lead_late", state(17, 4, 180, 55, 2, 2, 1), "punt"),
        ("extreme_field_goal_distance", state(0, 2, 1800, 80, 4), "punt"),
    )
    reports = []
    for label, state, actual in cases:
        audit = audit_decision_value(
            state,
            actual,
            action_models,
            state_model,
            threshold_policy=threshold_policy,
            bootstrap_replicates=bootstrap_replicates,
            confidence_level=confidence_level,
            bootstrap_context=context,
        )
        reports.append(
            {
                "label": label,
                "state": asdict(state),
                "audit": audit.to_dict(),
                "probability_bounds_pass": all(
                    value.expected_win_probability is None
                    or 0 <= value.expected_win_probability <= 1
                    for value in audit.actions
                ),
                "extreme_field_goal_abstention_pass": (
                    label != "extreme_field_goal_distance"
                    or next(
                        value for value in audit.actions if value.action == "field_goal"
                    ).support_status
                    == "unavailable"
                ),
            }
        )
    return reports


def _transition_audit(
    state: CanonicalState, action_models: ActionBaselineSet
) -> dict[str, object]:
    report: dict[str, object] = {}
    for action in ACTIONS:
        distribution = action_models.transition_distribution(action, state)
        if not distribution.support.in_support:
            report[action] = {
                "support_status": "unavailable"
                if not distribution.support.available
                else "unsupported",
                "reason": distribution.support.reason,
            }
            continue
        states = distribution.states
        training = _audit_training_rows(action_models, action, state)
        retained = training["possession_retained"].to_numpy()
        next_is_query_team = (
            states["evaluation_team"].to_numpy() == state.evaluation_team
        )
        original_score = np.where(
            next_is_query_team,
            states["score_differential"].to_numpy(),
            -states["score_differential"].to_numpy(),
        )
        expected_original_score = (
            state.score_differential + training["decision_score_delta"].to_numpy()
        )
        raw_clock = (
            state.game_seconds_remaining - training["elapsed_seconds"].to_numpy()
        )
        raw_field = (
            state.yards_to_goal + training["decision_yards_to_goal_delta"].to_numpy()
        )
        resets = training["field_position_resets"].to_numpy()
        expected_decision_field = np.clip(raw_field, 1.0, 99.0)
        expected_field = np.where(
            resets,
            training["next_yards_to_goal"].to_numpy(),
            np.where(
                retained, expected_decision_field, 100.0 - expected_decision_field
            ),
        )
        raw_decision_timeouts = (
            state.team_timeouts_remaining
            + training["decision_timeout_delta"].to_numpy()
        )
        raw_opponent_timeouts = (
            state.opponent_timeouts_remaining
            + training["opponent_timeout_delta"].to_numpy()
        )
        decision_timeouts = np.clip(raw_decision_timeouts, 0.0, 3.0)
        opponent_timeouts = np.clip(raw_opponent_timeouts, 0.0, 3.0)
        expected_team_timeouts = np.where(
            retained, decision_timeouts, opponent_timeouts
        )
        expected_opponent_timeouts = np.where(
            retained, opponent_timeouts, decision_timeouts
        )
        transport_mismatches = {
            "possession": int(np.count_nonzero(next_is_query_team != retained)),
            "score_perspective": int(
                np.count_nonzero(~np.isclose(original_score, expected_original_score))
            ),
            "clock": int(
                np.count_nonzero(
                    ~np.isclose(
                        states["game_seconds_remaining"].to_numpy(),
                        np.clip(raw_clock, 0.0, 3600.0),
                    )
                )
            ),
            "field_position": int(
                np.count_nonzero(
                    ~np.isclose(states["yards_to_goal"].to_numpy(), expected_field)
                )
            ),
            "timeouts": int(
                np.count_nonzero(
                    ~np.isclose(
                        states["team_timeouts_remaining"].to_numpy(),
                        expected_team_timeouts,
                    )
                    | ~np.isclose(
                        states["opponent_timeouts_remaining"].to_numpy(),
                        expected_opponent_timeouts,
                    )
                )
            ),
        }
        flags = {
            "clock_after_query": int(
                (states["game_seconds_remaining"] > state.game_seconds_remaining).sum()
            ),
            "clock_below_zero": int((states["game_seconds_remaining"] < 0).sum()),
            "field_position_out_of_bounds": int(
                (~states["yards_to_goal"].is_between(1, 99)).sum()
            ),
            "down_out_of_bounds": int((~states["down"].is_between(1, 4)).sum()),
            "yards_to_go_out_of_bounds": int(
                (
                    (states["yards_to_go"] < 0)
                    | (states["yards_to_go"] > states["yards_to_goal"])
                ).sum()
            ),
            "timeout_out_of_bounds": int(
                (
                    ~states["team_timeouts_remaining"].is_between(0, 3)
                    | ~states["opponent_timeouts_remaining"].is_between(0, 3)
                ).sum()
            ),
            "unknown_evaluation_team": int(
                (
                    ~states["evaluation_team"].is_in(
                        (state.evaluation_team, state.opponent_team)
                    )
                ).sum()
            ),
            "team_pair_mismatch": int(
                (
                    (states["evaluation_team"] == states["opponent_team"])
                    | ~states["opponent_team"].is_in(
                        (state.evaluation_team, state.opponent_team)
                    )
                ).sum()
            ),
            "home_perspective_mismatch": int(
                (
                    states["is_home"]
                    != pl.Series(
                        "expected_is_home",
                        np.where(retained, state.is_home, not state.is_home),
                    )
                ).sum()
            ),
            "query_relative_transport_mismatch": sum(transport_mismatches.values()),
        }
        boundary_count = int(
            states.select(
                (
                    (pl.col("game_seconds_remaining") <= 0)
                    & (pl.col("score_differential") == 0)
                ).sum()
            ).item()
        )
        score_delta_counts = Counter(
            float(value) for value in training["decision_score_delta"].to_list()
        )
        report[action] = {
            "support_status": "sparse" if distribution.support.sparse else "supported",
            "samples": states.height,
            "games": distribution.support.game_count,
            "support_cell": _support_cell(action, state),
            "possession_retained_samples": int(np.count_nonzero(retained)),
            "possession_changed_samples": int(np.count_nonzero(~retained)),
            "score_delta_counts_original_team_perspective": {
                str(key): value for key, value in sorted(score_delta_counts.items())
            },
            "scoring_restart_samples": int(np.count_nonzero(resets)),
            "overtime_boundary_samples": boundary_count,
            "overtime_boundary_mass": boundary_count / states.height,
            "successor_seconds_range": [
                float(states["game_seconds_remaining"].min()),
                float(states["game_seconds_remaining"].max()),
            ],
            "successor_yards_to_goal_range": [
                float(states["yards_to_goal"].min()),
                float(states["yards_to_goal"].max()),
            ],
            "successor_score_range": [
                float(states["score_differential"].min()),
                float(states["score_differential"].max()),
            ],
            "factual_outcomes": dict(
                sorted(Counter(states["factual_outcome"].to_list()).items())
            ),
            "transport_boundary_counts": {
                "clock_below_zero_before_clip": int(np.count_nonzero(raw_clock < 0)),
                "field_below_1_before_clip": int(
                    np.count_nonzero((~resets) & (raw_field < 1))
                ),
                "field_above_99_before_clip": int(
                    np.count_nonzero((~resets) & (raw_field > 99))
                ),
                "decision_timeouts_outside_0_3_before_clip": int(
                    np.count_nonzero(
                        (raw_decision_timeouts < 0) | (raw_decision_timeouts > 3)
                    )
                ),
                "opponent_timeouts_outside_0_3_before_clip": int(
                    np.count_nonzero(
                        (raw_opponent_timeouts < 0) | (raw_opponent_timeouts > 3)
                    )
                ),
            },
            "transport_mismatches": transport_mismatches,
            "structural_flags": flags,
        }
    return report


def _audit_training_rows(
    action_models: ActionBaselineSet, action: str, state: CanonicalState
) -> pl.DataFrame:
    rows = action_models.training_rows.filter(pl.col("actual_action") == action)
    cell = _support_cell(action, state)
    if action == "go":
        return rows.filter(
            (pl.col("distance_bin") == cell["distance_bin"])
            & (pl.col("field_bin") == cell["field_bin"])
        )
    if action == "field_goal":
        return rows.filter(pl.col("action_bin") == cell["field_goal_distance_bin"])
    return rows.filter(pl.col("field_bin") == cell["field_bin"])


def _support_cell(action: str, state: CanonicalState) -> dict[str, object]:
    if action == "go":
        return {
            "distance_bin": _yards_to_go_bucket(state.yards_to_go),
            "field_bin": _field_zone(state.yards_to_goal),
        }
    if action == "field_goal":
        distance = state.yards_to_goal + 18.0
        distance_bin = (
            "under_30"
            if distance < 30
            else "30_39"
            if distance < 40
            else "40_49"
            if distance < 50
            else "50_59"
            if distance < 60
            else "60_70"
        )
        return {
            "field_goal_distance": distance,
            "field_goal_distance_bin": distance_bin,
        }
    return {"field_bin": _field_zone(state.yards_to_goal)}


def _large_gap_flags(rows: list[dict[str, Any]]) -> dict[str, object]:
    counters: Counter[str] = Counter()
    suspicious: list[dict[str, object]] = []
    for row in rows:
        for action, report in row.get("transition_audit", {}).items():
            for flag, count in report.get("structural_flags", {}).items():
                counters[flag] += int(count)
                if count:
                    suspicious.append(
                        {
                            "game_id": row["game_id"],
                            "play_id": row["play_id"],
                            "action": action,
                            "flag": flag,
                            "count": count,
                        }
                    )
    return {
        "totals": dict(sorted(counters.items())),
        "suspicious_cases": suspicious,
    }


def _public_summary(row: dict[str, Any]) -> dict[str, object]:
    payload = {
        "season": row["season"],
        "game_id": row["game_id"],
        "play_id": row["play_id"],
        "situation": row["situation"],
        "actual_action": row["actual_action"],
        "target": row["target"],
        "classification": row["classification"],
        "support_profile": row["support_profile"],
        "audit": row["audit"].to_dict(),
        "play_audit": row["play_audit"],
    }
    if "audit_label" in row:
        payload["audit_label"] = row["audit_label"]
    if "transition_audit" in row:
        payload["transition_audit"] = row["transition_audit"]
    return payload


def _situation(row: dict[str, Any]) -> dict[str, object]:
    yards_to_goal = float(row["yards_to_goal"])
    yards_to_go = float(row["yards_to_go"])
    quarter = int(row["quarter"])
    quarter_seconds = int(row["quarter_seconds_remaining"])
    return {
        "possession_team": str(row["possession_team"]),
        "defense_team": str(row["defense_team"]),
        "quarter": quarter,
        "quarter_seconds_remaining": quarter_seconds,
        "game_seconds_remaining": int(row["game_seconds_remaining"]),
        "score_differential": int(row["score_differential"]),
        "yards_to_goal": yards_to_goal,
        "yards_to_go": yards_to_go,
        "field_zone": _field_zone(yards_to_goal),
        "yards_to_go_bucket": _yards_to_go_bucket(yards_to_go),
        "quarter_bucket": (
            "late_q4" if quarter == 4 and quarter_seconds <= 300 else f"Q{quarter}"
        ),
        "late_game_regime": (
            "q4_final_two_minutes"
            if quarter == 4 and quarter_seconds <= 120
            else "q4_two_to_five_minutes"
            if quarter == 4 and quarter_seconds <= 300
            else "other_regulation"
        ),
    }


def _play_audit(row: dict[str, Any]) -> dict[str, object]:
    """Retain the factual fields needed to inspect a reported large gap."""

    fields = (
        "description",
        "actual_action",
        "factual_outcome",
        "next_state_status",
        "possession_team",
        "defense_team",
        "home_team",
        "down",
        "yards_to_go",
        "yards_to_goal",
        "quarter",
        "quarter_seconds_remaining",
        "game_seconds_remaining",
        "score_differential",
        "posteam_timeouts_remaining",
        "defteam_timeouts_remaining",
        "next_possession_team",
        "next_defense_team",
        "next_down",
        "next_yards_to_go",
        "next_yards_to_goal",
        "next_quarter",
        "next_game_seconds_remaining",
        "decision_team_score_differential_next",
        "decision_team_timeouts_remaining_next",
        "opponent_timeouts_remaining_next",
    )
    return {field: row.get(field) for field in fields}


def _eventual_value(row: dict[str, Any]) -> float | None:
    margin = row.get("home_score_differential_final")
    if margin is None:
        return None
    if float(margin) == 0:
        return 0.5
    possession_is_home = row["possession_team"] == row["home_team"]
    return float((float(margin) > 0) == possession_is_home)


def _field_zone(yards_to_goal: float) -> str:
    if yards_to_goal <= 20:
        return "opponent_red_zone"
    if yards_to_goal <= 49:
        return "opponent_21_49"
    if yards_to_goal <= 79:
        return "own_21_to_midfield"
    return "own_1_20"


def _yards_to_go_bucket(yards_to_go: float) -> str:
    if yards_to_go <= 1:
        return "1"
    if yards_to_go <= 2:
        return "2"
    if yards_to_go <= 5:
        return "3_5"
    if yards_to_go <= 10:
        return "6_10"
    return "11_plus"


def _largest_gap_sort_key(row: dict[str, Any]) -> tuple[float, int, str, int]:
    return (
        -float(row["raw_action_value_gap"]),
        int(row["season"]),
        str(row["game_id"]),
        int(row["play_id"]),
    )


def _preference_gap_sort_key(row: dict[str, Any]) -> tuple[float, str, int]:
    gap = row["minimum_preference_gap"]
    return (
        float(gap) if gap is not None else float("inf"),
        str(row["game_id"]),
        int(row["play_id"]),
    )


def _validate_seasons(pbp: pl.DataFrame) -> None:
    seasons = sorted(int(value) for value in pbp["season"].unique())
    if not seasons:
        raise ValueError("decision diagnostics require play-by-play rows")
    if max(seasons) > 2024:
        raise ValueError("2025 and later seasons are protected")
    required = list(range(2014, 2025))
    if seasons != required:
        raise ValueError("decision diagnostics require complete 2014-2024 seasons")


__all__ = ["DECISION_EVALUATION_SEASONS", "evaluate_decision_diagnostics"]
