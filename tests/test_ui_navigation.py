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
