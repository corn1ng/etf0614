from __future__ import annotations

import math

import pandas as pd

from etf_trading.research.index_trend_v1 import IndexTrendV1


def row(**values: float) -> pd.Series:
    return pd.Series(values)


def test_buy_requires_fresh_cross_above_two_percent_upper_band():
    strategy = IndexTrendV1(buffer_rate=0.02, atr_multiple=3.0)

    signal = strategy.evaluate_close(
        row(close=101.9, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        row(close=102.1, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        in_position=False,
    )

    assert signal is not None
    assert signal.action == "BUY"
    assert signal.reason == "fresh_upper_band_breakout"


def test_price_inside_hysteresis_band_keeps_position():
    strategy = IndexTrendV1()

    signal = strategy.evaluate_close(
        row(close=103.0, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        row(close=99.0, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        in_position=True,
        highest_close=104.0,
    )

    assert signal is None


def test_atr_exit_requires_new_upper_cross_before_reentry():
    strategy = IndexTrendV1()

    assert strategy.evaluate_close(
        row(close=103.0, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        row(close=104.0, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        in_position=False,
    ) is None


def test_equal_upper_band_does_not_buy():
    signal = IndexTrendV1().evaluate_close(
        row(close=101.0, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        row(close=102.0, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        in_position=False,
    )

    assert signal is None


def test_equal_lower_band_does_not_normal_exit():
    signal = IndexTrendV1().evaluate_close(
        row(close=100.0, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        row(close=98.0, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        in_position=True,
        highest_close=101.0,
    )

    assert signal is None


def test_equal_atr_stop_exits_and_has_priority_over_lower_band_exit():
    signal = IndexTrendV1().evaluate_close(
        row(close=110.0, ma60=100.0, ma60_slope_20=0.01, atr20=2.0),
        row(close=104.0, ma60=110.0, ma60_slope_20=0.01, atr20=2.0),
        in_position=True,
        highest_close=110.0,
    )

    assert signal is not None
    assert signal.action == "SELL"
    assert signal.reason == "atr_emergency_exit"


def test_non_positive_slope_or_invalid_indicators_never_open_position():
    strategy = IndexTrendV1()
    previous = row(close=101.0, ma60=100.0, ma60_slope_20=0.01, atr20=2.0)

    assert strategy.evaluate_close(
        previous,
        row(close=103.0, ma60=100.0, ma60_slope_20=0.0, atr20=2.0),
        in_position=False,
    ) is None
    assert strategy.evaluate_close(
        previous,
        row(close=103.0, ma60=math.nan, ma60_slope_20=0.01, atr20=2.0),
        in_position=False,
    ) is None
