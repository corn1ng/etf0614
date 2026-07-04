"""Streamlit multi-tab ETF workbench."""

from __future__ import annotations

import threading
from datetime import date, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from etf_trading.backtest.engine import BacktestEngine
from etf_trading.data.indexes import DEFAULT_INDEXES, INDEX_HISTORY_AUTO_START, IndexDefinition, get_index_definition, index_options
from etf_trading.data.initialization import InitializationService
from etf_trading.data.providers.akshare_provider import AkShareProvider
from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.report.daily_report import DailyAdviceReport
from etf_trading.research.comparison import compare_regime_pairs
from etf_trading.research.config import load_research_candidates
from etf_trading.research.experiment import ResearchRunCancelled
from etf_trading.research.regime import TrendRegimeClassifier, add_trend_regime_features
from etf_trading.research.runner import attach_relative_strength_rank, load_price_frames, run_research
from etf_trading.research.signals import generate_candidate_signals
from etf_trading.strategy.features import add_technical_features
from etf_trading.strategy.models import StrategySignal
from etf_trading.strategy.trend import TrendStrategy
from etf_trading.ui.chart_renderer import build_lightweight_chart_payload
from etf_trading.ui.components.status import render_top_status_bar
from etf_trading.ui.navigation import render_primary_navigation
from etf_trading.ui.state import summarize_platform_status
from etf_trading.ui.styles import inject_global_styles
from etf_trading.universe.classification import CATEGORIES, is_hk_cross_market

try:
    from streamlit_lightweight_charts import renderLightweightCharts
except Exception:  # pragma: no cover - import fallback for non-UI environments
    renderLightweightCharts = None


DB_PATH = Path("database/etf_system.sqlite")
PARQUET_ROOT = Path("data/parquet")
RESEARCH_CONFIG = Path("configs/research.yaml")
RESEARCH_REPORT_DIR = Path("reports/research_dashboard")
SAMPLE_CATEGORIES = ["A股宽基", "A股行业", "港股宽基", "港股科技", "港股医药", "商品", "债券"]
WORKFLOW_TABS = ["今日行动", "市场地图", "ETF池", "研究复盘", "数据维护"]


class ResearchJobManager:
    """Run trend research in the background so the UI can request cancellation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._status: dict[str, object] = {
            "state": "idle",
            "message": "暂无运行中的趋势研究。",
            "done": 0,
            "total": 0,
            "current_code": "",
        }

    def status(self) -> dict[str, object]:
        with self._lock:
            return dict(self._status)

    def is_running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def request_stop(self) -> None:
        self._stop_event.set()
        self._set_status(message="已请求停止，将在当前 ETF 处理完后中断。")

    def start(
        self,
        *,
        parquet_root: Path,
        candidates: list[object],
        categories: dict[str, str],
        min_rows: int,
        limit: int | None,
        etf_codes: list[str] | None,
        output_dir: Path,
        index_summary: pd.DataFrame,
        scope_text: str,
    ) -> bool:
        if self.is_running():
            return False

        self._stop_event.clear()
        self._set_status(
            state="running",
            message="趋势研究已启动，正在准备样本...",
            done=0,
            total=0,
            current_code="",
        )

        thread = threading.Thread(
            target=self._run,
            kwargs={
                "parquet_root": parquet_root,
                "candidates": candidates,
                "categories": categories,
                "min_rows": min_rows,
                "limit": limit,
                "etf_codes": etf_codes,
                "output_dir": output_dir,
                "index_summary": index_summary.copy(),
                "scope_text": scope_text,
            },
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return True

    def _run(
        self,
        *,
        parquet_root: Path,
        candidates: list[object],
        categories: dict[str, str],
        min_rows: int,
        limit: int | None,
        etf_codes: list[str] | None,
        output_dir: Path,
        index_summary: pd.DataFrame,
        scope_text: str,
    ) -> None:
        def on_progress(done: int, total: int, etf_code: str) -> None:
            self._set_status(
                message=f"正在回测 {etf_code}，进度 {done}/{total}。",
                done=done,
                total=total,
                current_code=etf_code,
            )

        try:
            output = run_research(
                parquet_root=parquet_root,
                candidates=candidates,
                categories=categories,
                min_rows=min_rows,
                limit=limit,
                use_relative_strength=True,
                etf_codes=etf_codes,
                should_stop=self._stop_event.is_set,
                on_progress=on_progress,
            )
            _write_research_outputs(output_dir, output, index_summary)
        except ResearchRunCancelled:
            self._set_status(state="cancelled", message="趋势研究已停止，本次未覆盖旧结果。")
        except Exception as exc:  # noqa: BLE001 - preserve failure text for UI
            self._set_status(state="failed", message=f"趋势研究失败：{exc}")
        else:
            self._set_status(
                state="completed",
                message=f"已完成：{scope_text}回测 {output.used_count} 只 ETF，跳过 {output.skipped_count} 只样本。",
                done=output.used_count,
                total=output.used_count,
                current_code="",
            )

    def _set_status(self, **updates: object) -> None:
        with self._lock:
            self._status.update(updates)


def _write_research_outputs(output_dir: Path, output: object, index_summary: pd.DataFrame) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    output.results.to_csv(output_dir / "research_results.csv", index=False)
    output.ranking.to_csv(output_dir / "candidate_ranking.csv", index=False)
    index_summary.to_csv(output_dir / "index_trend_summary.csv", index=False)
    universe = sorted(output.results["etf_code"].astype(str).unique()) if not output.results.empty else []
    pd.DataFrame({"etf_code": universe}).to_csv(output_dir / "research_universe.csv", index=False)

RESEARCH_COLUMN_LABELS = {
    "candidate_name": "候选策略 Strategy",
    "base_candidate": "基准策略 Base Strategy",
    "category": "分类 Category",
    "index_code": "指数代码 Index Code",
    "index_name": "指数名称 Index Name",
    "market": "市场 Market",
    "large_trend": "大趋势 Large Trend",
    "medium_trend": "中趋势 Medium Trend",
    "small_trend": "小趋势 Small Trend",
    "allows_new_position": "可开仓 Eligible",
    "latest_date": "最新日期 Latest Date",
    "history_rows": "历史长度 Rows",
    "etf_code": "ETF代码 ETF Code",
    "etf_name": "ETF名称 ETF Name",
    "sample_count": "样本数 Samples",
    "mean_total_return": "平均总收益 Mean Total Return",
    "median_total_return": "中位总收益 Median Total Return",
    "positive_rate": "正收益比例 Positive Rate",
    "median_annualized_return": "中位年化收益 Median Annual Return",
    "annualized_return": "年化收益 Annual Return",
    "total_return": "总收益 Total Return",
    "volatility": "波动率 Volatility",
    "median_sharpe": "中位夏普 Median Sharpe",
    "sharpe": "夏普 Sharpe",
    "median_calmar": "中位卡玛 Median Calmar",
    "calmar": "卡玛 Calmar",
    "median_max_drawdown": "中位最大回撤 Median Max Drawdown",
    "worst_max_drawdown": "最差最大回撤 Worst Max Drawdown",
    "max_drawdown": "最大回撤 Max Drawdown",
    "avg_exposure": "平均暴露 Avg Exposure",
    "mean_trade_count": "平均交易次数 Avg Trades",
    "trade_count": "交易次数 Trades",
    "closed_trade_count": "已平仓次数 Closed Trades",
    "win_rate": "胜率 Win Rate",
    "avg_trade_return": "平均单笔收益 Avg Trade Return",
    "avg_holding_days": "平均持有天数 Avg Holding Days",
    "signal_count": "信号次数 Signals",
    "score": "综合分 Score",
    "base_median_sharpe": "基准中位夏普 Base Median Sharpe",
    "regime_median_sharpe": "趋势过滤中位夏普 Regime Median Sharpe",
    "delta_median_sharpe": "夏普变化 Sharpe Change",
    "base_median_max_drawdown": "基准中位最大回撤 Base Median Max Drawdown",
    "regime_median_max_drawdown": "趋势过滤中位最大回撤 Regime Median Max Drawdown",
    "delta_median_max_drawdown": "中位回撤变化 Drawdown Change",
    "base_worst_max_drawdown": "基准最差最大回撤 Base Worst Max Drawdown",
    "regime_worst_max_drawdown": "趋势过滤最差最大回撤 Regime Worst Max Drawdown",
    "base_mean_trade_count": "基准平均交易次数 Base Avg Trades",
    "regime_mean_trade_count": "趋势过滤平均交易次数 Regime Avg Trades",
}

CANDIDATE_DISPLAY_NAMES = {
    "balanced_breakout": "平衡突破 Balanced Breakout",
    "regime_balanced_breakout": "趋势过滤平衡突破 Regime-Gated Balanced Breakout",
    "early_breakout_tight_heat_filter": "早期突破 + 过热过滤 Early Breakout + Heat Filter",
    "regime_early_breakout_tight_heat_filter": "趋势过滤早期突破 + 过热过滤 Regime-Gated Early Breakout + Heat Filter",
    "relative_strength_momentum": "相对强度动量 Relative Strength Momentum",
    "regime_relative_strength_momentum": "趋势过滤相对强度动量 Regime-Gated Relative Strength Momentum",
}

RESEARCH_PERCENT_COLUMNS = {
    "mean_total_return",
    "median_total_return",
    "positive_rate",
    "median_annualized_return",
    "annualized_return",
    "total_return",
    "volatility",
    "median_max_drawdown",
    "worst_max_drawdown",
    "max_drawdown",
    "avg_exposure",
    "win_rate",
    "avg_trade_return",
    "base_median_max_drawdown",
    "regime_median_max_drawdown",
    "delta_median_max_drawdown",
    "base_worst_max_drawdown",
    "regime_worst_max_drawdown",
}
RESEARCH_COUNT_COLUMNS = {
    "sample_count",
    "trade_count",
    "closed_trade_count",
    "signal_count",
    "mean_trade_count",
    "base_mean_trade_count",
    "regime_mean_trade_count",
    "avg_holding_days",
    "history_rows",
}
RESEARCH_PERCENT_LABELS = {
    RESEARCH_COLUMN_LABELS[column] for column in RESEARCH_PERCENT_COLUMNS if column in RESEARCH_COLUMN_LABELS
}
RESEARCH_COUNT_LABELS = {
    RESEARCH_COLUMN_LABELS[column] for column in RESEARCH_COUNT_COLUMNS if column in RESEARCH_COLUMN_LABELS
}
RESEARCH_COMPACT_HEADER_LABELS = {
    "候选策略 Strategy": "策略 Strategy",
    "基准策略 Base Strategy": "基准 Base",
    "分类 Category": "分类 Category",
    "指数代码 Index Code": "代码 Code",
    "指数名称 Index Name": "指数 Name",
    "市场 Market": "市场 Market",
    "大趋势 Large Trend": "大趋势 Large",
    "中趋势 Medium Trend": "中趋势 Medium",
    "小趋势 Small Trend": "小趋势 Small",
    "可开仓 Eligible": "可开仓 Eligible",
    "最新日期 Latest Date": "日期 Date",
    "历史长度 Rows": "长度 Rows",
    "ETF代码 ETF Code": "代码 Code",
    "ETF名称 ETF Name": "名称 Name",
    "样本数 Samples": "样本 Samples",
    "平均总收益 Mean Total Return": "收益 Return",
    "中位年化收益 Median Annual Return": "年化 Ann.",
    "总收益 Total Return": "总收益 Total Return",
    "年化收益 Annual Return": "年化 Ann.",
    "中位夏普 Median Sharpe": "夏普 Sharpe",
    "夏普 Sharpe": "夏普 Sharpe",
    "综合分 Score": "综合分 Score",
    "最差最大回撤 Worst Max Drawdown": "回撤 MDD",
    "最大回撤 Max Drawdown": "回撤 MDD",
    "平均交易次数 Avg Trades": "平均交易 Avg Trades",
    "交易次数 Trades": "交易 Trades",
    "胜率 Win Rate": "胜率 Win Rate",
    "趋势过滤中位夏普 Regime Median Sharpe": "趋势夏普 Regime Sharpe",
    "基准中位夏普 Base Median Sharpe": "基准夏普 Base Sharpe",
    "夏普变化 Sharpe Change": "夏普变化 Sharpe Change",
    "中位回撤变化 Drawdown Change": "回撤变化 Drawdown Change",
}
RANKING_COLUMNS = [
    "candidate_name",
    "sample_count",
    "median_annualized_return",
    "worst_max_drawdown",
    "median_sharpe",
    "score",
]
COMPARISON_COLUMNS = [
    "base_candidate",
    "base_median_sharpe",
    "regime_median_sharpe",
    "delta_median_sharpe",
    "delta_median_max_drawdown",
    "regime_mean_trade_count",
]
CATEGORY_COLUMNS = [
    "candidate_name",
    "category",
    "sample_count",
    "mean_total_return",
    "worst_max_drawdown",
    "median_sharpe",
]
DETAIL_COLUMNS = [
    "etf_code",
    "etf_name",
    "category",
    "total_return",
    "annualized_return",
    "max_drawdown",
    "sharpe",
    "trade_count",
    "win_rate",
]
INDEX_TREND_COLUMNS = [
    "index_code",
    "index_name",
    "market",
    "category",
    "large_trend",
    "medium_trend",
    "small_trend",
    "allows_new_position",
    "latest_date",
    "history_rows",
]
INDEX_SYNC_COLUMNS = [
    "index_code",
    "status",
    "fetched_rows",
    "total_rows",
    "end_date",
    "error_message",
]
INDEX_SYNC_COLUMN_LABELS = {
    "index_code": "指数代码 Index Code",
    "status": "同步状态 Sync Status",
    "fetched_rows": "新增行数 Fetched Rows",
    "total_rows": "本地总行数 Total Rows",
    "end_date": "最新日期 Latest Date",
    "error_message": "错误信息 Error",
}
INDEX_SYNC_STATUS_DISPLAY_NAMES = {
    "INITIALIZED": "首次初始化 Initialized",
    "UPDATED": "已补齐 Updated",
    "SKIPPED": "已是最新 Current",
    "EMPTY": "无返回数据 Empty",
    "FAILED": "同步失败 Failed",
}
TREND_DISPLAY_NAMES = {
    "UP": "上升 UP",
    "RECOVERY": "修复 RECOVERY",
    "RANGE": "震荡 RANGE",
    "DOWN": "下降 DOWN",
    "UNKNOWN": "未知 UNKNOWN",
    "TURNING_UP": "转强 TURNING UP",
    "REBOUND": "反弹 REBOUND",
    "RIGHT_SIDE_START": "右侧开始 RIGHT SIDE",
    "EXTENDED": "过热 EXTENDED",
    "PULLBACK": "回踩 PULLBACK",
    "BROKEN": "破位 BROKEN",
}
TREND_VALUE_NAMES = {
    "UP": "上升",
    "RECOVERY": "修复",
    "RANGE": "震荡",
    "DOWN": "下降",
    "UNKNOWN": "未知",
    "TURNING_UP": "转强",
    "REBOUND": "反弹",
    "RIGHT_SIDE_START": "右侧开始",
    "EXTENDED": "过热",
    "PULLBACK": "回踩",
    "BROKEN": "破位",
}
INDEX_RULE_DISPLAY_NAMES = {
    "large_uptrend": "大趋势向上：价格站上长期均线，长期均线继续上行",
    "large_recovery": "大趋势修复：价格站回长期均线，长期均线转强",
    "large_range": "大趋势震荡：长期方向还不够明确",
    "medium_uptrend": "中趋势向上：价格站上中期均线，60日动量为正",
    "medium_turning_up": "中趋势转强：价格重新站上中期均线",
    "medium_rebound": "中趋势反弹：大趋势仍弱，只能先按反弹处理",
    "medium_range": "中趋势震荡：中期方向还不够明确",
    "small_right_side_start": "小趋势右侧开始：价格重新站上短期均线，离中期均线不远",
    "small_pullback": "小趋势回踩：趋势未破，短线回落到可观察区域",
    "small_range": "小趋势震荡：短线方向还不够明确",
}
INDEX_RISK_DISPLAY_NAMES = {
    "large_trend_unknown": "大趋势未知：长期均线数据不足",
    "large_downtrend": "大趋势下降：价格低于长期均线且回撤较深",
    "large_range": "大趋势震荡：长期方向不清晰",
    "medium_trend_unknown": "中趋势未知：中期均线数据不足",
    "medium_rebound_in_large_downtrend": "弱势反弹：大趋势仍在下降，反弹可靠性较低",
    "medium_downtrend": "中趋势下降：价格跌破中期均线",
    "medium_range": "中趋势震荡：中期方向不清晰",
    "small_trend_unknown": "小趋势未知：短期均线数据不足",
    "small_trend_extended": "短线过热：离中期均线太远，追高风险增加",
    "small_broken": "短线破位：价格跌破中期均线",
    "small_range": "小趋势震荡：短线方向不清晰",
}
INDEX_CHART_RANGE_OPTIONS = {
    "近3个月": 60,
    "近6个月": 120,
    "近1年": 240,
    "近2年": 480,
    "全部": 2000,
}
INDEX_SIGNAL_RULE_OPTIONS = {
    "长期趋势版": "long_trend",
    "趋势持有版": "trend_hold",
    "稳定确认版": "stable",
    "原始日切换": "raw",
}
STABLE_INDEX_SIGNAL_PARAMS = {
    "entry_confirm_days": 3,
    "exit_confirm_days": 3,
    "min_hold_days": 10,
    "cooldown_days": 5,
}
CHART_TYPE_OPTIONS = {
    "收盘折线 Close Line": "line",
    "K线 Candlestick": "candlestick",
}
PRICE_SCALE_OPTIONS = {
    "线性坐标 Linear": "normal",
    "涨跌幅视图 Return %": "percent",
    "比例视图 Log Return %": "log_return",
    "回撤视图 Drawdown %": "drawdown",
    "距区间低点 Downside %": "downside",
}
CHART_RANGE_PRESETS = {
    "近3月": 90,
    "近6月": 180,
    "近1年": 365,
    "近2年": 730,
    "全部": None,
    "自定义": "custom",
}
MA_DISPLAY_OPTIONS = {
    "MA51": "ma51",
    "MA120": "ma120",
    "MA250": "ma250",
    "MA850": "ma850",
}


def _candidate_display_name(candidate_name: str) -> str:
    return CANDIDATE_DISPLAY_NAMES.get(candidate_name, f"自定义策略 Custom Strategy: {candidate_name}")


def _format_etf_code(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if text.isdigit():
        return text.zfill(6)
    return text


def _research_display_frame(
    frame: pd.DataFrame,
    candidate_columns: tuple[str, ...] = ("candidate_name", "base_candidate"),
) -> pd.DataFrame:
    display = frame.copy()
    if "etf_code" in display.columns:
        display["etf_code"] = display["etf_code"].map(_format_etf_code)
    for column in RESEARCH_PERCENT_COLUMNS:
        if column in display.columns:
            display[column] = (display[column] * 100).round(4)
    for column in candidate_columns:
        if column in display.columns:
            display[column] = display[column].map(
                lambda value: _candidate_display_name(str(value)) if pd.notna(value) else value
            )
    return display.rename(columns=RESEARCH_COLUMN_LABELS)


def _research_select_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame[[column for column in columns if column in frame.columns]].copy()


def _research_attach_etf_names(frame: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()
    if "etf_code" not in enriched.columns:
        return enriched

    codes = enriched["etf_code"].map(_format_etf_code)
    enriched["etf_code"] = codes
    if master.empty or "etf_code" not in master.columns or "name" not in master.columns:
        names = pd.Series("未知名称", index=enriched.index)
    else:
        name_map = dict(zip(master["etf_code"].map(_format_etf_code), master["name"].fillna("未知名称").astype(str), strict=False))
        names = codes.map(name_map).fillna("未知名称")

    if "etf_name" in enriched.columns:
        enriched["etf_name"] = names
    else:
        enriched.insert(enriched.columns.get_loc("etf_code") + 1, "etf_name", names)
    return enriched


def _build_index_trend_summary(
    parquet_store: ParquetStore,
    definitions: tuple[IndexDefinition, ...] = DEFAULT_INDEXES,
) -> pd.DataFrame:
    classifier = TrendRegimeClassifier()
    rows: list[dict[str, object]] = []
    for definition in definitions:
        prices = parquet_store.read_index_prices(definition.index_code)
        base_row: dict[str, object] = {
            "index_code": definition.index_code,
            "index_name": definition.name,
            "market": definition.market,
            "category": definition.category,
            "large_trend": "UNKNOWN",
            "medium_trend": "UNKNOWN",
            "small_trend": "UNKNOWN",
            "allows_new_position": False,
            "latest_date": "",
            "history_rows": 0,
        }
        if prices.empty:
            rows.append(base_row)
            continue

        featured = add_trend_regime_features(prices)
        if featured.empty:
            rows.append(base_row)
            continue

        last = featured.iloc[-1]
        regime = classifier.classify(last)
        base_row.update(
            {
                "large_trend": regime.large_trend,
                "medium_trend": regime.medium_trend,
                "small_trend": regime.small_trend,
                "allows_new_position": bool(regime.allows_new_position),
                "latest_date": pd.Timestamp(last["trade_date"]).strftime("%Y-%m-%d"),
                "history_rows": int(len(featured)),
            }
        )
        rows.append(base_row)
    return pd.DataFrame(rows)


def _eligible_index_categories(index_summary: pd.DataFrame) -> list[str]:
    if index_summary.empty or "category" not in index_summary.columns or "allows_new_position" not in index_summary.columns:
        return []

    categories: list[str] = []
    eligible = index_summary[index_summary["allows_new_position"].fillna(False).astype(bool)]
    for category in eligible["category"].dropna().astype(str):
        if category not in categories:
            categories.append(category)
    return categories


def _filter_etf_codes_by_categories(master: pd.DataFrame, categories: list[str]) -> list[str]:
    if master.empty or not categories or "etf_code" not in master.columns or "category" not in master.columns:
        return []

    mask = master["category"].astype(str).isin(categories)
    if "is_active" in master.columns:
        mask &= master["is_active"].fillna(1).astype(int) == 1
    return master.loc[mask, "etf_code"].map(_format_etf_code).drop_duplicates().tolist()


def _index_trend_display_frame(index_summary: pd.DataFrame) -> pd.DataFrame:
    display = _research_select_columns(index_summary, INDEX_TREND_COLUMNS)
    for column in ["large_trend", "medium_trend", "small_trend"]:
        if column in display.columns:
            display[column] = display[column].map(lambda value: TREND_DISPLAY_NAMES.get(str(value), str(value)))
    if "allows_new_position" in display.columns:
        display["allows_new_position"] = display["allows_new_position"].map(
            lambda value: "可开仓 Eligible" if bool(value) else "暂不参与 Skip"
        )
    return _research_display_frame(display)


def _index_sync_status_message(summary: pd.DataFrame) -> tuple[str, str]:
    if summary.empty or "status" not in summary.columns:
        return "warning", "指数同步没有返回结果。"

    statuses = summary["status"].fillna("").astype(str).str.upper()
    wrote_count = int(statuses.isin(["INITIALIZED", "UPDATED"]).sum())
    skipped_count = int((statuses == "SKIPPED").sum())
    empty_count = int((statuses == "EMPTY").sum())
    failed_count = int((statuses == "FAILED").sum())

    parts: list[str] = []
    if wrote_count:
        parts.append(f"{wrote_count} 个写入/补齐")
    if skipped_count:
        parts.append(f"{skipped_count} 个已是最新")
    if empty_count:
        parts.append(f"{empty_count} 个无返回数据")
    if failed_count:
        parts.append(f"{failed_count} 个失败")
    if not parts:
        parts.append(f"{len(summary)} 个已处理")

    latest_date = _latest_index_sync_date(summary)
    latest_text = f"最新本地交易日 {latest_date}。" if latest_date else "未获得最新本地交易日。"
    level = "success"
    if failed_count or empty_count:
        level = "warning"
    if failed_count == len(summary):
        level = "error"
    return level, f"指数同步完成：{'，'.join(parts)}。{latest_text}"


def _latest_index_sync_date(summary: pd.DataFrame) -> str:
    if "end_date" not in summary.columns:
        return ""
    dates = pd.to_datetime(summary["end_date"], errors="coerce").dropna()
    if dates.empty:
        return ""
    return pd.Timestamp(dates.max()).strftime("%Y-%m-%d")


def _index_sync_display_frame(summary: pd.DataFrame) -> pd.DataFrame:
    display = _research_select_columns(summary, INDEX_SYNC_COLUMNS)
    if "status" in display.columns:
        display["status"] = display["status"].map(lambda value: INDEX_SYNC_STATUS_DISPLAY_NAMES.get(str(value), str(value)))
    if "end_date" in display.columns:
        display["end_date"] = pd.to_datetime(display["end_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    if "error_message" in display.columns:
        display["error_message"] = display["error_message"].fillna("")
    return display.rename(columns=INDEX_SYNC_COLUMN_LABELS)


def _render_latest_index_sync_result() -> None:
    sync_message = st.session_state.get("latest_index_sync_message")
    if isinstance(sync_message, dict):
        level = str(sync_message.get("level", "info"))
        message = str(sync_message.get("message", ""))
        renderer = {
            "success": st.success,
            "warning": st.warning,
            "error": st.error,
            "info": st.info,
        }.get(level, st.info)
        renderer(message)

    sync_summary = st.session_state.get("latest_index_sync_summary")
    if isinstance(sync_summary, pd.DataFrame) and not sync_summary.empty:
        with st.expander("查看指数同步明细", expanded=False):
            _render_research_table(_index_sync_display_frame(sync_summary), height=320)


def _format_index_rule_names(rules: list[str]) -> list[str]:
    return [INDEX_RULE_DISPLAY_NAMES.get(str(rule), f"未识别规则：{rule}") for rule in rules]


def _format_index_risk_names(risks: list[str]) -> list[str]:
    return [INDEX_RISK_DISPLAY_NAMES.get(str(risk), f"未识别风险：{risk}") for risk in risks]


def _index_option_label(row: pd.Series) -> str:
    status = "可找买点" if bool(row.get("allows_new_position", False)) else "暂不参与"
    return f"{row['index_code']} {row['index_name']}｜{row['category']}｜{status}"


def _index_status_code_items(regime: object, last: pd.Series) -> list[dict[str, str]]:
    return [
        {
            "label": "指数状态",
            "value": "可找买点" if bool(getattr(regime, "allows_new_position", False)) else "暂不参与",
        },
        {
            "label": "大趋势",
            "value": TREND_VALUE_NAMES.get(str(getattr(regime, "large_trend", "")), str(getattr(regime, "large_trend", ""))),
        },
        {
            "label": "中趋势",
            "value": TREND_VALUE_NAMES.get(str(getattr(regime, "medium_trend", "")), str(getattr(regime, "medium_trend", ""))),
        },
        {
            "label": "小趋势",
            "value": TREND_VALUE_NAMES.get(str(getattr(regime, "small_trend", "")), str(getattr(regime, "small_trend", ""))),
        },
        {"label": "最新收盘", "value": f"{float(last['close']):.2f}"},
    ]


def _render_index_status_code(items: list[dict[str, str]]) -> None:
    cells = "\n".join(
        (
            '<div class="index-status-code__item">'
            f'<div class="index-status-code__label">{item["label"]}</div>'
            f'<div class="index-status-code__value">{item["value"]}</div>'
            "</div>"
        )
        for item in items
    )
    st.markdown("#### 当前指数状态码")
    st.markdown(f'<div class="index-status-code">{cells}</div>', unsafe_allow_html=True)


def _filter_index_picker_frame(
    index_summary: pd.DataFrame,
    *,
    status_filter: str,
    category_filter: str,
) -> pd.DataFrame:
    frame = index_summary.copy()
    if frame.empty:
        return frame
    if category_filter != "全部分类" and "category" in frame.columns:
        frame = frame[frame["category"].astype(str) == category_filter]
    if status_filter == "可找买点" and "allows_new_position" in frame.columns:
        frame = frame[frame["allows_new_position"].fillna(False).astype(bool)]
    elif status_filter == "暂不参与" and "allows_new_position" in frame.columns:
        frame = frame[~frame["allows_new_position"].fillna(False).astype(bool)]
    return frame.reset_index(drop=True)


def _index_gate_markers(featured_prices: pd.DataFrame) -> list[dict[str, object]]:
    states = _entry_states_from_regime_states(_index_regime_signal_states(featured_prices))
    return _raw_index_signal_markers_from_states(states)


def _raw_index_signal_markers_from_states(states: list[dict[str, object]]) -> list[dict[str, object]]:
    markers: list[dict[str, object]] = []
    previous_allowed = False
    for state in states:
        allowed = bool(state["allowed"])
        if allowed and not previous_allowed:
            markers.append(
                {
                    "trade_date": pd.Timestamp(state["trade_date"]),
                    "action": "BUY",
                    "price": float(state.get("price", 0.0)),
                    "weight_before": 0.0,
                    "weight_after": 1.0,
                    "marker_text": "BUY",
                    "note": "指数趋势转为可找 ETF 买点",
                }
            )
        elif previous_allowed and not allowed:
            markers.append(
                {
                    "trade_date": pd.Timestamp(state["trade_date"]),
                    "action": "SELL",
                    "price": float(state.get("price", 0.0)),
                    "weight_before": 1.0,
                    "weight_after": 0.0,
                    "marker_text": "SELL",
                    "note": "指数趋势转为暂停参与",
                }
            )
        previous_allowed = allowed
    return markers


def _index_allowed_states(featured_prices: pd.DataFrame) -> list[dict[str, object]]:
    return _entry_states_from_regime_states(_index_regime_signal_states(featured_prices))


def _entry_states_from_regime_states(states: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "trade_date": state["trade_date"],
            "allowed": bool(state.get("entry_allowed", False)),
            "price": float(state.get("price", 0.0)),
        }
        for state in states
    ]


def _index_regime_signal_states(featured_prices: pd.DataFrame) -> list[dict[str, object]]:
    if featured_prices.empty:
        return []

    classifier = TrendRegimeClassifier()
    states: list[dict[str, object]] = []
    sorted_prices = featured_prices.sort_values("trade_date")
    for row in sorted_prices.to_dict("records"):
        regime = classifier.classify(row)
        states.append(
            {
                "trade_date": pd.Timestamp(row["trade_date"]),
                "entry_allowed": bool(regime.allows_new_position),
                "hold_allowed": _index_hold_allowed(regime, row),
                "long_hold_allowed": _index_long_hold_allowed(regime, row),
                "price": _coerce_float(row.get("close"), 0.0),
            }
        )
    return states


def _index_hold_allowed(regime: object, row: object) -> bool:
    large = str(getattr(regime, "large_trend", ""))
    medium = str(getattr(regime, "medium_trend", ""))
    small = str(getattr(regime, "small_trend", ""))
    close = _coerce_float(_row_get(row, "close"), None)
    ma120 = _coerce_float(_row_get(row, "ma120"), None)
    if large not in {"UP", "RECOVERY"}:
        return False
    if medium in {"DOWN", "UNKNOWN", "REBOUND"}:
        return False
    if small == "BROKEN":
        return False
    if close is not None and ma120 is not None and close < ma120:
        return False
    return True


def _index_long_hold_allowed(regime: object, row: object) -> bool:
    large = str(getattr(regime, "large_trend", ""))
    close = _coerce_float(_row_get(row, "close"), None)
    ma250 = _coerce_float(_row_get(row, "ma250"), None)
    if large not in {"UP", "RECOVERY"}:
        return False
    if close is not None and ma250 is not None and close < ma250:
        return False
    return True


def _row_get(row: object, key: str) -> object:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _coerce_float(value: object, default: float | None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if pd.isna(result) else result


def _stable_index_signal_markers(
    states: list[dict[str, object]],
    *,
    entry_confirm_days: int = STABLE_INDEX_SIGNAL_PARAMS["entry_confirm_days"],
    exit_confirm_days: int = STABLE_INDEX_SIGNAL_PARAMS["exit_confirm_days"],
    min_hold_days: int = STABLE_INDEX_SIGNAL_PARAMS["min_hold_days"],
    cooldown_days: int = STABLE_INDEX_SIGNAL_PARAMS["cooldown_days"],
) -> list[dict[str, object]]:
    markers: list[dict[str, object]] = []
    in_position = False
    allowed_streak = 0
    blocked_streak = 0
    hold_days = 0
    cooldown_left = 0

    for state in sorted(states, key=lambda item: pd.Timestamp(item["trade_date"])):
        allowed = bool(state.get("allowed", False))
        price = float(state.get("price", 0.0))
        trade_date = pd.Timestamp(state["trade_date"])

        if in_position:
            hold_days += 1
            if allowed:
                blocked_streak = 0
                continue
            blocked_streak += 1
            if hold_days >= min_hold_days and blocked_streak >= exit_confirm_days:
                markers.append(
                    {
                        "trade_date": trade_date,
                        "action": "SELL",
                        "price": price,
                        "weight_before": 1.0,
                        "weight_after": 0.0,
                        "marker_text": "SELL",
                        "note": f"稳定确认：连续{exit_confirm_days}个交易日不再允许参与",
                    }
                )
                in_position = False
                hold_days = 0
                blocked_streak = 0
                allowed_streak = 0
                cooldown_left = cooldown_days
            continue

        if cooldown_left > 0:
            cooldown_left -= 1
        if not allowed or cooldown_left > 0:
            allowed_streak = 0
            continue

        allowed_streak += 1
        if allowed_streak >= entry_confirm_days:
            markers.append(
                {
                    "trade_date": trade_date,
                    "action": "BUY",
                    "price": price,
                    "weight_before": 0.0,
                    "weight_after": 1.0,
                    "marker_text": "BUY",
                    "note": f"稳定确认：连续{entry_confirm_days}个交易日允许参与",
                }
            )
            in_position = True
            hold_days = 0
            blocked_streak = 0
            allowed_streak = 0

    return markers


def _long_trend_index_signal_markers(
    states: list[dict[str, object]],
    *,
    entry_confirm_days: int = STABLE_INDEX_SIGNAL_PARAMS["entry_confirm_days"],
    exit_confirm_days: int = STABLE_INDEX_SIGNAL_PARAMS["exit_confirm_days"],
    min_hold_days: int = STABLE_INDEX_SIGNAL_PARAMS["min_hold_days"],
    cooldown_days: int = STABLE_INDEX_SIGNAL_PARAMS["cooldown_days"],
) -> list[dict[str, object]]:
    markers: list[dict[str, object]] = []
    in_position = False
    entry_streak = 0
    exit_streak = 0
    hold_days = 0
    cooldown_left = 0

    for state in sorted(states, key=lambda item: pd.Timestamp(item["trade_date"])):
        entry_allowed = bool(state.get("entry_allowed", state.get("allowed", False)))
        long_hold_allowed = bool(state.get("long_hold_allowed", state.get("hold_allowed", entry_allowed)))
        price = float(state.get("price", 0.0))
        trade_date = pd.Timestamp(state["trade_date"])

        if in_position:
            hold_days += 1
            if long_hold_allowed:
                exit_streak = 0
                continue
            exit_streak += 1
            if hold_days >= min_hold_days and exit_streak >= exit_confirm_days:
                markers.append(
                    {
                        "trade_date": trade_date,
                        "action": "SELL",
                        "price": price,
                        "weight_before": 1.0,
                        "weight_after": 0.0,
                        "marker_text": "SELL",
                        "note": f"长期趋势：长期趋势连续{exit_confirm_days}日失效",
                    }
                )
                in_position = False
                hold_days = 0
                exit_streak = 0
                entry_streak = 0
                cooldown_left = cooldown_days
            continue

        if cooldown_left > 0:
            cooldown_left -= 1
        if not entry_allowed or cooldown_left > 0:
            entry_streak = 0
            continue

        entry_streak += 1
        if entry_streak >= entry_confirm_days:
            markers.append(
                {
                    "trade_date": trade_date,
                    "action": "BUY",
                    "price": price,
                    "weight_before": 0.0,
                    "weight_after": 1.0,
                    "marker_text": "BUY",
                    "note": f"长期趋势：连续{entry_confirm_days}日出现买入窗口",
                }
            )
            in_position = True
            hold_days = 0
            exit_streak = 0
            entry_streak = 0

    return markers


def _trend_hold_index_signal_markers(
    states: list[dict[str, object]],
    *,
    entry_confirm_days: int = STABLE_INDEX_SIGNAL_PARAMS["entry_confirm_days"],
    exit_confirm_days: int = STABLE_INDEX_SIGNAL_PARAMS["exit_confirm_days"],
    min_hold_days: int = STABLE_INDEX_SIGNAL_PARAMS["min_hold_days"],
    cooldown_days: int = STABLE_INDEX_SIGNAL_PARAMS["cooldown_days"],
) -> list[dict[str, object]]:
    markers: list[dict[str, object]] = []
    in_position = False
    entry_streak = 0
    exit_streak = 0
    hold_days = 0
    cooldown_left = 0

    for state in sorted(states, key=lambda item: pd.Timestamp(item["trade_date"])):
        entry_allowed = bool(state.get("entry_allowed", state.get("allowed", False)))
        hold_allowed = bool(state.get("hold_allowed", entry_allowed))
        price = float(state.get("price", 0.0))
        trade_date = pd.Timestamp(state["trade_date"])

        if in_position:
            hold_days += 1
            if hold_allowed:
                exit_streak = 0
                continue
            exit_streak += 1
            if hold_days >= min_hold_days and exit_streak >= exit_confirm_days:
                markers.append(
                    {
                        "trade_date": trade_date,
                        "action": "SELL",
                        "price": price,
                        "weight_before": 1.0,
                        "weight_after": 0.0,
                        "marker_text": "SELL",
                        "note": f"趋势持有：持有条件连续{exit_confirm_days}日失效",
                    }
                )
                in_position = False
                hold_days = 0
                exit_streak = 0
                entry_streak = 0
                cooldown_left = cooldown_days
            continue

        if cooldown_left > 0:
            cooldown_left -= 1
        if not entry_allowed or cooldown_left > 0:
            entry_streak = 0
            continue

        entry_streak += 1
        if entry_streak >= entry_confirm_days:
            markers.append(
                {
                    "trade_date": trade_date,
                    "action": "BUY",
                    "price": price,
                    "weight_before": 0.0,
                    "weight_after": 1.0,
                    "marker_text": "BUY",
                    "note": f"趋势持有：连续{entry_confirm_days}日出现买入窗口",
                }
            )
            in_position = True
            hold_days = 0
            exit_streak = 0
            entry_streak = 0

    return markers


def _index_signal_markers_for_rule(
    selected_rule: str,
    regime_states: list[dict[str, object]],
    *,
    entry_confirm_days: int = STABLE_INDEX_SIGNAL_PARAMS["entry_confirm_days"],
    exit_confirm_days: int = STABLE_INDEX_SIGNAL_PARAMS["exit_confirm_days"],
    min_hold_days: int = STABLE_INDEX_SIGNAL_PARAMS["min_hold_days"],
    cooldown_days: int = STABLE_INDEX_SIGNAL_PARAMS["cooldown_days"],
) -> list[dict[str, object]]:
    if selected_rule == "raw":
        return _raw_index_signal_markers_from_states(_entry_states_from_regime_states(regime_states))
    if selected_rule == "stable":
        return _stable_index_signal_markers(
            _entry_states_from_regime_states(regime_states),
            entry_confirm_days=entry_confirm_days,
            exit_confirm_days=exit_confirm_days,
            min_hold_days=min_hold_days,
            cooldown_days=cooldown_days,
        )
    if selected_rule == "trend_hold":
        return _trend_hold_index_signal_markers(
            regime_states,
            entry_confirm_days=entry_confirm_days,
            exit_confirm_days=exit_confirm_days,
            min_hold_days=min_hold_days,
            cooldown_days=cooldown_days,
        )
    return _long_trend_index_signal_markers(
        regime_states,
        entry_confirm_days=entry_confirm_days,
        exit_confirm_days=exit_confirm_days,
        min_hold_days=min_hold_days,
        cooldown_days=cooldown_days,
    )


def _number_index_signal_segments(markers: list[dict[str, object]]) -> list[dict[str, object]]:
    if not markers:
        return []
    ordered = sorted(markers, key=lambda marker: pd.Timestamp(marker["trade_date"]))
    labelled: list[dict[str, object]] = []
    segment_number = 0
    has_open_buy = False
    for marker in ordered:
        action = str(marker.get("action", "")).upper()
        if action == "BUY":
            segment_number += 1
            has_open_buy = True
        elif action == "SELL":
            if not has_open_buy:
                segment_number += 1
            has_open_buy = False
        else:
            continue

        labelled_marker = dict(marker)
        labelled_marker["marker_text"] = f"{action}{segment_number}"
        labelled.append(labelled_marker)
    return labelled


def _index_gate_history_frame(markers: list[dict[str, object]]) -> pd.DataFrame:
    if not markers:
        return pd.DataFrame(columns=["日期 Date", "信号 Signal", "说明 Note"])

    rows = []
    for marker in sorted(markers, key=lambda item: pd.Timestamp(item["trade_date"]), reverse=True):
        action = str(marker.get("action", ""))
        rows.append(
            {
                "日期 Date": pd.Timestamp(marker["trade_date"]).strftime("%Y-%m-%d"),
                "信号 Signal": "BUY 买入参考" if action == "BUY" else "SELL 卖出/暂停",
                "说明 Note": str(marker.get("note", "")),
            }
        )
    return pd.DataFrame(rows)


def _backtest_index_signal_markers(prices: pd.DataFrame, markers: list[dict[str, object]]) -> dict[str, object]:
    frame = _index_backtest_price_frame(prices)
    if frame.empty:
        return {
            "nav": pd.DataFrame(columns=["trade_date", "strategy_nav", "buy_hold_nav", "weight"]),
            "trades": pd.DataFrame(columns=["signal_date", "trade_date", "action", "price", "weight_before", "weight_after"]),
            "metrics": _empty_index_signal_metrics(),
        }

    first_date = pd.Timestamp(frame["trade_date"].iloc[0]).normalize()
    execution_map = _index_signal_execution_map(frame, markers, first_date)
    in_position = _initial_index_position(markers, first_date)
    first_close = float(frame["close"].iloc[0])
    cash = 0.0 if in_position else 1.0
    units = 0.0 if not in_position or first_close == 0 else 1.0 / first_close
    trade_rows: list[dict[str, object]] = []
    nav_rows: list[dict[str, float | pd.Timestamp]] = []

    for row in frame.itertuples(index=True):
        row_index = int(row.Index)
        open_price = float(row.open)
        close_price = float(row.close)
        trade_date = pd.Timestamp(row.trade_date)

        for signal in execution_map.get(row_index, []):
            action = str(signal.get("action", "")).upper()
            if action == "BUY" and not in_position and open_price > 0:
                trade_rows.append(
                    {
                        "signal_date": pd.Timestamp(signal["trade_date"]),
                        "trade_date": trade_date,
                        "action": "BUY",
                        "price": open_price,
                        "weight_before": 0.0,
                        "weight_after": 1.0,
                    }
                )
                units = cash / open_price
                cash = 0.0
                in_position = True
            elif action == "SELL" and in_position and open_price > 0:
                trade_rows.append(
                    {
                        "signal_date": pd.Timestamp(signal["trade_date"]),
                        "trade_date": trade_date,
                        "action": "SELL",
                        "price": open_price,
                        "weight_before": 1.0,
                        "weight_after": 0.0,
                    }
                )
                cash = units * open_price
                units = 0.0
                in_position = False

        nav = cash + units * close_price
        weight = 0.0 if nav == 0 else (units * close_price) / nav
        buy_hold_nav = 1.0 if first_close == 0 else close_price / first_close
        nav_rows.append(
            {
                "trade_date": trade_date,
                "strategy_nav": float(nav),
                "buy_hold_nav": float(buy_hold_nav),
                "weight": float(weight),
            }
        )

    nav = pd.DataFrame(nav_rows)
    trades = pd.DataFrame(trade_rows)
    metrics = _index_signal_backtest_metrics(nav, trades)
    return {"nav": nav, "trades": trades, "metrics": metrics}


def _index_backtest_price_frame(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty or "trade_date" not in prices.columns or "close" not in prices.columns:
        return pd.DataFrame(columns=["trade_date", "open", "close"])

    frame = prices.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values("trade_date").reset_index(drop=True)
    if "open" not in frame.columns:
        frame["open"] = frame["close"]
    frame["open"] = pd.to_numeric(frame["open"], errors="coerce").fillna(frame["close"]).astype(float)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce").astype(float)
    frame = frame.dropna(subset=["trade_date", "open", "close"])
    return frame[["trade_date", "open", "close"]].reset_index(drop=True)


def _index_signal_execution_map(
    prices: pd.DataFrame,
    markers: list[dict[str, object]],
    first_date: pd.Timestamp,
) -> dict[int, list[dict[str, object]]]:
    execution_map: dict[int, list[dict[str, object]]] = {}
    ordered = sorted(markers, key=lambda marker: pd.Timestamp(marker["trade_date"]))
    for marker in ordered:
        action = str(marker.get("action", "")).upper()
        if action not in {"BUY", "SELL"}:
            continue
        signal_date = pd.Timestamp(marker["trade_date"]).normalize()
        if signal_date < first_date:
            continue
        next_rows = prices.index[prices["trade_date"].dt.normalize() > signal_date]
        if len(next_rows) == 0:
            continue
        row_index = int(next_rows[0])
        execution_map.setdefault(row_index, []).append(marker)
    return execution_map


def _initial_index_position(markers: list[dict[str, object]], first_date: pd.Timestamp) -> bool:
    prior = [
        marker
        for marker in markers
        if pd.Timestamp(marker["trade_date"]).normalize() < first_date
        and str(marker.get("action", "")).upper() in {"BUY", "SELL"}
    ]
    if not prior:
        return False
    last_marker = max(prior, key=lambda marker: pd.Timestamp(marker["trade_date"]))
    return str(last_marker.get("action", "")).upper() == "BUY"


def _index_signal_backtest_metrics(nav: pd.DataFrame, trades: pd.DataFrame) -> dict[str, float]:
    if nav.empty:
        return _empty_index_signal_metrics()

    strategy_total = _nav_total_return(nav["strategy_nav"])
    buy_hold_total = _nav_total_return(nav["buy_hold_nav"])
    strategy_drawdown = _nav_max_drawdown(nav["strategy_nav"])
    buy_hold_drawdown = _nav_max_drawdown(nav["buy_hold_nav"])
    trade_metrics = _index_signal_trade_metrics(trades)
    days = max((pd.Timestamp(nav["trade_date"].iloc[-1]) - pd.Timestamp(nav["trade_date"].iloc[0])).days, 0)
    period_years = days / 365.25 if days > 0 else 0.0
    trade_count = float(trade_metrics["trade_count"])

    return {
        "strategy_total_return": round(strategy_total, 6),
        "buy_hold_total_return": round(buy_hold_total, 6),
        "excess_return": round(strategy_total - buy_hold_total, 6),
        "strategy_max_drawdown": round(strategy_drawdown, 6),
        "buy_hold_max_drawdown": round(buy_hold_drawdown, 6),
        "drawdown_improvement": round(strategy_drawdown - buy_hold_drawdown, 6),
        "avg_exposure": round(float(nav["weight"].mean()), 6),
        "period_years": round(period_years, 6),
        "trades_per_year": round(trade_count / period_years, 6) if period_years else trade_count,
        **trade_metrics,
    }


def _empty_index_signal_metrics() -> dict[str, float]:
    return {
        "strategy_total_return": 0.0,
        "buy_hold_total_return": 0.0,
        "excess_return": 0.0,
        "strategy_max_drawdown": 0.0,
        "buy_hold_max_drawdown": 0.0,
        "drawdown_improvement": 0.0,
        "avg_exposure": 0.0,
        "period_years": 0.0,
        "trades_per_year": 0.0,
        "trade_count": 0.0,
        "closed_trade_count": 0.0,
        "win_rate": 0.0,
        "avg_trade_return": 0.0,
        "avg_holding_days": 0.0,
    }


def _nav_total_return(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    start = float(series.iloc[0])
    if start == 0:
        return 0.0
    return float(series.iloc[-1]) / start - 1.0


def _nav_max_drawdown(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    running_max = series.cummax()
    drawdown = series / running_max - 1.0
    return float(drawdown.min())


def _index_signal_trade_metrics(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {
            "trade_count": 0.0,
            "closed_trade_count": 0.0,
            "win_rate": 0.0,
            "avg_trade_return": 0.0,
            "avg_holding_days": 0.0,
        }

    ordered = trades.sort_values("trade_date").reset_index(drop=True)
    closed_returns: list[float] = []
    holding_days: list[float] = []
    open_trade: pd.Series | None = None
    for _, trade in ordered.iterrows():
        action = str(trade["action"]).upper()
        if action == "BUY":
            open_trade = trade
            continue
        if action != "SELL" or open_trade is None:
            continue
        buy_price = float(open_trade["price"])
        sell_price = float(trade["price"])
        if buy_price != 0:
            closed_returns.append(sell_price / buy_price - 1.0)
        holding_days.append(float((pd.Timestamp(trade["trade_date"]) - pd.Timestamp(open_trade["trade_date"])).days))
        open_trade = None

    closed_count = len(closed_returns)
    wins = sum(1 for value in closed_returns if value > 0)
    return {
        "trade_count": float(len(ordered)),
        "closed_trade_count": float(closed_count),
        "win_rate": round(wins / closed_count, 6) if closed_count else 0.0,
        "avg_trade_return": round(float(sum(closed_returns) / closed_count), 6) if closed_count else 0.0,
        "avg_holding_days": round(float(sum(holding_days) / len(holding_days)), 6) if holding_days else 0.0,
    }


def _index_signal_problem_diagnostics(metrics: dict[str, float]) -> list[str]:
    if float(metrics.get("trade_count", 0.0)) == 0:
        return ["当前区间没有可执行的买卖参考信号，暂时无法评价择时质量。"]

    diagnostics: list[str] = []
    excess_return = float(metrics.get("excess_return", 0.0))
    drawdown_improvement = float(metrics.get("drawdown_improvement", 0.0))
    trades_per_year = float(metrics.get("trades_per_year", 0.0))
    avg_holding_days = float(metrics.get("avg_holding_days", 0.0))
    win_rate = float(metrics.get("win_rate", 0.0))
    avg_trade_return = float(metrics.get("avg_trade_return", 0.0))
    closed_trade_count = float(metrics.get("closed_trade_count", metrics.get("trade_count", 0.0)))

    if excess_return < -0.02:
        diagnostics.append(f"跑输买入持有：当前规则少赚 {_format_percent(abs(excess_return))}，说明过滤没有换来更好的收益。")
    if trades_per_year > 18:
        diagnostics.append(f"交易过密：折算每年约 {trades_per_year:.1f} 次信号，容易被噪音和成本吞掉收益。")
    if drawdown_improvement <= 0:
        diagnostics.append("回撤没有改善：策略最大回撤不优于买入持有，趋势过滤的防守价值不足。")
    if avg_holding_days and avg_holding_days < 10:
        diagnostics.append(f"持有期过短：平均只持有 {avg_holding_days:.1f} 天，更像短线抖动而不是趋势交易。")
    if closed_trade_count > 0 and (win_rate < 0.45 or avg_trade_return <= 0):
        diagnostics.append(
            f"买卖点质量偏弱：胜率 {win_rate:.0%}，单笔平均收益 {_format_percent(avg_trade_return)}，进出场位置还需要重做。"
        )
    if not diagnostics:
        diagnostics.append("当前区间没有暴露明显硬伤，但还需要跨指数、跨年份继续验证。")
    return diagnostics


def _index_signal_diagnostic_display_frame(metrics: dict[str, float]) -> pd.DataFrame:
    rows = [
        ("策略收益", _format_percent(metrics.get("strategy_total_return", 0.0))),
        ("买入持有收益", _format_percent(metrics.get("buy_hold_total_return", 0.0))),
        ("超额收益", _format_percent(metrics.get("excess_return", 0.0))),
        ("最大回撤", _format_percent(metrics.get("strategy_max_drawdown", 0.0))),
        ("交易次数", f"{float(metrics.get('trade_count', 0.0)):.0f}"),
        ("年化交易次数", f"{float(metrics.get('trades_per_year', 0.0)):.1f}"),
        ("胜率", _format_percent(metrics.get("win_rate", 0.0))),
        ("单笔平均收益", _format_percent(metrics.get("avg_trade_return", 0.0))),
        ("平均持有天数", f"{float(metrics.get('avg_holding_days', 0.0)):.1f}天"),
        ("平均在场比例", _format_percent(metrics.get("avg_exposure", 0.0))),
    ]
    return pd.DataFrame(rows, columns=["指标", "数值"])


def _format_percent(value: object) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


def _index_signal_nav_chart(nav: pd.DataFrame) -> alt.Chart:
    if nav.empty:
        return alt.Chart(pd.DataFrame({"日期": [], "净值": [], "路径": []})).mark_line()
    chart_data = nav[["trade_date", "strategy_nav", "buy_hold_nav"]].rename(
        columns={"trade_date": "日期", "strategy_nav": "策略净值", "buy_hold_nav": "买入持有净值"}
    )
    long = chart_data.melt("日期", var_name="路径", value_name="净值")
    return (
        alt.Chart(long)
        .mark_line(strokeWidth=2)
        .encode(
            x=alt.X("日期:T", title="日期"),
            y=alt.Y("净值:Q", title="净值", scale=alt.Scale(zero=False)),
            color=alt.Color("路径:N", title=""),
            tooltip=[
                alt.Tooltip("日期:T", title="日期"),
                alt.Tooltip("路径:N", title="路径"),
                alt.Tooltip("净值:Q", title="净值", format=".3f"),
            ],
        )
        .properties(height=260)
    )


def _render_index_signal_diagnostics(prices: pd.DataFrame, markers: list[dict[str, object]]) -> None:
    result = _backtest_index_signal_markers(prices, markers)
    metrics = result["metrics"]
    diagnostics = _index_signal_problem_diagnostics(metrics)

    st.markdown("#### 策略诊断")
    st.caption("按当前图表区间估算；信号日后一交易日开盘成交；暂不含手续费、滑点和 ETF 跟踪误差。")
    metric_cols = st.columns(4)
    metric_cols[0].metric("策略收益", _format_percent(metrics["strategy_total_return"]))
    metric_cols[1].metric("买入持有", _format_percent(metrics["buy_hold_total_return"]))
    metric_cols[2].metric("超额收益", _format_percent(metrics["excess_return"]))
    metric_cols[3].metric("年化信号", f"{float(metrics['trades_per_year']):.1f}次")

    if any(("跑输" in item or "过密" in item or "质量偏弱" in item or "回撤没有改善" in item) for item in diagnostics):
        st.warning("主要问题：\n" + "\n".join(f"- {item}" for item in diagnostics))
    else:
        st.success("主要问题：\n" + "\n".join(f"- {item}" for item in diagnostics))

    st.altair_chart(_index_signal_nav_chart(result["nav"]), width="stretch")
    detail_cols = st.columns([1, 1])
    detail_cols[0].dataframe(
        _index_signal_diagnostic_display_frame(metrics),
        width="stretch",
        hide_index=True,
        height=388,
    )
    trades = result["trades"]
    if trades.empty:
        detail_cols[1].info("当前区间没有可展示的实际成交参考。")
    else:
        trade_display = trades.copy()
        trade_display["signal_date"] = pd.to_datetime(trade_display["signal_date"]).dt.strftime("%Y-%m-%d")
        trade_display["trade_date"] = pd.to_datetime(trade_display["trade_date"]).dt.strftime("%Y-%m-%d")
        trade_display["price"] = trade_display["price"].round(2)
        trade_display = trade_display.rename(
            columns={
                "signal_date": "信号日",
                "trade_date": "成交日",
                "action": "动作",
                "price": "成交价",
                "weight_before": "前仓位",
                "weight_after": "后仓位",
            }
        )
        detail_cols[1].dataframe(
            trade_display[["信号日", "成交日", "动作", "成交价", "前仓位", "后仓位"]],
            width="stretch",
            hide_index=True,
            height=388,
        )


def _render_index_filter_explorer(index_summary: pd.DataFrame, parquet_store: ParquetStore) -> None:
    st.markdown("### 指数级买卖参考")
    st.info(
        "当前规则：三层趋势过滤 + 长期趋势退出。入场先看大趋势是否向上或修复，再看中趋势是否转强，最后看小趋势是否出现右侧开始或回踩。"
        "持仓后不因短线过热或中期震荡直接卖出，只有长期趋势连续失效才退出。图上的 BUY/SELL 是指数过滤层参考，不是具体 ETF 下单。"
    )

    available = index_summary.copy()
    if available.empty:
        st.info("暂无指数趋势数据。")
        return

    st.markdown("#### 选择指数")
    picker_cols = st.columns([1.1, 1.1, 2.4])
    status_filter = picker_cols[0].radio(
        "指数状态",
        ["可找买点", "全部", "暂不参与"],
        horizontal=True,
        key="index_signal_status_filter",
    )
    category_options = ["全部分类"] + sorted(available["category"].dropna().astype(str).unique().tolist())
    category_filter = picker_cols[1].selectbox("指数分类", category_options, key="index_signal_category_filter")
    picker_frame = _filter_index_picker_frame(
        available,
        status_filter=status_filter,
        category_filter=category_filter,
    )
    if picker_frame.empty:
        st.warning("当前筛选条件下没有指数，已临时显示全部指数。")
        picker_frame = available.reset_index(drop=True)

    labels = [_index_option_label(row) for _, row in picker_frame.iterrows()]
    selected_label = picker_cols[2].selectbox("指数", labels, key="index_filter_explorer_v2")
    selected_code = selected_label.split()[0]
    row = available[available["index_code"].astype(str) == selected_code].iloc[0]

    prices = parquet_store.read_index_prices(selected_code)
    if prices.empty:
        st.warning("本地尚无该指数历史数据。请在“数据与设置”补齐指数历史。")
        _render_research_table(_index_trend_display_frame(index_summary), height=360)
        return

    featured = add_trend_regime_features(prices.rename(columns={"index_code": "etf_code"}))
    last = featured.iloc[-1]
    regime = TrendRegimeClassifier().classify(last)

    _render_index_status_code(_index_status_code_items(regime, last))

    rule_cols = st.columns(2)
    trigger_text = "\n".join(f"- {item}" for item in _format_index_rule_names(regime.trigger_rules)) or "无"
    risk_text = "\n".join(f"- {item}" for item in _format_index_risk_names(regime.risk_tags)) or "无"
    rule_cols[0].info("触发条件：\n" + trigger_text)
    rule_cols[1].warning("风险提示：\n" + risk_text)

    chart_cols = st.columns([1.7, 1])
    with chart_cols[0]:
        recent = _chart_range_controls(featured, "index_signal", default_label="近2年")
    signal_rule_label = chart_cols[1].radio(
        "信号规则",
        list(INDEX_SIGNAL_RULE_OPTIONS),
        horizontal=True,
        key="index_signal_rule",
    )
    selected_rule = INDEX_SIGNAL_RULE_OPTIONS[signal_rule_label]
    if selected_rule == "long_trend":
        chart_cols[1].caption(
            "长期趋势版：买入连续3日确认；持有时只在长期趋势和长期均线连续失效后退出，避免主升段中过早离场。"
        )
    elif selected_rule == "trend_hold":
        chart_cols[1].caption(
            "趋势持有版：买入连续3日确认；持有时允许短线过热，退出看大/中趋势和中期均线连续失效。"
        )
    elif selected_rule == "stable":
        chart_cols[1].caption(
            "稳定确认版：买入连续3日确认，卖出连续3日失效，最短持有10日，卖后冷却5日。"
        )
    else:
        chart_cols[1].caption("原始日切换：当天允许就 BUY，当天失效就 SELL，仅用于对照。")

    recent_start = pd.Timestamp(recent["trade_date"].min()).normalize()
    recent_end = pd.Timestamp(recent["trade_date"].max()).normalize()
    with st.spinner("正在计算当前指数信号..."):
        regime_states = _index_regime_signal_states(featured)
        all_markers = _index_signal_markers_for_rule(selected_rule, regime_states)
    visible_markers = [
        marker for marker in all_markers
        if recent_start <= pd.Timestamp(marker["trade_date"]).normalize() <= recent_end
    ]
    markers = _number_index_signal_segments(visible_markers)
    st.caption(f"当前区间显示 {len(markers)} 个买卖参考信号。")
    chart_type, price_scale_mode, ma_columns = _chart_display_controls(
        "index_signal_chart",
        default_chart_label="收盘折线 Close Line",
        default_ma_labels=[],
    )
    payload = build_lightweight_chart_payload(
        recent,
        trades=markers,
        chart_type=chart_type,
        price_scale_mode=price_scale_mode,
        ma_columns=ma_columns,
    )
    if renderLightweightCharts is None:
        st.json(payload)
    else:
        renderLightweightCharts(payload, key=f"index-filter-signals-{selected_code}")

    _render_index_signal_diagnostics(recent, all_markers)

    with st.expander("查看历史指数买卖参考", expanded=False):
        history = _index_gate_history_frame(all_markers)
        st.dataframe(history, width="stretch", hide_index=True, height=300)

    with st.expander("查看全部指数过滤表", expanded=False):
        _render_research_table(_index_trend_display_frame(index_summary), height=420)


def _research_chart_featured_prices(
    parquet_store: ParquetStore,
    etf_code: str,
    candidate_name: str,
    universe_codes: list[str],
    min_rows: int,
) -> pd.DataFrame:
    return _research_chart_featured_prices_cached(
        str(parquet_store.root),
        _format_etf_code(etf_code),
        candidate_name,
        tuple(universe_codes),
        min_rows,
    )


@st.cache_data(show_spinner=False)
def _research_chart_featured_prices_cached(
    parquet_root: str,
    etf_code: str,
    candidate_name: str,
    universe_codes: tuple[str, ...],
    min_rows: int,
) -> pd.DataFrame:
    candidates = {candidate.name: candidate for candidate in load_research_candidates(RESEARCH_CONFIG)}
    candidate = candidates.get(candidate_name)
    if candidate is None:
        return pd.DataFrame()

    normalized_code = _format_etf_code(etf_code)
    parquet_store = ParquetStore(parquet_root)
    if candidate.rs_rank_max is None or not universe_codes:
        prices = parquet_store.read_prices(normalized_code)
        return add_trend_regime_features(prices)

    frames, _ = load_price_frames(parquet_root, min_rows=min_rows, etf_codes=universe_codes)
    featured_frames = {code: add_trend_regime_features(frame) for code, frame in frames.items()}
    ranked_frames = attach_relative_strength_rank(featured_frames)
    if normalized_code not in ranked_frames:
        prices = parquet_store.read_prices(normalized_code)
        return add_trend_regime_features(prices)
    return ranked_frames[normalized_code]


def _research_trade_display_frame(trades: list[object]) -> pd.DataFrame:
    rows = [vars(trade) if not isinstance(trade, dict) else trade for trade in trades]
    display = pd.DataFrame(rows)
    if display.empty:
        return display
    for column in ["trade_date", "signal_date"]:
        if column in display.columns:
            display[column] = pd.to_datetime(display[column]).dt.strftime("%Y-%m-%d")
    for column in ["weight_before", "weight_after"]:
        if column in display.columns:
            display[column] = (display[column].astype(float) * 100).round(2)
    return display.rename(
        columns={
            "etf_code": "ETF代码 ETF Code",
            "trade_date": "成交日期 Trade Date",
            "action": "动作 Action",
            "price": "成交价 Price",
            "weight_before": "成交前仓位 Before",
            "weight_after": "成交后仓位 After",
            "signal_date": "信号日期 Signal Date",
        }
    )


def _chart_display_controls(
    key_prefix: str,
    *,
    default_chart_label: str = "K线 Candlestick",
    default_ma_labels: list[str] | None = None,
    default_price_scale_label: str = "线性坐标 Linear",
) -> tuple[str, str, list[str]]:
    default_ma_labels = default_ma_labels if default_ma_labels is not None else ["MA51", "MA120", "MA250", "MA850"]
    control_cols = st.columns([1, 1, 2])
    chart_label = control_cols[0].radio(
        "图表类型 Chart Type",
        list(CHART_TYPE_OPTIONS),
        index=list(CHART_TYPE_OPTIONS).index(default_chart_label),
        horizontal=True,
        key=f"{key_prefix}_chart_type",
    )
    price_scale_label = control_cols[1].radio(
        "显示口径 View",
        list(PRICE_SCALE_OPTIONS),
        index=list(PRICE_SCALE_OPTIONS).index(default_price_scale_label),
        horizontal=True,
        key=f"{key_prefix}_price_scale",
    )
    price_scale_help = {
        "涨跌幅视图 Return %": "纵轴为相对区间起点的累计涨跌幅。",
        "比例视图 Log Return %": "纵轴为对数涨跌幅，等距离更接近等比例变化。",
        "回撤视图 Drawdown %": "纵轴为相对此前最高点的回撤。",
        "距区间低点 Downside %": "纵轴为从当前点位跌到区间最低点还需下跌的比例。",
    }
    if price_scale_label in price_scale_help:
        control_cols[1].caption(price_scale_help[price_scale_label])
    selected_ma_labels = control_cols[2].multiselect(
        "均线显示 Moving Averages",
        list(MA_DISPLAY_OPTIONS),
        default=default_ma_labels,
        key=f"{key_prefix}_ma_columns",
    )
    return (
        CHART_TYPE_OPTIONS[chart_label],
        PRICE_SCALE_OPTIONS[price_scale_label],
        [MA_DISPLAY_OPTIONS[label] for label in selected_ma_labels],
    )


def _chart_range_controls(frame: pd.DataFrame, key_prefix: str, *, default_label: str = "近2年") -> pd.DataFrame:
    if frame.empty or "trade_date" not in frame.columns:
        return frame

    prepared = frame.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"])
    min_date = pd.Timestamp(prepared["trade_date"].min()).date()
    max_date = pd.Timestamp(prepared["trade_date"].max()).date()
    labels = list(CHART_RANGE_PRESETS)
    default_index = labels.index(default_label) if default_label in labels else labels.index("近2年")
    range_label = st.radio(
        "图表区间",
        labels,
        index=default_index,
        horizontal=True,
        key=f"{key_prefix}_range_preset",
    )
    preset = CHART_RANGE_PRESETS[range_label]
    if preset == "custom":
        cols = st.columns(2)
        start_date = cols[0].date_input("开始日期", value=min_date, min_value=min_date, max_value=max_date, key=f"{key_prefix}_range_start")
        end_date = cols[1].date_input("结束日期", value=max_date, min_value=min_date, max_value=max_date, key=f"{key_prefix}_range_end")
        if start_date > end_date:
            st.warning("开始日期晚于结束日期，已临时按完整区间显示。")
            return prepared
        return _filter_date_range_frame(prepared, start_date, end_date)
    if preset is None:
        return prepared

    start_date = max(min_date, max_date - timedelta(days=int(preset)))
    return _filter_date_range_frame(prepared, start_date, max_date)


def _filter_date_range_frame(frame: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    prepared = frame.copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"])
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    return prepared[(prepared["trade_date"] >= start) & (prepared["trade_date"] <= end)].reset_index(drop=True)


def _research_chart_frame(frame: pd.DataFrame, index_column: str, value_columns: list[str]) -> pd.DataFrame:
    available = [column for column in value_columns if column in frame.columns]
    if index_column not in frame.columns or not available:
        return pd.DataFrame()

    chart = frame[[index_column, *available]].copy()
    if index_column in {"candidate_name", "base_candidate"}:
        chart[index_column] = chart[index_column].map(_candidate_display_name)
    chart = chart.set_index(index_column)
    chart.index.name = RESEARCH_COLUMN_LABELS.get(index_column, index_column)
    return chart.rename(columns=RESEARCH_COLUMN_LABELS)


def _inject_research_styles() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stMetricLabel"] p {
            white-space: normal;
            overflow: visible;
            text-overflow: clip;
            line-height: 1.25;
        }
        .index-status-code {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 1px;
            border: 1px solid #e5e7eb;
            border-radius: 6px;
            overflow: hidden;
            margin: 0.35rem 0 1rem 0;
            background: #e5e7eb;
        }
        .index-status-code__item {
            background: #ffffff;
            padding: 0.75rem 0.9rem;
            min-width: 0;
        }
        .index-status-code__label {
            color: #6b7280;
            font-size: 0.82rem;
            line-height: 1.2;
            margin-bottom: 0.35rem;
        }
        .index-status-code__value {
            color: #111827;
            font-size: 1.3rem;
            font-weight: 650;
            line-height: 1.2;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        @media (max-width: 900px) {
            .index-status-code {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _research_column_config(frame: pd.DataFrame) -> dict[str, object]:
    config: dict[str, object] = {}
    for column in frame.columns:
        label = RESEARCH_COMPACT_HEADER_LABELS.get(column, column)
        if column == "ETF代码 ETF Code":
            config[column] = st.column_config.TextColumn(label, width=92)
        elif column == "ETF名称 ETF Name":
            config[column] = st.column_config.TextColumn(label, width=160)
        elif column == "指数代码 Index Code":
            config[column] = st.column_config.TextColumn(label, width=92)
        elif column == "指数名称 Index Name":
            config[column] = st.column_config.TextColumn(label, width=150)
        elif column in {"大趋势 Large Trend", "中趋势 Medium Trend", "小趋势 Small Trend"}:
            config[column] = st.column_config.TextColumn(label, width=132)
        elif column == "可开仓 Eligible":
            config[column] = st.column_config.TextColumn(label, width=118)
        elif column in RESEARCH_PERCENT_LABELS:
            config[column] = st.column_config.NumberColumn(label, format="%.1f%%", width=112)
        elif column in RESEARCH_COUNT_LABELS:
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


def _render_research_table(frame: pd.DataFrame, *, height: int | None = None) -> None:
    st.dataframe(
        frame,
        width="stretch",
        height=height or "auto",
        hide_index=True,
        column_config=_research_column_config(frame),
        row_height=34,
    )


def _research_bar_chart(
    frame: pd.DataFrame,
    index_column: str,
    value_column: str,
    *,
    title: str,
    color: str,
    height_per_row: int = 34,
) -> alt.Chart:
    if index_column not in frame.columns or value_column not in frame.columns:
        return alt.Chart(pd.DataFrame({"策略 Strategy": [], "数值 Value": []})).mark_bar()

    data = frame[[index_column, value_column]].dropna().copy()
    if index_column in {"candidate_name", "base_candidate"}:
        data[index_column] = data[index_column].map(_candidate_display_name)
    data = data.rename(columns={index_column: "策略 Strategy", value_column: "数值 Value"})
    if value_column in RESEARCH_PERCENT_COLUMNS:
        data["数值 Value"] = data["数值 Value"] * 100
        value_format = ".1f"
        axis_title = f"{RESEARCH_COLUMN_LABELS.get(value_column, value_column)} (%)"
        tooltip_title = axis_title
    else:
        value_format = ".3f"
        axis_title = RESEARCH_COLUMN_LABELS.get(value_column, value_column)
        tooltip_title = axis_title

    data = data.sort_values("数值 Value", ascending=False)
    chart_height = max(180, min(360, len(data) * height_per_row))
    return (
        alt.Chart(data)
        .mark_bar(color=color, cornerRadiusEnd=3)
        .encode(
            x=alt.X("数值 Value:Q", title=axis_title, axis=alt.Axis(format=value_format)),
            y=alt.Y(
                "策略 Strategy:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelLimit=260),
            ),
            tooltip=[
                alt.Tooltip("策略 Strategy:N", title="策略 Strategy"),
                alt.Tooltip("数值 Value:Q", title=tooltip_title, format=value_format),
            ],
        )
        .properties(title=title, height=chart_height)
    )


def main() -> None:
    st.set_page_config(page_title="ETF 今日行动工作台", layout="wide")
    inject_global_styles()

    store = _store()
    parquet_store = _parquet()
    service = InitializationService(store=store, provider=None, parquet_store=parquet_store)
    page = render_primary_navigation()
    status = _platform_status(store, parquet_store)

    render_top_status_bar(summarize_platform_status(status))
    st.title(page.label)
    st.caption(page.caption)

    if page.slug == "decision":
        _tab_decision(store, parquet_store)
    elif page.slug == "market":
        _tab_market_watch(store, parquet_store)
    elif page.slug == "portfolio":
        _tab_portfolio(store, parquet_store)
    elif page.slug == "research":
        _tab_research(store, parquet_store)
    else:
        _tab_data_and_settings(store, parquet_store, service)


@st.cache_resource
def _store() -> SQLiteStore:
    store = SQLiteStore(DB_PATH)
    store.initialize_schema()
    return store


@st.cache_resource
def _parquet() -> ParquetStore:
    return ParquetStore(PARQUET_ROOT)


@st.cache_resource
def _research_job_manager() -> ResearchJobManager:
    return ResearchJobManager()


def _provider() -> AkShareProvider:
    return AkShareProvider()


def _platform_status(store: SQLiteStore, parquet_store: ParquetStore) -> dict[str, object]:
    master = store.list_etf_master()
    watchlist = store.list_watchlist()
    index_summary = _build_index_trend_summary(parquet_store)
    eligible_categories = _eligible_index_categories(index_summary)
    enabled_watchlist = _enabled_watchlist(watchlist)
    buyable_watchlist = (
        enabled_watchlist[enabled_watchlist["allow_buy"].astype(bool)]
        if not enabled_watchlist.empty and "allow_buy" in enabled_watchlist.columns
        else enabled_watchlist
    )
    missing_etf_history = _missing_watchlist_history(enabled_watchlist, parquet_store)
    index_history_count = _index_history_count(parquet_store)
    issues = _platform_issues(
        master=master,
        watchlist=watchlist,
        index_history_count=index_history_count,
        missing_etf_history=missing_etf_history,
    )
    return {
        "master": master,
        "watchlist": watchlist,
        "enabled_watchlist": enabled_watchlist,
        "buyable_watchlist": buyable_watchlist,
        "index_summary": index_summary,
        "eligible_categories": eligible_categories,
        "eligible_index_count": int(index_summary["allows_new_position"].sum())
        if "allows_new_position" in index_summary.columns
        else 0,
        "index_history_count": index_history_count,
        "missing_etf_history": missing_etf_history,
        "issues": issues,
    }


def _enabled_watchlist(watchlist: pd.DataFrame) -> pd.DataFrame:
    if watchlist.empty or "enabled" not in watchlist.columns:
        return watchlist
    return watchlist[watchlist["enabled"].astype(bool)]


def _index_history_count(parquet_store: ParquetStore) -> int:
    count = 0
    for definition in DEFAULT_INDEXES:
        if not parquet_store.read_index_prices(definition.index_code).empty:
            count += 1
    return count


def _missing_watchlist_history(watchlist: pd.DataFrame, parquet_store: ParquetStore) -> list[str]:
    if watchlist.empty or "etf_code" not in watchlist.columns:
        return []
    missing: list[str] = []
    for code in watchlist["etf_code"].astype(str).map(_format_etf_code).drop_duplicates():
        if parquet_store.read_prices(code).empty:
            missing.append(code)
    return missing


def _platform_issues(
    *,
    master: pd.DataFrame,
    watchlist: pd.DataFrame,
    index_history_count: int,
    missing_etf_history: list[str],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if master.empty:
        issues.append(
            {
                "title": "初始化 ETF 主列表",
                "detail": "数据维护 -> 数据中心 -> 主列表，先拉取全量 A 股 ETF 列表。",
            }
        )
    if index_history_count == 0:
        issues.append(
            {
                "title": "补齐指数历史",
                "detail": "数据维护顶部或数据中心 -> 指数历史，执行一键初始化/补齐全部指数。",
            }
        )
    if watchlist.empty:
        issues.append(
            {
                "title": "建立每日计算池",
                "detail": "ETF池 -> 搜索并加入常看的 ETF，然后今日行动才会生成建议。",
            }
        )
    if missing_etf_history:
        preview = "、".join(missing_etf_history[:5])
        suffix = " 等" if len(missing_etf_history) > 5 else ""
        issues.append(
            {
                "title": "补齐 ETF 历史行情",
                "detail": f"{preview}{suffix} 缺少本地行情；到数据维护 -> ETF历史补齐。",
            }
        )
    return issues


def _render_status_cards(status: dict[str, object]) -> None:
    cols = st.columns(4)
    cols[0].metric("可参与指数", f"{int(status['eligible_index_count'])}")
    cols[1].metric("可参与分类", f"{len(status['eligible_categories'])}")
    cols[2].metric("计算池 ETF", f"{len(status['enabled_watchlist'])}")
    cols[3].metric("数据缺口", f"{len(status['issues'])}")


def _render_next_steps(status: dict[str, object]) -> None:
    issues = status["issues"]
    if not issues:
        st.success("数据和计算池已就绪，可以直接查看今日建议。")
        return

    st.warning("当前还有准备项未完成，建议按下面顺序处理：")
    for index, issue in enumerate(issues, start=1):
        st.markdown(f"{index}. **{issue['title']}**：{issue['detail']}")


def _watchlist_status_frame(watchlist: pd.DataFrame, parquet_store: ParquetStore) -> pd.DataFrame:
    if watchlist.empty:
        return watchlist
    display = watchlist.copy()
    if "etf_code" in display.columns:
        display["etf_code"] = display["etf_code"].astype(str).map(_format_etf_code)
        display["历史行情"] = display["etf_code"].map(
            lambda code: "缺失" if parquet_store.read_prices(code).empty else "已就绪"
        )
    for column in ["enabled", "allow_buy"]:
        if column in display.columns:
            display[column] = display[column].map(lambda value: "是" if bool(value) else "否")
    return display


def _tab_decision(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("今日行动")
    st.caption("先看市场是否允许参与，再看计算池和今日建议；需要补数据时直接给下一步。")

    status = _platform_status(store, parquet_store)
    index_summary = status["index_summary"]
    eligible_categories = status["eligible_categories"]
    watchlist = status["watchlist"]

    _render_status_cards(status)
    if eligible_categories:
        st.info("当前指数趋势允许参与的分类：" + "、".join(eligible_categories))
    else:
        st.warning("当前没有指数分类满足新开仓条件，今日行动应偏防守。")
    _render_next_steps(status)

    view = st.radio(
        "今日视图",
        ["行动摘要", "每日建议", "计算池明细"],
        horizontal=True,
        key="daily_action_view",
    )
    if view == "行动摘要":
        top_indexes = (
            index_summary[index_summary["allows_new_position"].fillna(False).astype(bool)]
            .head(8)
            if not index_summary.empty and "allows_new_position" in index_summary.columns
            else pd.DataFrame()
        )
        if top_indexes.empty:
            st.info("暂无可开仓指数。可到“数据维护”补齐指数历史，或等待趋势条件改善。")
        else:
            st.markdown("### 当前通过趋势过滤的指数")
            _render_research_table(_index_trend_display_frame(top_indexes), height=260)
        st.markdown("### 今日建议")
        report = _build_daily_advice_report(store, parquet_store)
        if report is None:
            st.info("每日计算池为空。请先到“ETF池”加入 ETF。")
        else:
            st.markdown(report)
        with st.expander("查看原始计算池", expanded=False):
            if watchlist.empty:
                st.info("每日计算池为空。")
            else:
                st.dataframe(_watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=320)
    elif view == "每日建议":
        report = _build_daily_advice_report(store, parquet_store)
        if report is None:
            st.info("每日计算池为空。请先到“ETF池”加入 ETF。")
        else:
            st.markdown(report)
    else:
        if watchlist.empty:
            st.info("每日计算池为空。请先到“ETF池”加入 ETF。")
        else:
            st.dataframe(_watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=420)


def _tab_market_watch(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("市场地图")
    st.caption("先看指数过滤和趋势结构，再下钻到 ETF 行情。")
    index_summary = _build_index_trend_summary(parquet_store)
    view = st.radio("地图视图", ["指数买卖参考", "ETF行情", "指数K线"], horizontal=True, key="market_map_view")
    if view == "指数买卖参考":
        _render_index_filter_explorer(index_summary, parquet_store)
    elif view == "ETF行情":
        _tab_chart(store, parquet_store)
    else:
        _tab_index_watch(parquet_store)


def _tab_portfolio(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("ETF池")
    st.caption("找 ETF、加入每日计算池，并检查买入许可和历史行情状态。")
    _render_etf_search_and_add(store)

    st.markdown("### 每日计算池")
    watchlist = store.list_watchlist()
    if watchlist.empty:
        st.info("每日计算池为空。请先在上方搜索 ETF 并保存。")
    else:
        st.dataframe(_watchlist_status_frame(watchlist, parquet_store), width="stretch", hide_index=True, height=420)


def _tab_data_and_settings(store: SQLiteStore, parquet_store: ParquetStore, service: InitializationService) -> None:
    st.subheader("数据维护")
    st.caption("低频维护入口：先看数据健康，再初始化数据、补齐指数历史、查看任务日志。")
    status = _platform_status(store, parquet_store)
    _render_data_health(status)

    quick_cols = st.columns([1, 2])
    if quick_cols[0].button("一键补齐全部指数", type="primary", width="stretch", key="data_quick_sync_indexes"):
        provider = _provider()
        sync_service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
        with st.spinner("正在检查并补齐全部指数历史..."):
            summary = sync_service.ensure_all_index_history(date.today())
        level, message = _index_sync_status_message(summary)
        st.session_state["latest_index_sync_message"] = {"level": level, "message": message}
        st.session_state["latest_index_sync_summary"] = summary
    quick_cols[1].caption("指数历史是今日行动和研究过滤的前置数据；补齐后回到“今日行动”查看可参与范围。")
    _render_latest_index_sync_result()

    view = st.radio("管理视图", ["数据中心", "日志与设置"], horizontal=True, key="data_settings_view")
    if view == "数据中心":
        _tab_data_center(store, parquet_store)
    else:
        _tab_settings(store, service)


def _render_data_health(status: dict[str, object]) -> None:
    master = status["master"]
    watchlist = status["watchlist"]
    missing_etf_history = status["missing_etf_history"]
    cols = st.columns(4)
    cols[0].metric("ETF 主列表", "已初始化" if not master.empty else "缺失")
    cols[1].metric("指数历史", f"{int(status['index_history_count'])}/{len(DEFAULT_INDEXES)}")
    cols[2].metric("每日计算池", f"{len(watchlist)}")
    cols[3].metric("缺历史 ETF", f"{len(missing_etf_history)}")
    _render_next_steps(status)


def _render_etf_search_and_add(store: SQLiteStore) -> None:
    master = store.list_etf_master()
    if master.empty:
        st.info("尚未初始化 ETF 主列表。请到“数据维护”执行轻量初始化。")
        return

    col1, col2, col3 = st.columns([2, 1, 1])
    query = col1.text_input("搜索代码或名称", key="portfolio_query")
    category = col2.selectbox("分类", ["全部"] + CATEGORIES, key="portfolio_category")
    only_hk = col3.checkbox("只看港股跨境 ETF", key="portfolio_only_hk")

    view = master.copy()
    if query:
        view = view[view["etf_code"].astype(str).str.contains(query) | view["name"].fillna("").str.contains(query)]
    if category != "全部":
        view = view[view["category"] == category]
    if only_hk:
        view = view[view["category"].map(is_hk_cross_market)]

    table_cols = ["etf_code", "name", "exchange", "category", "amount", "latest_price", "is_active"]
    search_col, add_col = st.columns([1.7, 1])
    with search_col:
        st.markdown("### 搜索结果")
        st.dataframe(view[table_cols], width="stretch", hide_index=True, height=420)

    with add_col:
        st.markdown("### 加入每日计算池")
        selected = st.selectbox("ETF", view["etf_code"].tolist() if not view.empty else [], key="portfolio_add_etf")
        if selected:
            row = master[master["etf_code"] == selected].iloc[0]
            st.caption(f"{row['name']} ｜ {row['exchange']} ｜ {row['category']}")
            selected_category = st.selectbox(
                "分类修正",
                CATEGORIES,
                index=CATEGORIES.index(row["category"]) if row["category"] in CATEGORIES else 0,
                key="portfolio_add_category",
            )
            control_cols = st.columns(2)
            allow_buy = control_cols[0].checkbox("允许买入", value=True, key="portfolio_allow_buy")
            enabled = control_cols[1].checkbox("纳入每日计算", value=True, key="portfolio_enabled")
            if st.button("保存到每日计算池", key="portfolio_save_watchlist"):
                store.set_watchlist(selected, enabled=enabled, allow_buy=allow_buy, category=selected_category)
                st.success(f"{selected} 已保存")
        else:
            st.info("当前筛选条件下没有 ETF。")


def _build_daily_advice_report(store: SQLiteStore, parquet_store: ParquetStore) -> str | None:
    watchlist = store.list_watchlist()
    if watchlist.empty:
        return None

    strategy = TrendStrategy()
    signals: list[StrategySignal] = []
    for row in watchlist.itertuples(index=False):
        if not row.enabled:
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


def _tab_universe(store: SQLiteStore) -> None:
    st.subheader("ETF 池")
    master = store.list_etf_master()
    if master.empty:
        st.info("尚未初始化 ETF 主列表。请到“数据中心”执行轻量初始化。")
        return

    col1, col2, col3 = st.columns([2, 1, 1])
    query = col1.text_input("搜索代码或名称")
    category = col2.selectbox("分类", ["全部"] + CATEGORIES)
    only_hk = col3.checkbox("只看港股跨境 ETF")

    view = master.copy()
    if query:
        view = view[view["etf_code"].astype(str).str.contains(query) | view["name"].fillna("").str.contains(query)]
    if category != "全部":
        view = view[view["category"] == category]
    if only_hk:
        view = view[view["category"].map(is_hk_cross_market)]

    st.dataframe(view[["etf_code", "name", "exchange", "category", "amount", "latest_price", "is_active"]], width="stretch", hide_index=True)

    st.markdown("### 加入每日计算池")
    selected = st.selectbox("ETF", view["etf_code"].tolist() if not view.empty else [])
    if selected:
        row = master[master["etf_code"] == selected].iloc[0]
        selected_category = st.selectbox("分类修正", CATEGORIES, index=CATEGORIES.index(row["category"]) if row["category"] in CATEGORIES else 0)
        allow_buy = st.checkbox("允许买入", value=True)
        enabled = st.checkbox("纳入每日计算", value=True)
        if st.button("保存到每日计算池"):
            store.set_watchlist(selected, enabled=enabled, allow_buy=allow_buy, category=selected_category)
            st.success(f"{selected} 已保存")

    st.markdown("### 当前每日计算池")
    st.dataframe(store.list_watchlist(), width="stretch", hide_index=True)


def _tab_chart(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("行情 K 线")
    etf_code = _select_etf(store, "chart_etf")
    if not etf_code:
        return
    prices = parquet_store.read_prices(etf_code)
    if prices.empty:
        st.warning("本地尚无该 ETF 历史行情，请先到“数据中心”初始化历史。")
        return
    prices = add_technical_features(prices)
    recent = _chart_range_controls(prices, "chart_tab", default_label="近2年")
    master = store.list_etf_master()
    meta = master[master["etf_code"] == etf_code]
    if not meta.empty:
        row = meta.iloc[0]
        tags = [f"分类：{row['category']}", f"交易所：{row['exchange']}"]
        if is_hk_cross_market(row["category"]):
            tags.extend(["底层市场：港股", "跨境类型：A股上市人民币交易", "风险：关注折溢价和底层市场休市"])
        st.info(" ｜ ".join(tags))

    chart_type, price_scale_mode, ma_columns = _chart_display_controls("chart_tab")
    payload = build_lightweight_chart_payload(recent, chart_type=chart_type, price_scale_mode=price_scale_mode, ma_columns=ma_columns)
    if renderLightweightCharts is None:
        st.json(payload)
    else:
        renderLightweightCharts(payload, key=f"chart-{etf_code}")


def _tab_index_watch(parquet_store: ParquetStore) -> None:
    st.subheader("指数观察")
    st.caption("指数用于判断底层市场趋势；ETF 是后续交易载体。这里不输出具体买卖建议。")
    selected = st.selectbox("选择指数", index_options(), key="index_watch")
    index_code = selected.split()[0]
    definition = get_index_definition(index_code)
    st.info(f"指数：{definition.name} ｜ 市场：{definition.market} ｜ 分类：{definition.category}")

    prices = parquet_store.read_index_prices(index_code)
    if prices.empty:
        st.warning("本地尚无该指数历史数据。请在“数据中心”拉取指数历史。")
        return

    featured = add_technical_features(prices.rename(columns={"index_code": "etf_code"}))
    recent = _chart_range_controls(featured, "index_watch", default_label="近2年")
    chart_type, price_scale_mode, ma_columns = _chart_display_controls("index_watch")
    payload = build_lightweight_chart_payload(recent, chart_type=chart_type, price_scale_mode=price_scale_mode, ma_columns=ma_columns)
    if renderLightweightCharts is None:
        st.json(payload)
    else:
        renderLightweightCharts(payload, key=f"index-chart-{index_code}")

    last = featured.iloc[-1]
    cols = st.columns(5)
    cols[0].metric("最新收盘", f"{last['close']:.2f}")
    cols[1].metric("MA51", _fmt_optional(last.get("ma51")))
    cols[2].metric("MA120", _fmt_optional(last.get("ma120")))
    cols[3].metric("MA250", _fmt_optional(last.get("ma250")))
    cols[4].metric("MA850", _fmt_optional(last.get("ma850")))


def _tab_advice(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("每日建议")
    watchlist = store.list_watchlist()
    if watchlist.empty:
        st.info("每日计算池为空。请先在“ETF 池”中勾选 ETF。")
        return
    strategy = TrendStrategy()
    signals: list[StrategySignal] = []
    for row in watchlist.itertuples(index=False):
        if not row.enabled:
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

    report = DailyAdviceReport().render(pd.Timestamp.today(), "震荡", signals)
    st.markdown(report)


def _tab_backtest(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("回测")
    etf_code = _select_etf(store, "backtest_etf")
    if not etf_code:
        return
    prices = parquet_store.read_prices(etf_code)
    if prices.empty:
        st.warning("本地尚无该 ETF 历史行情，请先初始化。")
        return
    featured = add_technical_features(prices)
    category = _category_for(store, etf_code)
    target_weight = st.slider("测试目标仓位", 0.01, 0.15, 0.06, 0.01)
    start = pd.Timestamp(featured["trade_date"].min())
    first_signal_date = st.date_input("首个买入信号日期", value=start.date())
    if st.button("运行单 ETF 回测"):
        signal = StrategySignal(
            etf_code=etf_code,
            trade_date=pd.Timestamp(first_signal_date),
            action="BUY",
            target_weight=target_weight,
            reason="手动回测信号",
            trigger_rules=["manual_backtest"],
        )
        result = BacktestEngine().run_single_etf(etf_code, featured, [signal], category=category)
        st.metric("总收益", f"{result.metrics.get('total_return', 0) * 100:.2f}%")
        st.metric("最大回撤", f"{result.metrics.get('max_drawdown', 0) * 100:.2f}%")
        st.metric("港股跨境暴露", f"{result.metrics.get('max_hk_cross_market_exposure', 0) * 100:.2f}%")
        recent = _chart_range_controls(featured, "backtest_chart", default_label="近2年")
        recent_start = pd.Timestamp(recent["trade_date"].min()).normalize()
        recent_end = pd.Timestamp(recent["trade_date"].max()).normalize()
        recent_trades = [
            trade
            for trade in result.trades
            if recent_start <= pd.Timestamp(trade.trade_date).normalize() <= recent_end
        ]
        chart_type, price_scale_mode, ma_columns = _chart_display_controls(
            "backtest_chart",
            default_chart_label="收盘折线 Close Line",
            default_ma_labels=["MA51"],
        )
        payload = build_lightweight_chart_payload(
            recent,
            trades=recent_trades,
            chart_type=chart_type,
            price_scale_mode=price_scale_mode,
            ma_columns=ma_columns,
        )
        if renderLightweightCharts is None:
            st.json(payload)
        else:
            renderLightweightCharts(payload, key=f"backtest-trade-chart-{etf_code}")
        st.line_chart(result.nav.set_index("trade_date")["nav"])
        trades_display = _research_trade_display_frame(result.trades)
        st.dataframe(trades_display, width="stretch", hide_index=True)


def _tab_research(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("研究复盘")
    st.caption("读取已有研究结果，复盘策略表现；需要重新计算时再展开运行研究。")
    _inject_research_styles()
    job_manager = _research_job_manager()
    output_dir = RESEARCH_REPORT_DIR
    master = store.list_etf_master()
    index_summary = _build_index_trend_summary(parquet_store)
    eligible_categories = _eligible_index_categories(index_summary)
    eligible_codes = _filter_etf_codes_by_categories(master, eligible_categories)
    min_rows = 252
    limit = 120
    use_index_filter = True

    index_cols = st.columns(4)
    eligible_index_count = int(index_summary["allows_new_position"].sum()) if "allows_new_position" in index_summary.columns else 0
    index_cols[0].metric("可开仓指数 Eligible Indexes", f"{eligible_index_count}")
    index_cols[1].metric("趋势分类 Categories", f"{len(eligible_categories)}")
    index_cols[2].metric("筛后ETF Filtered ETFs", f"{len(eligible_codes)}")
    index_cols[3].metric("全市场ETF All ETFs", f"{len(master)}")
    if use_index_filter:
        if eligible_categories:
            st.info("当前进入回测的指数分类：" + "、".join(eligible_categories))
        else:
            st.warning("当前没有指数分类满足新开仓条件；按两阶段规则，此时不应强行扩大ETF候选池。")

    research_view = st.radio(
        "复盘视图",
        ["研究总览", "指数过滤", "策略对比", "ETF复盘", "手动回测", "明细表"],
        horizontal=True,
        key="research_view",
    )

    if research_view == "指数过滤":
        _render_index_filter_explorer(index_summary, parquet_store)
        return
    if research_view == "手动回测":
        _tab_backtest(store, parquet_store)
        return

    _render_research_job_status(job_manager)

    with st.expander("运行研究", expanded=False):
        st.caption("重新运行会在后台执行；停止不会覆盖旧结果。建议先同步指数数据，再运行趋势研究。")
        col1, col2, col3 = st.columns([1, 1, 2])
        min_rows = int(col1.number_input("最少历史交易日", min_value=60, max_value=2000, value=252, step=20))
        limit_value = int(col2.number_input("样本上限", min_value=0, max_value=2000, value=120, step=10))
        limit = None if limit_value == 0 else limit_value
        use_index_filter = col3.checkbox("先按ETF指数趋势筛选范围", value=True)

        sync_cols = st.columns([1, 1, 2])
        sync_disabled = job_manager.is_running()
        if sync_cols[0].button("同步指数数据", width="stretch", type="primary", disabled=sync_disabled):
            with st.spinner("正在同步指数历史到今天..."):
                try:
                    provider = _provider()
                    service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
                    sync_summary = service.ensure_all_index_history(date.today())
                except Exception as exc:  # noqa: BLE001 - UI should preserve provider failure text
                    st.session_state["latest_index_sync_message"] = {
                        "level": "error",
                        "message": f"指数同步失败：{exc}",
                    }
                    st.session_state.pop("latest_index_sync_summary", None)
                else:
                    level, message = _index_sync_status_message(sync_summary)
                    st.session_state["latest_index_sync_message"] = {"level": level, "message": message}
                    st.session_state["latest_index_sync_summary"] = sync_summary
        sync_cols[1].button(
            "同步 ETF 数据",
            width="stretch",
            disabled=True,
            help="ETF 数据同步将作为独立任务接入，默认按当前指数过滤后的 ETF 范围执行。",
        )
        sync_cols[2].caption("ETF 历史同步仍是独立任务；当前先保留入口提示。")
        _render_latest_index_sync_result()

        confirm_nonce = int(st.session_state.setdefault("research_run_confirm_nonce", 0))
        confirm_run = st.checkbox("确认运行本次趋势研究", value=False, key=f"confirm_research_run_{confirm_nonce}")
        if st.button("开始运行趋势研究", width="stretch", disabled=job_manager.is_running() or not confirm_run):
            research_codes = eligible_codes if use_index_filter else None
            if use_index_filter and not research_codes:
                st.error("指数趋势过滤后没有可回测ETF，本次不运行策略回测。")
                return
            candidates = load_research_candidates(RESEARCH_CONFIG)
            categories = _category_map(store)
            scope_text = "指数趋势过滤后" if use_index_filter else "全市场模式"
            started = job_manager.start(
                parquet_root=PARQUET_ROOT,
                candidates=candidates,
                categories=categories,
                min_rows=min_rows,
                limit=limit,
                etf_codes=research_codes,
                output_dir=output_dir,
                index_summary=index_summary,
                scope_text=scope_text,
            )
            if started:
                st.success("趋势研究已在后台启动。运行中可以点击停止，不会覆盖旧结果，完成后刷新本页即可查看新结果。")
                st.session_state["research_run_confirm_nonce"] = confirm_nonce + 1
                st.rerun()
            else:
                st.warning("已有趋势研究正在运行。")

    results_path = output_dir / "research_results.csv"
    ranking_path = output_dir / "candidate_ranking.csv"
    if not results_path.exists() or not ranking_path.exists():
        st.info("暂无趋势研究结果。点击“运行趋势研究”生成本地结果。")
        return

    results = pd.read_csv(results_path)
    ranking = pd.read_csv(ranking_path)
    if results.empty or ranking.empty:
        st.warning("趋势研究结果为空。")
        return

    if research_view == "研究总览":
        _render_research_overview(results, ranking)
    elif research_view == "策略对比":
        _render_research_comparison_and_category(results)
    elif research_view == "ETF复盘":
        _render_research_replay(results, store, parquet_store, min_rows)
    else:
        _render_research_detail_table(results, store)


def _render_research_job_status(job_manager: ResearchJobManager) -> None:
    status = job_manager.status()
    state = str(status.get("state", "idle"))
    message = str(status.get("message", ""))
    done = int(status.get("done", 0) or 0)
    total = int(status.get("total", 0) or 0)

    if state == "running":
        st.warning(message or "趋势研究运行中。")
        if total > 0:
            st.progress(min(done / total, 1.0), text=f"{done}/{total}")
        else:
            st.progress(0, text="准备样本中")
        stop_cols = st.columns([1, 3])
        if stop_cols[0].button("停止当前趋势研究", type="primary", key="stop_research_run"):
            job_manager.request_stop()
            st.warning("已请求停止。停止会在当前 ETF 完成后生效；旧结果不会被覆盖。")
            st.rerun()
        stop_cols[1].caption("后台任务不会阻塞页面；你可以停留在本页查看状态，或稍后刷新。")
    elif state == "completed":
        st.success(message)
    elif state == "cancelled":
        st.info(message)
    elif state == "failed":
        st.error(message)


def _render_research_overview(results: pd.DataFrame, ranking: pd.DataFrame) -> None:
    summary_top = st.columns(2)
    summary_bottom = st.columns(2)
    summary_top[0].metric("ETF 样本 Samples", f"{results['etf_code'].nunique():.0f}")
    summary_top[1].metric("候选策略 Strategies", f"{results['candidate_name'].nunique():.0f}")
    summary_bottom[0].metric("最佳中位夏普 Best Median Sharpe", f"{ranking['median_sharpe'].max():.3f}")
    summary_bottom[1].metric("最差最大回撤 Worst Max Drawdown", f"{ranking['worst_max_drawdown'].min() * 100:.1f}%")

    st.markdown("### 候选策略排名")
    ranking_view = _research_select_columns(ranking, RANKING_COLUMNS)
    for column in ["median_annualized_return", "median_sharpe", "worst_max_drawdown", "score"]:
        if column in ranking_view.columns:
            ranking_view[column] = ranking_view[column].round(4)
    ranking_display = _research_display_frame(ranking_view)
    _render_research_table(ranking_display, height=250)
    ranking_chart_cols = st.columns(2)
    ranking_chart_cols[0].altair_chart(
        _research_bar_chart(
            ranking,
            "candidate_name",
            "median_sharpe",
            title="中位夏普 Median Sharpe",
            color="#2A7F62",
        ),
        width="stretch",
    )
    ranking_chart_cols[1].altair_chart(
        _research_bar_chart(
            ranking,
            "candidate_name",
            "worst_max_drawdown",
            title="最差最大回撤 Worst Max Drawdown",
            color="#B85C38",
        ),
        width="stretch",
    )


def _render_research_comparison_and_category(results: pd.DataFrame) -> None:
    comparison = compare_regime_pairs(results)
    st.markdown("### 趋势过滤前后对比")
    if comparison.empty:
        st.info("没有找到趋势过滤策略与原始策略的配对结果。")
    else:
        comparison_view = _research_select_columns(comparison, COMPARISON_COLUMNS)
        comparison_display = _research_display_frame(comparison_view)
        _render_research_table(comparison_display, height=160)
        comparison_chart_cols = st.columns(2)
        comparison_chart_cols[0].altair_chart(
            _research_bar_chart(
                comparison,
                "base_candidate",
                "delta_median_sharpe",
                title="夏普变化 Sharpe Change",
                color="#4C6FAD",
                height_per_row=42,
            ),
            width="stretch",
        )
        comparison_chart_cols[1].altair_chart(
            _research_bar_chart(
                comparison,
                "base_candidate",
                "delta_median_max_drawdown",
                title="回撤变化 Drawdown Change",
                color="#8B6F47",
                height_per_row=42,
            ),
            width="stretch",
        )

    st.markdown("### 分类表现")
    category_view = (
        results.groupby(["candidate_name", "category"], as_index=False)
        .agg(
            sample_count=("etf_code", "nunique"),
            mean_total_return=("total_return", "mean"),
            median_annualized_return=("annualized_return", "median"),
            median_sharpe=("sharpe", "median"),
            worst_max_drawdown=("max_drawdown", "min"),
            mean_trade_count=("trade_count", "mean"),
        )
        .sort_values(["candidate_name", "sample_count"], ascending=[True, False])
    )
    category_view = _research_select_columns(category_view, CATEGORY_COLUMNS)
    category_display = _research_display_frame(category_view.round(4))
    _render_research_table(category_display, height=340)


def _research_detail_selection(
    results: pd.DataFrame,
    store: SQLiteStore,
    *,
    candidate_key: str,
    category_key: str,
) -> tuple[str, pd.DataFrame]:
    st.markdown("### 单 ETF 明细")
    candidate = st.selectbox(
        "候选策略 Strategy",
        sorted(results["candidate_name"].unique()),
        format_func=_candidate_display_name,
        key=candidate_key,
    )
    category_options = ["全部"] + sorted(results["category"].dropna().unique())
    category = st.selectbox("分类 Category", category_options, key=category_key)
    detail = results[results["candidate_name"] == candidate].copy()
    if category != "全部":
        detail = detail[detail["category"] == category]
    detail = detail.sort_values("sharpe", ascending=False)
    detail = _research_attach_etf_names(detail, store.list_etf_master())
    return candidate, detail


def _render_research_detail_table(results: pd.DataFrame, store: SQLiteStore) -> None:
    _, detail = _research_detail_selection(
        results,
        store,
        candidate_key="research_detail_candidate",
        category_key="research_detail_category",
    )
    detail_view = _research_select_columns(detail, DETAIL_COLUMNS)
    detail_display = _research_display_frame(detail_view.round(4))
    _render_research_table(detail_display, height=390)


def _render_research_replay(
    results: pd.DataFrame,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    min_rows: int,
) -> None:
    candidate, detail = _research_detail_selection(
        results,
        store,
        candidate_key="research_replay_candidate",
        category_key="research_replay_category",
    )
    if detail.empty:
        return

    st.markdown("#### 策略K线复盘")
    option_rows = detail[["etf_code", "etf_name", "category"]].drop_duplicates().copy()
    option_rows["etf_code"] = option_rows["etf_code"].map(_format_etf_code)
    option_rows = option_rows.sort_values("etf_code")
    option_labels = [f"{row.etf_code} {row.etf_name}" for row in option_rows.itertuples(index=False)]
    label_to_code = dict(zip(option_labels, option_rows["etf_code"], strict=False))
    selected_label = st.selectbox("选择复盘ETF", option_labels, key="research_trade_chart_etf")
    replay_code = label_to_code[selected_label]
    replay_category = str(option_rows[option_rows["etf_code"] == replay_code].iloc[0]["category"])
    universe_codes = sorted(results["etf_code"].astype(str).map(_format_etf_code).unique())
    candidates_by_name = {item.name: item for item in load_research_candidates(RESEARCH_CONFIG)}
    candidate_model = candidates_by_name.get(candidate)
    if candidate_model is None:
        st.warning("没有找到该候选策略配置，无法生成复盘信号。")
        return

    try:
        featured = _research_chart_featured_prices(parquet_store, replay_code, candidate, universe_codes, min_rows)
    except Exception as exc:  # noqa: BLE001 - keep UI failure visible
        st.error(f"复盘行情准备失败：{exc}")
        return
    if featured.empty:
        st.warning("本地尚无该ETF历史行情，无法绘制策略K线。")
        return

    signals = generate_candidate_signals(replay_code, featured, candidate_model, category=replay_category)
    result = BacktestEngine().run_single_etf(replay_code, featured, signals, category=replay_category)
    replay_metrics = st.columns(3)
    replay_metrics[0].metric("策略交易 Signals", f"{len(result.trades)}")
    replay_metrics[1].metric("总收益 Total Return", f"{result.metrics.get('total_return', 0) * 100:.1f}%")
    replay_metrics[2].metric("最大回撤 Max Drawdown", f"{result.metrics.get('max_drawdown', 0) * 100:.1f}%")
    st.caption(f"当前策略 Strategy：{_candidate_display_name(candidate)}")

    recent = _chart_range_controls(featured, "research_replay_chart", default_label="近2年")
    recent_start = pd.Timestamp(recent["trade_date"].min()).normalize()
    recent_end = pd.Timestamp(recent["trade_date"].max()).normalize()
    recent_trades = [
        trade
        for trade in result.trades
        if recent_start <= pd.Timestamp(trade.trade_date).normalize() <= recent_end
    ]
    chart_type, price_scale_mode, ma_columns = _chart_display_controls(
        "research_replay_chart",
        default_chart_label="收盘折线 Close Line",
        default_ma_labels=["MA51"],
    )
    payload = build_lightweight_chart_payload(
        recent,
        trades=recent_trades,
        chart_type=chart_type,
        price_scale_mode=price_scale_mode,
        ma_columns=ma_columns,
    )
    if renderLightweightCharts is None:
        st.json(payload)
    else:
        renderLightweightCharts(payload, key=f"research-trade-chart-{candidate}-{replay_code}")

    trades_display = _research_trade_display_frame(result.trades)
    if trades_display.empty:
        st.info("该策略在当前ETF历史区间内没有产生交易。")
    else:
        st.dataframe(
            trades_display,
            width="stretch",
            hide_index=True,
            column_config={
                "成交前仓位 Before": st.column_config.NumberColumn("成交前仓位 Before", format="%.1f%%", width=110),
                "成交后仓位 After": st.column_config.NumberColumn("成交后仓位 After", format="%.1f%%", width=110),
                "成交价 Price": st.column_config.NumberColumn("成交价 Price", format="%.3f", width=92),
            },
        )


def _tab_data_center(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    st.subheader("数据中心")
    st.caption("初始化采用“主列表 -> ETF 历史 -> 指数历史 -> 批量任务”的顺序。")
    data_view = st.radio("数据任务", ["主列表", "ETF历史", "指数历史", "批量任务"], horizontal=True, key="data_center_view")

    if data_view == "主列表":
        if st.button("轻量初始化：拉取全量 A 股 ETF 列表"):
            provider = _provider()
            service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
            with st.spinner("正在拉取 ETF 主列表..."):
                try:
                    master = service.initialize_master()
                except Exception as exc:  # noqa: BLE001 - UI should surface provider errors clearly
                    st.error(str(exc))
                else:
                    st.success(f"已写入 {len(master)} 只 ETF")

        if st.button("选择样本 ETF"):
            samples = InitializationService(store).select_sample_etfs(SAMPLE_CATEGORIES)
            st.dataframe(samples[["etf_code", "name", "category", "amount"]], width="stretch", hide_index=True)
    elif data_view == "ETF历史":
        etf_code = _select_etf(store, "init_etf")
        col1, col2 = st.columns(2)
        start = col1.date_input("开始日期", value=date.today() - timedelta(days=365 * 5))
        end = col2.date_input("结束日期", value=date.today())
        if etf_code and st.button("拉取并保存历史行情"):
            provider = _provider()
            service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
            with st.spinner(f"正在拉取 {etf_code} 历史行情..."):
                try:
                    frame = service.fetch_and_store_history(etf_code, start, end)
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
                else:
                    st.success(f"保存 {len(frame)} 行历史行情")
    elif data_view == "指数历史":
        selected_index = st.selectbox("指数", index_options(), key="init_index")
        index_code = selected_index.split()[0]
        st.caption(f"开始日期自动使用 {INDEX_HISTORY_AUTO_START.isoformat()} 请求，最终以数据源返回的最早交易日为准。")
        index_end = st.date_input("指数结束日期", value=date.today(), key="index_end")
        if st.button("拉取并保存指数历史"):
            provider = _provider()
            with st.spinner(f"正在拉取 {selected_index} 历史行情..."):
                try:
                    frame = provider.fetch_index_daily(index_code, INDEX_HISTORY_AUTO_START, index_end)
                    featured = add_technical_features(frame.rename(columns={"index_code": "etf_code"})).rename(columns={"etf_code": "index_code"})
                    parquet_store.write_index_prices(index_code, featured)
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
                else:
                    if featured.empty:
                        st.warning("数据源没有返回指数历史行情。")
                    else:
                        first_date = pd.Timestamp(featured["trade_date"].min()).date()
                        st.success(f"保存 {len(featured)} 行指数历史行情，起始交易日 {first_date}")

        st.markdown("### 一键初始化/补齐全部指数")
        st.caption("逐个检查本地指数数据：不存在则全量拉取，已存在则从最后交易日之后补到结束日期。单个指数失败不会中断其他指数。")
        if st.button("一键初始化/补齐全部指数"):
            provider = _provider()
            service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
            with st.spinner("正在检查并补齐全部指数历史..."):
                summary = service.ensure_all_index_history(index_end)
            st.dataframe(summary, width="stretch", hide_index=True)
            failed = summary[summary["status"] == "FAILED"] if not summary.empty else summary
            if failed is not None and not failed.empty:
                st.warning(f"{len(failed)} 个指数补齐失败，请查看表格中的 error_message。")
            else:
                st.success("全部指数检查完成。")
    else:
        if st.button("为每日计算池创建历史初始化任务"):
            count = InitializationService(store).create_history_jobs_for_watchlist()
            st.success(f"已创建 {count} 个历史任务")


def _tab_settings(store: SQLiteStore, service: InitializationService) -> None:
    st.subheader("日志与设置")
    st.write("港股跨境 ETF 关键词和仓位上限当前由配置文件控制：`configs/strategy.yaml`、`configs/risk.yaml`。")
    with store.connect() as conn:
        jobs = pd.read_sql_query("SELECT * FROM data_fetch_job ORDER BY job_id DESC LIMIT 100", conn)
        state = pd.read_sql_query("SELECT * FROM data_update_state ORDER BY updated_at DESC LIMIT 100", conn)
        quality = pd.read_sql_query("SELECT * FROM data_quality_log ORDER BY log_id DESC LIMIT 100", conn)
    log_view = st.radio("日志视图", ["更新状态", "任务日志", "数据质量日志"], horizontal=True, key="settings_log_view")
    if log_view == "更新状态":
        st.dataframe(state, width="stretch", hide_index=True, height=520)
    elif log_view == "任务日志":
        st.dataframe(jobs, width="stretch", hide_index=True, height=520)
    else:
        st.dataframe(quality, width="stretch", hide_index=True, height=520)


def _select_etf(store: SQLiteStore, key: str) -> str | None:
    master = store.list_etf_master()
    if master.empty:
        st.info("尚未初始化 ETF 主列表。")
        return None
    labels = [f"{r.etf_code} {r.name}" for r in master.itertuples(index=False)]
    selected = st.selectbox("选择 ETF", labels, key=key)
    return selected.split()[0] if selected else None


def _category_for(store: SQLiteStore, etf_code: str) -> str:
    master = store.list_etf_master()
    row = master[master["etf_code"] == etf_code]
    if row.empty:
        return "A股主题"
    return str(row.iloc[0]["category"])


def _category_map(store: SQLiteStore) -> dict[str, str]:
    master = store.list_etf_master()
    if master.empty or "etf_code" not in master.columns or "category" not in master.columns:
        return {}
    return dict(zip(master["etf_code"].astype(str), master["category"].fillna("A股行业").astype(str), strict=False))


def _fmt_optional(value: object) -> str:
    if pd.isna(value):
        return "不足"
    return f"{float(value):.2f}"


if __name__ == "__main__":
    main()
