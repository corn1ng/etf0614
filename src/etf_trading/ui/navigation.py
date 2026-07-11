"""Navigation configuration and controls for the Streamlit workbench."""

from __future__ import annotations

import html
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
        caption="观察指数和市场参与状态，不承载 ETF 行情下钻。",
        sections=("市场总览", "指数买卖参考", "指数K线"),
    ),
    PageSpec(
        slug="portfolio",
        label="ETF数据",
        caption="统一查看 ETF 主列表、行情、计算池和样本归属。",
        sections=("ETF总览", "ETF行情", "搜索加入", "每日计算池", "指数样本池"),
    ),
    PageSpec(
        slug="research",
        label="策略实验室",
        caption="创建策略、运行回测、比较表现并复盘 ETF 的 B/S 点。",
        sections=("策略库", "新建策略", "运行回测", "策略比较", "ETF复盘", "指数过滤实验"),
    ),
    PageSpec(
        slug="data",
        label="数据维护",
        caption="统一检查全局数据缺口、补齐历史和查看日志。",
        sections=("数据总览", "缺口明细", "补齐任务", "日志与设置"),
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


def render_page_header(page: PageSpec) -> None:
    title = html.escape(page.label)
    caption = html.escape(page.caption)
    st.markdown(
        (
            '<div class="workbench-page-header">'
            f'<div class="workbench-page-header__title">{title}</div>'
            f'<div class="workbench-page-header__caption">{caption}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


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
