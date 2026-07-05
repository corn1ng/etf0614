"""Daily action page."""

from __future__ import annotations

import pandas as pd
from nicegui import ui

from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.status import metric_strip
from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.view_models import PlatformSnapshot, current_ui_audit_findings, status_metrics
from etf_trading.report.daily_report import DailyAdviceReport
from etf_trading.strategy.features import add_technical_features
from etf_trading.strategy.models import StrategySignal
from etf_trading.strategy.trend import TrendStrategy
from etf_trading.universe.classification import is_hk_cross_market


def render(snapshot: PlatformSnapshot, section: str, store=None, parquet_store=None) -> None:
    metric_strip(status_metrics(snapshot))
    if section == "计算池明细":
        _render_rows(_watchlist_status_rows(snapshot.watchlist, parquet_store), "每日计算池为空", "请先到 ETF数据 -> 搜索加入 保存 ETF。")
    elif section == "每日建议":
        _render_daily_advice(store, parquet_store)
    else:
        _render_action_summary(snapshot, store, parquet_store)
    _render_audit()


def _render_action_summary(snapshot: PlatformSnapshot, store, parquet_store) -> None:
    frame = snapshot.index_summary
    allowed = frame[frame["allows_new_position"].fillna(False).astype(bool)] if "allows_new_position" in frame else frame.iloc[0:0]
    if allowed.empty:
        ui.label("当前没有指数分类满足新开仓条件，今日行动偏防守。").classes("workbench-warning-line")
    else:
        categories = "、".join(sorted(allowed["category"].dropna().astype(str).unique()))
        ui.label(f"当前指数趋势允许参与的分类：{categories}").classes("workbench-success-line")

    _render_daily_advice(store, parquet_store, compact=True)
    with ui.expansion("查看原始计算池", icon="playlist_add_check").classes("w-full text-sm"):
        _render_rows(_watchlist_status_rows(snapshot.watchlist, parquet_store), "每日计算池为空", "请先到 ETF数据 -> 搜索加入 保存 ETF。")


def _render_daily_advice(store, parquet_store, compact: bool = False) -> None:
    report = _build_daily_advice_report(store, parquet_store)
    if report is None:
        empty_state("每日计算池为空", "请先到 ETF数据 -> 搜索加入 保存 ETF。")
        return
    with ui.column().classes("workbench-markdown-panel w-full"):
        if compact:
            ui.label("今日建议").classes("text-sm font-semibold text-slate-700")
        ui.markdown(report).classes("w-full")


def _render_rows(rows: list[dict[str, object]], empty_title: str, empty_detail: str) -> None:
    if rows:
        ui.table(columns=table_columns(rows), rows=rows, pagination=10).classes("workbench-data-table w-full")
    else:
        empty_state(empty_title, empty_detail)


def _build_daily_advice_report(store, parquet_store) -> str | None:
    if store is None or parquet_store is None:
        return None
    watchlist = store.list_watchlist()
    if watchlist.empty:
        return None

    strategy = TrendStrategy()
    signals: list[StrategySignal] = []
    for row in watchlist.itertuples(index=False):
        if hasattr(row, "enabled") and not bool(row.enabled):
            continue
        prices = parquet_store.read_prices(row.etf_code)
        if prices.empty:
            signals.append(
                StrategySignal(
                    etf_code=row.etf_code,
                    trade_date=pd.Timestamp.today().normalize(),
                    action="FORBID",
                    target_weight=0.0,
                    reason="历史行情未初始化",
                    trigger_rules=["missing_history"],
                    risk_tags=["数据缺失"],
                )
            )
            continue
        featured = add_technical_features(prices).iloc[-1].copy()
        featured["etf_code"] = row.etf_code
        featured["category"] = row.category
        featured["relative_strength_rank"] = 0.2
        featured["premium_rate"] = 0.0
        featured["data_quality_score"] = 1.0
        featured["underlying_market_open"] = True
        signal = strategy.evaluate(featured, market_risk_on=True)
        if is_hk_cross_market(row.category):
            signal.risk_tags.append("港股跨境ETF")
        signals.append(signal)

    return DailyAdviceReport().render(pd.Timestamp.today(), "震荡", signals)


def _watchlist_status_rows(watchlist: pd.DataFrame, parquet_store) -> list[dict[str, object]]:
    if watchlist.empty:
        return []
    rows: list[dict[str, object]] = []
    for item in watchlist.fillna("").to_dict("records"):
        etf_code = str(item.get("etf_code", ""))
        prices = parquet_store.read_prices(etf_code) if parquet_store is not None and etf_code else pd.DataFrame()
        latest = ""
        if not prices.empty and "trade_date" in prices:
            latest = pd.Timestamp(prices["trade_date"].max()).strftime("%Y-%m-%d")
        rows.append(
            {
                "ETF代码": etf_code,
                "名称": item.get("name", ""),
                "分类": item.get("category", ""),
                "启用": "是" if bool(item.get("enabled", False)) else "否",
                "允许买入": "是" if bool(item.get("allow_buy", False)) else "否",
                "本地历史": "已就绪" if not prices.empty else "缺失",
                "历史长度": int(len(prices)),
                "最新日期": latest,
                "备注": item.get("note", ""),
            }
        )
    return rows


def _render_audit() -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == "action":
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
