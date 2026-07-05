"""Daily action page."""

from __future__ import annotations
import streamlit as st

from etf_trading.data.storage import ParquetStore, SQLiteStore


def render(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    view: str,
    status: dict[str, object],
    render_status_cards,
    render_next_steps,
    index_trend_display_frame,
    render_research_table,
    build_daily_advice_report,
    watchlist_status_frame,
) -> None:
    eligible_categories = status["eligible_categories"]
    watchlist = status["watchlist"]

    render_status_cards(status)
    if eligible_categories:
        st.info("当前指数趋势允许参与的分类：" + "、".join(eligible_categories))
    else:
        st.warning("当前没有指数分类满足新开仓条件，今日行动应偏防守。")
    render_next_steps(status)

    if view == "行动摘要":
        st.markdown("### 今日建议")
        report = build_daily_advice_report(store, parquet_store)
        if report is None:
            st.info("每日计算池为空。请先到“ETF数据”加入 ETF。")
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
            st.info("每日计算池为空。请先到“ETF数据”加入 ETF。")
        else:
            st.markdown(report)
    else:
        if watchlist.empty:
            st.info("每日计算池为空。请先到“ETF数据”加入 ETF。")
        else:
            st.dataframe(
                watchlist_status_frame(watchlist, parquet_store),
                width="stretch",
                hide_index=True,
                height=420,
            )
