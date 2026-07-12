from contextlib import nullcontext
from types import SimpleNamespace

import pandas as pd

from etf_trading.ui import app
from etf_trading.ui.navigation import (
    PAGE_SPECS,
    default_page,
    default_section,
    get_page_by_label,
    page_labels,
    resolve_section,
    section_options,
)


def test_primary_navigation_follows_investment_workflow():
    assert page_labels() == ["今日行动", "市场地图", "ETF数据", "策略实验室", "数据维护"]
    assert [page.slug for page in PAGE_SPECS] == ["decision", "market", "portfolio", "research", "data"]


def test_price_scale_options_are_ordered_by_investment_workflow():
    assert list(app.PRICE_SCALE_OPTIONS.items()) == [
        ("价格走势 Price", "normal"),
        ("累计涨跌幅 Return %", "percent"),
        ("回撤风险 Drawdown %", "drawdown"),
        ("回到低点需跌幅 Down to Low %", "downside"),
        ("对数收益 Log Return %", "log_return"),
    ]


def test_each_page_exposes_expected_secondary_sections():
    sections_by_label = {page.label: section_options(page) for page in PAGE_SPECS}

    assert sections_by_label["今日行动"] == ["行动摘要", "每日建议", "计算池明细"]
    assert sections_by_label["市场地图"] == ["市场总览", "指数买卖参考", "指数K线"]
    assert sections_by_label["ETF数据"] == ["ETF总览", "ETF行情", "搜索加入", "每日计算池", "指数样本池"]
    assert sections_by_label["策略实验室"] == [
        "策略库",
        "新建策略",
        "运行回测",
        "策略比较",
        "ETF复盘",
        "指数过滤实验",
    ]
    assert sections_by_label["数据维护"] == ["数据总览", "缺口明细", "补齐任务", "日志与设置"]


def test_navigation_defaults_to_daily_action_summary():
    page = default_page()

    assert page.label == "今日行动"
    assert default_section(page) == "行动摘要"


def test_unknown_page_and_section_fall_back_to_safe_defaults():
    page = get_page_by_label("不存在")

    assert page.label == "今日行动"
    assert resolve_section(page, "不存在") == "行动摘要"


def test_render_page_header_outputs_compact_markup(monkeypatch):
    from etf_trading.ui.navigation import PageSpec, render_page_header

    rendered = {}

    def capture_markdown(body, *, unsafe_allow_html=False):
        rendered["body"] = body
        rendered["unsafe"] = unsafe_allow_html

    monkeypatch.setattr("etf_trading.ui.navigation.st.markdown", capture_markdown)
    page = PageSpec(
        slug="market",
        label="市场地图",
        caption="观察指数和市场参与状态。",
        sections=("指数买卖参考",),
    )

    render_page_header(page)

    assert rendered["unsafe"] is True
    assert 'class="workbench-page-header"' in rendered["body"]
    assert 'class="workbench-page-header__title"' in rendered["body"]
    assert 'class="workbench-page-header__caption"' in rendered["body"]
    assert "市场地图" in rendered["body"]
    assert "观察指数和市场参与状态。" in rendered["body"]


def test_research_secondary_navigation_is_not_overridden_by_sticky_auxiliary_tool(monkeypatch):
    calls = {"run_controls": 0, "explorer": 0}

    class FakeMetricColumn:
        def metric(self, *args, **kwargs):
            return None

    monkeypatch.setattr(app, "_inject_research_styles", lambda: None)
    monkeypatch.setattr(app, "_research_job_manager", lambda: object())
    monkeypatch.setattr(app, "_build_index_trend_summary", lambda parquet_store: pd.DataFrame({"allows_new_position": [True]}))
    monkeypatch.setattr(app, "_eligible_index_categories", lambda index_summary: ["A股宽基"])
    monkeypatch.setattr(app, "_filter_etf_codes_by_categories", lambda master, categories: ["510300"])
    monkeypatch.setattr(app, "_render_research_job_status", lambda job_manager: None)
    monkeypatch.setattr(
        app,
        "_render_strategy_lab_run_controls",
        lambda **kwargs: calls.__setitem__("run_controls", calls["run_controls"] + 1),
    )
    monkeypatch.setattr(
        app,
        "_render_index_filter_explorer",
        lambda index_summary, parquet_store: calls.__setitem__("explorer", calls["explorer"] + 1),
    )
    monkeypatch.setattr(app.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "columns", lambda size: [FakeMetricColumn() for _ in range(size)])
    monkeypatch.setattr(app.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "selectbox", lambda *args, **kwargs: "指数过滤")
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: nullcontext())
    store = SimpleNamespace(list_etf_master=lambda: pd.DataFrame({"etf_code": []}))

    app._tab_research(store, object(), research_view="运行回测")

    assert calls["run_controls"] == 1


def test_main_reuses_platform_status_for_decision_page(monkeypatch):
    decision_page = next(page for page in PAGE_SPECS if page.slug == "decision")
    status = {
        "index_summary": pd.DataFrame({"allows_new_position": []}),
        "eligible_categories": [],
        "watchlist": pd.DataFrame(),
        "enabled_watchlist": pd.DataFrame(),
        "issues": [],
        "eligible_index_count": 0,
    }
    calls = {"platform_status": 0}
    header_calls = {"page_header": 0}

    def fake_platform_status(store, parquet_store):
        calls["platform_status"] += 1
        return status

    monkeypatch.setattr(app.st, "set_page_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "inject_global_styles", lambda: None)
    monkeypatch.setattr(app, "_store", lambda: object())
    monkeypatch.setattr(app, "_parquet", lambda: object())
    monkeypatch.setattr(app, "InitializationService", lambda **kwargs: object())
    monkeypatch.setattr(app, "render_primary_navigation", lambda: decision_page)
    monkeypatch.setattr(app, "render_secondary_navigation", lambda page: page.sections[1])
    monkeypatch.setattr(
        app,
        "render_page_header",
        lambda page: header_calls.__setitem__("page_header", header_calls["page_header"] + 1),
        raising=False,
    )
    monkeypatch.setattr(app, "_platform_status", fake_platform_status)
    monkeypatch.setattr(app, "summarize_platform_status", lambda current_status: object())
    monkeypatch.setattr(app, "render_top_status_bar", lambda summary: None)
    monkeypatch.setattr(app, "render_status_cards", lambda current_status: None)
    monkeypatch.setattr(app, "render_next_steps", lambda current_status: None)
    monkeypatch.setattr(app, "_build_daily_advice_report", lambda store, parquet_store: None)
    monkeypatch.setattr(app.decision.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.decision.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.decision.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.decision.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.decision.st, "markdown", lambda *args, **kwargs: None)

    app.main()

    assert calls["platform_status"] == 1
    assert header_calls["page_header"] == 1


def test_main_reuses_precomputed_index_summary_for_market_page(monkeypatch):
    market_page = next(page for page in PAGE_SPECS if page.slug == "market")
    status = {
        "index_summary": pd.DataFrame({"index_code": ["000300"], "allows_new_position": [True]}),
        "eligible_categories": [],
        "watchlist": pd.DataFrame(),
        "enabled_watchlist": pd.DataFrame(),
        "issues": [],
        "eligible_index_count": 1,
    }
    calls = {"build_index_summary": 0}

    def fake_build_index_summary(parquet_store):
        calls["build_index_summary"] += 1
        return status["index_summary"]

    monkeypatch.setattr(app.st, "set_page_config", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "title", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "inject_global_styles", lambda: None)
    monkeypatch.setattr(app, "_store", lambda: object())
    monkeypatch.setattr(app, "_parquet", lambda: object())
    monkeypatch.setattr(app, "InitializationService", lambda **kwargs: object())
    monkeypatch.setattr(app, "render_primary_navigation", lambda: market_page)
    monkeypatch.setattr(app, "render_secondary_navigation", lambda page: page.sections[0])
    monkeypatch.setattr(app, "_platform_status", lambda store, parquet_store: status)
    monkeypatch.setattr(app, "summarize_platform_status", lambda current_status: object())
    monkeypatch.setattr(app, "render_top_status_bar", lambda summary: None)
    monkeypatch.setattr(app, "_build_index_trend_summary", fake_build_index_summary)
    monkeypatch.setattr(app, "_render_index_filter_explorer", lambda index_summary, parquet_store: None)
    monkeypatch.setattr(app, "_tab_chart", lambda store, parquet_store: None)
    monkeypatch.setattr(app, "_tab_index_watch", lambda parquet_store: None)

    app.main()

    assert calls["build_index_summary"] == 0


def test_page_modules_do_not_render_duplicate_page_titles(monkeypatch):
    calls = {"subheader": 0, "caption": 0}

    def count_subheader(*args, **kwargs):
        calls["subheader"] += 1

    def count_caption(*args, **kwargs):
        calls["caption"] += 1

    monkeypatch.setattr(app.decision.st, "subheader", count_subheader)
    monkeypatch.setattr(app.decision.st, "caption", count_caption)
    monkeypatch.setattr(app.decision.st, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.decision.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.decision.st, "markdown", lambda *args, **kwargs: None)

    status = {
        "index_summary": pd.DataFrame(),
        "eligible_categories": [],
        "watchlist": pd.DataFrame(),
        "enabled_watchlist": pd.DataFrame(),
        "issues": [],
        "eligible_index_count": 0,
    }

    app.decision.render(
        store=object(),
        parquet_store=object(),
        view="每日建议",
        status=status,
        render_status_cards=lambda current_status: None,
        render_next_steps=lambda current_status: None,
        index_trend_display_frame=lambda frame: frame,
        render_research_table=lambda frame, height=None: None,
        build_daily_advice_report=lambda store, parquet_store: None,
        watchlist_status_frame=lambda watchlist, parquet_store: watchlist,
    )

    assert calls["subheader"] == 0
    assert calls["caption"] == 0


def test_market_page_routes_index_decision_views():
    calls = {"overview": 0, "explorer": 0, "index_watch": 0}
    index_summary = pd.DataFrame({"index_code": ["000300"], "allows_new_position": [True]})

    app.market.render(
        store=object(),
        parquet_store=object(),
        view="市场总览",
        index_summary=index_summary,
        render_market_overview=lambda frame: calls.__setitem__("overview", calls["overview"] + 1),
        render_index_filter_explorer=lambda frame, parquet_store: calls.__setitem__("explorer", calls["explorer"] + 1),
        render_index_watch=lambda parquet_store: calls.__setitem__("index_watch", calls["index_watch"] + 1),
    )
    app.market.render(
        store=object(),
        parquet_store=object(),
        view="指数买卖参考",
        index_summary=index_summary,
        render_market_overview=lambda frame: calls.__setitem__("overview", calls["overview"] + 1),
        render_index_filter_explorer=lambda frame, parquet_store: calls.__setitem__("explorer", calls["explorer"] + 1),
        render_index_watch=lambda parquet_store: calls.__setitem__("index_watch", calls["index_watch"] + 1),
    )
    app.market.render(
        store=object(),
        parquet_store=object(),
        view="指数K线",
        index_summary=index_summary,
        render_market_overview=lambda frame: calls.__setitem__("overview", calls["overview"] + 1),
        render_index_filter_explorer=lambda frame, parquet_store: calls.__setitem__("explorer", calls["explorer"] + 1),
        render_index_watch=lambda parquet_store: calls.__setitem__("index_watch", calls["index_watch"] + 1),
    )

    assert calls == {"overview": 1, "explorer": 1, "index_watch": 1}


def test_portfolio_page_routes_etf_data_views():
    calls = {"overview": 0, "chart": 0, "index_pool": 0}
    store = SimpleNamespace(list_watchlist=lambda: pd.DataFrame({"etf_code": ["510300"]}))
    parquet_store = object()

    app.portfolio.render(
        store=store,
        parquet_store=parquet_store,
        view="ETF总览",
        render_data_overview=lambda store, parquet_store: calls.__setitem__("overview", calls["overview"] + 1),
        render_etf_chart=lambda store, parquet_store: calls.__setitem__("chart", calls["chart"] + 1),
        render_index_etf_pool=lambda store, parquet_store: calls.__setitem__("index_pool", calls["index_pool"] + 1),
        render_search_and_add=lambda store: None,
        watchlist_status_frame=lambda watchlist, parquet_store: watchlist,
    )

    app.portfolio.render(
        store=store,
        parquet_store=parquet_store,
        view="ETF行情",
        render_data_overview=lambda store, parquet_store: calls.__setitem__("overview", calls["overview"] + 1),
        render_etf_chart=lambda store, parquet_store: calls.__setitem__("chart", calls["chart"] + 1),
        render_index_etf_pool=lambda store, parquet_store: calls.__setitem__("index_pool", calls["index_pool"] + 1),
        render_search_and_add=lambda store: None,
        watchlist_status_frame=lambda watchlist, parquet_store: watchlist,
    )

    app.portfolio.render(
        store=store,
        parquet_store=parquet_store,
        view="指数样本池",
        render_data_overview=lambda store, parquet_store: calls.__setitem__("overview", calls["overview"] + 1),
        render_etf_chart=lambda store, parquet_store: calls.__setitem__("chart", calls["chart"] + 1),
        render_index_etf_pool=lambda store, parquet_store: calls.__setitem__("index_pool", calls["index_pool"] + 1),
        render_search_and_add=lambda store: None,
        watchlist_status_frame=lambda watchlist, parquet_store: watchlist,
    )

    assert calls == {"overview": 1, "chart": 1, "index_pool": 1}


def test_market_overview_summarizes_index_state(monkeypatch):
    metrics = []
    dataframe_calls = []

    class FakeMetricColumn:
        def metric(self, label, value):
            metrics.append((label, value))

    summary = pd.DataFrame(
        {
            "index_code": ["000300", "000905", "399006"],
            "category": ["A股宽基", "A股宽基", "A股成长"],
            "allows_new_position": [True, False, True],
        }
    )

    monkeypatch.setattr(app.st, "columns", lambda count: [FakeMetricColumn() for _ in range(count)])
    monkeypatch.setattr(app.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "dataframe", lambda frame, *args, **kwargs: dataframe_calls.append(frame.copy()))
    monkeypatch.setattr(app, "_render_research_table", lambda frame, height=None: dataframe_calls.append(frame.copy()))
    monkeypatch.setattr(app, "_index_trend_display_frame", lambda frame: frame[["index_code", "allows_new_position"]])

    app._render_market_overview(summary)

    assert metrics == [
        ("指数总数", "3"),
        ("可找买点", "2"),
        ("暂不参与", "1"),
        ("覆盖分类", "2"),
    ]
    category_frame = dataframe_calls[0]
    assert category_frame.to_dict("records") == [
        {"分类": "A股宽基", "指数数量": 2, "可参与数量": 1},
        {"分类": "A股成长", "指数数量": 1, "可参与数量": 1},
    ]


def test_market_overview_handles_empty_index_summary(monkeypatch):
    info_calls = []

    monkeypatch.setattr(app.st, "info", lambda body: info_calls.append(body))

    app._render_market_overview(pd.DataFrame())

    assert info_calls == ["暂无指数趋势数据。请到“数据维护 -> 补齐任务”补齐指数历史。"]


def test_data_maintenance_routes_data_console_views():
    calls = {"overview": 0, "gaps": 0, "repair": 0, "settings": 0}
    store = object()
    parquet_store = object()
    service = object()
    status = {}

    for view in ["数据总览", "缺口明细", "补齐任务", "日志与设置"]:
        app.data_maintenance.render(
            store=store,
            parquet_store=parquet_store,
            service=service,
            view=view,
            status=status,
            render_data_overview=lambda store, parquet_store, status: calls.__setitem__("overview", calls["overview"] + 1),
            render_gap_detail=lambda store, parquet_store, status: calls.__setitem__("gaps", calls["gaps"] + 1),
            render_repair_tasks=lambda store, parquet_store: calls.__setitem__("repair", calls["repair"] + 1),
            render_settings=lambda store, service: calls.__setitem__("settings", calls["settings"] + 1),
        )

    assert calls == {"overview": 1, "gaps": 1, "repair": 1, "settings": 1}


def test_data_maintenance_overview_sizes_short_tables_to_content(monkeypatch):
    class FakeMetricColumn:
        def metric(self, *args, **kwargs):
            return None

    dataframe_calls = []
    master = pd.DataFrame({"etf_code": ["510300"]})
    watchlist = pd.DataFrame(columns=["etf_code"])
    gaps = pd.DataFrame(
        {
            "数据类型": ["ETF历史", "指数历史"],
            "状态": ["缺少", "历史不足"],
        }
    )
    index_summary = pd.DataFrame({"index_code": ["000300"]})

    monkeypatch.setattr(app, "_data_maintenance_context", lambda store, parquet_store, status: (gaps, pd.DataFrame(), index_summary))
    monkeypatch.setattr(app.st, "columns", lambda count: [FakeMetricColumn() for _ in range(count)])
    monkeypatch.setattr(app.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app.st,
        "dataframe",
        lambda frame, *args, **kwargs: dataframe_calls.append({"rows": len(frame), "height": kwargs.get("height")}),
    )

    app._render_data_coverage_overview(object(), object(), {"master": master, "watchlist": watchlist})

    assert dataframe_calls[0] == {"rows": 5, "height": 222}
    assert dataframe_calls[1] == {"rows": 2, "height": 114}


def test_index_filter_explorer_folds_long_rule_copy(monkeypatch):
    markdown_calls = []
    info_calls = []

    monkeypatch.setattr(app.st, "markdown", lambda body, *args, **kwargs: markdown_calls.append(str(body)))
    monkeypatch.setattr(app.st, "info", lambda body, *args, **kwargs: info_calls.append(str(body)))
    monkeypatch.setattr(app.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: nullcontext())

    app._render_index_filter_explorer(pd.DataFrame(), object())

    assert all("### 指数级买卖参考" not in call for call in markdown_calls)
    assert all("#### 选择指数" not in call for call in markdown_calls)
    assert all("当前规则：三层趋势过滤" not in call for call in info_calls)
