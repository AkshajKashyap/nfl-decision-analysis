"""Run the explicit one-time CoachIQ 2025 holdout evaluation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import polars as pl

from coachiq.analysis.holdout import (
    HISTORICAL_SEASONS,
    HOLDOUT_SEASON,
    evaluate_2025_holdout,
    frozen_artifact_identity,
)
from coachiq.data import build_manifest, load_pbp, normalize_pbp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parquet-dir",
        type=Path,
        help="Directory containing play_by_play_2014.parquet through 2025.",
    )
    parser.add_argument(
        "--historical-decision-report",
        type=Path,
        required=True,
        help="Frozen 2014-2024 coachiq-decision-v1 diagnostic JSON.",
    )
    parser.add_argument(
        "--holdout-parquet",
        type=Path,
        help=(
            "Explicit raw 2025 snapshot; historical seasons use --parquet-dir "
            "or nflreadpy."
        ),
    )
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument(
        "--snapshot-2025",
        type=Path,
        help="Optional explicit destination for the raw 2025 parquet snapshot.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    # Abort before any data access if the preregistration or frozen stack moved.
    frozen_artifact_identity(project_root)
    historical_report = json.loads(
        args.historical_decision_report.read_text(encoding="utf-8")
    )
    normalized: dict[int, pl.DataFrame] = {}
    sources: dict[str, object] = {}
    for season in (*HISTORICAL_SEASONS, HOLDOUT_SEASON):
        raw, path = _load_raw(season, args.parquet_dir, args.holdout_parquet)
        if season == HOLDOUT_SEASON and args.snapshot_2025:
            args.snapshot_2025.parent.mkdir(parents=True, exist_ok=True)
            raw.write_parquet(args.snapshot_2025)
            path = args.snapshot_2025
        manifest = build_manifest(raw, [season]).to_dict()
        manifest.pop("retrieved_at_utc", None)
        sources[str(season)] = {
            **manifest,
            "snapshot_path": str(path) if path else None,
            "snapshot_sha256": _sha256(path) if path else None,
        }
        normalized[season] = normalize_pbp(raw)
        print(
            f"loaded {season}: {raw.height:,} raw / "
            f"{normalized[season].height:,} normalized rows"
        )
    historical = pl.concat([normalized[year] for year in HISTORICAL_SEASONS]).sort(
        ["season", "game_id", "play_id", "play_sequence"], nulls_last=True
    )
    report = evaluate_2025_holdout(
        historical,
        normalized[HOLDOUT_SEASON],
        historical_report,
        project_root=project_root,
        progress=print,
    )
    report["data_sources"] = sources
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"holdout status: {report['acceptance']['status']}")
    print(f"machine-readable holdout report: {args.json_output}")


def _load_raw(
    season: int, parquet_dir: Path | None, holdout_parquet: Path | None
) -> tuple[pl.DataFrame, Path | None]:
    if season == HOLDOUT_SEASON and holdout_parquet is not None:
        if not holdout_parquet.exists():
            raise SystemExit(f"missing holdout snapshot: {holdout_parquet}")
        return pl.read_parquet(holdout_parquet), holdout_parquet
    if parquet_dir is None:
        return load_pbp([season]), None
    path = parquet_dir / f"play_by_play_{season}.parquet"
    if not path.exists():
        raise SystemExit(f"missing snapshot: {path}")
    return pl.read_parquet(path), path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
