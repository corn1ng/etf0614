"""Navigation definitions for the NiceGUI workbench."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NicePageSpec:
    slug: str
    label: str
    caption: str
    sections: tuple[str, ...]


NICEGUI_PAGES: tuple[NicePageSpec, ...] = (
    NicePageSpec(
        slug="action",
        label="今日行动",
        caption="先看系统状态、市场参与条件和今日计算池。",
        sections=("行动摘要", "每日建议", "计算池明细"),
    ),
    NicePageSpec(
        slug="market",
        label="市场地图",
        caption="观察指数和市场参与状态，不承载 ETF 行情下钻。",
        sections=("市场总览", "指数买卖参考", "指数K线"),
    ),
    NicePageSpec(
        slug="etf-data",
        label="ETF数据",
        caption="统一查看 ETF 主列表、行情、计算池和样本归属。",
        sections=("ETF总览", "ETF行情", "搜索加入", "每日计算池", "指数样本池"),
    ),
    NicePageSpec(
        slug="research",
        label="策略实验室",
        caption="查看研究任务和已有结果，复杂回测迁移到后续版本。",
        sections=("策略概览", "已有结果"),
    ),
    NicePageSpec(
        slug="maintenance",
        label="数据维护",
        caption="检查数据缺口、补齐历史和查看任务结果。",
        sections=("数据健康", "补齐任务", "任务日志", "设置"),
    ),
)


def page_labels() -> list[str]:
    return [page.label for page in NICEGUI_PAGES]


def default_page() -> NicePageSpec:
    return NICEGUI_PAGES[0]


def get_page_by_slug(slug: str | None) -> NicePageSpec:
    for page in NICEGUI_PAGES:
        if page.slug == slug:
            return page
    return default_page()


def section_options(page: NicePageSpec) -> list[str]:
    return list(page.sections)


def default_section(page: NicePageSpec) -> str:
    return page.sections[0]


def resolve_section(page: NicePageSpec, selected: str | None) -> str:
    if selected in page.sections:
        return str(selected)
    return default_section(page)
