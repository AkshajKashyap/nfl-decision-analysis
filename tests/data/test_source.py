from __future__ import annotations

import polars as pl
import pytest

from coachiq.data import (
    SeasonValidationError,
    build_manifest,
    load_pbp,
    source,
    validate_seasons,
)


@pytest.mark.parametrize(
    ("seasons", "expected"),
    [([2024], (2024,)), ([2024, 2023, 2024], (2023, 2024))],
)
def test_validate_seasons_canonicalizes_input(
    seasons: list[int], expected: tuple[int, ...]
) -> None:
    assert validate_seasons(seasons) == expected


@pytest.mark.parametrize("seasons", [[], "2024", [1998], [True], [2024.0]])
def test_validate_seasons_rejects_invalid_input(seasons: object) -> None:
    with pytest.raises(SeasonValidationError):
        validate_seasons(seasons)  # type: ignore[arg-type]


def test_load_pbp_requests_canonical_seasons_and_sorts_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, tuple[int, ...]] = {}

    def fake_loader(seasons: tuple[int, ...]) -> pl.DataFrame:
        captured["seasons"] = seasons
        return pl.DataFrame(
            {
                "season": [2024, 2023, 2024],
                "game_id": ["2024_01_A_B", "2023_01_C_D", "2024_01_A_B"],
                "play_id": [55, 40, 12],
                "order_sequence": [2, 1, 1],
            }
        )

    monkeypatch.setattr(source, "_load_from_nflreadpy", fake_loader)

    raw = load_pbp([2024, 2023, 2024])

    assert captured["seasons"] == (2023, 2024)
    assert raw.select("season", "play_id").rows() == [
        (2023, 40),
        (2024, 12),
        (2024, 55),
    ]


def test_build_manifest_records_schema_and_observed_seasons() -> None:
    raw = pl.DataFrame({"season": [2024, 2023], "game_id": ["a", "b"]})

    manifest = build_manifest(raw, [2024, 2023])

    assert manifest.requested_seasons == (2023, 2024)
    assert manifest.observed_seasons == (2023, 2024)
    assert manifest.raw_row_count == 2
    assert manifest.raw_schema == {"season": "Int64", "game_id": "String"}
    assert manifest.resolved_assets == (
        "play_by_play_2023.parquet",
        "play_by_play_2024.parquet",
    )
    assert manifest.coachiq_worktree_dirty in {True, False, None}
