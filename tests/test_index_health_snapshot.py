from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from etf_trading.data.indexes import IndexDefinition
from etf_trading.data.storage import ParquetStore
from etf_trading.research.index_health_snapshot import (
    INDEX_ATOMIC_DETAIL_COLUMNS,
    INDEX_ATOMIC_SUMMARY_COLUMNS,
    build_index_atomic_snapshot,
)


def _definition(index_code: str) -> IndexDefinition:
    return IndexDefinition(
        index_code,
        f"指数{index_code}",
        "A股",
        "A股宽基",
        index_code,
        pool="core",
        index_base_date=date(2005, 1, 4),
        baseline_source="official_methodology",
    )


def _price_history(rows: int, *, amount: float | None = 100_000_000) -> pd.DataFrame:
    close = np.linspace(100.0, 220.0, rows)
    data: dict[str, object] = {
        "trade_date": pd.bdate_range("2024-01-02", periods=rows),
        "open": close * 0.99,
        "high": close * 1.01,
        "low": close * 0.98,
        "close": close,
        "volume": np.arange(rows) + 1_000,
        "data_source": "unit",
    }
    if amount is not None:
        data["amount"] = np.full(rows, amount)
    return pd.DataFrame(data)


def _crossing_history() -> pd.DataFrame:
    frame = _price_history(260)
    frame["close"] = 100.0
    frame.loc[frame.index[-2], "close"] = 90.0
    frame.loc[frame.index[-1], "close"] = 110.0
    return frame


def _store_with_index_prices(tmp_path, index_code: str, prices: pd.DataFrame) -> ParquetStore:
    store = ParquetStore(tmp_path)
    store.write_index_prices(index_code, prices.assign(index_code=index_code))
    return store


def _detail_row(details: pd.DataFrame, index_code: str, metric_key: str) -> pd.Series:
    matches = details[(details["index_code"] == index_code) & (details["metric_key"] == metric_key)]
    assert len(matches) == 1
    return matches.iloc[0]


def _detail_value(details: pd.DataFrame, index_code: str, metric_key: str) -> object:
    return _detail_row(details, index_code, metric_key)["value"]


def _detail_status(details: pd.DataFrame, index_code: str, metric_key: str) -> str:
    return str(_detail_row(details, index_code, metric_key)["status"])


def test_build_index_atomic_snapshot_calculates_price_ma_cross_range_return_and_drawdown(tmp_path):
    prices = _price_history(260, amount=100_000_000)
    prices.loc[prices.index[-1], "close"] = 219.0
    store = _store_with_index_prices(tmp_path, "000300", prices)

    summary, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    row = summary.iloc[0]
    assert list(summary.columns) == INDEX_ATOMIC_SUMMARY_COLUMNS
    assert list(details.columns) == INDEX_ATOMIC_DETAIL_COLUMNS
    assert row["ma_20"] == pytest.approx(prices.tail(20)["close"].mean())
    assert row["close_above_ma_20"] is True
    assert row["return_20"] == pytest.approx(row["close"] / prices.iloc[-21]["close"] - 1)
    assert _detail_value(details, "000300", "ma_cross_up_20") in {True, False}
    assert _detail_status(details, "000300", "range_20_high") == "computed"
    assert _detail_value(details, "000300", "drawdown_60") == pytest.approx(
        prices.iloc[-1]["close"] / prices.tail(60)["close"].max() - 1
    )


def test_snapshot_summary_exposes_20_day_range_high_and_low_facts(tmp_path):
    store = _store_with_index_prices(tmp_path, "000300", _price_history(260))

    summary, _ = build_index_atomic_snapshot(store, (_definition("000300"),))

    row = summary.iloc[0]
    assert row["range_20_status"] == "computed"
    assert row["range_20_high"] is True
    assert row["range_20_low"] is False


def test_build_index_atomic_snapshot_reports_progress_after_each_local_index(tmp_path):
    store = _store_with_index_prices(tmp_path, "000300", _price_history(260))
    store.write_index_prices("000905", _price_history(260).assign(index_code="000905"))
    progress = []

    build_index_atomic_snapshot(
        store,
        (_definition("000300"), _definition("000905")),
        on_progress=progress.append,
    )

    assert [(item.done, item.total, item.index_code) for item in progress] == [
        (1, 2, "000300"),
        (2, 2, "000905"),
    ]


def test_cross_is_true_only_when_current_and_previous_day_switch_sides(tmp_path):
    store = _store_with_index_prices(tmp_path, "000300", _crossing_history())

    _, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    assert _detail_value(details, "000300", "ma_cross_up_20") is True
    assert _detail_value(details, "000300", "ma_cross_down_20") is False


def test_cross_is_false_when_price_stays_on_the_same_ma_side(tmp_path):
    store = _store_with_index_prices(tmp_path, "000300", _price_history(260))

    _, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    assert _detail_value(details, "000300", "ma_cross_up_20") is False
    assert _detail_value(details, "000300", "ma_cross_down_20") is False


def test_missing_amount_only_marks_volume_metrics_missing(tmp_path):
    store = _store_with_index_prices(tmp_path, "000300", _price_history(260, amount=None))

    summary, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    assert summary.iloc[0]["return_20"] is not None
    assert _detail_status(details, "000300", "amount_avg_20") == "missing_input"
    assert _detail_status(details, "000300", "return_20") == "computed"


def test_snapshot_calculates_expanded_momentum_risk_and_activity_atoms(tmp_path):
    prices = _price_history(300)
    store = _store_with_index_prices(tmp_path, "000300", prices)

    _, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    returns = prices["close"].pct_change()
    assert _detail_value(details, "000300", "ma_20_change_20") == pytest.approx(
        prices["close"].rolling(20).mean().iloc[-1] / prices["close"].rolling(20).mean().iloc[-21] - 1
    )
    assert _detail_value(details, "000300", "ma_60_change_20") == pytest.approx(
        prices["close"].rolling(60).mean().iloc[-1] / prices["close"].rolling(60).mean().iloc[-21] - 1
    )
    assert _detail_value(details, "000300", "ma_120_change_20") == pytest.approx(
        prices["close"].rolling(120).mean().iloc[-1] / prices["close"].rolling(120).mean().iloc[-21] - 1
    )
    assert _detail_value(details, "000300", "rsi_14") == pytest.approx(100.0)
    assert _detail_value(details, "000300", "up_day_ratio_20") == pytest.approx((returns.iloc[-20:] > 0).mean())
    assert _detail_value(details, "000300", "max_drawdown_60") == pytest.approx(
        (prices["close"].iloc[-60:] / prices["close"].iloc[-60:].cummax() - 1).min()
    )
    assert _detail_value(details, "000300", "max_drawdown_120") == pytest.approx(
        (prices["close"].iloc[-120:] / prices["close"].iloc[-120:].cummax() - 1).min()
    )
    assert _detail_value(details, "000300", "max_drawdown_250") == pytest.approx(
        (prices["close"].iloc[-250:] / prices["close"].iloc[-250:].cummax() - 1).min()
    )
    assert _detail_value(details, "000300", "annualized_volatility_20") == pytest.approx(
        returns.iloc[-20:].std() * np.sqrt(252)
    )
    assert _detail_value(details, "000300", "annualized_volatility_60") == pytest.approx(
        returns.iloc[-60:].std() * np.sqrt(252)
    )
    assert _detail_value(details, "000300", "downside_volatility_60") == pytest.approx(
        np.sqrt(np.square(np.minimum(returns.iloc[-60:], 0)).mean()) * np.sqrt(252)
    )
    assert _detail_value(details, "000300", "atr_14_pct") == pytest.approx(
        _detail_value(details, "000300", "atr_14") / prices["close"].iloc[-1]
    )
    assert _detail_value(details, "000300", "amount_avg_60") == pytest.approx(prices["amount"].iloc[-60:].mean())
    assert _detail_value(details, "000300", "amount_vs_avg_20") == pytest.approx(0.0)
    assert _detail_value(details, "000300", "amount_vs_avg_60") == pytest.approx(0.0)
    assert _detail_status(details, "000300", "amount_avg_60") == "computed"


def test_missing_amount_only_marks_expanded_activity_atoms_missing(tmp_path):
    prices = _price_history(300, amount=None)
    store = _store_with_index_prices(tmp_path, "000300", prices)

    _, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    assert _detail_status(details, "000300", "amount_avg_60") == "missing_input"
    assert _detail_status(details, "000300", "amount_vs_avg_20") == "missing_input"
    assert _detail_status(details, "000300", "amount_vs_avg_60") == "missing_input"
    assert _detail_status(details, "000300", "rsi_14") == "computed"


def test_snapshot_preserves_catalog_order_and_never_reads_valuation_parquet(tmp_path, monkeypatch):
    store = _store_with_index_prices(tmp_path, "000300", _price_history(260))
    store.write_index_prices("000905", _price_history(260).assign(index_code="000905"))
    monkeypatch.setattr(
        store,
        "read_index_valuations",
        lambda index_code: (_ for _ in ()).throw(AssertionError(f"unexpected valuation read: {index_code}")),
    )
    coverage = pd.DataFrame(
        [
            {
                "index_code": "000905",
                "completeness_status": "INCOMPLETE",
                "completeness_message": "历史不完整",
            }
        ]
    )

    summary, details = build_index_atomic_snapshot(
        store,
        (_definition("000905"), _definition("000300")),
        coverage=coverage,
    )

    assert summary["index_code"].tolist() == ["000905", "000300"]
    assert summary["catalog_order"].tolist() == [0, 1]
    assert summary.iloc[0]["history_completeness_status"] == "INCOMPLETE"
    assert _detail_value(details, "000905", "history_completeness_status") == "INCOMPLETE"


def test_snapshot_keeps_the_last_record_for_a_duplicate_trade_date(tmp_path):
    prices = _price_history(260)
    duplicate = prices.iloc[[-1]].copy()
    duplicate.loc[:, "close"] = 250.0
    store = _store_with_index_prices(tmp_path, "000300", pd.concat([prices, duplicate], ignore_index=True))

    summary, _ = build_index_atomic_snapshot(store, (_definition("000300"),))

    assert summary.iloc[0]["history_rows"] == 260
    assert summary.iloc[0]["close"] == 250.0


def test_atr_requires_the_previous_close_for_the_first_true_range_day(tmp_path):
    prices = _price_history(260)
    prices.loc[prices.index[-15], "close"] = np.nan
    store = _store_with_index_prices(tmp_path, "000300", prices)

    _, details = build_index_atomic_snapshot(store, (_definition("000300"),))

    assert _detail_status(details, "000300", "atr_14") == "missing_input"
