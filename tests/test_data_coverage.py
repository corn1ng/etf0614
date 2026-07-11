from __future__ import annotations

import pandas as pd

from etf_trading.ui.data_coverage import (
    build_data_coverage_summary,
    build_data_gap_detail,
    build_etf_data_overview,
    expected_latest_trade_date,
)


class FakeParquetStore:
    def __init__(self, prices: dict[str, pd.DataFrame]) -> None:
        self._prices = prices

    def read_prices(self, code: str) -> pd.DataFrame:
        return self._prices.get(str(code), pd.DataFrame()).copy()


def price_frame_ending(end: str, rows: int) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp(end), periods=rows)
    return pd.DataFrame(
        {
            "trade_date": dates,
            "open": range(rows),
            "high": range(rows),
            "low": range(rows),
            "close": range(rows),
        }
    )


def master_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "etf_code": ["510300", "159915", "513180"],
            "name": ["沪深300ETF", "创业板ETF", "恒生科技ETF"],
            "exchange": ["SH", "SZ", "SH"],
            "category": ["A股宽基", "A股成长", "港股科技"],
            "tracking_index": ["000300", "399006", "HSTECH"],
            "amount": [12_000_000_000, 6_000_000_000, 2_000_000_000],
            "is_active": [1, 1, 1],
        }
    )


def watchlist_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "etf_code": ["510300"],
            "category": ["A股宽基"],
            "enabled": [1],
            "allow_buy": [1],
            "note": [""],
        }
    )


def universe_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": ["000300", "399006"],
            "index_name": ["沪深300", "创业板指"],
            "market": ["A股", "A股"],
            "index_category": ["A股宽基", "A股成长"],
            "etf_code": ["510300", "159915"],
            "etf_name": ["沪深300ETF", "创业板ETF"],
            "tracking_index": ["000300", "399006"],
            "mapping_source": ["data_source", "name_inferred"],
            "confidence": ["high", "medium"],
            "amount": [12_000_000_000, 6_000_000_000],
            "volume": [1000, 900],
            "history_rows": [300, 120],
            "sample_rank": [1, 11],
            "is_top_sample": [True, False],
        }
    )


def index_summary_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": ["000300", "399006", "HSTECH"],
            "index_name": ["沪深300", "创业板指", "恒生科技"],
            "market": ["A股", "A股", "港股"],
            "category": ["A股宽基", "A股成长", "港股科技"],
            "latest_date": ["2026-06-01", "", "2026-07-03"],
            "history_rows": [300, 0, 320],
        }
    )


def test_expected_latest_trade_date_uses_previous_friday_on_weekend():
    assert expected_latest_trade_date(pd.Timestamp("2026-07-05")).strftime("%Y-%m-%d") == "2026-07-03"


def test_etf_data_overview_marks_watchlist_index_pool_and_history_status():
    store = FakeParquetStore(
        {
            "510300": price_frame_ending("2026-06-01", 300),
            "159915": price_frame_ending("2026-01-01", 120),
        }
    )

    overview = build_etf_data_overview(
        master_frame(),
        watchlist_frame(),
        store,
        universe_frame(),
        today=pd.Timestamp("2026-06-01"),
    )

    assert list(overview.columns) == [
        "ETF代码",
        "ETF名称",
        "分类",
        "交易所",
        "成交额",
        "追踪指数",
        "映射来源",
        "置信度",
        "每日计算池",
        "允许买入",
        "启用",
        "指数样本池",
        "本地历史",
        "历史长度",
        "最新日期",
        "状态说明",
    ]
    assert overview.loc[overview["ETF代码"] == "510300", "每日计算池"].item() == "是"
    assert overview.loc[overview["ETF代码"] == "510300", "指数样本池"].item() == "是"
    assert overview.loc[overview["ETF代码"] == "510300", "本地历史"].item() == "数据可用"
    assert overview.loc[overview["ETF代码"] == "159915", "状态说明"].item() == "行情滞后"
    assert overview.loc[overview["ETF代码"] == "513180", "状态说明"].item() == "历史缺失"


def test_data_gap_detail_reports_missing_days_and_global_objects():
    store = FakeParquetStore(
        {
            "510300": price_frame_ending("2026-06-01", 300),
            "159915": price_frame_ending("2026-01-01", 120),
        }
    )

    gaps = build_data_gap_detail(
        master_frame(),
        watchlist_frame(),
        index_summary_frame(),
        universe_frame(),
        store,
        today=pd.Timestamp("2026-07-05"),
    )

    assert {"数据类型": "ETF历史", "代码": "513180", "状态": "历史缺失"} in gaps[
        ["数据类型", "代码", "状态"]
    ].to_dict("records")
    row = gaps[(gaps["数据类型"] == "ETF历史") & (gaps["代码"] == "510300")].iloc[0]
    assert row["本地最新日期"] == "2026-06-01"
    assert row["应有最新交易日"] == "2026-07-03"
    assert row["缺失天数"] > 0
    assert {"数据类型": "指数历史", "代码": "399006", "状态": "历史缺失"} in gaps[
        ["数据类型", "代码", "状态"]
    ].to_dict("records")


def test_data_coverage_summary_counts_missing_and_short_data():
    store = FakeParquetStore(
        {
            "510300": price_frame_ending("2026-06-01", 300),
            "159915": price_frame_ending("2026-01-01", 120),
        }
    )
    gaps = build_data_gap_detail(
        master_frame(),
        watchlist_frame(),
        index_summary_frame(),
        universe_frame(),
        store,
        today=pd.Timestamp("2026-07-05"),
    )

    summary = build_data_coverage_summary(gaps, master_frame(), watchlist_frame(), index_summary_frame(), universe_frame())

    etf_history = summary[summary["数据类型"] == "ETF历史"].iloc[0]
    assert etf_history["总数"] == 3
    assert etf_history["缺失"] == 1
    assert etf_history["历史不足"] == 0
    assert etf_history["缺少"] == 2
    assert etf_history["完整"] == 0
    index_history = summary[summary["数据类型"] == "指数历史"].iloc[0]
    assert index_history["总数"] == 3
    assert index_history["完整"] == 1


def test_etf_overview_and_gap_detail_report_same_primary_status_for_stale_history():
    store = FakeParquetStore({"510300": price_frame_ending("2026-06-01", 300)})

    overview = build_etf_data_overview(
        master_frame().iloc[:1],
        watchlist_frame(),
        store,
        universe_frame(),
        today=pd.Timestamp("2026-07-10"),
    )
    gaps = build_data_gap_detail(
        master_frame().iloc[:1],
        watchlist_frame(),
        index_summary_frame().iloc[:0],
        universe_frame(),
        store,
        today=pd.Timestamp("2026-07-10"),
    )

    assert overview.loc[overview["ETF代码"] == "510300", "本地历史"].item() == "行情滞后"
    assert gaps.loc[(gaps["数据类型"] == "ETF历史") & (gaps["代码"] == "510300"), "状态"].item() == "行情滞后"
