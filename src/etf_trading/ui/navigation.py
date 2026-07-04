"""Navigation configuration and controls for the Streamlit workbench."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class PageSpec:
    slug: str
    label: str
    caption: str
    sections: tuple[str, ...]


PAGE_SPECS: tuple[PageSpec, ...] = (
    PageSpec(
        slug="decision",
        label="今日行动",
        caption="先看市场是否允许参与，再看今日建议。",
        sections=("行动摘要", "每日建议", "计算池明细"),
    ),
    PageSpec(
        slug="market",
        label="市场地图",
        caption="观察指数、ETF行情和趋势结构。",
        sections=("指数买卖参考", "ETF行情", "指数K线"),
    ),
    PageSpec(
        slug="portfolio",
        label="ETF池",
        caption="搜索 ETF、加入每日计算池并检查历史行情。",
        sections=("搜索加入", "每日计算池"),
    ),
    PageSpec(
        slug="research",
        label="研究复盘",
        caption="查看策略研究、对比结果和单 ETF 复盘。",
        sections=("研究总览", "策略对比", "ETF复盘", "明细表", "运行研究"),
    ),
    PageSpec(
        slug="data",
        label="数据维护",
        caption="检查数据健康、补齐历史和查看日志。",
        sections=("数据健康", "数据中心", "日志与设置"),
    ),
)


def page_labels() -> list[str]:
    return [page.label for page in PAGE_SPECS]


def default_page() -> PageSpec:
    return PAGE_SPECS[0]


def get_page_by_label(label: str | None) -> PageSpec:
    for page in PAGE_SPECS:
        if page.label == label:
            return page
    return default_page()


def section_options(page: PageSpec) -> list[str]:
    return list(page.sections)


def default_section(page: PageSpec) -> str:
    return page.sections[0]


def resolve_section(page: PageSpec, selected: str | None) -> str:
    if selected in page.sections:
        return str(selected)
    return default_section(page)


def render_primary_navigation() -> PageSpec:
    with st.sidebar:
        st.markdown("### ETF 工作台")
        selected = st.radio(
            "主菜单",
            page_labels(),
            index=0,
            key="primary_navigation",
            label_visibility="collapsed",
        )
    return get_page_by_label(selected)


def render_secondary_navigation(page: PageSpec) -> str:
    options = section_options(page)
    control = getattr(st, "segmented_control", None)
    if control is not None:
        selected = control(
            "页面视图",
            options,
            default=default_section(page),
            key=f"secondary_navigation_{page.slug}",
        )
        return resolve_section(page, selected)

    selected = st.radio(
        "页面视图",
        options,
        horizontal=True,
        key=f"secondary_navigation_{page.slug}",
    )
    return resolve_section(page, selected)
