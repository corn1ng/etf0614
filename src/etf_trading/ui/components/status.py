"""Status display components for the workbench."""

from __future__ import annotations

import html

import streamlit as st

from etf_trading.ui.state import StatusSummary


def render_top_status_bar(summary: StatusSummary) -> None:
    items = [
        ("工作台", "ETF 今日行动"),
        ("数据健康", summary.data_health),
        ("可参与指数", str(summary.eligible_index_count)),
        ("可参与分类", str(summary.eligible_category_count)),
        ("计算池 ETF", str(summary.enabled_watchlist_count)),
        ("数据缺口", str(summary.issue_count)),
    ]
    cells = "".join(
        (
            '<div class="workbench-topbar__item">'
            f'<div class="workbench-topbar__label">{html.escape(label)}</div>'
            f'<div class="workbench-topbar__value">{html.escape(value)}</div>'
            "</div>"
        )
        for label, value in items
    )
    st.markdown(f'<div class="workbench-topbar">{cells}</div>', unsafe_allow_html=True)


def render_status_cards(status: dict[str, object]) -> None:
    cols = st.columns(4)
    cols[0].metric("可参与指数", f"{int(status['eligible_index_count'])}")
    cols[1].metric("可参与分类", f"{len(status['eligible_categories'])}")
    cols[2].metric("计算池 ETF", f"{len(status['enabled_watchlist'])}")
    cols[3].metric("数据缺口", f"{len(status['issues'])}")


def render_next_steps(status: dict[str, object]) -> None:
    issues = status["issues"]
    if not issues:
        st.success("数据和计算池已就绪，可以直接查看今日建议。")
        return

    st.warning("当前还有准备项未完成，建议按下面顺序处理：")
    for index, issue in enumerate(issues, start=1):
        st.markdown(f"{index}. **{issue['title']}**：{issue['detail']}")
