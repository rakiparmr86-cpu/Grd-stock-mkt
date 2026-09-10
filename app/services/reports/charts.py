"""Matplotlib chart helpers. Return base64 PNG so charts embed straight into HTML."""

from __future__ import annotations

import base64
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def _fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def price_with_indicators_png(
    frame: pd.DataFrame,
    *,
    title: str = "",
    overlays: tuple[str, ...] = ("sma_20", "sma_50", "sma_200"),
    lookback: int = 250,
) -> str:
    df = frame.tail(lookback)
    fig, (ax_price, ax_rsi) = plt.subplots(
        2, 1, figsize=(10, 6), gridspec_kw={"height_ratios": [3, 1]}, sharex=True
    )
    ax_price.plot(df.index, df["close"], label="close", linewidth=1.3)
    for col in overlays:
        if col in df.columns:
            ax_price.plot(df.index, df[col], label=col, linewidth=1.0, alpha=0.8)
    if {"bb_upper", "bb_lower"}.issubset(df.columns):
        ax_price.fill_between(df.index, df["bb_lower"], df["bb_upper"], alpha=0.08,
                             label="bollinger")
    ax_price.set_title(title or "Price")
    ax_price.legend(loc="upper left", fontsize=8)
    ax_price.grid(alpha=0.25)

    rsi_col = next((c for c in df.columns if c.startswith("rsi_")), None)
    if rsi_col:
        ax_rsi.plot(df.index, df[rsi_col], color="purple", linewidth=1.0, label=rsi_col)
        ax_rsi.axhline(70, color="red", linestyle="--", linewidth=0.7)
        ax_rsi.axhline(30, color="green", linestyle="--", linewidth=0.7)
        ax_rsi.set_ylim(0, 100)
    ax_rsi.grid(alpha=0.25)
    ax_rsi.legend(loc="upper left", fontsize=8)
    fig.autofmt_xdate()
    return _fig_to_b64(fig)
