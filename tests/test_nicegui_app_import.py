from datetime import date, datetime
from pathlib import Path

import pandas as pd


def test_market_page_uses_readonly_atomic_snapshot_and_no_legacy_health_builder():
    source = Path("src/etf_trading/nicegui_app/pages/market.py").read_text(encoding="utf-8")

    assert "load_index_atomic_snapshot_readonly" in source
    assert "load_index_health_snapshot_cached" not in source
    assert "build_index_atomic_snapshot" not in source
    assert "CORE_VALUATION_METRICS" not in source


def test_market_page_declares_pool_search_and_tabbed_detail_dialog():
    source = Path("src/etf_trading/nicegui_app/pages/market.py").read_text(encoding="utf-8")

    for text in ("核心池", "研究池", "搜索指数", "关键指标", "全部原子指标", "数据质量"):
        assert text in source
    for forbidden in ("大趋势", "中趋势", "小趋势", "允许开仓", "估值"):
        assert forbidden not in source


def test_market_page_declares_snapshot_states_fixed_columns_and_readonly_reload():
    source = Path("src/etf_trading/nicegui_app/pages/market.py").read_text(encoding="utf-8")

    for text in (
        "原子指标快照待重建",
        "尚未生成指数原子指标快照",
        "最近一次原子指标快照生成失败",
        "当前输入最新日期",
        "指标状态计数",
        "前往数据维护",
        "index_atomic_detail_groups",
        "ui.dialog()",
        "index-atomic-dialog",
    ):
        assert text in source
    assert source.count("load_index_atomic_snapshot_readonly") == 3
    assert "index_atomic_snapshot_inputs(create_store())" in source
    assert '"computed": "已计算"' in source
    assert "IndexAtomicFilters(pool=str(pool.value or \"core\")" in source
    assert "row_key=\"index_code\"" in source


def test_market_key_metrics_use_stored_atoms_for_range_and_snapshot_data_status():
    from etf_trading.nicegui_app.pages import market
    from etf_trading.nicegui_app.view_models import IndexAtomicDetailGroup, IndexAtomicDetailItem

    def item(metric_key: str, value: str) -> IndexAtomicDetailItem:
        return IndexAtomicDetailItem(
            metric_key=metric_key,
            label=metric_key,
            value=value,
            status="已计算",
            reason="测试快照",
            as_of_date="2026-07-12",
            sample_count="300",
            data_source="测试数据源",
        )

    groups = [
        IndexAtomicDetailGroup("价格与均线", [item("close", "1,001.00"), item("ma_20", "995.00"), item("ma_60", "980.00"), item("close_vs_ma_20", "0.6%"), item("close_vs_ma_60", "2.1%")]),
        IndexAtomicDetailGroup("区间位置", [item("range_20_high", "是"), item("range_20_low", "否")]),
    ]

    rows = dict((label, value) for label, value, _status in market._key_metric_rows(groups, {"snapshot_status": "computed"}))

    assert rows["20日区间"] == "20日新高"
    assert rows["数据状态"] == "已计算"


def test_market_atomic_presentation_uses_chinese_known_and_unknown_fallbacks():
    from etf_trading.nicegui_app.pages import market
    from etf_trading.nicegui_app.view_models import IndexAtomicDetailItem

    items = [
        IndexAtomicDetailItem("close", "收盘价", "1,001.00", "computed", "测试", "2026-07-12", "300", "akshare_zh_em"),
        IndexAtomicDetailItem("data_source", "数据源", "unknown_provider", "mystery_status", "测试", "2026-07-12", "300", "unknown_provider"),
    ]

    rows = {label: (value, status) for label, value, status in market._detail_metric_rows(items)}

    assert market._status_text("computed", "") == "已计算"
    assert market._status_text("mystery_status", "") == "未知状态"
    assert market._data_source_text("akshare_zh_em") == "AkShare（东方财富指数行情）"
    assert market._data_source_text("unknown_provider") == "未知数据源"
    assert rows["收盘价"][1] == "已计算"
    assert rows["数据源"] == ("未知数据源", "未知状态")


def test_market_atomic_table_projection_keeps_exactly_eight_visible_columns_and_hidden_row_key():
    from etf_trading.nicegui_app.components.tables import table_columns
    from etf_trading.nicegui_app.pages import market

    rows = market._index_atomic_table_rows(
        [
            {
                "index_code": "000300",
                "index": "000300 沪深300",
                "category": "A股宽基",
                "latest_date": "2026-07-12",
                "close_vs_ma_20": "高于 1.0%",
                "close_vs_ma_60": "高于 2.0%",
                "range_20": "区间内",
                "return_20": "1.2%",
                "data_status": "已计算",
                "unexpected": "不得显示",
            }
        ]
    )

    assert rows[0]["index_code"] == "000300"
    assert list(rows[0]) == [
        "index",
        "category",
        "latest_date",
        "close_vs_ma_20",
        "close_vs_ma_60",
        "range_20",
        "return_20",
        "data_status",
        "index_code",
    ]
    assert [column["label"] for column in table_columns(rows, compact=True)] == [
        "指数",
        "分类",
        "最新日期",
        "相对20日线",
        "相对60日线",
        "20日区间",
        "20日收益",
        "数据状态",
    ]


def test_market_atomic_table_projection_sanitizes_known_and_unknown_data_statuses():
    from etf_trading.nicegui_app.pages import market

    rows = market._index_atomic_table_rows(
        [
            {"index_code": "000300", "index": "000300 沪深300", "data_status": "computed"},
            {"index_code": "000905", "index": "000905 中证500", "data_status": "unrecognized_status"},
        ]
    )

    assert [row["data_status"] for row in rows] == ["已计算", "未知状态"]


def test_index_trend_summary_exposes_chinese_data_status_and_trading_day_lag():
    from etf_trading.data.indexes import IndexDefinition
    from etf_trading.nicegui_app.state import build_index_trend_summary

    class FakeParquetStore:
        def read_index_prices(self, index_code: str) -> pd.DataFrame:
            dates = pd.bdate_range(end="2026-07-03", periods=300)
            close = pd.Series(range(300), dtype=float) + 100.0
            return pd.DataFrame(
                {
                    "index_code": index_code,
                    "trade_date": dates,
                    "open": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 1_000,
                    "amount": 1_000_000,
                }
            )

    definition = IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300")
    summary = build_index_trend_summary(
        FakeParquetStore(),
        definitions=(definition,),
        today=pd.Timestamp("2026-07-10"),
    )

    assert summary.loc[0, "data_status"] == "行情滞后"
    assert summary.loc[0, "expected_trade_date"] == "2026-07-10"
    assert summary.loc[0, "trading_day_lag"] == 5


def test_build_index_trend_summary_exposes_exact_stale_gap_message(tmp_path):
    from etf_trading.data.indexes import IndexDefinition
    from etf_trading.data.storage import ParquetStore
    from etf_trading.nicegui_app.state import build_index_trend_summary

    store = ParquetStore(tmp_path)
    dates = pd.bdate_range(end="2026-07-09", periods=300)
    close = pd.Series(range(300), dtype=float) + 100.0
    store.write_index_prices(
        "000300",
        pd.DataFrame(
            {
                "index_code": "000300",
                "trade_date": dates,
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000,
                "amount": 1_000_000,
            }
        ),
    )

    summary = build_index_trend_summary(
        store,
        definitions=(IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),),
        today="2026-07-10",
    )

    assert summary.iloc[0]["data_status_message"] == "已更新至 2026-07-09，缺少 2026-07-10 行情。"


def test_market_snapshot_keeps_ready_quotes_for_third_party_baseline_reference(tmp_path):
    from etf_trading.data.indexes import IndexDefinition
    from etf_trading.data.storage import ParquetStore
    from etf_trading.nicegui_app.state import build_index_trend_summary

    store = ParquetStore(tmp_path)
    dates = pd.bdate_range(end="2026-07-10", periods=300)
    close = pd.Series(range(300), dtype=float) + 100.0
    store.write_index_prices(
        "000300",
        pd.DataFrame(
            {
                "index_code": "000300",
                "trade_date": dates,
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000,
                "amount": 1_000_000,
            }
        ),
    )
    definition = IndexDefinition(
        "000300",
        "沪深300",
        "A股",
        "A股宽基",
        "000300",
        index_base_date=date(2005, 4, 8),
        baseline_source="third_party_publication",
        baseline_evidence_kind="publication_date",
        baseline_evidence_name="聚宽",
        baseline_evidence_url="https://www.joinquant.com/data/dict/indexData",
        baseline_checked_at=date(2026, 7, 12),
    )

    row = build_index_trend_summary(store, definitions=(definition,), today="2026-07-10").iloc[0]

    assert row["data_status"] == "数据可用"
    assert row["history_completeness_status"] == "BASELINE_REFERENCED"
    assert row["history_completeness_message"] == (
        "参考起点 2005-04-08（第三方：聚宽，发布日期）；"
        "不用于长周期回测或新开仓。"
    )
    assert bool(row["allows_new_position"]) is False
    assert row["baseline_evidence_url"] == "https://www.joinquant.com/data/dict/indexData"
    assert row["baseline_checked_at"] == "2026-07-12"


def test_market_snapshot_downgrades_persisted_complete_coverage_for_third_party_baseline():
    from etf_trading.data.indexes import IndexDefinition
    from etf_trading.nicegui_app.state import build_index_trend_summary

    class FakeParquetStore:
        def read_index_prices(self, index_code: str) -> pd.DataFrame:
            dates = pd.bdate_range(end="2026-07-10", periods=300)
            close = pd.Series(range(300), dtype=float) + 100.0
            return pd.DataFrame(
                {
                    "index_code": index_code,
                    "trade_date": dates,
                    "open": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 1_000,
                    "amount": 1_000_000,
                }
            )

    definition = IndexDefinition(
        "000300",
        "沪深300",
        "A股",
        "A股宽基",
        "000300",
        index_base_date=date(2005, 4, 8),
        baseline_source="third_party_publication",
        baseline_evidence_kind="publication_date",
        baseline_evidence_name="聚宽",
    )
    coverage = pd.DataFrame(
        {
            "index_code": ["000300"],
            "completeness_status": ["COMPLETE"],
            "completeness_message": ["历史从官方基日开始，数据完整。"],
        }
    )

    row = build_index_trend_summary(
        FakeParquetStore(),
        definitions=(definition,),
        coverage=coverage,
        today="2026-07-10",
    ).iloc[0]

    assert row["data_status"] == "数据可用"
    assert row["history_completeness_status"] == "BASELINE_REFERENCED"
    assert bool(row["allows_new_position"]) is False


def test_market_snapshot_downgrades_persisted_complete_coverage_for_unverified_baseline():
    from etf_trading.data.indexes import IndexDefinition
    from etf_trading.nicegui_app.state import build_index_trend_summary

    class FakeParquetStore:
        def read_index_prices(self, index_code: str) -> pd.DataFrame:
            dates = pd.bdate_range(end="2026-07-10", periods=300)
            close = pd.Series(range(300), dtype=float) + 100.0
            return pd.DataFrame(
                {
                    "index_code": index_code,
                    "trade_date": dates,
                    "open": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 1_000,
                    "amount": 1_000_000,
                }
            )

    definition = IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300")
    coverage = pd.DataFrame(
        {
            "index_code": ["000300"],
            "completeness_status": ["COMPLETE"],
            "completeness_message": ["历史从官方基日开始，数据完整。"],
        }
    )

    row = build_index_trend_summary(
        FakeParquetStore(),
        definitions=(definition,),
        coverage=coverage,
        today="2026-07-10",
    ).iloc[0]

    assert row["data_status"] == "数据可用"
    assert row["history_completeness_status"] == "BASELINE_UNVERIFIED"
    assert bool(row["allows_new_position"]) is False


def test_market_snapshot_keeps_catalog_baseline_status_when_price_read_fails():
    from etf_trading.data.indexes import IndexDefinition
    from etf_trading.nicegui_app.state import build_index_trend_summary

    class UnreadableParquetStore:
        def read_index_prices(self, index_code: str) -> pd.DataFrame:
            raise OSError("价格文件不可读")

    definitions = (
        IndexDefinition(
            "000300",
            "沪深300",
            "A股",
            "A股宽基",
            "000300",
            index_base_date=date(2005, 4, 8),
            baseline_source="third_party_publication",
            baseline_evidence_kind="publication_date",
            baseline_evidence_name="聚宽",
        ),
        IndexDefinition("000905", "中证500", "A股", "A股宽基", "000905"),
    )
    coverage = pd.DataFrame(
        {
            "index_code": ["000300", "000905"],
            "completeness_status": ["COMPLETE", "COMPLETE"],
            "completeness_message": ["历史完整。", "历史完整。"],
        }
    )

    summary = build_index_trend_summary(
        UnreadableParquetStore(),
        definitions=definitions,
        coverage=coverage,
        today="2026-07-10",
    ).set_index("index_code")

    assert summary.loc["000300", "data_status"] == "读取失败"
    assert summary.loc["000300", "history_completeness_status"] == "BASELINE_REFERENCED"
    assert bool(summary.loc["000300", "allows_new_position"]) is False
    assert summary.loc["000905", "history_completeness_status"] == "BASELINE_UNVERIFIED"
    assert bool(summary.loc["000905", "allows_new_position"]) is False


def test_baseline_evidence_task_uses_its_dedicated_summary():
    from etf_trading.nicegui_app.pages import maintenance

    message = maintenance._catalog_task_message(
        "index_baseline_evidence",
        [
            {"evidence_status": "OFFICIAL"},
            {"evidence_status": "THIRD_PARTY_PUBLICATION"},
            {"evidence_status": "UNRESOLVED"},
            {"evidence_status": "REJECTED"},
        ],
    )

    assert message == "已核验 1，第三方参考 1，仍未确认 1，拒绝 1"


def test_index_trend_summary_upgrades_legacy_coverage_baseline_explanation():
    from etf_trading.data.indexes import IndexDefinition
    from etf_trading.nicegui_app.state import build_index_trend_summary

    class FakeParquetStore:
        def read_index_prices(self, index_code: str) -> pd.DataFrame:
            dates = pd.bdate_range(end="2026-07-10", periods=300)
            close = pd.Series(range(300), dtype=float) + 100.0
            return pd.DataFrame(
                {
                    "index_code": index_code,
                    "trade_date": dates,
                    "open": close,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 1_000,
                    "amount": 1_000_000,
                }
            )

    coverage = pd.DataFrame(
        {
            "index_code": ["000300"],
            "local_first_trade_date": ["1990-12-19"],
            "latest_trade_date": ["2026-07-10"],
            "completeness_status": ["BASELINE_UNVERIFIED"],
            "completeness_message": ["基日待核验，不能判定历史完整"],
        }
    )
    summary = build_index_trend_summary(
        FakeParquetStore(),
        definitions=(IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),),
        coverage=coverage,
        today="2026-07-10",
    )

    assert summary.iloc[0]["history_completeness_message"] == (
        "已有 1990-12-19 至 2026-07-10 的行情，但缺少官方基日；"
        "暂时无法判断是否从指数起点完整，不作为交易依据。"
    )


def test_index_trend_summary_upgrades_empty_legacy_missing_history_coverage_message():
    from etf_trading.data.indexes import IndexDefinition
    from etf_trading.nicegui_app.state import build_index_trend_summary

    class FakeParquetStore:
        def read_index_prices(self, index_code: str) -> pd.DataFrame:
            return pd.DataFrame()

    definition = IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300")
    for legacy_message in ("", None):
        coverage = pd.DataFrame(
            {
                "index_code": ["000300"],
                "completeness_status": ["MISSING_HISTORY"],
                "completeness_message": [legacy_message],
            }
        )

        summary = build_index_trend_summary(
            FakeParquetStore(),
            definitions=(definition,),
            coverage=coverage,
            today="2026-07-10",
        )

        assert summary.iloc[0]["history_completeness_message"] == "数据源未返回 000300 的历史行情。"


def test_index_trend_summary_uses_catalog_source_kind_for_legacy_missing_history_coverage():
    from etf_trading.data.index_catalog import default_index_catalog
    from etf_trading.nicegui_app.state import build_index_trend_summary

    class FakeParquetStore:
        def read_index_prices(self, index_code: str) -> pd.DataFrame:
            return pd.DataFrame()

    definition = next(entry.to_index_definition() for entry in default_index_catalog() if entry.index_code == "H30533")
    for legacy_message in ("", "历史数据缺失"):
        coverage = pd.DataFrame(
            {
                "index_code": ["H30533"],
                "completeness_status": ["MISSING_HISTORY"],
                "completeness_message": [legacy_message],
            }
        )

        summary = build_index_trend_summary(
            FakeParquetStore(),
            definitions=(definition,),
            coverage=coverage,
            today="2026-07-10",
        )

        assert summary.iloc[0]["history_completeness_message"] == "港股数据源未返回 H30533 的历史行情。"


def test_index_trend_summary_preserves_current_coverage_explanation():
    from etf_trading.data.indexes import IndexDefinition
    from etf_trading.nicegui_app.state import build_index_trend_summary

    class FakeParquetStore:
        def read_index_prices(self, index_code: str) -> pd.DataFrame:
            return pd.DataFrame()

    current_message = "中证数据源未返回 000300 的历史行情。"
    summary = build_index_trend_summary(
        FakeParquetStore(),
        definitions=(IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),),
        coverage=pd.DataFrame(
            {
                "index_code": ["000300"],
                "completeness_status": ["MISSING_HISTORY"],
                "completeness_message": [current_message],
            }
        ),
        today="2026-07-10",
    )

    assert summary.iloc[0]["history_completeness_message"] == current_message


def test_nicegui_app_factory_imports_without_running_server():
    from etf_trading.nicegui_app.main import create_app, run

    assert callable(create_app)
    assert callable(run)


def test_nicegui_layout_exports_shell_renderer():
    from etf_trading.nicegui_app.layout import render_shell

    assert callable(render_shell)


def test_index_atomic_snapshot_maintenance_runner_is_importable():
    from etf_trading.nicegui_app.maintenance_tasks import IndexAtomicSnapshotMaintenanceRunner

    assert callable(IndexAtomicSnapshotMaintenanceRunner)


def test_nicegui_run_sets_longer_connection_timeouts(monkeypatch):
    from etf_trading.nicegui_app import main

    calls = {}

    def fake_create_app():
        calls["create_app"] = calls.get("create_app", 0) + 1

    def fake_run(**kwargs):
        calls["run_kwargs"] = kwargs

    monkeypatch.setattr(main, "create_app", fake_create_app)
    monkeypatch.setattr(main.ui, "run", fake_run)

    main.run(host="127.0.0.1", port=9000, reload=True)

    assert calls["create_app"] == 1
    assert calls["run_kwargs"]["host"] == "127.0.0.1"
    assert calls["run_kwargs"]["port"] == 9000
    assert calls["run_kwargs"]["reload"] is True
    assert calls["run_kwargs"]["title"] == "ETF 工作台"
    assert calls["run_kwargs"]["reconnect_timeout"] == 60.0


def test_nicegui_topbar_separates_page_calculation_from_source_data_status(monkeypatch):
    from etf_trading.nicegui_app import layout
    from etf_trading.nicegui_app.view_models import PlatformSnapshot

    labels = []

    class FakeElement:
        def __init__(self, text=None):
            self.text = text

        def classes(self, value):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeUi:
        def row(self):
            return FakeElement()

        def label(self, text):
            labels.append(text)
            return FakeElement(text)

        def link(self, text, target):
            labels.append(text)
            return FakeElement(text)

        def icon(self, name):
            return FakeElement(name)

    monkeypatch.setattr(layout, "ui", FakeUi())
    snapshot = PlatformSnapshot(
        master=pd.DataFrame(
            {
                "ETF代码": ["510300", "512880"],
                "本地历史": ["数据可用", "行情滞后"],
                "最新日期": ["2026-07-03", "2026-07-01"],
            }
        ),
        watchlist=pd.DataFrame(),
        index_summary=pd.DataFrame(
            {
                "data_status": ["数据可用", "行情滞后"],
                "latest_date": ["2026-07-03", "2026-07-01"],
            }
        ),
        universe=pd.DataFrame(),
        gaps=pd.DataFrame(),
        coverage=pd.DataFrame(),
        generated_at=datetime(2026, 7, 5, 15, 30),
    )

    layout._render_topbar(snapshot)

    assert "本地量化工作台" in labels
    assert "ETF：1/2 数据可用" in labels
    assert "指数：1/2 数据可用" in labels
    assert "行情有效至 2026-07-03" in labels
    assert "页面计算 2026-07-05 15:30" in labels
    assert not any("数据更新" in label for label in labels)
    assert "NiceGUI" not in labels


def test_nicegui_page_header_places_section_tabs_under_title(monkeypatch):
    from etf_trading.nicegui_app import layout
    from etf_trading.nicegui_app.navigation import NicePageSpec

    calls = []

    class FakeElement:
        def __init__(self, kind, text=None, target=None):
            self.kind = kind
            self.text = text
            self.target = target

        def classes(self, value):
            calls.append((self.kind, self.text, self.target, value))
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeUi:
        def row(self):
            return FakeElement("row")

        def column(self):
            return FakeElement("column")

        def label(self, text):
            return FakeElement("label", text=text)

        def link(self, text, target):
            return FakeElement("link", text=text, target=target)

    monkeypatch.setattr(layout, "ui", FakeUi())
    page = NicePageSpec(
        slug="market",
        label="市场地图",
        caption="观察指数和市场参与状态。",
        sections=("市场总览", "指数买卖参考", "指数K线"),
    )

    layout._render_page_header(page, "指数买卖参考")

    assert ("column", None, None, "workbench-page-header w-full gap-2") in calls
    assert ("row", None, None, "workbench-section-tabs w-full justify-start") in calls
    assert not any(
        kind == "row" and "items-end justify-between" in classes
        for kind, _text, _target, classes in calls
    )
    assert ("link", "指数买卖参考", "/page/market/%E6%8C%87%E6%95%B0%E4%B9%B0%E5%8D%96%E5%8F%82%E8%80%83", "workbench-section-tab is-active") in calls


def test_kline_selector_rows_do_not_split_across_wide_pages():
    import inspect

    from etf_trading.nicegui_app.pages import etf_data, market
    from etf_trading.nicegui_app.theme import WORKBENCH_CSS

    market_source = inspect.getsource(market._render_index_chart)
    etf_source = inspect.getsource(etf_data._render_etf_chart)

    assert "workbench-chart-selector" in market_source
    assert "workbench-chart-selector" in etf_source
    assert "workbench-chart-note" in market_source
    assert "workbench-chart-note" in etf_source
    assert "justify-between" not in market_source
    assert "justify-between" not in etf_source
    assert ".workbench-chart-selector" in WORKBENCH_CSS
    assert ".workbench-chart-note" in WORKBENCH_CSS


def test_atomic_indicator_page_uses_cached_snapshot(monkeypatch):
    from etf_trading.nicegui_app.pages import etf_data
    from etf_trading.nicegui_app.state import AtomicSnapshotCacheResult
    from etf_trading.nicegui_app.view_models import PlatformSnapshot

    calls = []
    labels = []
    table_rows = []
    tables = []
    toggle_values = []

    class FakeProps:
        def __init__(self, owner):
            self.owner = owner
            self.values = {}

        def __call__(self, value):
            return self.owner

        def __setitem__(self, key, value):
            self.values[key] = value

    class FakeElement:
        def __init__(self, value=None, options=None):
            self.value = value
            self.options = options or []
            self.props = FakeProps(self)

        def classes(self, value):
            return self

        def on_value_change(self, handler):
            return self

        def on(self, event_name, handler):
            self.event_name = event_name
            self.handler = handler
            return self

        def clear(self):
            return None

        def update(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def input(self, label):
            return FakeElement(value="")

        def select(self, options, value=None, label=None):
            return FakeElement(value=value, options=options)

        def toggle(self, options, value=None):
            toggle_values.append((tuple(options), value))
            return FakeElement(value=value, options=options)

        def number(self, label, value=None, format=None):
            return FakeElement(value=value)

        def checkbox(self, label, value=False):
            return FakeElement(value=value)

        def button(self, label, icon=None, on_click=None):
            return FakeElement()

        def link(self, label, target):
            return FakeElement()

        def label(self, text):
            labels.append(text)
            return FakeElement()

        def icon(self, name):
            return FakeElement()

        def badge(self, text):
            labels.append(text)
            return FakeElement()

        def table(self, columns, rows, row_key=None, pagination=None):
            table = FakeElement()
            table.row_key = row_key
            tables.append(table)
            table_rows.extend(rows)
            return table

        def notify(self, message, type=None):
            return None

    frame = pd.DataFrame(
        {
            "etf_code": ["510300", "512880"],
            "name": ["???300ETF", "???ETF"],
            "category": ["A?????", "???"],
            "exchange": ["SSE", "SSE"],
            "history_status": ["complete", "complete"],
            "feature_status": ["complete", "complete"],
            "latest_trade_date": ["2026-07-03", "2026-07-03"],
            "history_rows": [520, 520],
            "return_20": [0.05, 0.03],
            "return_60": [0.08, 0.04],
            "return_20_rank_all": [1, 2],
            "return_60_rank_all": [1, 2],
            "return_20_rank_category": [1, 1],
            "return_60_rank_category": [1, 1],
            "close_above_ma20": [True, True],
            "ma20_above_ma60": [True, False],
            "close_above_ma60": [True, True],
            "weekly_close_above_ma10": [True, False],
            "weekly_close_above_ma30": [False, False],
            "avg_amount_5": [2_000_000, 1_500_000],
            "avg_amount_20": [1_800_000, 1_400_000],
            "amount_ratio_5_20": [1.11, 1.05],
            "distance_ma20_pct": [0.02, 0.01],
            "distance_ma20_atr": [1.2, 0.8],
            "ma60_slope_20": [0.015, 0.008],
            "is_60d_close_breakout": [False, True],
            "missing_feature_names": ["", ""],
        }
    )

    def fake_cached(master, parquet_store, *, force_refresh=False):
        calls.append(force_refresh)
        return AtomicSnapshotCacheResult(frame=frame, status="ready", generated_at=datetime(2026, 7, 5, 12, 0, 0))

    monkeypatch.setattr(etf_data, "ui", FakeUi())
    monkeypatch.setattr(etf_data, "load_atomic_snapshot_cached", fake_cached, raising=False)
    monkeypatch.setattr(
        etf_data,
        "build_atomic_indicator_snapshot",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("sync atomic builder should not run in page render")),
        raising=False,
    )
    snapshot = PlatformSnapshot(
        master=pd.DataFrame({"ETF\u4ee3\u7801": ["510300"]}),
        watchlist=pd.DataFrame(),
        index_summary=pd.DataFrame(),
        universe=pd.DataFrame(),
        gaps=pd.DataFrame(),
        coverage=pd.DataFrame(),
        generated_at=datetime(2026, 7, 5, 12, 0, 0),
    )

    etf_data._render_atomic_indicators(snapshot, object())

    assert calls == [False]
    assert toggle_values == [(("\u673a\u4f1a\u7279\u5f81", "\u4f53\u68c0\u7279\u5f81"), "\u673a\u4f1a\u7279\u5f81")]
    assert tables[0].props.values["rows-per-page-label"] == "\u6bcf\u9875\u884c\u6570"
    assert tables[0].row_key == "ETF代码"
    assert table_rows[0]["ETF\u4ee3\u7801"] == "510300"
    assert tuple(table_rows[0].keys()) == (
        "ETF\u4ee3\u7801",
        "ETF\u540d\u79f0",
        "\u5206\u7c7b",
        "20\u65e5\u6536\u76ca",
        "60\u65e5\u6536\u76ca",
        "20\u65e5\u5168\u6c60\u6392\u540d",
        "60\u65e5\u5168\u6c60\u6392\u540d",
        "20\u65e5\u540c\u7c7b\u6392\u540d",
        "60\u65e5\u540c\u7c7b\u6392\u540d",
        "60\u65e5\u7a81\u7834",
        "\u5468\u7ebf>10\u5468",
        "20\u65e5\u6210\u4ea4\u989d",
    )
    assert "\u539f\u5b50\u6307\u6807\u8be6\u60c5\uff1a510300" in labels
    assert {"\u8eab\u4efd\u4fe1\u606f", "\u6570\u636e\u4f53\u68c0", "\u76f8\u5bf9\u5f3a\u5ea6", "\u8d8b\u52bf\u7ed3\u6784", "\u91cf\u80fd\u4f4d\u7f6e", "\u504f\u79bb\u7a0b\u5ea6"}.issubset(set(labels))
    assert len(tables) == 1
    assert "ETF检查器" in labels
    assert "20日收益" in labels
    assert "8.0%" in labels
    tables[0].handler(type("Event", (), {"args": {"row": {"ETF\u4ee3\u7801": "512880"}}})())
    assert "\u539f\u5b50\u6307\u6807\u8be6\u60c5\uff1a512880" in labels
    assert "3.0%" in labels


def test_atomic_indicator_page_renders_data_health_and_filters_from_summary(monkeypatch):
    from etf_trading.nicegui_app.pages import etf_data
    from etf_trading.nicegui_app.state import AtomicSnapshotCacheResult
    from etf_trading.nicegui_app.view_models import PlatformSnapshot

    labels = []
    table_batches = []
    health_actions = {}
    select_by_label = {}

    class FakeProps:
        def __init__(self, owner):
            self.owner = owner
            self.values = {}

        def __call__(self, value):
            self.values[str(value)] = True
            return self.owner

        def __setitem__(self, key, value):
            self.values[key] = value

    class FakeElement:
        def __init__(self, value=None, options=None, label=None):
            self.value = value
            self.options = options or []
            self.label = label
            self.props = FakeProps(self)

        def classes(self, value):
            return self

        def on_value_change(self, handler):
            self.value_handler = handler
            return self

        def on(self, event_name, handler):
            self.event_name = event_name
            self.handler = handler
            return self

        def clear(self):
            return None

        def update(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def element(self, tag):
            return FakeElement()

        def input(self, label):
            return FakeElement(value="", label=label)

        def select(self, options, value=None, label=None):
            element = FakeElement(value=value, options=options, label=label)
            if label:
                select_by_label[label] = element
            return element

        def toggle(self, options, value=None):
            return FakeElement(value=value, options=options)

        def number(self, label, value=None, format=None):
            return FakeElement(value=value, label=label)

        def checkbox(self, label, value=False):
            return FakeElement(value=value, label=label)

        def button(self, label, icon=None, on_click=None):
            if label.startswith("行情滞后"):
                health_actions["行情滞后"] = on_click
            if label.startswith("特征缺失"):
                health_actions["特征缺失"] = on_click
            return FakeElement(label=label)

        def link(self, label, target):
            labels.append(f"{label}->{target}")
            return FakeElement(label=label)

        def label(self, text):
            labels.append(str(text))
            return FakeElement(label=str(text))

        def icon(self, name):
            return FakeElement(label=name)

        def badge(self, text):
            labels.append(str(text))
            return FakeElement(label=str(text))

        def table(self, columns, rows, row_key=None, pagination=None):
            table_batches.append(list(rows))
            table = FakeElement()
            table.row_key = row_key
            return table

        def notify(self, message, type=None):
            return None

    frame = pd.DataFrame(
        {
            "etf_code": ["510300", "512880", "159915"],
            "name": ["沪深300ETF", "证券ETF", "创业板ETF"],
            "category": ["A股宽基", "A股行业", "A股宽基"],
            "exchange": ["SSE", "SSE", "SZSE"],
            "history_status": ["complete", "stale", "short_history"],
            "feature_status": ["complete", "complete", "missing_features"],
            "latest_trade_date": ["2026-07-08", "2026-07-03", "2026-07-08"],
            "history_rows": [520, 520, 120],
            "return_20": [0.05, 0.03, None],
            "return_60": [0.08, 0.04, None],
            "return_20_rank_all": [1, 2, None],
            "return_60_rank_all": [1, 2, None],
            "return_20_rank_category": [1, 1, None],
            "return_60_rank_category": [1, 1, None],
            "close_above_ma20": [True, True, None],
            "ma20_above_ma60": [True, False, None],
            "close_above_ma60": [True, True, None],
            "weekly_close_above_ma10": [True, False, None],
            "weekly_close_above_ma30": [False, False, None],
            "avg_amount_5": [2_000_000, 1_500_000, None],
            "avg_amount_20": [1_800_000, 1_400_000, None],
            "amount_ratio_5_20": [1.11, 1.05, None],
            "distance_ma20_pct": [0.02, 0.01, None],
            "distance_ma20_atr": [1.2, 0.8, None],
            "ma60_slope_20": [0.015, 0.008, None],
            "is_60d_close_breakout": [False, True, None],
            "missing_feature_names": ["", "", "return_60"],
        }
    )

    monkeypatch.setattr(etf_data, "ui", FakeUi())
    monkeypatch.setattr(
        etf_data,
        "load_atomic_snapshot_cached",
        lambda master, parquet_store, *, force_refresh=False: AtomicSnapshotCacheResult(frame=frame, status="ready"),
        raising=False,
    )
    snapshot = PlatformSnapshot(
        master=pd.DataFrame({"ETF代码": ["510300", "512880", "159915"]}),
        watchlist=pd.DataFrame(),
        index_summary=pd.DataFrame(),
        universe=pd.DataFrame(),
        gaps=pd.DataFrame(),
        coverage=pd.DataFrame(),
        generated_at=datetime(2026, 7, 8, 12, 0, 0),
    )

    etf_data._render_atomic_indicators(snapshot, object())

    assert "数据更新体检" in labels
    assert "主状态互斥统计每只 ETF 一次；特征缺失是附加诊断。行情滞后或历史不足的数据不会进入机会排名。" in labels
    assert any(text.startswith("去补齐任务->/page/maintenance/") for text in labels)
    assert "行情滞后" in health_actions
    assert "特征缺失" in health_actions

    health_actions["行情滞后"]()

    assert select_by_label["历史状态"].value == "行情滞后"
    assert select_by_label["特征状态"].value == "全部特征状态"
    assert [row["ETF代码"] for row in table_batches[-1]] == ["512880"]

    health_actions["特征缺失"]()

    assert select_by_label["特征状态"].value == "特征缺失"
    assert select_by_label["历史状态"].value == "全部历史状态"
    assert [row["ETF代码"] for row in table_batches[-1]] == ["159915"]


def test_atomic_indicator_refresh_rebuilds_filter_options_for_health_actions(monkeypatch):
    from etf_trading.nicegui_app.pages import etf_data
    from etf_trading.nicegui_app.state import AtomicSnapshotCacheResult
    from etf_trading.nicegui_app.view_models import PlatformSnapshot

    health_actions = {}
    select_by_label = {}
    refresh_actions = []
    table_batches = []

    class FakeProps:
        def __init__(self, owner):
            self.owner = owner
            self.values = {}

        def __call__(self, value):
            self.values[str(value)] = True
            return self.owner

        def __setitem__(self, key, value):
            self.values[key] = value

    class FakeElement:
        def __init__(self, value=None, options=None, label=None):
            self.value = value
            self.options = options or []
            self.label = label
            self.props = FakeProps(self)

        def classes(self, value):
            return self

        def on_value_change(self, handler):
            self.value_handler = handler
            return self

        def on(self, event_name, handler):
            self.event_name = event_name
            self.handler = handler
            return self

        def clear(self):
            return None

        def update(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def element(self, tag):
            return FakeElement()

        def input(self, label):
            return FakeElement(value="", label=label)

        def select(self, options, value=None, label=None):
            element = FakeElement(value=value, options=options, label=label)
            if label:
                select_by_label[label] = element
            return element

        def toggle(self, options, value=None):
            return FakeElement(value=value, options=options)

        def number(self, label, value=None, format=None):
            return FakeElement(value=value, label=label)

        def checkbox(self, label, value=False):
            return FakeElement(value=value, label=label)

        def button(self, label, icon=None, on_click=None):
            if label == "刷新快照":
                refresh_actions.append(on_click)
            if label.startswith("行情滞后"):
                health_actions["行情滞后"] = on_click
            if label.startswith("特征缺失"):
                health_actions["特征缺失"] = on_click
            return FakeElement(label=label)

        def link(self, label, target):
            return FakeElement(label=label)

        def label(self, text):
            return FakeElement(label=str(text))

        def icon(self, name):
            return FakeElement(label=name)

        def badge(self, text):
            return FakeElement(label=str(text))

        def table(self, columns, rows, row_key=None, pagination=None):
            table_batches.append(list(rows))
            table = FakeElement()
            table.row_key = row_key
            return table

        def notify(self, message, type=None):
            return None

    empty_frame = pd.DataFrame()
    populated_frame = pd.DataFrame(
        {
            "etf_code": ["512880", "159915"],
            "name": ["证券ETF", "创业板ETF"],
            "category": ["A股行业", "A股宽基"],
            "exchange": ["SSE", "SZSE"],
            "history_status": ["stale", "complete"],
            "feature_status": ["complete", "missing_features"],
            "latest_trade_date": ["2026-07-03", "2026-07-08"],
            "history_rows": [520, 520],
            "return_20": [0.03, None],
            "return_60": [0.04, None],
            "return_20_rank_all": [2, None],
            "return_60_rank_all": [2, None],
            "return_20_rank_category": [1, None],
            "return_60_rank_category": [1, None],
            "close_above_ma20": [True, None],
            "ma20_above_ma60": [False, None],
            "close_above_ma60": [True, None],
            "weekly_close_above_ma10": [False, None],
            "weekly_close_above_ma30": [False, None],
            "avg_amount_5": [1_500_000, None],
            "avg_amount_20": [1_400_000, None],
            "amount_ratio_5_20": [1.05, None],
            "distance_ma20_pct": [0.01, None],
            "distance_ma20_atr": [0.8, None],
            "ma60_slope_20": [0.008, None],
            "is_60d_close_breakout": [True, None],
            "missing_feature_names": ["", "return_60"],
        }
    )
    cache_results = iter(
        [
            AtomicSnapshotCacheResult(frame=empty_frame, status="building"),
            AtomicSnapshotCacheResult(frame=populated_frame, status="ready"),
        ]
    )

    monkeypatch.setattr(etf_data, "ui", FakeUi())
    monkeypatch.setattr(
        etf_data,
        "load_atomic_snapshot_cached",
        lambda master, parquet_store, *, force_refresh=False: next(cache_results),
        raising=False,
    )
    snapshot = PlatformSnapshot(
        master=pd.DataFrame({"ETF代码": ["512880", "159915"]}),
        watchlist=pd.DataFrame(),
        index_summary=pd.DataFrame(),
        universe=pd.DataFrame(),
        gaps=pd.DataFrame(),
        coverage=pd.DataFrame(),
        generated_at=datetime(2026, 7, 8, 12, 0, 0),
    )

    etf_data._render_atomic_indicators(snapshot, object())

    assert refresh_actions

    refresh_actions[0]()

    assert "行情滞后" in select_by_label["历史状态"].options
    assert "特征缺失" in select_by_label["特征状态"].options
    assert "行情滞后" in health_actions
    assert "特征缺失" in health_actions

    health_actions["行情滞后"]()

    assert select_by_label["历史状态"].value == "行情滞后"
    assert select_by_label["特征状态"].value == "全部特征状态"
    assert [row["ETF代码"] for row in table_batches[-1]] == ["512880"]

    health_actions["特征缺失"]()

    assert select_by_label["特征状态"].value == "特征缺失"
    assert select_by_label["历史状态"].value == "全部历史状态"
    assert [row["ETF代码"] for row in table_batches[-1]] == ["159915"]


def test_atomic_filter_label_returns_display_label_for_internal_value():
    from etf_trading.nicegui_app.pages.etf_data import _atomic_filter_label

    options = {"全部历史状态": "全部历史状态", "行情滞后": "stale"}

    assert _atomic_filter_label(options, "stale") == "行情滞后"
    assert _atomic_filter_label(options, "missing_history") == ""


def test_atomic_row_click_event_extracts_etf_code():
    from etf_trading.nicegui_app.pages.etf_data import _event_row_code

    class Event:
        def __init__(self, args):
            self.args = args

    assert _event_row_code(Event([None, {"ETF代码": "510300"}])) == "510300"
    assert _event_row_code(Event({"row": {"ETF代码": "512880"}})) == "512880"
    assert _event_row_code(Event({"ETF代码": "159915"})) == "159915"
    assert _event_row_code(Event([])) == ""
