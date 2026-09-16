from __future__ import annotations

import pandas as pd

from app.services.calculations.macro import add_lagged_macro_features


def test_add_lagged_macro_features_shifts_values_back():
    years = ["2020", "2021", "2022", "2023"]
    df = pd.DataFrame({"net_profit": [10.0, 12.0, 15.0, 18.0]}, index=years)
    macro = pd.DataFrame({"repo_rate": [4.0, 4.5, 6.0, 6.5]}, index=years)

    out = add_lagged_macro_features(df, macro, lags=(0, 1))

    assert "repo_rate" in out.columns
    assert "repo_rate_lag1" in out.columns
    # lag 0 is the contemporaneous value
    assert out.loc["2022", "repo_rate"] == 6.0
    # lag 1 at 2022 is the 2021 value
    assert out.loc["2022", "repo_rate_lag1"] == 4.5
    # first period has nothing to lag from
    assert pd.isna(out.loc["2020", "repo_rate_lag1"])


def test_add_lagged_macro_features_preserves_original_columns():
    df = pd.DataFrame({"net_profit": [10.0, 12.0]}, index=["2020", "2021"])
    macro = pd.DataFrame({"gdp_growth": [7.0, 6.5]}, index=["2020", "2021"])
    out = add_lagged_macro_features(df, macro)
    assert out["net_profit"].tolist() == [10.0, 12.0]
