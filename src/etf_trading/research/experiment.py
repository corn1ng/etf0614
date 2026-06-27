"""Batch experiment runner for ETF strategy research."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import pandas as pd

from etf_trading.backtest.engine import BacktestEngine
from etf_trading.research.metrics import summarize_backtest
from etf_trading.research.models import StrategyCandidate
from etf_trading.research.regime import add_trend_regime_features
from etf_trading.research.signals import generate_candidate_signals


class ResearchRunCancelled(RuntimeError):
    """Raised when a research run is cancelled between ETF backtests."""


class StrategyExperimentRunner:
    """Run strategy candidates over a universe of ETF price frames."""

    def __init__(self, backtest_engine: BacktestEngine | None = None) -> None:
        self.backtest_engine = backtest_engine or BacktestEngine()

    def run_universe(
        self,
        price_frames: Mapping[str, pd.DataFrame],
        candidates: Sequence[StrategyCandidate],
        categories: Mapping[str, str] | None = None,
        should_stop: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> pd.DataFrame:
        rows: list[dict[str, float | str]] = []
        categories = categories or {}
        total = len(price_frames)

        for done, (etf_code, prices) in enumerate(price_frames.items(), start=1):
            if should_stop is not None and should_stop():
                raise ResearchRunCancelled("research run cancelled")
            category = categories.get(etf_code, "A股行业")
            featured = _ensure_features(prices)
            for candidate in candidates:
                signals = generate_candidate_signals(
                    etf_code=etf_code,
                    featured_prices=featured,
                    candidate=candidate,
                    category=category,
                )
                result = self.backtest_engine.run_single_etf(
                    etf_code=etf_code,
                    prices=featured,
                    signals=signals,
                    category=category,
                )
                row: dict[str, float | str] = {
                    "candidate_name": candidate.name,
                    "etf_code": etf_code,
                    "category": category,
                }
                row.update(summarize_backtest(result))
                rows.append(row)
            if on_progress is not None:
                on_progress(done, total, etf_code)

        return pd.DataFrame(rows)


def rank_candidates(results: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-ETF results into a candidate leaderboard."""

    if results.empty:
        return pd.DataFrame()

    grouped = results.groupby("candidate_name", as_index=False).agg(
        sample_count=("etf_code", "nunique"),
        mean_total_return=("total_return", "mean"),
        median_annualized_return=("annualized_return", "median"),
        median_sharpe=("sharpe", "median"),
        median_calmar=("calmar", "median"),
        worst_max_drawdown=("max_drawdown", "min"),
        mean_trade_count=("trade_count", "mean"),
    )
    grouped["score"] = (
        grouped["mean_total_return"]
        + grouped["median_annualized_return"].clip(lower=-1, upper=1)
        + grouped["median_sharpe"].clip(lower=-3, upper=3) * 0.10
        + grouped["median_calmar"].clip(lower=-3, upper=3) * 0.05
        + grouped["worst_max_drawdown"]
    )
    return grouped.sort_values(["score", "mean_total_return"], ascending=False).reset_index(drop=True)


def _ensure_features(prices: pd.DataFrame) -> pd.DataFrame:
    required_feature_columns = {"ma20", "ma51", "ma120", "momentum_20", "momentum_60", "ma51_slope_20", "ma120_slope_20", "ma250_slope_60"}
    if required_feature_columns.issubset(prices.columns):
        return prices.copy()
    return add_trend_regime_features(prices)
