"""Pre-2025 diagnostics for boundary-aware punt transition development."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from coachiq.analysis.decision_value import (
    ACTIONS,
    DECISION_BOOTSTRAP_REPLICATES,
    DECISION_BOOTSTRAP_SEED,
    DECISION_THRESHOLD_POLICY_V1,
    PAIRWISE_ACTIONS,
    _action_bootstrap_draws,
    _action_value_output,
    _decision_output,
    _overtime_boundary_mass,
    _pairwise_output,
    build_decision_bootstrap_context,
)
from coachiq.analysis.fourth_down import extract_fourth_down_candidates
from coachiq.models.action_baselines import (
    ActionBaselineSet,
    TransitionDistribution,
    canonical_state_from_candidate,
    fit_action_baselines,
)
from coachiq.models.state import CanonicalState, build_state_value_rows
from coachiq.models.wp_selection import fit_locked_wp_model

PUNT_STUDY_SEASONS = tuple(range(2014, 2025))
PUNT_EVALUATION_SEASONS = tuple(range(2020, 2025))
CLIPPING_THRESHOLDS = (0.0, 0.10, 0.25, 0.50)
RAW_PUNT_AUDIT_COLUMNS = (
    "season",
    "game_id",
    "play_id",
    "punt_attempt",
    "kick_distance",
    "return_yards",
    "touchback",
    "punt_blocked",
    "punt_fair_catch",
    "punt_out_of_bounds",
    "punt_downed",
    "punt_in_endzone",
    "punt_inside_twenty",
)
CANDIDATES = ("A", "B", "C")
CLUSTER_BOOTSTRAP_REPLICATES = 2000
CLUSTER_BOOTSTRAP_SEED = 2707


@dataclass(frozen=True)
class PuntSampleDiagnostics:
    """Field-only diagnostics aligned with a candidate transition sample."""

    invalid_mass: float
    boundary_mass: float
    touchback_mass: float


class PuntTransitionCandidateModel:
    """Replace only punt field transport while delegating every other behavior."""

    def __init__(self, base: ActionBaselineSet, candidate: str) -> None:
        if candidate not in CANDIDATES:
            raise ValueError(f"unknown punt candidate: {candidate}")
        self.base = base
        self.candidate = candidate

    @property
    def training_rows(self) -> pl.DataFrame:
        """Expose the frozen model's identical training rows."""

        return self.base.training_rows

    @property
    def training_seasons(self) -> tuple[int, ...]:
        """Expose the frozen model's identical training seasons."""

        return self.base.training_seasons

    def support(self, action: str, state: CanonicalState) -> Any:
        """Delegate the frozen availability and support policy."""

        return self.base.support(action, state)

    def empirical_binary_probability(
        self, action: str, state: CanonicalState
    ) -> tuple[float | None, Any]:
        """Delegate unchanged go and field-goal outcome behavior."""

        return self.base.empirical_binary_probability(action, state)

    def transition_distribution(
        self, action: str, state: CanonicalState
    ) -> TransitionDistribution:
        """Return the selected punt transport or the unchanged v1 transition."""

        frozen = self.base.transition_distribution(action, state)
        if action != "punt" or self.candidate == "A" or not frozen.support.in_support:
            return frozen
        rows = self.base._comparable_rows(action, state)  # noqa: SLF001
        destinations = _candidate_destinations(rows, state, self.candidate)
        states = frozen.states.with_columns(
            pl.Series("yards_to_goal", destinations, dtype=pl.Float64),
            pl.Series(
                "yards_to_go",
                np.minimum(rows["next_yards_to_go"].to_numpy(), destinations),
                dtype=pl.Float64,
            ),
        )
        return TransitionDistribution(
            action=action,
            support=frozen.support,
            states=states,
            game_clusters=frozen.game_clusters,
        )

    def punt_expected_opponent_yards_to_goal(
        self, state: CanonicalState
    ) -> tuple[float | None, Any]:
        """Return the selected candidate's conditional mean and frozen support."""

        distribution = self.transition_distribution("punt", state)
        if not distribution.support.in_support:
            return None, distribution.support
        return float(distribution.states["yards_to_goal"].mean()), distribution.support

    def punt_sample_diagnostics(self, state: CanonicalState) -> PuntSampleDiagnostics:
        """Measure invalid pre-boundary and legal boundary/touchback mass."""

        support = self.base.support("punt", state)
        if not support.in_support:
            return PuntSampleDiagnostics(0.0, 0.0, 0.0)
        rows = self.base._comparable_rows("punt", state)  # noqa: SLF001
        if self.candidate == "A":
            raw_decision_position = (
                state.yards_to_goal + rows["decision_yards_to_goal_delta"].to_numpy()
            )
            resets = rows["field_position_resets"].to_numpy()
            invalid = (~resets) & (
                (raw_decision_position < 1.0) | (raw_decision_position > 99.0)
            )
        else:
            invalid = np.zeros(rows.height, dtype=bool)
        destinations = (
            self.transition_distribution("punt", state)
            .states["yards_to_goal"]
            .to_numpy()
        )
        touchbacks = rows["is_touchback"].fill_null(False).to_numpy()
        return PuntSampleDiagnostics(
            invalid_mass=float(invalid.mean()),
            boundary_mass=float(((destinations == 1) | (destinations == 99)).mean()),
            touchback_mass=float(touchbacks.mean()),
        )


def validate_punt_study_seasons(pbp: pl.DataFrame) -> None:
    """Prevent holdout or prospective data from entering model development."""

    seasons = tuple(sorted(int(value) for value in pbp["season"].unique()))
    if seasons != PUNT_STUDY_SEASONS:
        raise ValueError("punt study requires exactly 2014-2024; 2025+ are prohibited")


def diagnose_punt_v1(
    pbp: pl.DataFrame, raw_punt_fields: pl.DataFrame | None = None
) -> dict[str, object]:
    """Reproduce v1 and quantify the empirical clipping mechanism."""

    validate_punt_study_seasons(pbp)
    candidates = extract_fourth_down_candidates(pbp)
    folds = []
    pooled_factual = []
    for season in PUNT_EVALUATION_SEASONS:
        model = fit_action_baselines(candidates.filter(pl.col("season") < season))
        evaluation = candidates.filter(pl.col("season") == season)
        factual = _factual_punt_metrics(model, evaluation)
        pooled_factual.extend(factual)
        queries = _punt_query_records(model, evaluation)
        folds.append(
            {
                "training_seasons": list(range(2014, season)),
                "evaluation_season": season,
                "factual": _metric_summary(factual),
                "support": _support_summary(queries),
                "clipping": _clipping_report(queries),
            }
        )

    full_model = fit_action_baselines(candidates)
    punt_rows = full_model.training_rows.filter(pl.col("actual_action") == "punt")
    return {
        "protocol": {
            "candidate": "A",
            "model": "coachiq-action-transition-v1",
            "development_seasons": list(PUNT_STUDY_SEASONS),
            "evaluation_seasons": list(PUNT_EVALUATION_SEASONS),
            "protected_seasons": [2025, 2026],
        },
        "folds": folds,
        "pooled_factual": _metric_summary(pooled_factual),
        "mechanism": _mechanism_report(punt_rows),
        "source_field_audit": _source_field_audit(punt_rows, raw_punt_fields),
        "candidate_cell_feasibility": _candidate_cell_feasibility(candidates),
    }


def compare_punt_candidates(pbp: pl.DataFrame) -> dict[str, object]:
    """Run the preregistered rolling comparison for candidates A, B, and C."""

    validate_punt_study_seasons(pbp)
    candidates = extract_fourth_down_candidates(pbp)
    folds = []
    pooled_rows: dict[str, list[dict[str, Any]]] = {
        candidate: [] for candidate in CANDIDATES
    }
    pooled_queries: dict[str, list[dict[str, Any]]] = {
        candidate: [] for candidate in CANDIDATES
    }
    for season in PUNT_EVALUATION_SEASONS:
        base = fit_action_baselines(candidates.filter(pl.col("season") < season))
        evaluation = candidates.filter(pl.col("season") == season)
        candidate_reports = {}
        for candidate in CANDIDATES:
            model = PuntTransitionCandidateModel(base, candidate)
            factual = _factual_punt_metrics(model, evaluation)
            for row in factual:
                row["season"] = season
            pooled_rows[candidate].extend(factual)
            queries = _punt_query_records(model, evaluation)
            pooled_queries[candidate].extend(queries)
            candidate_reports[candidate] = {
                "factual": _metric_summary(factual),
                "support": _support_summary(queries),
                "clipping": _clipping_report(queries),
                "legal_boundary_mass": _boundary_report(queries),
            }
        folds.append(
            {
                "training_seasons": list(range(2014, season)),
                "evaluation_season": season,
                "candidates": candidate_reports,
            }
        )

    full_base = fit_action_baselines(candidates)
    pooled = {
        candidate: {
            "factual": _metric_summary(rows),
            "clipping": _clipping_report(pooled_queries[candidate]),
            "legal_boundary_mass": _boundary_report(pooled_queries[candidate]),
            "support": _support_summary(pooled_queries[candidate]),
        }
        for candidate, rows in pooled_rows.items()
    }
    return {
        "protocol": {
            "candidates": list(CANDIDATES),
            "development_seasons": list(PUNT_STUDY_SEASONS),
            "evaluation_seasons": list(PUNT_EVALUATION_SEASONS),
            "protected_seasons": [2025, 2026],
            "cluster_bootstrap_replicates": CLUSTER_BOOTSTRAP_REPLICATES,
            "cluster_bootstrap_seed": CLUSTER_BOOTSTRAP_SEED,
        },
        "folds": folds,
        "pooled": pooled,
        "clustered_comparisons": _clustered_comparisons(pooled_rows),
        "stress_states": _stress_state_report(full_base),
        "shape_sanity": _shape_sanity_report(full_base),
        "invariants": _candidate_invariants(full_base),
    }


def evaluate_punt_decision_sensitivity(
    pbp: pl.DataFrame, progress: Any = None
) -> dict[str, object]:
    """Substitute punt candidates in an otherwise frozen v1 decision audit."""

    validate_punt_study_seasons(pbp)
    candidates = extract_fourth_down_candidates(pbp)
    states = build_state_value_rows(pbp)
    all_rows = []
    folds = []
    for season in PUNT_EVALUATION_SEASONS:
        if progress:
            progress(f"decision sensitivity: fit through {season - 1}; score {season}")
        training = candidates.filter(pl.col("season") < season)
        evaluation = candidates.filter(
            (pl.col("season") == season) & (pl.col("disposition") == "eligible")
        )
        base = fit_action_baselines(training)
        state_model = fit_locked_wp_model(states.filter(pl.col("season") < season))
        context = build_decision_bootstrap_context(
            base,
            bootstrap_replicates=DECISION_BOOTSTRAP_REPLICATES,
            random_seed=DECISION_BOOTSTRAP_SEED,
        )
        models = {
            candidate: PuntTransitionCandidateModel(base, candidate)
            for candidate in CANDIDATES
        }
        fold_rows = []
        for row in evaluation.iter_rows(named=True):
            state = canonical_state_from_candidate(row)
            audits, distributions = _shared_decision_audits(
                state,
                str(row["actual_action"]),
                models,
                state_model,
                context,
            )
            values = {
                candidate: {value.action: value for value in audit.actions}
                for candidate, audit in audits.items()
            }
            candidate_rows = {}
            for candidate, model in models.items():
                audit = audits[candidate]
                punt_distribution = distributions[candidate]["punt"]
                diagnostics = model.punt_sample_diagnostics(state)
                destination = (
                    _destination_summary(punt_distribution.states["yards_to_goal"])
                    if punt_distribution.support.in_support
                    else None
                )
                candidate_rows[candidate] = {
                    "punt_ewp": values[candidate]["punt"].expected_win_probability,
                    "actual_action_gap": audit.raw_action_value_gap,
                    "classification": audit.classification,
                    "preferred_action": audit.model_preferred_action,
                    "invalid_mass": (
                        diagnostics.invalid_mass
                        if punt_distribution.support.in_support
                        else None
                    ),
                    "destination": destination,
                }
            non_punt_equal = all(
                values[candidate][action].expected_win_probability
                == values["A"][action].expected_win_probability
                for candidate in ("B", "C")
                for action in ("go", "field_goal")
            )
            fold_rows.append(
                {
                    "season": season,
                    "game_id": str(row["game_id"]),
                    "play_id": int(row["play_id"]),
                    "actual_action": str(row["actual_action"]),
                    "description": row.get("description"),
                    "state": {
                        "quarter": state.quarter,
                        "game_seconds_remaining": state.game_seconds_remaining,
                        "score_differential": state.score_differential,
                        "yards_to_goal": state.yards_to_goal,
                        "yards_to_go": state.yards_to_go,
                    },
                    "candidates": candidate_rows,
                    "non_punt_point_values_equal": non_punt_equal,
                }
            )
        folds.append(
            {
                "evaluation_season": season,
                "training_seasons": list(range(2014, season)),
                "summary": _decision_sensitivity_summary(fold_rows),
            }
        )
        all_rows.extend(fold_rows)
        if progress:
            progress(f"decision sensitivity completed {season}: {len(fold_rows):,}")

    return {
        "protocol": {
            "development_seasons": list(PUNT_STUDY_SEASONS),
            "evaluation_seasons": list(PUNT_EVALUATION_SEASONS),
            "protected_seasons": [2025, 2026],
            "wp_model": "coachiq-wp-v1",
            "decision_model": "coachiq-decision-v1 offline sensitivity only",
            "bootstrap_replicates": DECISION_BOOTSTRAP_REPLICATES,
            "bootstrap_seed": DECISION_BOOTSTRAP_SEED,
        },
        "folds": folds,
        "pooled": _decision_sensitivity_summary(all_rows),
        "representative_heavy_clipping_cases": _representative_cases(all_rows),
        "largest_gap_comparison": _largest_gap_comparison(all_rows),
        "largest_candidate_changes": _largest_candidate_changes(all_rows),
    }


def _shared_decision_audits(
    state: CanonicalState,
    actual_action: str,
    models: dict[str, PuntTransitionCandidateModel],
    state_model: Any,
    context: Any,
) -> tuple[dict[str, Any], dict[str, dict[str, TransitionDistribution]]]:
    base_distributions = {
        action: models["A"].transition_distribution(action, state) for action in ACTIONS
    }
    distributions = {
        "A": base_distributions,
        **{
            candidate: {
                **base_distributions,
                "punt": models[candidate].transition_distribution("punt", state),
            }
            for candidate in ("B", "C")
        },
    }
    base_samples = _decision_samples(state, base_distributions, state_model)
    base_draws = {
        action: _action_bootstrap_draws(
            values,
            base_distributions[action].game_clusters,
            context.training_games,
            context.weights,
        )
        for action, values in base_samples.items()
    }
    audits = {}
    for candidate in CANDIDATES:
        candidate_samples = dict(base_samples)
        candidate_draws = dict(base_draws)
        if candidate != "A" and distributions[candidate]["punt"].support.in_support:
            punt_states = distributions[candidate]["punt"].states
            probabilities = state_model.predict_proba(punt_states)
            next_teams = punt_states["evaluation_team"].to_numpy()
            candidate_samples["punt"] = np.where(
                next_teams == state.evaluation_team,
                probabilities,
                1.0 - probabilities,
            )
            candidate_draws["punt"] = _action_bootstrap_draws(
                candidate_samples["punt"],
                distributions[candidate]["punt"].game_clusters,
                context.training_games,
                context.weights,
            )
        overtime = {
            action: _overtime_boundary_mass(
                state, distributions[candidate][action].states
            )
            for action in ACTIONS
        }
        action_values = tuple(
            _action_value_output(
                action,
                distributions[candidate][action].support,
                candidate_samples.get(action),
                candidate_draws.get(action),
                state_model.version,
                DECISION_BOOTSTRAP_REPLICATES,
                0.90,
                overtime[action],
            )
            for action in ACTIONS
        )
        pairs = tuple(
            _pairwise_output(
                action_a,
                action_b,
                candidate_samples,
                candidate_draws,
                DECISION_BOOTSTRAP_REPLICATES,
                0.90,
            )
            for action_a, action_b in PAIRWISE_ACTIONS
        )
        audits[candidate] = _decision_output(
            actual_action,
            action_values,
            pairs,
            DECISION_THRESHOLD_POLICY_V1,
            state_model.version,
        )
    return audits, distributions


def _decision_samples(
    state: CanonicalState,
    distributions: dict[str, TransitionDistribution],
    state_model: Any,
) -> dict[str, np.ndarray]:
    samples = {}
    for action, distribution in distributions.items():
        if not distribution.support.in_support:
            continue
        probabilities = state_model.predict_proba(distribution.states)
        next_teams = distribution.states["evaluation_team"].to_numpy()
        samples[action] = np.where(
            next_teams == state.evaluation_team,
            probabilities,
            1.0 - probabilities,
        )
    return samples


def _decision_sensitivity_summary(rows: list[dict[str, Any]]) -> dict[str, object]:
    output = {"decisions": len(rows), "candidates": {}}
    base = [row["candidates"]["A"] for row in rows]
    for candidate in CANDIDATES:
        current = [row["candidates"][candidate] for row in rows]
        punt_pairs = [
            (a["punt_ewp"], b["punt_ewp"])
            for a, b in zip(base, current, strict=True)
            if a["punt_ewp"] is not None and b["punt_ewp"] is not None
        ]
        gap_pairs = [
            (a["actual_action_gap"], b["actual_action_gap"])
            for a, b in zip(base, current, strict=True)
            if a["actual_action_gap"] is not None and b["actual_action_gap"] is not None
        ]
        clear = [
            item
            for item in current
            if item["classification"] == "clear_model_preference"
        ]
        clear_supported = [item for item in clear if item["invalid_mass"] is not None]
        output["candidates"][candidate] = {
            "punt_ewp_change": _paired_change_summary(punt_pairs),
            "actual_action_gap_change": _paired_change_summary(gap_pairs),
            "classification": _counts_and_rates(
                [str(item["classification"]) for item in current]
            ),
            "classification_changes_vs_v1": sum(
                a["classification"] != b["classification"]
                for a, b in zip(base, current, strict=True)
            ),
            "classification_change_rate_vs_v1": float(
                np.mean(
                    [
                        a["classification"] != b["classification"]
                        for a, b in zip(base, current, strict=True)
                    ]
                )
            ),
            "preferred_action_changes_vs_v1": sum(
                a["preferred_action"] != b["preferred_action"]
                for a, b in zip(base, current, strict=True)
            ),
            "clear_case_clipping": _invalid_threshold_summary(clear_supported),
            "clipping_by_classification": {
                classification: _invalid_threshold_summary(
                    [
                        item
                        for item in current
                        if item["classification"] == classification
                        and item["invalid_mass"] is not None
                    ]
                )
                for classification in sorted(
                    {str(item["classification"]) for item in current}
                )
            },
        }
    output["non_punt_point_values_equal"] = all(
        bool(row["non_punt_point_values_equal"]) for row in rows
    )
    heavy = [
        row
        for row in rows
        if row["candidates"]["A"]["invalid_mass"] is not None
        and row["candidates"]["A"]["invalid_mass"] > 0.25
    ]
    output["v1_heavy_clipping_subset"] = {
        "decisions": len(heavy),
        "rate": len(heavy) / len(rows) if rows else 0.0,
        "candidate_changes": {
            candidate: {
                "punt_ewp_change": _paired_change_summary(
                    [
                        (
                            row["candidates"]["A"]["punt_ewp"],
                            row["candidates"][candidate]["punt_ewp"],
                        )
                        for row in heavy
                    ]
                ),
                "classification_changes": sum(
                    row["candidates"]["A"]["classification"]
                    != row["candidates"][candidate]["classification"]
                    for row in heavy
                ),
            }
            for candidate in ("B", "C")
        },
    }
    return output


def _paired_change_summary(
    pairs: list[tuple[float | None, float | None]],
) -> dict[str, float | int | None]:
    differences = np.asarray(
        [float(candidate) - float(base) for base, candidate in pairs], dtype=float
    )
    if not differences.size:
        return {
            "observations": 0,
            "mean": None,
            "median": None,
            "p10": None,
            "p90": None,
            "minimum": None,
            "maximum": None,
        }
    return {
        "observations": int(differences.size),
        "mean": float(differences.mean()),
        "median": float(np.median(differences)),
        "p10": float(np.quantile(differences, 0.10)),
        "p90": float(np.quantile(differences, 0.90)),
        "minimum": float(differences.min()),
        "maximum": float(differences.max()),
    }


def _counts_and_rates(values: list[str]) -> dict[str, dict[str, float | int]]:
    counts = Counter(values)
    return {
        key: {"decisions": value, "rate": value / len(values) if values else 0.0}
        for key, value in sorted(counts.items())
    }


def _invalid_threshold_summary(rows: list[dict[str, Any]]) -> dict[str, object]:
    masses = [float(row["invalid_mass"]) for row in rows]
    return {
        "queries": len(masses),
        "thresholds": {
            name: {
                "count": sum(value > threshold for value in masses),
                "rate": float(np.mean([value > threshold for value in masses]))
                if masses
                else 0.0,
            }
            for name, threshold in zip(
                ("any", "above_10_percent", "above_25_percent", "above_50_percent"),
                CLIPPING_THRESHOLDS,
                strict=True,
            )
        },
    }


def _destination_summary(values: pl.Series) -> dict[str, float]:
    array = values.to_numpy()
    return {
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "p10": float(np.quantile(array, 0.10)),
        "p90": float(np.quantile(array, 0.90)),
        "minimum": float(array.min()),
        "maximum": float(array.max()),
    }


def _representative_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    supported = [
        row
        for row in rows
        if row["candidates"]["A"]["invalid_mass"] is not None
        and row["candidates"]["A"]["punt_ewp"] is not None
    ]
    ordered = sorted(
        supported,
        key=lambda row: (
            -float(row["candidates"]["A"]["invalid_mass"]),
            row["game_id"],
            row["play_id"],
        ),
    )
    selected = []
    used_bands = set()
    for row in ordered:
        band = _position_band(float(row["state"]["yards_to_goal"]))
        if band in used_bands and len(selected) >= 4:
            continue
        selected.append(row)
        used_bands.add(band)
        if len(selected) == 8:
            break
    return selected


def _largest_gap_comparison(rows: list[dict[str, Any]]) -> dict[str, object]:
    report = {}
    for candidate in CANDIDATES:
        available = [
            row
            for row in rows
            if row["candidates"][candidate]["actual_action_gap"] is not None
        ]
        largest = sorted(
            available,
            key=lambda row: (
                -float(row["candidates"][candidate]["actual_action_gap"]),
                row["game_id"],
                row["play_id"],
            ),
        )[:20]
        report[candidate] = [
            {
                "season": row["season"],
                "game_id": row["game_id"],
                "play_id": row["play_id"],
                "actual_action": row["actual_action"],
                "gap": row["candidates"][candidate]["actual_action_gap"],
                "v1_gap": row["candidates"]["A"]["actual_action_gap"],
                "classification": row["candidates"][candidate]["classification"],
                "v1_invalid_mass": row["candidates"]["A"]["invalid_mass"],
            }
            for row in largest
        ]
    return report


def _largest_candidate_changes(rows: list[dict[str, Any]]) -> dict[str, object]:
    report = {}
    for candidate in ("B", "C"):
        available = [
            row
            for row in rows
            if row["candidates"]["A"]["punt_ewp"] is not None
            and row["candidates"][candidate]["punt_ewp"] is not None
        ]
        largest = sorted(
            available,
            key=lambda row: (
                -abs(
                    float(row["candidates"][candidate]["punt_ewp"])
                    - float(row["candidates"]["A"]["punt_ewp"])
                ),
                row["game_id"],
                row["play_id"],
            ),
        )[:20]
        report[candidate] = [
            {
                "season": row["season"],
                "game_id": row["game_id"],
                "play_id": row["play_id"],
                "state": row["state"],
                "v1_punt_ewp": row["candidates"]["A"]["punt_ewp"],
                "candidate_punt_ewp": row["candidates"][candidate]["punt_ewp"],
                "v1_invalid_mass": row["candidates"]["A"]["invalid_mass"],
                "v1_classification": row["candidates"]["A"]["classification"],
                "candidate_classification": row["candidates"][candidate][
                    "classification"
                ],
            }
            for row in largest
        ]
    return report


def _candidate_destinations(
    rows: pl.DataFrame, state: CanonicalState, candidate: str
) -> np.ndarray:
    observed = rows["next_yards_to_goal"].to_numpy().astype(float)
    if candidate == "B":
        return observed
    if candidate != "C":
        raise ValueError("candidate destination transport is defined for B or C")

    retained = rows["possession_retained"].to_numpy()
    reset = rows["field_position_resets"].to_numpy()
    touchback = rows["is_touchback"].fill_null(False).to_numpy()
    start = rows["yards_to_goal"].to_numpy().astype(float)
    historical_decision_position = np.where(retained, observed, 100.0 - observed)
    forward = historical_decision_position <= start
    forward_denominator = start - 1.0
    backward_denominator = 99.0 - start
    fraction = np.zeros(rows.height, dtype=float)
    np.divide(
        start - historical_decision_position,
        forward_denominator,
        out=fraction,
        where=forward & (forward_denominator > 0),
    )
    np.divide(
        historical_decision_position - start,
        backward_denominator,
        out=fraction,
        where=(~forward) & (backward_denominator > 0),
    )
    if np.any((fraction < -1e-12) | (fraction > 1.0 + 1e-12)):
        raise ValueError("historical punt movement fraction is outside [0, 1]")
    query_decision_position = np.where(
        forward,
        state.yards_to_goal - fraction * (state.yards_to_goal - 1.0),
        state.yards_to_goal + fraction * (99.0 - state.yards_to_goal),
    )
    transported = np.where(
        retained, query_decision_position, 100.0 - query_decision_position
    )
    use_absolute = reset | touchback
    result = np.where(use_absolute, observed, transported)
    if not np.all(np.isfinite(result)) or np.any((result < 1) | (result > 99)):
        raise ValueError("bounded punt transport produced an invalid destination")
    return result


def select_raw_punt_audit_fields(raw: pl.DataFrame) -> pl.DataFrame:
    """Retain only source fields needed to assess punt-field reliability."""

    required = {"season", "game_id", "play_id"}
    if not required.issubset(raw.columns):
        raise ValueError("raw punt audit requires season/game_id/play_id")
    expressions = []
    for column in RAW_PUNT_AUDIT_COLUMNS:
        if column in raw.columns:
            expressions.append(pl.col(column))
        elif column in required:
            raise ValueError(f"raw punt audit is missing {column}")
        else:
            expressions.append(pl.lit(None).alias(column))
    return raw.select(expressions)


def _factual_punt_metrics(
    model: ActionBaselineSet, candidates: pl.DataFrame
) -> list[dict[str, Any]]:
    rows = candidates.filter(
        (pl.col("disposition") == "eligible")
        & (pl.col("actual_action") == "punt")
        & (pl.col("next_state_status") == "reconstructed")
        & pl.col("next_yards_to_goal").is_not_null()
    )
    output = []
    for row in rows.iter_rows(named=True):
        state = canonical_state_from_candidate(row)
        distribution = model.transition_distribution("punt", state)
        if not distribution.support.in_support:
            continue
        samples = distribution.states["yards_to_goal"].to_numpy()
        target = float(row["next_yards_to_goal"])
        prediction = float(samples.mean())
        output.append(
            {
                "game_id": str(row["game_id"]),
                "prediction": prediction,
                "target": target,
                "error": prediction - target,
                "crps": _empirical_crps(samples, target),
            }
        )
    return output


def _punt_query_records(
    model: ActionBaselineSet | PuntTransitionCandidateModel,
    candidates: pl.DataFrame,
) -> list[dict[str, Any]]:
    eligible = candidates.filter(pl.col("disposition") == "eligible")
    candidate_model = (
        model
        if isinstance(model, PuntTransitionCandidateModel)
        else PuntTransitionCandidateModel(model, "A")
    )
    output = []
    for row in eligible.iter_rows(named=True):
        state = canonical_state_from_candidate(row)
        support = model.support("punt", state)
        clipping_mass = None
        boundary_mass = None
        touchback_mass = None
        if support.in_support:
            diagnostics = candidate_model.punt_sample_diagnostics(state)
            clipping_mass = diagnostics.invalid_mass
            boundary_mass = diagnostics.boundary_mass
            touchback_mass = diagnostics.touchback_mass
        output.append(
            {
                "game_id": str(row["game_id"]),
                "play_id": int(row["play_id"]),
                "yards_to_goal": state.yards_to_goal,
                "field_zone": _field_zone(state.yards_to_goal),
                "position_band": _position_band(state.yards_to_goal),
                "yards_to_go_band": _yards_to_go_band(state.yards_to_go),
                "time_regime": _time_regime(
                    state.quarter, state.game_seconds_remaining
                ),
                "available": support.available,
                "supported": support.in_support,
                "sparse": support.sparse and support.in_support,
                "observations": support.observation_count,
                "games": support.game_count,
                "clipping_mass": clipping_mass,
                "boundary_mass": boundary_mass,
                "touchback_mass": touchback_mass,
            }
        )
    return output


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, object]:
    errors = np.asarray([row["error"] for row in rows], dtype=float)
    absolute = np.abs(errors)
    return {
        "observations": len(rows),
        "mae": float(absolute.mean()),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "median_absolute_error": float(np.median(absolute)),
        "p90_absolute_error": float(np.quantile(absolute, 0.90)),
        "mean_crps": float(np.mean([row["crps"] for row in rows])),
    }


def _clustered_comparisons(
    rows_by_candidate: dict[str, list[dict[str, Any]]],
) -> dict[str, object]:
    rng = np.random.default_rng(CLUSTER_BOOTSTRAP_SEED)
    game_stats = {
        candidate: _game_metric_sufficient_statistics(rows)
        for candidate, rows in rows_by_candidate.items()
    }
    draws = {
        candidate: {metric: [] for metric in ("mae", "rmse", "mean_crps")}
        for candidate in CANDIDATES
    }
    fold_games = {
        season: sorted(
            game
            for observed_season, game in game_stats["A"]
            if observed_season == season
        )
        for season in PUNT_EVALUATION_SEASONS
    }
    for _ in range(CLUSTER_BOOTSTRAP_REPLICATES):
        weights: dict[tuple[int, str], int] = {}
        for season, games in fold_games.items():
            counts = rng.multinomial(len(games), np.full(len(games), 1 / len(games)))
            weights.update(
                {
                    (season, game): int(count)
                    for game, count in zip(games, counts, strict=True)
                }
            )
        for candidate in CANDIDATES:
            totals = np.zeros(4, dtype=float)
            for key, weight in weights.items():
                totals += weight * game_stats[candidate][key]
            observations, absolute, squared, crps = totals
            draws[candidate]["mae"].append(absolute / observations)
            draws[candidate]["rmse"].append(np.sqrt(squared / observations))
            draws[candidate]["mean_crps"].append(crps / observations)

    report = {}
    for candidate in ("B", "C"):
        metrics = {}
        for metric in ("mae", "rmse", "mean_crps"):
            differences = np.asarray(draws[candidate][metric]) - np.asarray(
                draws["A"][metric]
            )
            metrics[metric] = {
                "candidate_minus_v1": float(
                    _metric_summary(rows_by_candidate[candidate])[metric]
                    - _metric_summary(rows_by_candidate["A"])[metric]
                ),
                "interval_90": [
                    float(np.quantile(differences, 0.05)),
                    float(np.quantile(differences, 0.95)),
                ],
            }
        report[candidate] = metrics
    return {
        "replicates": CLUSTER_BOOTSTRAP_REPLICATES,
        "seed": CLUSTER_BOOTSTRAP_SEED,
        "unit": "evaluation game within chronological fold",
        "comparisons": report,
    }


def _game_metric_sufficient_statistics(
    rows: list[dict[str, Any]],
) -> dict[tuple[int, str], np.ndarray]:
    result: dict[tuple[int, str], np.ndarray] = {}
    for row in rows:
        key = (int(row["season"]), str(row["game_id"]))
        values = result.setdefault(key, np.zeros(4, dtype=float))
        error = float(row["error"])
        values += (1.0, abs(error), error**2, float(row["crps"]))
    return result


def _stress_state_report(base: ActionBaselineSet) -> list[dict[str, object]]:
    starts = (
        ("own_10", 90.0),
        ("own_25", 75.0),
        ("own_40", 60.0),
        ("midfield", 50.0),
        ("opponent_45", 45.0),
        ("opponent_35", 35.0),
        ("opponent_25", 25.0),
        ("opponent_15", 15.0),
    )
    output = []
    for label, yards_to_goal in starts:
        state = _stress_state(yards_to_goal)
        candidates = {}
        for candidate in CANDIDATES:
            model = PuntTransitionCandidateModel(base, candidate)
            distribution = model.transition_distribution("punt", state)
            support = distribution.support
            item: dict[str, object] = {
                "supported": support.in_support,
                "support_reason": support.reason,
                "observations": support.observation_count,
                "games": support.game_count,
            }
            if support.in_support:
                values = distribution.states["yards_to_goal"].to_numpy()
                rows = base._comparable_rows("punt", state)  # noqa: SLF001
                touchback = rows["is_touchback"].fill_null(False).to_numpy()
                diagnostics = model.punt_sample_diagnostics(state)
                item.update(
                    {
                        "mean": float(values.mean()),
                        "median": float(np.median(values)),
                        "p10": float(np.quantile(values, 0.10)),
                        "p90": float(np.quantile(values, 0.90)),
                        "p90_minus_p10": float(
                            np.quantile(values, 0.90) - np.quantile(values, 0.10)
                        ),
                        "invalid_mass": diagnostics.invalid_mass,
                        "legal_boundary_mass": diagnostics.boundary_mass,
                        "touchback_mass": diagnostics.touchback_mass,
                        "touchback_destination": _distribution(
                            values[touchback].tolist()
                        ),
                    }
                )
            candidates[candidate] = item
        output.append(
            {
                "label": label,
                "yards_to_goal": yards_to_goal,
                "candidates": candidates,
            }
        )
    return output


def _shape_sanity_report(base: ActionBaselineSet) -> dict[str, object]:
    report = {}
    for candidate in CANDIDATES:
        model = PuntTransitionCandidateModel(base, candidate)
        curve = []
        for yards_to_goal in range(21, 100):
            state = _stress_state(float(yards_to_goal))
            distribution = model.transition_distribution("punt", state)
            if not distribution.support.in_support:
                continue
            values = distribution.states["yards_to_goal"].to_numpy()
            curve.append(
                {
                    "yards_to_goal": yards_to_goal,
                    "cell": _field_zone(yards_to_goal),
                    "mean": float(values.mean()),
                    "p10": float(np.quantile(values, 0.10)),
                    "p90": float(np.quantile(values, 0.90)),
                }
            )
        adjacent = []
        for left, right in zip(curve, curve[1:], strict=False):
            if right["yards_to_goal"] != left["yards_to_goal"] + 1:
                continue
            adjacent.append(
                {
                    "from": left["yards_to_goal"],
                    "to": right["yards_to_goal"],
                    "crosses_cell": left["cell"] != right["cell"],
                    "mean_change": right["mean"] - left["mean"],
                }
            )
        largest = max(adjacent, key=lambda row: abs(float(row["mean_change"])))
        within = [row for row in adjacent if not row["crosses_cell"]]
        report[candidate] = {
            "curve": curve,
            "largest_adjacent_mean_jump": largest,
            "maximum_absolute_adjacent_mean_jump": abs(float(largest["mean_change"])),
            "maximum_within_cell_reversal": max(
                (max(float(row["mean_change"]), 0.0) for row in within), default=0.0
            ),
            "minimum_p90_minus_p10": min(
                float(row["p90"]) - float(row["p10"]) for row in curve
            ),
        }
    return report


def _candidate_invariants(base: ActionBaselineSet) -> dict[str, object]:
    report: dict[str, object] = {}
    for candidate in ("B", "C"):
        model = PuntTransitionCandidateModel(base, candidate)
        checks = []
        for yards_to_goal in (25.0, 45.0, 55.0, 75.0, 90.0):
            state = _stress_state(yards_to_goal)
            frozen = base.transition_distribution("punt", state)
            changed = model.transition_distribution("punt", state)
            rows = base._comparable_rows("punt", state)  # noqa: SLF001
            non_field = [
                column
                for column in frozen.states.columns
                if column not in {"yards_to_goal", "yards_to_go"}
            ]
            resets = rows["field_position_resets"].to_numpy()
            touchbacks = rows["is_touchback"].fill_null(False).to_numpy()
            changed_destinations = changed.states["yards_to_goal"].to_numpy()
            observed = rows["next_yards_to_goal"].to_numpy()
            checks.append(
                {
                    "yards_to_goal": yards_to_goal,
                    "bounds_pass": bool(
                        np.all(
                            (changed_destinations >= 1) & (changed_destinations <= 99)
                        )
                    ),
                    "non_field_sample_equality": frozen.states.select(non_field).equals(
                        changed.states.select(non_field)
                    ),
                    "scoring_restart_equality": bool(
                        np.array_equal(changed_destinations[resets], observed[resets])
                    ),
                    "touchback_destination_equality": bool(
                        np.array_equal(
                            changed_destinations[touchbacks], observed[touchbacks]
                        )
                    ),
                    "deterministic_repeat": changed.states.equals(
                        model.transition_distribution("punt", state).states
                    ),
                    "outcome_counts_equal": Counter(
                        frozen.states["factual_outcome"].to_list()
                    )
                    == Counter(changed.states["factual_outcome"].to_list()),
                    "game_clusters_equal": frozen.game_clusters
                    == changed.game_clusters,
                }
            )
        unchanged_actions = {}
        state = _stress_state(55.0)
        for action in ("go", "field_goal"):
            unchanged_actions[action] = base.transition_distribution(
                action, state
            ).states.equals(model.transition_distribution(action, state).states)
        report[candidate] = {
            "punt_checks": checks,
            "unchanged_non_punt_actions": unchanged_actions,
        }
    return report


def _stress_state(yards_to_goal: float) -> CanonicalState:
    return CanonicalState(
        evaluation_team="HOME",
        opponent_team="AWAY",
        is_home=True,
        score_differential=0.0,
        quarter=3,
        game_seconds_remaining=1500.0,
        yards_to_goal=yards_to_goal,
        down=4,
        yards_to_go=5.0,
        team_timeouts_remaining=3.0,
        opponent_timeouts_remaining=3.0,
        team_pregame_spread=0.0,
    )


def _support_summary(rows: list[dict[str, Any]]) -> dict[str, object]:
    count = len(rows)
    supported = [row for row in rows if row["supported"]]
    observations = [row["observations"] for row in supported]
    games = [row["games"] for row in supported]
    return {
        "queries": count,
        "available": sum(row["available"] for row in rows),
        "available_rate": float(np.mean([row["available"] for row in rows])),
        "supported": len(supported),
        "supported_rate": len(supported) / count,
        "unsupported": count - len(supported),
        "unsupported_rate": 1 - len(supported) / count,
        "sparse": sum(row["sparse"] for row in rows),
        "sparse_rate": float(np.mean([row["sparse"] for row in rows])),
        "effective_observations": _distribution(observations),
        "effective_games": _distribution(games),
    }


def _clipping_report(rows: list[dict[str, Any]]) -> dict[str, object]:
    supported = [row for row in rows if row["clipping_mass"] is not None]
    return {
        "overall": _clipping_summary(supported),
        "by_field_zone": _group_clipping(supported, "field_zone"),
        "by_position_band": _group_clipping(supported, "position_band"),
        "by_yards_to_go_band": _group_clipping(supported, "yards_to_go_band"),
        "by_time_regime": _group_clipping(supported, "time_regime"),
    }


def _boundary_report(rows: list[dict[str, Any]]) -> dict[str, object]:
    supported = [row for row in rows if row["boundary_mass"] is not None]
    return {
        "overall": _mass_summary(supported, "boundary_mass"),
        "by_field_zone": _group_mass(supported, "field_zone", "boundary_mass"),
        "by_position_band": _group_mass(supported, "position_band", "boundary_mass"),
    }


def _group_clipping(
    rows: list[dict[str, Any]], field: str
) -> dict[str, dict[str, object]]:
    values: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        values.setdefault(str(row[field]), []).append(row)
    return {key: _clipping_summary(group) for key, group in sorted(values.items())}


def _clipping_summary(rows: list[dict[str, Any]]) -> dict[str, object]:
    masses = [float(row["clipping_mass"]) for row in rows]
    names = ("any", "above_10_percent", "above_25_percent", "above_50_percent")
    return {
        "queries": len(rows),
        "thresholds": {
            name: {
                "count": sum(value > threshold for value in masses),
                "rate": float(np.mean([value > threshold for value in masses]))
                if masses
                else 0.0,
            }
            for name, threshold in zip(names, CLIPPING_THRESHOLDS, strict=True)
        },
        "mass_distribution": _distribution(masses),
    }


def _group_mass(
    rows: list[dict[str, Any]], group_field: str, value_field: str
) -> dict[str, dict[str, object]]:
    values: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        values.setdefault(str(row[group_field]), []).append(row)
    return {
        key: _mass_summary(group, value_field) for key, group in sorted(values.items())
    }


def _mass_summary(rows: list[dict[str, Any]], value_field: str) -> dict[str, object]:
    masses = [float(row[value_field]) for row in rows]
    return {
        "queries": len(rows),
        "positive": sum(value > 0 for value in masses),
        "positive_rate": float(np.mean([value > 0 for value in masses]))
        if masses
        else 0.0,
        "mass_distribution": _distribution(masses),
    }


def _mechanism_report(rows: pl.DataFrame) -> dict[str, object]:
    frame = rows.with_columns(
        (pl.col("yards_to_goal") + pl.col("decision_yards_to_goal_delta")).alias(
            "decision_team_destination"
        ),
        pl.col("next_yards_to_goal").alias("opponent_destination"),
        (-pl.col("decision_yards_to_goal_delta")).alias("net_field_movement"),
        _position_band_expression().alias("position_band"),
    )
    return {
        "training_punt_transitions": frame.height,
        "training_games": frame["game_id"].n_unique(),
        "destination_bounds": {
            "minimum": float(frame["opponent_destination"].min()),
            "maximum": float(frame["opponent_destination"].max()),
            "outside_1_99": frame.filter(
                ~pl.col("opponent_destination").is_between(1, 99)
            ).height,
        },
        "by_position_band": _position_relationship(frame),
        "by_v1_field_zone": _position_relationship(
            frame.with_columns(
                pl.col("yards_to_goal")
                .map_elements(_field_zone, return_dtype=pl.String)
                .alias("position_band")
            )
        ),
        "outcome_counts": dict(
            sorted(Counter(frame["factual_outcome"].to_list()).items())
        ),
    }


def _position_relationship(frame: pl.DataFrame) -> list[dict[str, object]]:
    return (
        frame.group_by("position_band")
        .agg(
            pl.len().alias("transitions"),
            pl.col("yards_to_goal").min().alias("start_min"),
            pl.col("yards_to_goal").max().alias("start_max"),
            pl.col("yards_to_goal").mean().alias("start_mean"),
            pl.col("opponent_destination").mean().alias("destination_mean"),
            pl.col("opponent_destination").median().alias("destination_median"),
            pl.col("opponent_destination").quantile(0.10).alias("destination_p10"),
            pl.col("opponent_destination").quantile(0.90).alias("destination_p90"),
            pl.col("net_field_movement").mean().alias("net_movement_mean"),
            pl.col("kick_distance").is_not_null().mean().alias("kick_distance_rate"),
            pl.col("kick_distance").mean().alias("kick_distance_mean"),
            pl.col("return_yards").is_not_null().mean().alias("return_yards_rate"),
            pl.col("return_yards").mean().alias("return_yards_mean"),
            pl.col("is_touchback").fill_null(False).mean().alias("touchback_rate"),
            pl.col("is_punt_blocked").fill_null(False).mean().alias("blocked_rate"),
        )
        .sort("start_mean", descending=True)
        .to_dicts()
    )


def _source_field_audit(
    training_rows: pl.DataFrame, raw: pl.DataFrame | None
) -> dict[str, object] | None:
    if raw is None:
        return None
    raw = raw.with_columns(pl.col("play_id").cast(pl.Int64, strict=True))
    joined = training_rows.select("season", "game_id", "play_id").join(
        raw, on=["season", "game_id", "play_id"], how="left", validate="1:1"
    )
    report: dict[str, object] = {"matched_transitions": joined.height}
    for column in RAW_PUNT_AUDIT_COLUMNS[3:]:
        available = joined[column].is_not_null()
        values = joined.filter(available)[column]
        item: dict[str, object] = {
            "non_null": int(available.sum()),
            "non_null_rate": float(available.mean()),
        }
        if column.startswith("punt_") or column in {"punt_attempt", "touchback"}:
            numeric = values.cast(pl.Float64, strict=False)
            item["invalid_binary"] = int((~numeric.is_in((0, 1))).sum())
            item["positive"] = int((numeric == 1).sum())
        report[column] = item

    ordinary = training_rows.filter(
        (pl.col("next_possession_team") != pl.col("possession_team"))
        & ~pl.col("field_position_resets")
        & pl.col("kick_distance").is_not_null()
    ).with_columns(
        (-pl.col("decision_yards_to_goal_delta")).alias("net_movement"),
        (pl.col("kick_distance") - pl.col("return_yards").fill_null(0)).alias(
            "kick_minus_return"
        ),
    )
    report["derived_consistency"] = {
        "observations": ordinary.height,
        "kick_distance_net_movement_correlation": float(
            ordinary.select(pl.corr("kick_distance", "net_movement")).item()
        ),
        "kick_minus_return_net_movement_correlation": float(
            ordinary.select(pl.corr("kick_minus_return", "net_movement")).item()
        ),
        "kick_minus_return_net_movement_mae": float(
            ordinary.select(
                (pl.col("kick_minus_return") - pl.col("net_movement")).abs().mean()
            ).item()
        ),
    }
    touchbacks = training_rows.filter(pl.col("is_touchback").fill_null(False))
    report["touchback_destinations_by_season"] = (
        touchbacks.group_by("season")
        .agg(
            pl.len().alias("touchbacks"),
            pl.col("next_yards_to_goal").min().alias("minimum"),
            pl.col("next_yards_to_goal").median().alias("median"),
            pl.col("next_yards_to_goal").max().alias("maximum"),
            (pl.col("next_yards_to_goal") == 80).mean().alias("at_opponent_20_rate"),
        )
        .sort("season")
        .to_dicts()
    )
    return report


def _candidate_cell_feasibility(candidates: pl.DataFrame) -> list[dict[str, object]]:
    punts = candidates.filter(
        (pl.col("disposition") == "eligible")
        & (pl.col("actual_action") == "punt")
        & (pl.col("next_state_status") == "reconstructed")
        & pl.col("next_yards_to_goal").is_not_null()
    ).with_columns(_position_band_expression().alias("position_band"))
    return (
        punts.group_by("season", "position_band")
        .agg(pl.len().alias("punts"), pl.col("game_id").n_unique().alias("games"))
        .sort("season", "position_band")
        .to_dicts()
    )


def _empirical_crps(samples: np.ndarray, target: float) -> float:
    ordered = np.sort(np.asarray(samples, dtype=float))
    n = len(ordered)
    indexes = np.arange(1, n + 1)
    pairwise = 2.0 * np.sum((2 * indexes - n - 1) * ordered) / (n * n)
    return float(np.mean(np.abs(ordered - target)) - 0.5 * pairwise)


def _distribution(values: list[float] | list[int]) -> dict[str, float | int | None]:
    if not values:
        return {
            "observations": 0,
            "minimum": None,
            "median": None,
            "p90": None,
            "maximum": None,
        }
    array = np.asarray(values, dtype=float)
    return {
        "observations": len(values),
        "minimum": float(array.min()),
        "median": float(np.median(array)),
        "p90": float(np.quantile(array, 0.90)),
        "maximum": float(array.max()),
    }


def _field_zone(yards_to_goal: float) -> str:
    if yards_to_goal <= 20:
        return "opponent_red_zone"
    if yards_to_goal <= 49:
        return "opponent_21_49"
    if yards_to_goal <= 79:
        return "own_21_to_midfield"
    return "own_1_20"


def _position_band(yards_to_goal: float) -> str:
    if yards_to_goal <= 20:
        return "opponent_red_zone"
    if yards_to_goal <= 34:
        return "opponent_34_21"
    if yards_to_goal <= 49:
        return "opponent_49_35"
    if yards_to_goal <= 59:
        return "own_41_to_midfield"
    if yards_to_goal <= 79:
        return "own_21_40"
    return "own_1_20"


def _position_band_expression() -> pl.Expr:
    return (
        pl.when(pl.col("yards_to_goal") <= 20)
        .then(pl.lit("opponent_red_zone"))
        .when(pl.col("yards_to_goal") <= 34)
        .then(pl.lit("opponent_34_21"))
        .when(pl.col("yards_to_goal") <= 49)
        .then(pl.lit("opponent_49_35"))
        .when(pl.col("yards_to_goal") <= 59)
        .then(pl.lit("own_41_to_midfield"))
        .when(pl.col("yards_to_goal") <= 79)
        .then(pl.lit("own_21_40"))
        .otherwise(pl.lit("own_1_20"))
    )


def _yards_to_go_band(value: float) -> str:
    if value <= 2:
        return "1_2"
    if value <= 5:
        return "3_5"
    if value <= 10:
        return "6_10"
    return "11_plus"


def _time_regime(quarter: int, seconds: float) -> str:
    if quarter == 4 and seconds <= 120:
        return "q4_final_two_minutes"
    if quarter == 4 and seconds <= 300:
        return "q4_two_to_five_minutes"
    return "other_regulation"


__all__ = [
    "CANDIDATES",
    "PUNT_EVALUATION_SEASONS",
    "PUNT_STUDY_SEASONS",
    "PuntTransitionCandidateModel",
    "RAW_PUNT_AUDIT_COLUMNS",
    "compare_punt_candidates",
    "diagnose_punt_v1",
    "evaluate_punt_decision_sensitivity",
    "select_raw_punt_audit_fields",
    "validate_punt_study_seasons",
]
