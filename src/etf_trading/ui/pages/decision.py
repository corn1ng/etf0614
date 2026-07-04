"""Daily action page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    platform_status,
    render_status_cards,
    render_next_steps,
    index_trend_display_frame,
    render_research_table,
    build_daily_advice_report,
    watchlist_status_frame,
) -> None:
    st.subheader("今日行动")
    st.caption("先看市场是否允许参与，再看计算池和今日建议；需要补数据时直接给下一步。")

    status = platform_status(store, parquet_store)
    index_summary = status["index_summary"]
    eligible_categories = status["eligible_categories"]
    watchlist = status["watchlist"]

    render_status_cards(status)
    if eligible_categories:
        st.info("当前指数趋势允许参与的分类：" + "、".join(eligible_categories))
    else:
        st.warning("当前没有指数分类满足新开仓条件，今日行动应偏防守。")
    render_next_steps(status)

    if view == "行动摘要":
        top_indexes = (
            index_summary[index_summary["allows_new_position"].fillna(False).astype(bool)].head(8)
            if not index_summary.empty and "allows_new_position" in index_summary.columns
            else pd.DataFrame()
        )
        if top_indexes.empty:
            st.info("暂无可开仓指数。可到“数据维护”补齐指数历史，或等待趋势条件改善。")
        else:
            st.markdown("### 当前通过趋势过滤的指数")
            render_research_table(index_trend_display_frame(top_indexes), height=260)
        st.markdown("### 今日建议")
        report = build_daily_advice_report(store, parquet_store)
        if report is None:
            st.info("每日计算池为空。请先到“ETF池”加入 ETF。")
        else:
            st.markdown(report)
        with st.expander("查看原始计算池", expanded=False):
            if watchlist.empty:
                st.info("每日计算池为空。")
            else:
                st.dataframe(
                    watchlist_status_frame(watchlist, parquet_store),
                    width="stretch",
                    hide_index=True,
                    height=320,
                )
    elif view == "每日建议":
        report = build_daily_advice_report(store, parquet_store)
        if report is None:
            st.info("每日计算池为空。请先到“ETF池”加入 ETF。")
        else:
            st.markdown(report)
    else:
        if watchlist.empty:
            st.info("每日计算池为空。请先到“ETF池”加入 ETF。")
        else:
            st.dataframe(
                watchlist_status_frame(watchlist, parquet_store),
                width="stretch",
                hide_index=True,
                height=420,
            )
