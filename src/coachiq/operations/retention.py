"""Immutable, week-scoped source retention for prospective correction diffs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import polars as pl

from coachiq.operations.shadow import SourceManifest

SOURCE_SNAPSHOT_FORMAT = "coachiq-week-source-v1"


def retain_week_source_snapshot(
    output_dir: Path,
    schedule: pl.DataFrame,
    raw_pbp: pl.DataFrame | None,
    manifest: SourceManifest,
) -> Path:
    """Retain exact week rows in a content-addressed, immutable directory."""

    identity = {
        "format": SOURCE_SNAPSHOT_FORMAT,
        "season": manifest.season,
        "week": manifest.week,
        "schedule_fingerprint": manifest.schedule_fingerprint,
        "pbp_fingerprint": manifest.pbp_fingerprint,
    }
    snapshot_id = hashlib.sha256(_json_bytes(identity)).hexdigest()
    snapshot_dir = output_dir / "source-snapshots" / snapshot_id
    manifest_path = snapshot_dir / "manifest.json"

    if manifest_path.exists():
        _validate_existing_snapshot(manifest_path, identity)
        return snapshot_dir

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    selected_schedule = _select_week(schedule, manifest.season, manifest.week)
    schedule_path = snapshot_dir / "schedule.parquet"
    schedule_hash = _write_or_validate_parquet(schedule_path, selected_schedule)

    selected_pbp = _select_week(raw_pbp, manifest.season, manifest.week)
    games = []
    if selected_pbp is not None:
        games_dir = snapshot_dir / "games"
        games_dir.mkdir(exist_ok=True)
        for game_id in manifest.observed_game_ids:
            game_rows = selected_pbp.filter(pl.col("game_id") == game_id)
            relative_path = Path("games") / f"{game_id}.parquet"
            artifact_hash = _write_or_validate_parquet(
                snapshot_dir / relative_path, game_rows
            )
            games.append(
                {
                    "artifact_path": relative_path.as_posix(),
                    "artifact_sha256": artifact_hash,
                    "game_id": game_id,
                    "raw_rows": game_rows.height,
                    "source_fingerprint": manifest.per_game_fingerprints[game_id],
                }
            )

    payload = {
        **identity,
        "snapshot_id": snapshot_id,
        "retrieved_at_utc": manifest.retrieved_at_utc,
        "schedule": {
            "artifact_path": "schedule.parquet",
            "artifact_sha256": schedule_hash,
            "rows": selected_schedule.height,
            "source_fingerprint": manifest.schedule_fingerprint,
        },
        "games": games,
    }
    manifest_path.write_bytes(_json_bytes(payload))
    return snapshot_dir


def _select_week(
    frame: pl.DataFrame | None, season: int, week: int
) -> pl.DataFrame | None:
    if frame is None:
        return None
    return frame.filter((pl.col("season") == season) & (pl.col("week") == week))


def _write_or_validate_parquet(path: Path, frame: pl.DataFrame) -> str:
    if not path.exists():
        frame.write_parquet(path, compression="zstd", statistics=True)
    artifact_hash = _file_sha256(path)
    if pl.read_parquet(path).equals(frame, null_equal=True):
        return artifact_hash
    raise RuntimeError(f"immutable source artifact differs from requested rows: {path}")


def _validate_existing_snapshot(path: Path, identity: dict[str, Any]) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for field, expected in identity.items():
        if payload.get(field) != expected:
            raise RuntimeError(f"immutable source snapshot identity mismatch: {field}")
    snapshot_dir = path.parent
    artifacts = [payload["schedule"], *payload["games"]]
    for artifact in artifacts:
        artifact_path = snapshot_dir / artifact["artifact_path"]
        if not artifact_path.is_file():
            raise RuntimeError(f"immutable source artifact is missing: {artifact_path}")
        if _file_sha256(artifact_path) != artifact["artifact_sha256"]:
            raise RuntimeError(
                f"immutable source artifact hash mismatch: {artifact_path}"
            )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()


__all__ = ["SOURCE_SNAPSHOT_FORMAT", "retain_week_source_snapshot"]
