"""Research table and chart components."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st


def research_column_config(
    frame: pd.DataFrame,
    *,
    compact_header_labels: dict[str, str],
    percent_labels: set[str],
    count_labels: set[str],
) -> dict[str, object]:
    config: dict[str, object] = {}
    for column in frame.columns:
        label = compact_header_labels.get(column, column)
        if column == "ETF代码 ETF Code":
            config[column] = st.column_config.TextColumn(label, width=92)
        elif column == "ETF名称":
            config[column] = st.column_config.TextColumn(label, width=160)
        elif column == "指数代码 Index Code":
            config[column] = st.column_config.TextColumn(label, width=92)
        elif column == "指数名称":
            config[column] = st.column_config.TextColumn(label, width=150)
        elif column in {"大趋势 Large Trend", "中趋势 Medium Trend", "小趋势 Small Trend"}:
            config[column] = st.column_config.TextColumn(label, width=132)
        elif column == "可开仓 Eligible":
            config[column] = st.column_config.TextColumn(label, width=118)
        elif column in percent_labels:
            config[column] = st.column_config.NumberColumn(label, format="%.1f%%", width=112)
        elif column in count_labels:
            config[column] = st.column_config.NumberColumn(label, format="%.0f", width=82)
        elif pd.api.types.is_numeric_dtype(frame[column]):
            config[column] = st.column_config.NumberColumn(label, format="%.2f", width=88)
        elif column in {"候选策略 Strategy", "基准策略 Base Strategy"}:
            config[column] = st.column_config.TextColumn(label, width=260)
        elif column == "分类 Category":
            config[column] = st.column_config.TextColumn(label, width=88)
        else:
            config[column] = st.column_config.TextColumn(label, width=90)
    return config


def render_research_table(
    frame: pd.DataFrame,
    *,
    column_config: dict[str, object],
    height: int | None = None,
) -> None:
    st.dataframe(
        frame,
        width="stretch",
        height=height or "auto",
        hide_index=True,
        column_config=column_config,
        row_height=34,
    )


def research_bar_chart(
    frame: pd.DataFrame,
    index_column: str,
    value_column: str,
    *,
    title: str,
    color: str,
    percent_columns: set[str],
    column_labels: dict[str, str],
    candidate_display_name,
    height_per_row: int = 34,
) -> alt.Chart:
    if index_column not in frame.columns or value_column not in frame.columns:
        return alt.Chart(pd.DataFrame({"策略 Strategy": [], "数值 Value": []})).mark_bar()

    data = frame[[index_column, value_column]].dropna().copy()
    if index_column in {"candidate_name", "base_candidate"}:
        data[index_column] = data[index_column].map(candidate_display_name)
    data = data.rename(columns={index_column: "策略 Strategy", value_column: "数值 Value"})
    if value_column in percent_columns:
        data["数值 Value"] = data["数值 Value"] * 100
        value_format = ".1f"
        axis_title = f"{column_labels.get(value_column, value_column)} (%)"
    else:
        value_format = ".3f"
        axis_title = column_labels.get(value_column, value_column)

    row_count = max(len(data), 1)
    chart_height = max(150, min(420, row_count * height_per_row))
    tooltip_title = column_labels.get(value_column, value_column)
    return (
        alt.Chart(data)
        .mark_bar(color=color)
        .encode(
            y=alt.Y("策略 Strategy:N", sort="-x", title=None),
            x=alt.X("数值 Value:Q", title=axis_title),
            tooltip=[
                alt.Tooltip("策略 Strategy:N", title="策略 Strategy"),
                alt.Tooltip("数值 Value:Q", title=tooltip_title, format=value_format),
            ],
        )
        .properties(title=title, height=chart_height)
    )
