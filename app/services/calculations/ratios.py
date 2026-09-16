"""Financial ratio categories the calculation engine derives from ingested
fundamentals: Margins, Returns, Valuation, and Quality.

Unlike ``statistics.py`` (generic time-series math over any numeric column),
these functions know the *meaning* of specific statement line items — they
look a fundamentals-shaped DataFrame up by a table of known column-name
aliases (Screener's own row labels, lowercased, as they land in
``Fundamental.metrics`` — see ``app.services.inputs.excel`` and
``app.services.market_data.repository.load_fundamentals_frame_full``) and
combine them into named ratios.

Every function degrades gracefully: a ratio whose inputs aren't present in
this particular dataset comes back with ``"insufficient_data": True`` and a
``reason`` naming what's missing, rather than raising or fabricating a
number. Several ratios (NIM, ROCE, EV multiples) are necessarily
approximations given what a plain P&L/Balance Sheet export actually contains
(e.g. no average earning-assets figure for NIM, no cash balance to net off
for EV) — those carry a ``"note"`` saying so.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

__all__ = ["margins", "returns", "valuation", "quality", "full_ratio_report"]

# canonical field -> accepted column-name aliases (lowercase, matched
# case-insensitively against whatever the ingested statement called it)
_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "sales"),
    "operating_profit": ("operating profit", "operating_profit", "ebit"),
    "net_income": ("net_income", "net profit"),
    "interest_earned": ("interest earned", "interest income", "interest_earned"),
    "interest_expended": ("interest expended", "interest expense", "interest_expended"),
    "depreciation": ("depreciation",),
    "equity_share_capital": ("equity share capital", "equity capital", "share capital"),
    "reserves": ("reserves", "reserves and surplus", "reserves & surplus"),
    "shareholders_equity": ("shareholders equity", "net worth", "total equity",
                            "shareholder's funds"),
    "total_assets": ("total assets", "total_assets"),
    "borrowings": ("borrowings", "total debt", "debt"),
    "cash_from_operations": ("cash from operating activity", "operating cash flow", "cfo",
                             "net cash flow from operating activities"),
    "eps": ("eps", "eps in rs"),
    "pe": ("pe", "price to earning"),
    "shares_outstanding": ("shares outstanding", "no. of shares", "shares", "no of shares"),
    "gross_npa_pct": ("gross npa %", "gross npa"),
}


def _find(df: pd.DataFrame, key: str) -> pd.Series | None:
    cols = {c.strip().lower(): c for c in df.columns}
    for alias in _ALIASES.get(key, (key,)):
        if alias in cols:
            s = pd.to_numeric(df[cols[alias]], errors="coerce")
            if s.notna().any():
                return s
    return None


def _equity(df: pd.DataFrame) -> pd.Series | None:
    direct = _find(df, "shareholders_equity")
    if direct is not None:
        return direct
    cap, res = _find(df, "equity_share_capital"), _find(df, "reserves")
    if cap is not None and res is not None:
        return cap.add(res, fill_value=0)
    return cap if cap is not None else res


def _ratio(
    numerator: pd.Series | None, denominator: pd.Series | None, *,
    pct: bool = True, missing: str = "",
) -> dict[str, Any]:
    if numerator is None or denominator is None:
        return {"insufficient_data": True, "reason": f"missing input(s): {missing}"}
    aligned = pd.concat({"n": numerator, "d": denominator}, axis=1).dropna()
    aligned = aligned[aligned["d"] != 0]
    if aligned.empty:
        return {"insufficient_data": True, "reason": "no overlapping non-zero periods"}
    ratio = aligned["n"] / aligned["d"] * (100 if pct else 1)
    return {
        "series": {str(idx): float(v) for idx, v in ratio.items()},
        "latest": float(ratio.iloc[-1]),
        "insufficient_data": False,
    }


# ── Margins — profit-or-income / base ("Profitability") ────────────────────
def margins(df: pd.DataFrame) -> dict[str, Any]:
    """Operating margin (OPM), net profit margin, and net interest margin
    (NIM — banks/lenders only)."""
    revenue = _find(df, "revenue")
    opm = _ratio(_find(df, "operating_profit"), revenue, missing="operating profit, revenue")
    net_margin = _ratio(_find(df, "net_income"), revenue, missing="net profit, revenue")

    interest_earned = _find(df, "interest_earned")
    interest_expended = _find(df, "interest_expended")
    total_assets = _find(df, "total_assets")
    if interest_earned is not None and interest_expended is not None and total_assets is not None:
        nii = interest_earned.subtract(interest_expended, fill_value=0)
        nim = _ratio(nii, total_assets, missing="")
        if not nim.get("insufficient_data"):
            nim["note"] = ("approximated as net interest income / total assets — no separate "
                           "average interest-earning-assets figure is tracked")
    else:
        nim = {
            "insufficient_data": True,
            "reason": "missing input(s): interest earned, interest expended, total assets "
                     "(bank/lender-specific — not applicable to non-financial companies)",
        }

    return {"operating_profit_margin_pct": opm, "net_profit_margin_pct": net_margin,
            "net_interest_margin_pct": nim}


# ── Returns — profit / capital base ("Capital efficiency") ─────────────────
def returns(df: pd.DataFrame) -> dict[str, Any]:
    """ROE, ROA, ROCE."""
    net_income = _find(df, "net_income")
    equity = _equity(df)
    total_assets = _find(df, "total_assets")
    borrowings = _find(df, "borrowings")
    ebit = _find(df, "operating_profit")

    roe = _ratio(net_income, equity, missing="net profit, shareholders' equity")
    roa = _ratio(net_income, total_assets, missing="net profit, total assets")

    if ebit is not None and equity is not None and borrowings is not None:
        capital_employed = equity.add(borrowings, fill_value=0)
        roce = _ratio(ebit, capital_employed, missing="")
        if not roce.get("insufficient_data"):
            roce["note"] = "capital employed approximated as equity + borrowings"
    else:
        roce = {
            "insufficient_data": True,
            "reason": "missing input(s): operating profit (EBIT proxy), shareholders' equity, "
                     "borrowings",
        }

    return {"roe_pct": roe, "roa_pct": roa, "roce_pct": roce}


# ── Valuation — market value / financial base ("Relative valuation") ───────
def valuation(df: pd.DataFrame, *, price: float | None = None) -> dict[str, Any]:
    """P/E, P/B, EV/EBITDA, EV/Sales.

    ``price`` (e.g. the latest close) is used to derive P/E when the
    statement itself has none, and is required for P/B and the EV multiples
    — none of those can be computed from the statement alone.
    """
    pe = _find(df, "pe")
    eps = _find(df, "eps")
    revenue = _find(df, "revenue")
    equity = _equity(df)
    shares = _find(df, "shares_outstanding")
    borrowings = _find(df, "borrowings")
    ebit = _find(df, "operating_profit")
    depreciation = _find(df, "depreciation")

    if pe is not None:
        pe_result = {"series": {str(i): float(v) for i, v in pe.items()},
                      "latest": float(pe.iloc[-1]), "insufficient_data": False}
    elif price is not None and eps is not None:
        implied = eps.apply(lambda e: price / e if e else np.nan).dropna()
        pe_result = (
            {"series": {str(i): float(v) for i, v in implied.items()},
             "latest": float(implied.iloc[-1]), "insufficient_data": False,
             "note": f"computed as supplied price ({price:g}) / EPS"}
            if not implied.empty else
            {"insufficient_data": True, "reason": "EPS is zero in every period"}
        )
    else:
        pe_result = {"insufficient_data": True,
                     "reason": "missing input(s): P/E, or a price plus EPS"}

    if price is not None and equity is not None and shares is not None:
        book_value_per_share = equity / shares
        pb = book_value_per_share.apply(lambda b: price / b if b else np.nan).dropna()
        pb_result = (
            {"series": {str(i): float(v) for i, v in pb.items()},
             "latest": float(pb.iloc[-1]), "insufficient_data": False}
            if not pb.empty else
            {"insufficient_data": True, "reason": "book value per share is zero in every period"}
        )
    else:
        pb_result = {"insufficient_data": True,
                     "reason": "missing input(s): price, shareholders' equity, shares outstanding"}

    if price is not None and shares is not None and ebit is not None:
        market_cap = shares * price
        ebitda = ebit.add(depreciation, fill_value=0) if depreciation is not None else ebit
        net_debt = borrowings if borrowings is not None else pd.Series(0.0, index=ebit.index)
        ev = market_cap + net_debt
        ev_ebitda = _ratio(ev, ebitda, pct=False, missing="")
        if not ev_ebitda.get("insufficient_data"):
            ev_ebitda["note"] = ("EV approximated as market cap + borrowings — no cash balance "
                                "is tracked to net off")
        ev_sales = _ratio(ev, revenue, pct=False, missing="")
        if not ev_sales.get("insufficient_data"):
            ev_sales["note"] = ev_ebitda.get("note", "")
    else:
        ev_ebitda = {"insufficient_data": True,
                     "reason": "missing input(s): price, shares outstanding, operating profit "
                              "(EBITDA proxy)"}
        ev_sales = {"insufficient_data": True,
                    "reason": "missing input(s): price, shares outstanding, revenue"}

    return {"pe": pe_result, "pb": pb_result, "ev_to_ebitda": ev_ebitda, "ev_to_sales": ev_sales}


# ── Quality — std dev / downside distribution of how profit is earned ──────
def quality(df: pd.DataFrame) -> dict[str, Any]:
    """Cash conversion, leverage, and asset quality."""
    cfo = _find(df, "cash_from_operations")
    net_income = _find(df, "net_income")
    borrowings = _find(df, "borrowings")
    equity = _equity(df)
    revenue = _find(df, "revenue")
    total_assets = _find(df, "total_assets")
    gross_npa = _find(df, "gross_npa_pct")

    cash_conversion = _ratio(cfo, net_income, pct=False,
                             missing="cash from operations, net profit")
    leverage = _ratio(borrowings, equity, pct=False,
                      missing="borrowings, shareholders' equity")

    if gross_npa is not None:
        asset_quality = {"series": {str(i): float(v) for i, v in gross_npa.items()},
                         "latest": float(gross_npa.iloc[-1]), "insufficient_data": False,
                         "metric": "gross_npa_pct"}
    else:
        asset_quality = _ratio(
            revenue, total_assets, pct=True,
            missing="gross NPA % (banks), or revenue + total assets (asset turnover proxy)",
        )
        if not asset_quality.get("insufficient_data"):
            asset_quality["metric"] = "asset_turnover_pct"
            asset_quality["note"] = ("no NPA data available — asset turnover "
                                     "(revenue / total assets) used as a proxy")

    return {"cash_conversion": cash_conversion, "leverage_debt_to_equity": leverage,
            "asset_quality": asset_quality}


# ── orchestration ────────────────────────────────────────────────────────
def full_ratio_report(df: pd.DataFrame, *, price: float | None = None) -> dict[str, Any]:
    """All four categories in one call — the shape ``excel_writeback`` and
    the fundamental analyst agent consume."""
    return {
        "margins": margins(df),
        "returns": returns(df),
        "valuation": valuation(df, price=price),
        "quality": quality(df),
    }
