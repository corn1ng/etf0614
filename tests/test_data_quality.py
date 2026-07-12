from __future__ import annotations

import pandas as pd

from etf_trading.data.quality import (
    HistoryReadiness,
    assess_price_history,
    expected_latest_trade_date,
    history_readiness_label,
    trading_day_lag,
)


def test_assessment_keeps_stale_as_primary_and_short_history_as_reason() -> None:
    prices = pd.DataFrame({"trade_date": pd.bdate_range(end="2026-06-01", periods=40)})

    result = assess_price_history(
        prices,
        expected_trade_date=pd.Timestamp("2026-07-10"),
        min_history_rows=252,
    )

    assert result.readiness is HistoryReadiness.STALE
    assert result.reason_codes == ("stale", "short_history")
    assert result.trading_day_lag == 29


def test_expected_latest_trade_date_skips_weekends_and_explicit_holidays() -> None:
    holidays = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07"]

    assert expected_latest_trade_date("2026-07-05") == pd.Timestamp("2026-07-03")
    assert expected_latest_trade_date("2026-10-07", holidays=holidays) == pd.Timestamp("2026-09-30")


def test_trading_day_lag_skips_explicit_holidays() -> None:
    holidays = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07"]

    assert trading_day_lag("2026-09-30", "2026-10-07", holidays=holidays) == 0
    assert trading_day_lag("2026-09-29", "2026-10-07", holidays=holidays) == 1


def test_history_readiness_label_is_chinese() -> None:
    assert history_readiness_label(HistoryReadiness.READY) == "数据可用"
    assert history_readiness_label(HistoryReadiness.STALE) == "行情滞后"
    assert history_readiness_label(HistoryReadiness.SHORT_HISTORY) == "历史不足"
    assert history_readiness_label(HistoryReadiness.MISSING_HISTORY) == "历史缺失"
    assert history_readiness_label(HistoryReadiness.READ_FAILED) == "读取失败"
