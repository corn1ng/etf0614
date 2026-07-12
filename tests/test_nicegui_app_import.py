from datetime import datetime

import pandas as pd


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


def test_index_health_page_uses_cached_snapshot(monkeypatch):
    from etf_trading.nicegui_app.pages import market
    from etf_trading.nicegui_app.state import IndexHealthSnapshotCacheResult
    from etf_trading.nicegui_app.view_models import PlatformSnapshot

    calls = []
    labels = []
    table_batches = []

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

        def props(self, value):
            return self

        def on_value_change(self, handler):
            return self

        def on(self, event_name, handler):
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

        def button(self, label, icon=None, on_click=None):
            return FakeElement()

        def label(self, text):
            labels.append(str(text))
            return FakeElement()

        def icon(self, name):
            return FakeElement()

        def table(self, columns, rows, row_key=None, pagination=None):
            table_batches.append(list(rows))
            return FakeElement()

        def notify(self, message, type=None):
            return None

    summary = pd.DataFrame(
        {
            "index_code": ["000300"],
            "index_name": ["沪深300"],
            "market": ["A股"],
            "category": ["A股宽基"],
            "latest_date": ["2026-07-03"],
            "data_status": ["数据可用"],
            "history_rows": [900],
            "large_trend": ["UP"],
            "medium_trend": ["UP"],
            "small_trend": ["PULLBACK"],
            "allows_new_position": [True],
            "trend_health_status": ["normal"],
            "trend_health_reason": ["趋势门槛通过"],
            "valuation_overview_label": ["mid_percentile"],
            "valuation_health_status": ["complete"],
            "valuation_health_reason": ["核心估值可用"],
            "valuation_latest_date": ["2026-07-03"],
            "valuation_coverage_years": [3.1],
            "valuation_primary_source": ["unit"],
        }
    )
    details = pd.DataFrame(
        {
            "index_code": ["000300", "000300"],
            "detail_kind": ["trend", "valuation"],
            "metric_name": ["large_trend", "pe_ttm"],
            "metric_label": ["大趋势", "市盈率TTM"],
            "current_value": ["UP", 12.5],
            "status": ["normal", "computed"],
            "reason": ["大趋势向上", "已计算历史分位"],
            "display_direction": ["higher_is_better", "higher_is_more_expensive"],
            "historical_percentile": [pd.NA, 42.0],
            "window_years": [pd.NA, 3.1],
            "first_date": ["2022-01-03", "2023-01-03"],
            "latest_date": ["2026-07-03", "2026-07-03"],
            "sample_count": [900, 800],
            "data_source": ["unit", "unit"],
        }
    )

    def fake_cached(parquet_store, definitions=None, *, coverage=None, force_refresh=False):
        calls.append(force_refresh)
        return IndexHealthSnapshotCacheResult(summary=summary, details=details, status="ready", generated_at=datetime(2026, 7, 6, 10, 0, 0))

    monkeypatch.setattr(market, "ui", FakeUi())
    monkeypatch.setattr(market, "load_index_health_snapshot_cached", fake_cached, raising=False)
    snapshot = PlatformSnapshot(
        master=pd.DataFrame(),
        watchlist=pd.DataFrame(),
        index_summary=summary,
        universe=pd.DataFrame(),
        gaps=pd.DataFrame(),
        coverage=pd.DataFrame(),
        generated_at=datetime(2026, 7, 6, 10, 0, 0),
    )

    market._render_index_health(snapshot, object())

    assert calls == [False]
    assert table_batches[0][0]["index_code"] == "000300"
    assert "指数数据状态：指数：1/1 数据可用；最近有效交易日 2026-07-03。非“数据可用”的指数不应作为趋势或买卖依据。" in labels
    assert "趋势原子指标：000300" in labels
    assert "估值原子指标：000300" in labels
