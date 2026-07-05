from etf_trading.nicegui_app.navigation import (
    NICEGUI_PAGES,
    default_page,
    default_section,
    get_page_by_slug,
    page_labels,
    resolve_section,
    section_options,
)


def test_nicegui_primary_navigation_matches_workbench_flow():
    assert page_labels() == ["今日行动", "市场地图", "ETF数据", "策略实验室", "数据维护"]
    assert [page.slug for page in NICEGUI_PAGES] == ["action", "market", "etf-data", "research", "maintenance"]


def test_nicegui_sections_keep_market_and_etf_boundaries():
    sections_by_slug = {page.slug: section_options(page) for page in NICEGUI_PAGES}

    assert sections_by_slug["market"] == ["市场总览", "指数买卖参考", "指数K线"]
    assert sections_by_slug["etf-data"] == ["ETF总览", "ETF行情", "搜索加入", "每日计算池", "指数样本池"]
    assert "ETF行情" not in sections_by_slug["market"]


def test_nicegui_navigation_defaults_are_safe():
    page = default_page()

    assert page.slug == "action"
    assert page.label == "今日行动"
    assert default_section(page) == "行动摘要"
    assert get_page_by_slug("missing").slug == "action"
    assert resolve_section(page, "不存在") == "行动摘要"
