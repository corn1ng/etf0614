import pandas as pd

from etf_trading.research.models import StrategyCandidate
from etf_trading.research.signals import generate_candidate_signals


def _featured_prices(**overrides) -> pd.DataFrame:
    base = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "open": [10.0, 10.3, 10.5],
            "high": [10.2, 10.8, 10.7],
            "low": [9.8, 10.1, 10.0],
            "close": [9.8, 10.6, 10.4],
            "ma51": [10.0, 10.0, 10.0],
            "ma120": [10.1, 10.2, 10.2],
            "ma250": [9.0, 9.0, 9.0],
            "ma850": [8.0, 8.0, 8.0],
            "ma20": [9.9, 10.3, 10.2],
            "ma60": [9.6, 10.0, 10.1],
            "ma51_slope_20": [0.02, 0.03, 0.03],
            "ma60_slope_20": [0.01, 0.03, 0.03],
            "ma120_slope_20": [0.01, 0.02, 0.02],
            "ma250_slope_60": [0.05, 0.05, 0.05],
            "momentum_20": [-0.01, 0.05, 0.04],
            "momentum_60": [0.02, 0.08, 0.07],
            "momentum_60_skip5": [0.01, 0.08, 0.07],
            "momentum_120_skip5": [0.02, 0.10, 0.09],
            "return_20": [-0.02, 0.10, 0.08],
            "drawdown_120": [-0.10, -0.04, -0.03],
            "relative_strength_rank": [0.4, 0.2, 0.2],
            "atr20": [0.20, 0.20, 0.20],
            "distance_ma20_atr": [-0.5, 1.5, 1.0],
        }
    )
    for column, values in overrides.items():
        base[column] = values
    return base


def test_generate_candidate_signals_buys_when_right_side_conditions_are_met():
    candidate = StrategyCandidate(
        name="right_side_balanced",
        max_distance_from_entry_ma=0.10,
        max_recent_return_20=0.20,
        min_trade_interval_days=1,
    )

    signals = generate_candidate_signals("510300", _featured_prices(), candidate)

    assert len(signals) == 1
    assert signals[0].action == "BUY"
    assert signals[0].trade_date == pd.Timestamp("2024-01-03")
    assert signals[0].target_weight == 1.0
    assert "price_above_ma51" in signals[0].trigger_rules
    assert "not_overextended_from_ma51" in signals[0].trigger_rules


def test_generate_candidate_signals_blocks_overextended_entries():
    candidate = StrategyCandidate(
        name="right_side_balanced",
        max_distance_from_entry_ma=0.10,
        max_recent_return_20=0.20,
        min_trade_interval_days=1,
    )

    signals = generate_candidate_signals(
        "510300",
        _featured_prices(close=[9.8, 12.0, 12.2], return_20=[-0.02, 0.10, 0.08]),
        candidate,
    )

    assert signals == []


def test_generate_candidate_signals_uses_momentum_20_as_heat_filter_when_return_20_missing():
    candidate = StrategyCandidate(
        name="right_side_balanced",
        max_distance_from_entry_ma=0.10,
        max_recent_return_20=0.20,
        min_trade_interval_days=1,
    )
    prices = _featured_prices(momentum_20=[-0.01, 0.30, 0.25]).drop(columns=["return_20"])

    signals = generate_candidate_signals("510300", prices, candidate)

    assert signals == []


def test_generate_candidate_signals_does_not_sell_when_close_is_missing():
    candidate = StrategyCandidate(
        name="right_side_balanced",
        max_distance_from_entry_ma=0.10,
        max_recent_return_20=0.20,
        min_trade_interval_days=1,
    )
    prices = _featured_prices(close=[9.8, 10.6, None])

    signals = generate_candidate_signals("510300", prices, candidate)

    assert [signal.action for signal in signals] == ["BUY"]


def test_generate_candidate_signals_sells_when_exit_average_breaks():
    candidate = StrategyCandidate(
        name="right_side_balanced",
        exit_ma="ma120",
        max_distance_from_entry_ma=0.10,
        max_recent_return_20=0.20,
        min_trade_interval_days=1,
    )

    signals = generate_candidate_signals(
        "510300",
        _featured_prices(close=[9.8, 10.6, 10.0], ma120=[10.1, 10.2, 10.2]),
        candidate,
    )

    assert [signal.action for signal in signals] == ["BUY", "SELL"]
    assert signals[1].trade_date == pd.Timestamp("2024-01-04")
    assert "price_below_ma120" in signals[1].trigger_rules


def test_generate_candidate_signals_blocks_entries_disallowed_by_trend_regime():
    candidate = StrategyCandidate(
        name="right_side_balanced",
        max_distance_from_entry_ma=0.10,
        max_recent_return_20=0.20,
        min_trade_interval_days=1,
        require_trend_regime=True,
    )

    signals = generate_candidate_signals(
        "510300",
        _featured_prices(
            close=[9.8, 10.6, 10.7],
            ma120=[10.4, 10.4, 10.4],
            ma250=[12.0, 12.0, 12.0],
            ma850=[13.0, 13.0, 13.0],
            ma250_slope_60=[-0.08, -0.08, -0.08],
            momentum_60=[-0.05, -0.03, -0.02],
            drawdown_120=[-0.30, -0.25, -0.24],
        ),
        candidate,
    )

    assert signals == []


def test_generate_candidate_signals_blocks_missing_relative_strength_rank_when_required():
    candidate = StrategyCandidate(
        name="right_side_balanced",
        rs_rank_max=0.30,
        max_distance_from_entry_ma=0.10,
        max_recent_return_20=0.20,
        min_trade_interval_days=1,
    )
    prices = _featured_prices().drop(columns=["relative_strength_rank"])

    signals = generate_candidate_signals("510300", prices, candidate)

    assert signals == []


def test_generate_candidate_signals_blocks_nan_relative_strength_rank_when_required():
    candidate = StrategyCandidate(
        name="right_side_balanced",
        rs_rank_max=0.30,
        max_distance_from_entry_ma=0.10,
        max_recent_return_20=0.20,
        min_trade_interval_days=1,
    )
    prices = _featured_prices(relative_strength_rank=[0.4, float("nan"), float("nan")])

    signals = generate_candidate_signals("510300", prices, candidate)

    assert signals == []


def test_generate_candidate_signals_supports_trend_v1_filters():
    candidate = StrategyCandidate(
        name="etf_trend_v1_standard",
        entry_ma="ma60",
        trend_ma="ma60",
        exit_ma="ma60",
        momentum_windows=(),
        skip_momentum_windows=(60, 120),
        required_ma_relations=(("ma20", "ma60"),),
        slope_field="ma60_slope_20",
        rs_rank_max=0.30,
        max_atr_distance_from_ma=2.0,
        min_trade_interval_days=1,
    )

    signals = generate_candidate_signals("510300", _featured_prices(), candidate)

    assert len(signals) == 1
    assert signals[0].action == "BUY"
    assert "ma20_above_ma60" in signals[0].trigger_rules
    assert "ma60_slope_20_positive" in signals[0].trigger_rules
    assert "momentum_60_skip5_positive" in signals[0].trigger_rules
    assert "not_overextended_2ATR" in signals[0].trigger_rules


def test_generate_candidate_signals_blocks_trend_v1_atr_overheat():
    candidate = StrategyCandidate(
        name="etf_trend_v1_standard",
        entry_ma="ma60",
        trend_ma="ma60",
        exit_ma="ma60",
        momentum_windows=(),
        skip_momentum_windows=(60, 120),
        required_ma_relations=(("ma20", "ma60"),),
        slope_field="ma60_slope_20",
        rs_rank_max=0.30,
        max_atr_distance_from_ma=2.0,
        min_trade_interval_days=1,
    )

    signals = generate_candidate_signals(
        "510300",
        _featured_prices(distance_ma20_atr=[-0.5, 2.4, 2.2]),
        candidate,
    )

    assert signals == []


def test_generate_candidate_signals_sells_on_trailing_atr_stop():
    candidate = StrategyCandidate(
        name="etf_trend_v1_standard",
        entry_ma="ma60",
        trend_ma="ma60",
        exit_ma="ma60",
        momentum_windows=(),
        skip_momentum_windows=(60, 120),
        required_ma_relations=(("ma20", "ma60"),),
        slope_field="ma60_slope_20",
        rs_rank_max=0.30,
        max_atr_distance_from_ma=2.0,
        trailing_atr_multiple=3.0,
        min_trade_interval_days=1,
    )

    signals = generate_candidate_signals(
        "510300",
        _featured_prices(
            close=[9.8, 10.6, 9.9],
            ma60=[9.6, 10.0, 9.6],
            atr20=[0.20, 0.20, 0.20],
        ),
        candidate,
    )

    assert [signal.action for signal in signals] == ["BUY", "SELL"]
    assert "trailing_ATR_stop" in signals[1].trigger_rules


def test_generate_candidate_signals_uses_trailing_atr_high_water_mark():
    candidate = StrategyCandidate(
        name="etf_trend_v1_standard",
        entry_ma="ma60",
        trend_ma="ma60",
        exit_ma="ma60",
        momentum_windows=(),
        skip_momentum_windows=(60, 120),
        required_ma_relations=(("ma20", "ma60"),),
        slope_field="ma60_slope_20",
        rs_rank_max=0.30,
        max_atr_distance_from_ma=2.0,
        trailing_atr_multiple=3.0,
        min_trade_interval_days=1,
    )
    prices = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]),
            "close": [9.8, 10.6, 11.0, 10.3],
            "ma60": [9.6, 10.0, 10.0, 10.0],
            "ma20": [9.9, 10.3, 10.4, 10.4],
            "ma60_slope_20": [0.01, 0.03, 0.03, 0.03],
            "momentum_60_skip5": [0.01, 0.08, 0.07, 0.07],
            "momentum_120_skip5": [0.02, 0.10, 0.09, 0.09],
            "return_20": [-0.02, 0.10, 0.08, 0.07],
            "relative_strength_rank": [0.4, 0.2, 0.2, 0.2],
            "atr20": [0.20, 0.20, 0.20, 0.20],
            "distance_ma20_atr": [-0.5, 1.5, 1.0, 1.0],
        }
    )

    signals = generate_candidate_signals("510300", prices, candidate)

    assert [signal.action for signal in signals] == ["BUY", "SELL"]
    assert signals[1].trade_date == pd.Timestamp("2024-01-05")
    assert "trailing_ATR_stop" in signals[1].trigger_rules
