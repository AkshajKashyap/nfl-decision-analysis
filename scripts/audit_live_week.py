"""Run the frozen CoachIQ stack on one completed 2026 week in shadow mode."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import polars as pl

from coachiq.data import normalize_pbp
from coachiq.operations import (
    ShadowOperationalReport,
    SourceManifest,
    build_shadow_brief,
    compare_source_manifests,
    finalize_operational_evidence,
    run_shadow_week,
    validate_live_shadow_request,
)
from coachiq.product import fit_frozen_models, stable_json_dumps

TRAINING_SEASONS = tuple(range(2014, 2025))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--training-parquet-dir",
        type=Path,
        help="Explicit 2014-2024 snapshots; required once final games exist.",
    )
    parser.add_argument("--schedule-parquet", type=Path)
    parser.add_argument("--pbp-parquet", type=Path)
    parser.add_argument("--source-retrieved-at-utc")
    parser.add_argument(
        "--accept-source-correction",
        action="store_true",
        help="Explicitly preserve and replace output after a detected correction.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate_live_shadow_request(args.season, args.week)
    started = perf_counter()
    schedule, schedule_source, retrieved = _load_schedule(args)
    selected_schedule = schedule.filter(
        (pl.col("season") == args.season) & (pl.col("week") == args.week)
    )
    final_count = selected_schedule.filter(
        pl.all_horizontal(
            pl.col("away_score").is_not_null(),
            pl.col("home_score").is_not_null(),
            pl.col("result").is_not_null(),
        )
    ).height
    raw_pbp: pl.DataFrame | None = None
    pbp_source: str | None = None
    source_error: str | None = None
    if final_count:
        try:
            raw_pbp, pbp_source = _load_pbp(args)
        except Exception as error:
            source_error = f"{type(error).__name__}: {error}"
            pbp_source = f"unavailable ({source_error})"
    source_loaded_at = perf_counter()

    models = None
    fit_seconds = 0.0
    if final_count and raw_pbp is not None:
        if args.training_parquet_dir is None:
            raise SystemExit("--training-parquet-dir is required for final games")
        fit_started = perf_counter()
        historical = _load_training(args.training_parquet_dir)
        models = fit_frozen_models(
            historical, project_root=Path(__file__).resolve().parents[1]
        )
        fit_seconds = perf_counter() - fit_started

    first_audit_started = perf_counter()
    first, first_weekly = run_shadow_week(
        schedule,
        raw_pbp,
        models,
        season=args.season,
        week=args.week,
        retrieved_at_utc=retrieved,
        schedule_source=schedule_source,
        pbp_source=pbp_source,
    )
    first_audit_seconds = perf_counter() - first_audit_started
    rerun_started = perf_counter()
    second, second_weekly = run_shadow_week(
        schedule,
        raw_pbp,
        models,
        season=args.season,
        week=args.week,
        retrieved_at_utc=retrieved,
        schedule_source=schedule_source,
        pbp_source=pbp_source,
    )
    rerun_seconds = perf_counter() - rerun_started
    weekly_matches = (
        first_weekly is None
        and second_weekly is None
        or first_weekly is not None
        and second_weekly is not None
        and stable_json_dumps(first_weekly) == stable_json_dumps(second_weekly)
    )
    determinism_verified = (
        weekly_matches
        and first == second
        and first.source_manifest == second.source_manifest
    )
    correction_verified = _correction_self_check(first.source_manifest)
    readiness_runtime = (source_loaded_at - started) + fit_seconds + first_audit_seconds
    report = finalize_operational_evidence(
        first,
        determinism_verified=determinism_verified,
        correction_detection_verified=correction_verified,
        runtime_seconds=readiness_runtime,
    )
    weekly = first_weekly
    if source_error:
        report = replace(
            report,
            readiness_reasons=(
                *report.readiness_reasons,
                f"pbp_source_load_failed:{source_error}",
            ),
        )
    export_started = perf_counter()
    report = _write_outputs(args, report, report.source_manifest, weekly)
    exported_at = perf_counter()
    metrics = {
        "source_loading_seconds": source_loaded_at - started,
        "frozen_component_fit_seconds": fit_seconds,
        "validation_normalization_scoring_publication_seconds": first_audit_seconds,
        "deterministic_rerun_seconds": rerun_seconds,
        "readiness_workflow_seconds_before_export": readiness_runtime,
        "export_seconds": exported_at - export_started,
        "total_seconds": exported_at - started,
        "scoring_runtime_available": weekly is not None,
    }
    (args.output_dir / "run-metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"readiness: {report.readiness_status}")
    print(f"final games: {report.games_final}")
    print(f"operational summary: {args.output_dir / 'operational-summary.json'}")
    print(f"runtime seconds: {metrics['total_seconds']:.3f}")


def _load_schedule(args: argparse.Namespace) -> tuple[pl.DataFrame, str, str]:
    if args.schedule_parquet is not None:
        if not args.schedule_parquet.exists():
            raise SystemExit(f"missing schedule snapshot: {args.schedule_parquet}")
        retrieved = (
            args.source_retrieved_at_utc
            or datetime.fromtimestamp(
                args.schedule_parquet.stat().st_mtime, tz=UTC
            ).isoformat()
        )
        return (
            pl.read_parquet(args.schedule_parquet),
            str(args.schedule_parquet),
            retrieved,
        )
    import nflreadpy as nfl

    return (
        nfl.load_schedules([args.season]),
        "nflreadpy.load_schedules",
        args.source_retrieved_at_utc or datetime.now(tz=UTC).isoformat(),
    )


def _load_pbp(args: argparse.Namespace) -> tuple[pl.DataFrame, str]:
    if args.pbp_parquet is not None:
        if not args.pbp_parquet.exists():
            raise FileNotFoundError(f"missing PBP snapshot: {args.pbp_parquet}")
        return pl.read_parquet(args.pbp_parquet), str(args.pbp_parquet)
    import nflreadpy as nfl

    return nfl.load_pbp([args.season]), "nflreadpy.load_pbp"


def _load_training(directory: Path) -> pl.DataFrame:
    normalized = []
    for season in TRAINING_SEASONS:
        path = directory / f"play_by_play_{season}.parquet"
        if not path.exists():
            raise SystemExit(f"missing frozen training snapshot: {path}")
        normalized.append(normalize_pbp(pl.read_parquet(path)))
    return pl.concat(normalized).sort(
        ["season", "game_id", "play_id", "play_sequence"], nulls_last=True
    )


def _correction_self_check(manifest: SourceManifest) -> bool:
    if manifest.per_game_fingerprints:
        game_id = sorted(manifest.per_game_fingerprints)[0]
        changed_hashes = {
            **manifest.per_game_fingerprints,
            game_id: "controlled-change",
        }
        changed = replace(
            manifest,
            pbp_fingerprint="controlled-change",
            per_game_fingerprints=changed_hashes,
        )
        result = compare_source_manifests(manifest, changed)
        all_game_ids = set(manifest.per_game_schedule_fingerprints) | set(
            manifest.per_game_fingerprints
        )
        return result.changed_game_ids == (game_id,) and set(
            result.unchanged_game_ids
        ) == all_game_ids - {game_id}
    return True


def _write_outputs(
    args: argparse.Namespace,
    operational_report: ShadowOperationalReport,
    manifest: SourceManifest,
    weekly: Any,
) -> ShadowOperationalReport:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output_dir / "source-manifest.json"
    current_manifest = _load_existing_manifest(manifest_path)
    if current_manifest is not None:
        correction = compare_source_manifests(current_manifest, manifest)
        if correction.source_changed and not args.accept_source_correction:
            (args.output_dir / "source-manifest.candidate.json").write_text(
                _json(manifest.to_dict()), encoding="utf-8"
            )
            (args.output_dir / "correction-report.json").write_text(
                _json(correction.to_dict()), encoding="utf-8"
            )
            raise SystemExit(
                "source correction detected; inspect and rerun with "
                "--accept-source-correction"
            )
        if correction.source_changed:
            operational_report = replace(
                operational_report,
                source_correction_events=1,
            )
            (args.output_dir / "source-manifest.previous.json").write_text(
                manifest_path.read_text(encoding="utf-8"), encoding="utf-8"
            )
            for name in ("hashes.json", "operational-summary.json"):
                old_path = args.output_dir / name
                if old_path.exists():
                    (
                        args.output_dir / f"{old_path.stem}.previous{old_path.suffix}"
                    ).write_text(old_path.read_text(encoding="utf-8"), encoding="utf-8")
            (args.output_dir / "correction-report.json").write_text(
                _json(correction.to_dict()), encoding="utf-8"
            )
    deterministic: dict[str, str] = {
        "source-manifest.json": _json(manifest.to_dict()),
        "operational-summary.json": _json(operational_report.to_dict()),
        "shadow-brief.md": build_shadow_brief(operational_report),
    }
    if weekly is not None:
        deterministic["weekly-report.json"] = stable_json_dumps(weekly)
        for game in weekly.games:
            deterministic[f"game-{game.game_id}.json"] = _json(game.to_dict())
    for name, content in deterministic.items():
        (args.output_dir / name).write_text(content, encoding="utf-8")
    hashes = {
        name: hashlib.sha256(content.encode()).hexdigest()
        for name, content in sorted(deterministic.items())
    }
    (args.output_dir / "hashes.json").write_text(_json(hashes), encoding="utf-8")
    return operational_report


def _load_existing_manifest(path: Path) -> SourceManifest | None:
    if not path.exists():
        return None
    return SourceManifest(**json.loads(path.read_text(encoding="utf-8")))


def _json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"


if __name__ == "__main__":
    main()
