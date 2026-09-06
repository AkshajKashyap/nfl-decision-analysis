from __future__ import annotations

import polars as pl
import pytest

from coachiq.analysis import evaluate_decision_diagnostics


def test_decision_diagnostics_require_complete_pre_2025_data() -> None:
    with pytest.raises(ValueError, match="complete 2014-2024"):
        evaluate_decision_diagnostics(pl.DataFrame({"season": [2024]}))

    with pytest.raises(ValueError, match="2025"):
        evaluate_decision_diagnostics(pl.DataFrame({"season": [2014, 2025]}))
