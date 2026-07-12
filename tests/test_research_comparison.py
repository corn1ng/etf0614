import pandas as pd

from etf_trading.research.comparison import compare_regime_pairs


def test_compare_regime_pairs_matches_regime_candidates_to_base_candidates():
    results = pd.DataFrame(
        {
            "candidate_name": ["balanced", "balanced", "regime_balanced", "regime_balanced"],
            "etf_code": ["510300", "512800", "510300", "512800"],
            "sharpe": [0.1, 0.3, 0.2, 0.4],
            "max_drawdown": [-0.4, -0.2, -0.3, -0.1],
            "trade_count": [10.0, 20.0, 6.0, 8.0],
        }
    )

    comparison = compare_regime_pairs(results)

    assert list(comparison["base_candidate"]) == ["balanced"]
    row = comparison.iloc[0]
    assert row["base_median_sharpe"] == 0.2
    assert row["regime_median_sharpe"] == 0.3
    assert row["delta_median_sharpe"] == 0.1
    assert row["base_mean_trade_count"] == 15.0
    assert row["regime_mean_trade_count"] == 7.0
