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
        sections=("市场总览", "指数体检", "指数买卖参考", "指数K线"),
    ),
    NicePageSpec(
        slug="etf-data",
        label="ETF数据",
        caption="统一查看 ETF 主列表、行情、计算池和样本归属。",
        sections=("ETF总览", "原子指标", "ETF行情", "搜索加入", "每日计算池", "指数样本池"),
    ),
    NicePageSpec(
        slug="research",
        label="策略实验室",
        caption="创建策略、运行回测、比较表现并复盘 ETF 的买卖点。",
        sections=("策略库", "新建策略", "运行回测", "策略比较", "ETF复盘", "指数过滤实验", "指数趋势回测"),
    ),
    NicePageSpec(
        slug="maintenance",
        label="数据维护",
        caption="统一检查全局数据缺口、补齐历史和查看日志。",
        sections=("数据体检", "缺口明细", "补齐任务", "日志与设置"),
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
