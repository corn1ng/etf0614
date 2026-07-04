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
    assert page_labels() == ["今日行动", "市场地图", "ETF池", "研究复盘", "数据维护"]
    assert [page.slug for page in PAGE_SPECS] == ["decision", "market", "portfolio", "research", "data"]


def test_each_page_exposes_expected_secondary_sections():
    sections_by_label = {page.label: section_options(page) for page in PAGE_SPECS}

    assert sections_by_label["今日行动"] == ["行动摘要", "每日建议", "计算池明细"]
    assert sections_by_label["市场地图"] == ["指数买卖参考", "ETF行情", "指数K线"]
    assert sections_by_label["ETF池"] == ["搜索加入", "每日计算池"]
    assert sections_by_label["研究复盘"] == ["研究总览", "策略对比", "ETF复盘", "明细表", "运行研究"]
    assert sections_by_label["数据维护"] == ["数据健康", "数据中心", "日志与设置"]


def test_navigation_defaults_to_daily_action_summary():
    page = default_page()

    assert page.label == "今日行动"
    assert default_section(page) == "行动摘要"


def test_unknown_page_and_section_fall_back_to_safe_defaults():
    page = get_page_by_label("不存在")

    assert page.label == "今日行动"
    assert resolve_section(page, "不存在") == "行动摘要"


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
        "_render_research_run_controls",
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

    app._tab_research(store, object(), research_view="运行研究")

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
    monkeypatch.setattr(app.market.st, "subheader", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.market.st, "caption", lambda *args, **kwargs: None)

    app.main()

    assert calls["build_index_summary"] == 0
