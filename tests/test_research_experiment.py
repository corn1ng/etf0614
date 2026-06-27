import pandas as pd
import pytest

from etf_trading.research.experiment import ResearchRunCancelled, StrategyExperimentRunner, rank_candidates
from etf_trading.research.models import StrategyCandidate


def _experiment_prices() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            "open": [10.0, 10.3, 10.5, 11.5],
            "high": [10.2, 10.8, 11.2, 12.2],
            "low": [9.8, 10.1, 10.4, 11.2],
            "close": [9.8, 10.6, 11.0, 12.0],
            "ma20": [9.9, 10.3, 10.5, 11.0],
            "ma51": [10.0, 10.0, 10.0, 10.2],
            "ma120": [10.1, 10.2, 10.2, 10.4],
            "ma250": [9.0, 9.0, 9.0, 9.2],
            "ma850": [8.0, 8.0, 8.0, 8.2],
            "ma51_slope_20": [0.02, 0.03, 0.03, 0.04],
            "ma120_slope_20": [0.01, 0.02, 0.02, 0.03],
            "ma250_slope_60": [0.05, 0.05, 0.05, 0.06],
            "momentum_20": [-0.01, 0.05, 0.04, 0.06],
            "momentum_60": [0.02, 0.08, 0.07, 0.09],
            "return_20": [-0.02, 0.10, 0.08, 0.12],
            "drawdown_120": [-0.10, -0.04, -0.03, -0.02],
            "relative_strength_rank": [0.4, 0.2, 0.2, 0.15],
        }
    )


def test_experiment_runner_returns_one_metric_row_per_etf_and_candidate():
    candidates = [
        StrategyCandidate(name="balanced", max_distance_from_entry_ma=0.10, min_trade_interval_days=1),
        StrategyCandidate(name="regime_balanced", max_distance_from_entry_ma=0.10, min_trade_interval_days=1, require_trend_regime=True),
        StrategyCandidate(name="too_strict", max_distance_from_entry_ma=0.01, min_trade_interval_days=1),
    ]
    price_frames = {
        "510300": _experiment_prices(),
        "512800": _experiment_prices(),
    }

    results = StrategyExperimentRunner().run_universe(
        price_frames=price_frames,
        candidates=candidates,
        categories={"510300": "A股宽基", "512800": "A股行业"},
    )

    assert len(results) == 6
    assert {"candidate_name", "etf_code", "category", "total_return", "volatility", "sharpe", "trade_count"}.issubset(results.columns)
    assert results.loc[results["candidate_name"] == "balanced", "trade_count"].sum() == 2
    assert results.loc[results["candidate_name"] == "regime_balanced", "trade_count"].sum() == 2
    assert results.loc[results["candidate_name"] == "too_strict", "trade_count"].sum() == 0


def test_rank_candidates_aggregates_universe_results():
    candidates = [
        StrategyCandidate(name="balanced", max_distance_from_entry_ma=0.10, min_trade_interval_days=1),
        StrategyCandidate(name="too_strict", max_distance_from_entry_ma=0.01, min_trade_interval_days=1),
    ]
    results = StrategyExperimentRunner().run_universe(
        price_frames={"510300": _experiment_prices()},
        candidates=candidates,
        categories={"510300": "A股宽基"},
    )

    ranking = rank_candidates(results)

    assert list(ranking["candidate_name"]) == ["balanced", "too_strict"]
    assert ranking.loc[0, "sample_count"] == 1
    assert ranking.loc[0, "mean_total_return"] > ranking.loc[1, "mean_total_return"]


def test_experiment_runner_can_cancel_between_etfs():
    candidates = [StrategyCandidate(name="balanced", max_distance_from_entry_ma=0.10, min_trade_interval_days=1)]
    processed = 0

    def on_progress(done: int, total: int, etf_code: str) -> None:
        nonlocal processed
        processed = done

    def should_stop() -> bool:
        return processed >= 1

    with pytest.raises(ResearchRunCancelled):
        StrategyExperimentRunner().run_universe(
            price_frames={"510300": _experiment_prices(), "512800": _experiment_prices()},
            candidates=candidates,
            categories={"510300": "A股宽基", "512800": "A股行业"},
            should_stop=should_stop,
            on_progress=on_progress,
        )
