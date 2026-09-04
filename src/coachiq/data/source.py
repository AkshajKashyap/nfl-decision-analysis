"""Small, explicit nflreadpy boundary for raw play-by-play loading."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from numbers import Integral
from pathlib import Path
from typing import Any

import polars as pl

FIRST_NFLVERSE_PBP_SEASON = 1999


class SeasonValidationError(ValueError):
    """Raised when a requested season cannot be a supported nflverse season."""


class PbpLoadError(RuntimeError):
    """Raised when nflreadpy cannot provide a requested season."""


@dataclass(frozen=True)
class PbpManifest:
    """In-memory audit record for one raw retrieval; writing is caller controlled."""

    requested_seasons: tuple[int, ...]
    observed_seasons: tuple[int, ...]
    retrieved_at_utc: str
    raw_row_count: int
    raw_column_count: int
    raw_schema: dict[str, str]
    nflreadpy_version: str | None
    resolved_assets: tuple[str, ...]
    coachiq_revision: str | None
    coachiq_worktree_dirty: bool | None
    source: str = "nflreadpy"

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable manifest data."""

        return asdict(self)


def validate_seasons(seasons: Sequence[int]) -> tuple[int, ...]:
    """Validate and canonicalize requested seasons without touching the network."""

    if isinstance(seasons, (str, bytes)) or not isinstance(seasons, Sequence):
        raise SeasonValidationError(
            "seasons must be a non-empty sequence of integer years"
        )
    if not seasons:
        raise SeasonValidationError("seasons must contain at least one season")

    current_year = datetime.now(tz=UTC).year
    normalized: set[int] = set()
    for season in seasons:
        if isinstance(season, bool) or not isinstance(season, Integral):
            raise SeasonValidationError(
                f"season values must be integer years; received {season!r}"
            )
        value = int(season)
        if value < FIRST_NFLVERSE_PBP_SEASON or value > current_year:
            raise SeasonValidationError(
                "season must be between "
                f"{FIRST_NFLVERSE_PBP_SEASON} and {current_year}; received {value}"
            )
        normalized.add(value)
    return tuple(sorted(normalized))


def load_pbp(seasons: Sequence[int]) -> pl.DataFrame:
    """Load requested nflverse PBP seasons through nflreadpy in stable row order."""

    requested = validate_seasons(seasons)
    try:
        raw = _load_from_nflreadpy(requested)
    except Exception as error:
        if isinstance(error, PbpLoadError):
            raise
        requested_text = ", ".join(map(str, requested))
        raise PbpLoadError(
            "Unable to load nflverse PBP for season(s) "
            f"{requested_text}. Check nflreadpy availability and the source release."
        ) from error

    if not isinstance(raw, pl.DataFrame):
        raise PbpLoadError(
            "nflreadpy.load_pbp() did not return a Polars DataFrame; "
            f"received {type(raw).__name__}"
        )

    sort_columns = [
        column
        for column in ("season", "game_id", "play_id", "order_sequence")
        if column in raw
    ]
    return raw.sort(sort_columns, nulls_last=True) if sort_columns else raw


def build_manifest(raw: pl.DataFrame, seasons: Sequence[int]) -> PbpManifest:
    """Build a manifest for a retrieval without writing data or cache files."""

    requested = validate_seasons(seasons)
    observed_seasons: tuple[int, ...] = ()
    if "season" in raw.columns:
        observed_seasons = tuple(
            sorted(
                int(value)
                for value in raw.get_column("season").drop_nulls().unique().to_list()
            )
        )
    return PbpManifest(
        requested_seasons=requested,
        observed_seasons=observed_seasons,
        retrieved_at_utc=datetime.now(tz=UTC).isoformat(),
        raw_row_count=raw.height,
        raw_column_count=raw.width,
        raw_schema={name: str(dtype) for name, dtype in raw.schema.items()},
        nflreadpy_version=_package_version("nflreadpy"),
        resolved_assets=tuple(f"play_by_play_{season}.parquet" for season in requested),
        coachiq_revision=_current_revision(),
        coachiq_worktree_dirty=_is_worktree_dirty(),
    )


def write_manifest(manifest: PbpManifest, path: str | Path) -> None:
    """Write a manifest only to an explicit caller-selected path."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_from_nflreadpy(seasons: tuple[int, ...]) -> pl.DataFrame:
    """Import lazily so unit tests and schema work do not need the network."""

    try:
        import nflreadpy as nfl
    except ImportError as error:  # pragma: no cover - packaging failure path
        raise PbpLoadError(
            "nflreadpy is required to load raw PBP. Install CoachIQ with its "
            "runtime dependencies."
        ) from error
    return nfl.load_pbp(list(seasons))


def _package_version(package: str) -> str | None:
    try:
        return version(package)
    except PackageNotFoundError:  # pragma: no cover - packaging failure path
        return None


def _current_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_project_root(),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        return None
    return completed.stdout.strip() or None


def _is_worktree_dirty() -> bool | None:
    try:
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=_project_root(),
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        return None
    return bool(completed.stdout.strip())


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]
