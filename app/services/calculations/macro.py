"""Merge externally supplied macro-economic series (policy rate, GDP growth,
inflation, a sector/benchmark index, ...) into a fundamentals frame as lagged
features for ``statistics.regression`` — "macro linkage" via lagged external
features.

This module does not fetch macro data itself: there is no wired-up source
for GDP/inflation/policy-rate/index data in this codebase. It expects the
caller to supply ``macro_df`` — e.g. hand-maintained or uploaded through the
same CSV/Excel upload path already used for fundamentals — indexed by the
same period labels as the company data.
"""

from __future__ import annotations

import pandas as pd

__all__ = ["add_lagged_macro_features"]


def add_lagged_macro_features(
    df: pd.DataFrame, macro_df: pd.DataFrame, *, lags: tuple[int, ...] = (1,),
) -> pd.DataFrame:
    """Join ``macro_df`` onto ``df`` (matched by index — align periods before
    calling this) and add one lagged column per (macro column, lag) pair,
    e.g. ``repo_rate_lag1``. A positive ``lag`` looks back — period *t* sees
    the macro value from *lag* periods earlier, modelling a delayed macro
    effect on the company metric. Include ``0`` in ``lags`` for the
    unlagged (contemporaneous) value as well.
    """
    out = df.copy()
    for col in macro_df.columns:
        series = pd.to_numeric(macro_df[col], errors="coerce")
        for lag in lags:
            name = col if lag == 0 else f"{col}_lag{lag}"
            out[name] = series.shift(lag).reindex(df.index)
    return out
