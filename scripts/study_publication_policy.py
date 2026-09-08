"""Run the preregistered 2020-2025 CoachIQ publication-policy sensitivity."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import polars as pl

from coachiq.analysis.fourth_down import extract_fourth_down_candidates
from coachiq.data import normalize_pbp
from coachiq.product import (
    PUBLICATION_POLICY_V1,
    PublicationPolicy,
    SourceMetadata,
    apply_publication_policy,
    evaluate_candidate,
    fit_chronological_models,
    publication_record_from_evaluation,
    validate_policy_development_boundary,
)

EVALUATION_SEASONS = tuple(range(2020, 2026))
REQUIRED_SEASONS = tuple(range(2014, 2026))
FIELD_CLIPPING_CANDIDATES = (0.05, 0.10, 0.25)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        required=True,
        help="Directory containing explicit 2014-2025 nflverse parquet snapshots.",
    )
    parser.add_argument("--json-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_policy_development_boundary(REQUIRED_SEASONS)
    started = perf_counter()
    project_root = Path(__file__).resolve().parents[1]
    normalized: dict[int, pl.DataFrame] = {}
    sources: dict[int, SourceMetadata] = {}
    for season in REQUIRED_SEASONS:
        path = args.parquet_dir / f"play_by_play_{season}.parquet"
        if not path.exists():
            raise SystemExit(f"missing explicit snapshot: {path}")
        raw = pl.read_parquet(path)
        normalized[season] = normalize_pbp(raw)
        sources[season] = SourceMetadata(
            source="explicit nflverse parquet snapshot",
            retrieved_at_utc=datetime.fromtimestamp(
                path.stat().st_mtime, tz=UTC
            ).isoformat(),
            seasons=(season,),
            weeks=tuple(
                sorted(int(value) for value in normalized[season]["week"].unique())
            ),
            row_count=raw.height,
            sha256=_sha256(path),
            resolved_assets=(path.name,),
        )
        print(
            f"loaded {season}: {raw.height:,} raw / "
            f"{normalized[season].height:,} normalized rows"
        )
    loaded_at = perf_counter()

    policies = {
        threshold: PublicationPolicy(
            maximum_field_clipping_mass=threshold,
            maximum_clock_clipping_mass=(
                PUBLICATION_POLICY_V1.maximum_clock_clipping_mass
            ),
            version=f"publication-field-clip-candidate-{threshold:.0%}",
        )
        for threshold in FIELD_CLIPPING_CANDIDATES
    }
    sensitivity_rows: dict[float, list[dict[str, Any]]] = {
        threshold: [] for threshold in FIELD_CLIPPING_CANDIDATES
    }
    fold_rows: dict[int, dict[float, list[dict[str, Any]]]] = {}
    representatives: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
    fold_runtimes: list[dict[str, float | int]] = []

    for season in EVALUATION_SEASONS:
        fold_started = perf_counter()
        training = pl.concat([normalized[value] for value in range(2014, season)]).sort(
            ["season", "game_id", "play_id", "play_sequence"], nulls_last=True
        )
        models = fit_chronological_models(training, project_root=project_root)
        fitted_at = perf_counter()
        candidates = extract_fourth_down_candidates(normalized[season]).filter(
            pl.col("disposition") == "eligible"
        )
        season_rows = {threshold: [] for threshold in FIELD_CLIPPING_CANDIDATES}
        for row in candidates.iter_rows(named=True):
            evaluation = evaluate_candidate(row, models)
            for threshold, policy in policies.items():
                publication = apply_publication_policy(
                    evaluation.audit, evaluation.diagnostics, policy
                )
                summary = _sensitivity_row(evaluation, publication)
                sensitivity_rows[threshold].append(summary)
                season_rows[threshold].append(summary)
            if season >= 2024:
                record = publication_record_from_evaluation(
                    row,
                    models,
                    evaluation,
                    PUBLICATION_POLICY_V1,
                    source=sources[season],
                ).to_dict()
                _consider_representatives(representatives, record)
        fold_rows[season] = season_rows
        completed_at = perf_counter()
        fold_runtimes.append(
            {
                "season": season,
                "fit_seconds": fitted_at - fold_started,
                "score_seconds": completed_at - fitted_at,
                "eligible_decisions": candidates.height,
            }
        )
        print(
            f"completed {season}: {candidates.height:,} decisions; "
            f"fit={fitted_at - fold_started:.3f}s, "
            f"score={completed_at - fitted_at:.3f}s"
        )

    completed_at = perf_counter()
    selected = PUBLICATION_POLICY_V1.maximum_field_clipping_mass
    report = {
        "protocol": {
            "purpose": "publication-policy-v1 historical sensitivity",
            "evaluation_seasons": list(EVALUATION_SEASONS),
            "chronological_training": "2014 through season-1",
            "field_clipping_candidates": list(FIELD_CLIPPING_CANDIDATES),
            "selected_field_clipping_limit": selected,
            "clock_clipping_limit": (PUBLICATION_POLICY_V1.maximum_clock_clipping_mass),
            "selection_rule": (
                "exclude the known heavy-clipping model-form regime without "
                "selecting a threshold to maximize publication volume"
            ),
            "latest_accessed_season": max(REQUIRED_SEASONS),
            "accessed_2026": False,
        },
        "selected_policy": asdict(PUBLICATION_POLICY_V1),
        "pooled_sensitivity": {
            f"{threshold:.0%}": _sensitivity_report(rows)
            for threshold, rows in sensitivity_rows.items()
        },
        "season_sensitivity": {
            str(season): {
                f"{threshold:.0%}": _sensitivity_report(rows)
                for threshold, rows in thresholds.items()
            }
            for season, thresholds in fold_rows.items()
        },
        "representative_2024_2025_cases": {
            name: value[1] for name, value in sorted(representatives.items())
        },
        "data_sources": {
            str(season): source.to_dict() for season, source in sources.items()
        },
        "runtime": {
            "load_normalize_seconds": loaded_at - started,
            "folds": fold_runtimes,
            "total_seconds": completed_at - started,
        },
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"publication-policy study: {args.json_output}")
    print(f"total runtime: {completed_at - started:.3f}s")


def _sensitivity_row(evaluation: Any, publication: Any) -> dict[str, Any]:
    audit = evaluation.audit
    diagnostics = evaluation.diagnostics
    return {
        "classification": audit.classification,
        "publication_status": publication.status,
        "publishable": publication.publishable,
        "withholding_reasons": publication.withholding_reasons,
        "actual_action_modeled_gap": audit.raw_action_value_gap,
        "maximum_field_clipping_mass": diagnostics.maximum_field_clipping_mass,
        "maximum_clock_clipping_mass": diagnostics.maximum_clock_clipping_mass,
        "supported_action_count": audit.supported_action_count,
        "sparse_supported_action": diagnostics.sparse_supported_action,
        "unsupported_available_action": diagnostics.unsupported_available_action,
        "actual_action_supported": diagnostics.actual_action_supported,
    }


def _sensitivity_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    clear = [row for row in rows if row["classification"] == "clear_model_preference"]
    publishable = [row for row in rows if row["publishable"]]
    statuses = Counter(
        row["publication_status"] for row in rows if not row["publishable"]
    )
    reasons = Counter(reason for row in rows for reason in row["withholding_reasons"])
    support_profiles = Counter(_support_profile(row) for row in publishable)
    return {
        "eligible_decisions": total,
        "clear_model_preferences": len(clear),
        "publishable_decisions": len(publishable),
        "eligible_publishable_rate": len(publishable) / total if total else 0.0,
        "clear_preference_publishable_rate": (
            len(publishable) / len(clear) if clear else 0.0
        ),
        "withheld_by_primary_status": dict(sorted(statuses.items())),
        "withheld_by_reason": dict(sorted(reasons.items())),
        "publishable_gap_distribution": _distribution(
            [
                float(row["actual_action_modeled_gap"])
                for row in publishable
                if row["actual_action_modeled_gap"] is not None
            ]
        ),
        "publishable_field_clipping_distribution": _distribution(
            [float(row["maximum_field_clipping_mass"]) for row in publishable]
        ),
        "publishable_clock_clipping_distribution": _distribution(
            [float(row["maximum_clock_clipping_mass"]) for row in publishable]
        ),
        "publishable_support_distribution": dict(sorted(support_profiles.items())),
    }


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "observations": 0,
            "minimum": None,
            "median": None,
            "p90": None,
            "maximum": None,
        }
    array = np.asarray(values)
    return {
        "observations": len(values),
        "minimum": float(array.min()),
        "median": float(np.quantile(array, 0.50)),
        "p90": float(np.quantile(array, 0.90)),
        "maximum": float(array.max()),
    }


def _support_profile(row: dict[str, Any]) -> str:
    return (
        f"{row['supported_action_count']}_supported;"
        f"sparse={str(row['sparse_supported_action']).lower()};"
        f"unsupported_available={str(row['unsupported_available_action']).lower()}"
    )


def _consider_representatives(
    selected: dict[str, tuple[tuple[Any, ...], dict[str, Any]]],
    record: dict[str, Any],
) -> None:
    publication = record["publication"]
    comparison = record["comparison"]
    safety = record["safety_diagnostics"]
    reasons = set(publication["withholding_reasons"])
    labels = []
    if publication["publishable"]:
        labels.append("publication_safe_clear_preference")
    if (
        comparison["decision_v1_classification"] == "clear_model_preference"
        and "field_clipping_mass_above_policy" in reasons
    ):
        labels.append("clear_preference_withheld_for_clipping")
    if "decision_v1_close_call" in reasons:
        labels.append("close_call_withheld")
    if "supported_action_sparse" in reasons:
        labels.append("sparse_support_withheld")
    if "overtime_boundary_mass_nonzero" in reasons:
        labels.append("overtime_risk_withheld")
    if reasons & {"actual_action_unsupported", "available_action_unsupported"}:
        labels.append("unsupported_comparison_withheld")
    gap = float(comparison["actual_action_modeled_gap"] or 0.0)
    clipping = float(safety["maximum_field_clipping_mass"])
    identity = record["identity"]
    key = (gap, clipping, -int(identity["season"]), str(identity["game_id"]))
    for label in labels:
        if label not in selected or key > selected[label][0]:
            selected[label] = (key, record)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
