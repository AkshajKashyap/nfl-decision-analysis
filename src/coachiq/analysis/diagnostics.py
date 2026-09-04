"""Deterministic coverage summaries for fourth-down reconstruction."""

from __future__ import annotations

import hashlib

import polars as pl

from coachiq.analysis.fourth_down import NextStateStatus


def deterministic_manual_sample(
    candidates: pl.DataFrame, size: int = 20
) -> pl.DataFrame:
    """Return a stable pseudo-random audit sample keyed by game and play ID."""

    if size < 0:
        raise ValueError("sample size cannot be negative")
    if not candidates.height or size == 0:
        return candidates.head(0)

    keys = candidates.select("game_id", "play_id").rows()
    ranked_indices = sorted(
        range(candidates.height),
        key=lambda index: hashlib.sha256(
            f"{keys[index][0]}:{keys[index][1]}".encode()
        ).digest(),
    )
    return candidates[ranked_indices[:size]].sort(
        ["season", "game_id", "play_sequence", "play_id"], nulls_last=True
    )


def count_by(candidates: pl.DataFrame, column: str) -> list[tuple[str, int]]:
    """Return stable null-safe counts for a categorical audit column."""

    values = candidates.group_by(column).len().sort(column, nulls_last=True).rows()
    return [
        ("none" if value is None else str(value), int(count)) for value, count in values
    ]


def next_state_coverage(candidates: pl.DataFrame) -> dict[str, int]:
    """Return the public successful/unavailable/ambiguous coverage buckets."""

    counts = dict(count_by(candidates, "next_state_status"))
    reconstructed = counts.get(NextStateStatus.RECONSTRUCTED, 0)
    terminal = counts.get(NextStateStatus.TERMINAL, 0)
    return {
        "successful": reconstructed + terminal,
        "reconstructed": reconstructed,
        "terminal": terminal,
        "unavailable": counts.get(NextStateStatus.UNAVAILABLE, 0),
        "ambiguous": counts.get(NextStateStatus.AMBIGUOUS, 0),
    }


__all__ = ["count_by", "deterministic_manual_sample", "next_state_coverage"]
