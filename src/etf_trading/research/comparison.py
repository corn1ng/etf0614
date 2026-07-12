"""Comparison helpers for base candidates and trend-regime gated variants."""

from __future__ import annotations

import pandas as pd


REGIME_PREFIX = "regime_"


def compare_regime_pairs(results: pd.DataFrame) -> pd.DataFrame:
    """Compare each `regime_*` candidate against its base candidate."""

    if results.empty:
        return pd.DataFrame()
    required = {"candidate_name", "etf_code", "sharpe", "max_drawdown", "trade_count"}
    missing = required - set(results.columns)
    if missing:
        raise ValueError(f"results missing required columns: {sorted(missing)}")

    summary = (
        results.groupby("candidate_name", as_index=False)
        .agg(
            sample_count=("etf_code", "nunique"),
            median_sharpe=("sharpe", "median"),
            median_max_drawdown=("max_drawdown", "median"),
            worst_max_drawdown=("max_drawdown", "min"),
            mean_trade_count=("trade_count", "mean"),
        )
        .assign(base_candidate=lambda frame: frame["candidate_name"].map(_base_name))
    )
    base = summary[~summary["candidate_name"].str.startswith(REGIME_PREFIX)].copy()
    regime = summary[summary["candidate_name"].str.startswith(REGIME_PREFIX)].copy()
    if base.empty or regime.empty:
        return pd.DataFrame()

    paired = base.merge(regime, on="base_candidate", suffixes=("_base", "_regime"))
    if paired.empty:
        return pd.DataFrame()
    result = pd.DataFrame(
        {
            "base_candidate": paired["base_candidate"],
            "base_median_sharpe": paired["median_sharpe_base"].round(6),
            "regime_median_sharpe": paired["median_sharpe_regime"].round(6),
            "delta_median_sharpe": (paired["median_sharpe_regime"] - paired["median_sharpe_base"]).round(6),
            "base_median_max_drawdown": paired["median_max_drawdown_base"].round(6),
            "regime_median_max_drawdown": paired["median_max_drawdown_regime"].round(6),
            "delta_median_max_drawdown": (paired["median_max_drawdown_regime"] - paired["median_max_drawdown_base"]).round(6),
            "base_worst_max_drawdown": paired["worst_max_drawdown_base"].round(6),
            "regime_worst_max_drawdown": paired["worst_max_drawdown_regime"].round(6),
            "base_mean_trade_count": paired["mean_trade_count_base"].round(6),
            "regime_mean_trade_count": paired["mean_trade_count_regime"].round(6),
        }
    )
    return result.sort_values("delta_median_sharpe", ascending=False).reset_index(drop=True)


def _base_name(candidate_name: str) -> str:
    return candidate_name[len(REGIME_PREFIX) :] if candidate_name.startswith(REGIME_PREFIX) else candidate_name
