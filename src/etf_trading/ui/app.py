"""Streamlit multi-tab ETF workbench."""

from __future__ import annotations

import json
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
from etf_trading.data.quality import (
    HistoryReadiness,
    allows_new_index_position,
    assess_index_history_completeness,
    assess_price_history,
    expected_latest_trade_date,
)
from etf_trading.data.storage import ParquetStore, SQLiteStore
from etf_trading.report.daily_report import DailyAdviceReport
from etf_trading.research.comparison import compare_regime_pairs
from etf_trading.research.config import append_research_candidate, load_research_candidates
from etf_trading.research.experiment import ResearchRunCancelled
from etf_trading.research.index_etf_universe import (
    IndexEtfSampleConfig,
    build_index_etf_universe,
    selected_etf_codes,
)
from etf_trading.research.models import StrategyCandidate
from etf_trading.research.regime import TrendRegimeClassifier, add_trend_regime_features
from etf_trading.research.runner import attach_relative_strength_rank, load_price_frames, run_research
from etf_trading.research.signals import generate_candidate_signals
from etf_trading.strategy.features import add_technical_features
from etf_trading.strategy.models import StrategySignal
from etf_trading.strategy.trend import TrendStrategy
from etf_trading.ui.chart_renderer import build_lightweight_chart_payload
from etf_trading.ui.components.charts import chart_display_controls, chart_range_controls, filter_date_range_frame
from etf_trading.ui.components.research_tables import render_research_table, research_bar_chart, research_column_config
from etf_trading.ui.components.status import render_next_steps, render_status_cards, render_top_status_bar
from etf_trading.ui.data_coverage import build_data_coverage_summary, build_data_gap_detail, build_etf_data_overview
from etf_trading.ui.navigation import render_page_header, render_primary_navigation, render_secondary_navigation
from etf_trading.ui.pages import data_maintenance, decision, market, portfolio, research
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
UI_PREFERENCES_PATH = Path("data/ui_preferences.json")
SAMPLE_CATEGORIES = ["A股宽基", "A股行业", "港股宽基", "港股科技", "港股医药", "商品", "债券"]
WORKFLOW_TABS = ["今日行动", "市场地图", "ETF数据", "策略实验室", "数据维护"]
INDEX_WATCH_COMMON_CODES = ("000300", "000905", "000852", "932000", "000510", "000016", "399006", "000688")
INDEX_WATCH_COMMON_KEY = "common_index_codes"
INDEX_WATCH_QUICK_COLUMN_LIMIT = 8
INDEX_WATCH_RECENT_KEY = "recent_index_codes"
INDEX_WATCH_RECENT_LIMIT = 6
INDEX_WATCH_SELECTED_KEY = "index_watch_selected_code"
INDEX_WATCH_SELECTBOX_KEY = "index_watch_selectbox"
INDEX_WATCH_CATEGORY_KEY = "index_watch_category_filter"
INDEX_WATCH_SEARCH_KEY = "index_watch_search"
COMPACT_DATAFRAME_HEADER_HEIGHT = 42
COMPACT_DATAFRAME_ROW_HEIGHT = 36


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
    "index_name": "指数名称",
    "market": "市场 Market",
    "large_trend": "大趋势 Large Trend",
    "medium_trend": "中趋势 Medium Trend",
    "small_trend": "小趋势 Small Trend",
    "allows_new_position": "可开仓 Eligible",
    "latest_date": "最新日期 Latest Date",
    "history_rows": "历史长度 Rows",
    "etf_code": "ETF代码 ETF Code",
    "etf_name": "ETF名称",
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
    "指数名称": "指数名称",
    "市场 Market": "市场 Market",
    "大趋势 Large Trend": "大趋势 Large",
    "中趋势 Medium Trend": "中趋势 Medium",
    "小趋势 Small Trend": "小趋势 Small",
    "可开仓 Eligible": "可开仓 Eligible",
    "最新日期 Latest Date": "日期 Date",
    "历史长度 Rows": "长度 Rows",
    "ETF代码 ETF Code": "代码 Code",
    "ETF名称": "ETF名称",
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
INDEX_ETF_UNIVERSE_COLUMNS = [
    "index_code",
    "index_name",
    "etf_code",
    "etf_name",
    "mapping_source",
    "confidence",
    "amount",
    "history_rows",
    "sample_rank",
    "is_top_sample",
]
INDEX_ETF_UNIVERSE_COLUMN_LABELS = {
    "index_code": "指数代码",
    "index_name": "追踪指数",
    "etf_code": "ETF代码",
    "etf_name": "ETF名称",
    "mapping_source": "映射来源",
    "confidence": "置信度",
    "amount": "成交额",
    "history_rows": "历史长度",
    "sample_rank": "样本排名",
    "is_top_sample": "纳入默认样本",
}
MAPPING_SOURCE_DISPLAY_NAMES = {
    "official": "官方",
    "data_source": "数据源",
    "manual": "人工确认",
    "name_inferred": "名称推断",
}
MAPPING_CONFIDENCE_DISPLAY_NAMES = {
    "high": "高",
    "medium": "中",
    "low": "低",
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
    "价格走势 Price": "normal",
    "累计涨跌幅 Return %": "percent",
    "回撤风险 Drawdown %": "drawdown",
    "回到低点需跌幅 Down to Low %": "downside",
    "对数收益 Log Return %": "log_return",
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

        completeness = assess_index_history_completeness(
            prices,
            definition.index_base_date,
            baseline_source=definition.baseline_source,
            index_code=definition.index_code,
            source_kind=definition.source_kind,
            evidence_name=definition.baseline_evidence_name,
            evidence_kind=definition.baseline_evidence_kind,
        )
        readiness = assess_price_history(
            prices,
            expected_latest_trade_date(),
            min_history_rows=252,
        )
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
                "allows_new_position": allows_new_index_position(
                    regime.allows_new_position,
                    pool=definition.pool,
                    baseline_source=definition.baseline_source,
                    index_base_date=definition.index_base_date,
                    completeness_status=completeness.status,
                    data_is_ready=readiness.readiness == HistoryReadiness.READY,
                ),
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


def _index_etf_universe_display_frame(universe: pd.DataFrame) -> pd.DataFrame:
    display = _research_select_columns(universe, INDEX_ETF_UNIVERSE_COLUMNS)
    if display.empty:
        return pd.DataFrame(columns=list(INDEX_ETF_UNIVERSE_COLUMN_LABELS.values()))
    if "mapping_source" in display.columns:
        display["mapping_source"] = display["mapping_source"].map(
            lambda value: MAPPING_SOURCE_DISPLAY_NAMES.get(str(value), str(value))
        )
    if "confidence" in display.columns:
        display["confidence"] = display["confidence"].map(
            lambda value: MAPPING_CONFIDENCE_DISPLAY_NAMES.get(str(value), str(value))
        )
    if "is_top_sample" in display.columns:
        display["is_top_sample"] = display["is_top_sample"].map(lambda value: "是" if bool(value) else "否")
    return display.rename(columns=INDEX_ETF_UNIVERSE_COLUMN_LABELS)


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


def _index_definition_label(definition: IndexDefinition) -> str:
    return f"{definition.index_code} {definition.name}"


def _index_definition_for_code(index_code: str) -> IndexDefinition | None:
    try:
        return get_index_definition(str(index_code))
    except KeyError:
        return None


def _index_definitions_for_codes(index_codes: list[str] | tuple[str, ...]) -> list[IndexDefinition]:
    definitions: list[IndexDefinition] = []
    seen: set[str] = set()
    for index_code in index_codes:
        definition = _index_definition_for_code(index_code)
        if definition is None or definition.index_code in seen:
            continue
        definitions.append(definition)
        seen.add(definition.index_code)
    return definitions


def _load_ui_preferences(path: Path = UI_PREFERENCES_PATH) -> dict[str, object]:
    preferences_path = Path(path)
    if not preferences_path.exists():
        return {}
    try:
        data = json.loads(preferences_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_ui_preferences(preferences: dict[str, object], path: Path = UI_PREFERENCES_PATH) -> None:
    preferences_path = Path(path)
    preferences_path.parent.mkdir(parents=True, exist_ok=True)
    preferences_path.write_text(json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_common_index_codes(raw_codes: object) -> list[str]:
    configured_codes = raw_codes if isinstance(raw_codes, list) else []
    valid_codes: list[str] = []
    seen: set[str] = set()

    for raw_code in configured_codes:
        if not isinstance(raw_code, str) or raw_code in seen:
            continue
        definition = _index_definition_for_code(raw_code)
        if definition is None:
            continue
        valid_codes.append(definition.index_code)
        seen.add(definition.index_code)
        if len(valid_codes) >= INDEX_WATCH_QUICK_COLUMN_LIMIT:
            return valid_codes

    for default_code in INDEX_WATCH_COMMON_CODES:
        if default_code in seen:
            continue
        valid_codes.append(default_code)
        seen.add(default_code)
        if len(valid_codes) >= INDEX_WATCH_QUICK_COLUMN_LIMIT:
            break
    return valid_codes


def _load_common_index_codes(path: Path = UI_PREFERENCES_PATH) -> list[str]:
    return _normalize_common_index_codes(_load_ui_preferences(path).get(INDEX_WATCH_COMMON_KEY, []))


def _save_common_index_codes(index_codes: list[str], path: Path = UI_PREFERENCES_PATH) -> list[str]:
    common_codes = _normalize_common_index_codes(index_codes)
    preferences = _load_ui_preferences(path)
    preferences[INDEX_WATCH_COMMON_KEY] = common_codes
    _write_ui_preferences(preferences, path)
    return common_codes


def _replace_common_index_code(slot_index: int, replacement_code: str, path: Path = UI_PREFERENCES_PATH) -> list[str]:
    common_codes = _load_common_index_codes(path)
    definition = _index_definition_for_code(replacement_code)
    if definition is None or slot_index < 0 or slot_index >= len(common_codes):
        return common_codes
    if definition.index_code in common_codes and common_codes[slot_index] != definition.index_code:
        return common_codes

    common_codes[slot_index] = definition.index_code
    return _save_common_index_codes(common_codes, path)


def _reset_common_index_codes(path: Path = UI_PREFERENCES_PATH) -> list[str]:
    preferences = _load_ui_preferences(path)
    preferences.pop(INDEX_WATCH_COMMON_KEY, None)
    _write_ui_preferences(preferences, path)
    return list(INDEX_WATCH_COMMON_CODES)


def _load_recent_index_codes(path: Path = UI_PREFERENCES_PATH) -> list[str]:
    recent = _load_ui_preferences(path).get(INDEX_WATCH_RECENT_KEY, [])
    if not isinstance(recent, list):
        return []

    valid_codes: list[str] = []
    seen: set[str] = set()
    for raw_code in recent:
        if not isinstance(raw_code, str) or raw_code in seen:
            continue
        definition = _index_definition_for_code(raw_code)
        if definition is None:
            continue
        valid_codes.append(definition.index_code)
        seen.add(definition.index_code)
        if len(valid_codes) >= INDEX_WATCH_RECENT_LIMIT:
            break
    return valid_codes


def _remember_recent_index_code(index_code: str, path: Path = UI_PREFERENCES_PATH) -> list[str]:
    definition = _index_definition_for_code(index_code)
    if definition is None:
        return _load_recent_index_codes(path)

    recent = [definition.index_code]
    recent.extend(code for code in _load_recent_index_codes(path) if code != definition.index_code)
    recent = recent[:INDEX_WATCH_RECENT_LIMIT]

    preferences = _load_ui_preferences(path)
    preferences[INDEX_WATCH_RECENT_KEY] = recent
    _write_ui_preferences(preferences, path)
    return recent


def _filter_index_definitions(
    *,
    category_filter: str,
    query: str,
    definitions: tuple[IndexDefinition, ...] = DEFAULT_INDEXES,
) -> list[IndexDefinition]:
    normalized_query = query.strip().lower()
    filtered: list[IndexDefinition] = []
    for definition in definitions:
        if category_filter != "全部分类" and definition.category != category_filter:
            continue
        haystack = " ".join(
            [
                definition.index_code,
                definition.name,
                definition.market,
                definition.category,
            ]
        ).lower()
        if normalized_query and normalized_query not in haystack:
            continue
        filtered.append(definition)
    return filtered


def _render_index_quick_buttons(title: str, definitions: list[IndexDefinition], key_prefix: str) -> str | None:
    if not definitions:
        return None

    st.markdown(f"###### {title}")
    columns = st.columns(min(len(definitions), INDEX_WATCH_QUICK_COLUMN_LIMIT), gap="small")
    for idx, definition in enumerate(definitions):
        column = columns[idx % len(columns)]
        if column.button(definition.name, key=f"{key_prefix}_{definition.index_code}", use_container_width=True):
            return definition.index_code
    return None


def _render_common_index_customizer(common_index_codes: list[str]) -> None:
    common_definitions = _index_definitions_for_codes(common_index_codes)
    if not common_definitions:
        return

    with st.expander("调整常用指数", expanded=False):
        controls = st.columns([1.15, 2.35, 0.75, 0.95], gap="small")
        slot_labels = [
            f"{idx + 1}. {_index_definition_label(definition)}"
            for idx, definition in enumerate(common_definitions)
        ]
        slot_label = controls[0].selectbox("替换位置", slot_labels, key="index_watch_common_slot")
        slot_index = slot_labels.index(slot_label) if slot_label in slot_labels else 0
        current_code = common_definitions[slot_index].index_code
        active_codes = {definition.index_code for definition in common_definitions}
        replacement_definitions = [
            definition
            for definition in DEFAULT_INDEXES
            if definition.index_code == current_code or definition.index_code not in active_codes
        ]
        replacement_labels = [_index_definition_label(definition) for definition in replacement_definitions]
        replacement_index = next(
            (
                idx
                for idx, definition in enumerate(replacement_definitions)
                if definition.index_code == current_code
            ),
            0,
        )
        replacement_label = controls[1].selectbox(
            "换成",
            replacement_labels,
            index=replacement_index,
            key="index_watch_common_replacement",
        )
        replacement_code = replacement_label.split()[0]

        if controls[2].button("保存", key="index_watch_common_save", use_container_width=True):
            _replace_common_index_code(slot_index, replacement_code)
            st.success("已更新常用指数")
            st.rerun()
        if controls[3].button("恢复默认", key="index_watch_common_reset", use_container_width=True):
            _reset_common_index_codes()
            st.success("已恢复默认常用指数")
            st.rerun()


def _select_index_for_watch() -> str:
    default_code = DEFAULT_INDEXES[0].index_code
    current_code = default_code
    selectbox_label = st.session_state.get(INDEX_WATCH_SELECTBOX_KEY)
    stored_code = st.session_state.get(INDEX_WATCH_SELECTED_KEY)
    if isinstance(selectbox_label, str) and _index_definition_for_code(selectbox_label.split()[0]) is not None:
        current_code = selectbox_label.split()[0]
    elif isinstance(stored_code, str):
        current_code = stored_code
    if _index_definition_for_code(current_code) is None:
        current_code = default_code

    common_index_codes = _load_common_index_codes()
    clicked_code = _render_index_quick_buttons(
        "常用指数",
        _index_definitions_for_codes(common_index_codes),
        "index_watch_common",
    )
    _render_common_index_customizer(common_index_codes)
    recent_definitions = _index_definitions_for_codes(_load_recent_index_codes())
    recent_clicked_code = _render_index_quick_buttons("最近选择", recent_definitions, "index_watch_recent")
    if clicked_code or recent_clicked_code:
        current_code = clicked_code or recent_clicked_code or current_code
        st.session_state[INDEX_WATCH_SELECTED_KEY] = current_code
        st.session_state[INDEX_WATCH_CATEGORY_KEY] = "全部分类"
        st.session_state[INDEX_WATCH_SEARCH_KEY] = ""

    picker_cols = st.columns([1.1, 1.4, 2.4])
    category_options = ["全部分类"] + sorted({definition.category for definition in DEFAULT_INDEXES})
    category_filter = picker_cols[0].selectbox("分类", category_options, key=INDEX_WATCH_CATEGORY_KEY)
    query = picker_cols[1].text_input("搜索指数", key=INDEX_WATCH_SEARCH_KEY, placeholder="代码 / 名称 / 分类")
    picker_definitions = _filter_index_definitions(category_filter=category_filter, query=query)
    if not picker_definitions:
        st.warning("没有匹配的指数，已显示全部指数。")
        picker_definitions = list(DEFAULT_INDEXES)

    labels = [_index_definition_label(definition) for definition in picker_definitions]
    selected_index = next(
        (idx for idx, definition in enumerate(picker_definitions) if definition.index_code == current_code),
        0,
    )
    if (clicked_code or recent_clicked_code) and current_code in {definition.index_code for definition in picker_definitions}:
        st.session_state[INDEX_WATCH_SELECTBOX_KEY] = _index_definition_label(
            picker_definitions[selected_index]
        )

    selected_label = picker_cols[2].selectbox("指数", labels, index=selected_index, key=INDEX_WATCH_SELECTBOX_KEY)
    selected_code = selected_label.split()[0]
    st.session_state[INDEX_WATCH_SELECTED_KEY] = selected_code
    _remember_recent_index_code(selected_code)
    return selected_code


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


def _index_gate_markers(
    featured_prices: pd.DataFrame,
    definition: IndexDefinition,
    *,
    completeness_status: object,
    data_is_ready: bool,
) -> list[dict[str, object]]:
    states = _entry_states_from_regime_states(
        _index_regime_signal_states(
            featured_prices,
            definition,
            completeness_status=completeness_status,
            data_is_ready=data_is_ready,
        )
    )
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


def _index_allowed_states(
    featured_prices: pd.DataFrame,
    definition: IndexDefinition,
    *,
    completeness_status: object,
    data_is_ready: bool,
) -> list[dict[str, object]]:
    return _entry_states_from_regime_states(
        _index_regime_signal_states(
            featured_prices,
            definition,
            completeness_status=completeness_status,
            data_is_ready=data_is_ready,
        )
    )


def _entry_states_from_regime_states(states: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "trade_date": state["trade_date"],
            "allowed": bool(state.get("entry_allowed", False)),
            "price": float(state.get("price", 0.0)),
        }
        for state in states
    ]


def _index_regime_signal_states(
    featured_prices: pd.DataFrame,
    definition: IndexDefinition,
    *,
    completeness_status: object,
    data_is_ready: bool,
) -> list[dict[str, object]]:
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
                "entry_allowed": allows_new_index_position(
                    regime.allows_new_position,
                    pool=definition.pool,
                    baseline_source=definition.baseline_source,
                    index_base_date=definition.index_base_date,
                    completeness_status=completeness_status,
                    data_is_ready=data_is_ready,
                ),
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
    with st.expander("指数过滤规则", expanded=False):
        st.caption("三层趋势过滤 + 长期趋势退出。BUY/SELL 是指数过滤层参考，不是具体 ETF 下单。")

    available = index_summary.copy()
    if available.empty:
        st.info("暂无指数趋势数据。")
        return

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

    definition = get_index_definition(selected_code)
    completeness = assess_index_history_completeness(
        prices,
        definition.index_base_date,
        baseline_source=definition.baseline_source,
        index_code=definition.index_code,
        source_kind=definition.source_kind,
        evidence_name=definition.baseline_evidence_name,
        evidence_kind=definition.baseline_evidence_kind,
    )
    readiness = assess_price_history(
        prices,
        expected_latest_trade_date(),
        min_history_rows=252,
    )
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
        regime_states = _index_regime_signal_states(
            featured,
            definition,
            completeness_status=completeness.status,
            data_is_ready=readiness.readiness == HistoryReadiness.READY,
        )
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
    default_price_scale_label: str = "价格走势 Price",
) -> tuple[str, str, list[str]]:
    price_scale_help = {
        "价格走势 Price": "原始价格走势，适合观察K线、均线和买卖点。",
        "累计涨跌幅 Return %": "纵轴为相对当前图表区间起点的累计涨跌幅。",
        "回撤风险 Drawdown %": "纵轴为相对此前最高点的回撤，适合观察风险暴露和修复状态。",
        "回到低点需跌幅 Down to Low %": "纵轴为从当前价格回到图表区间最低点仍需下跌的比例。",
        "对数收益 Log Return %": "纵轴为对数收益，适合长周期、等比例比较。",
    }
    return chart_display_controls(
        key_prefix,
        chart_type_options=CHART_TYPE_OPTIONS,
        price_scale_options=PRICE_SCALE_OPTIONS,
        ma_display_options=MA_DISPLAY_OPTIONS,
        default_chart_label=default_chart_label,
        default_ma_labels=default_ma_labels or ["MA51", "MA120", "MA250", "MA850"],
        default_price_scale_label=default_price_scale_label,
        price_scale_help=price_scale_help,
    )


def _chart_range_controls(frame: pd.DataFrame, key_prefix: str, *, default_label: str = "近2年") -> pd.DataFrame:
    return chart_range_controls(frame, key_prefix, range_presets=CHART_RANGE_PRESETS, default_label=default_label)


def _filter_date_range_frame(frame: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    return filter_date_range_frame(frame, start_date, end_date)


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
    return research_column_config(
        frame,
        compact_header_labels=RESEARCH_COMPACT_HEADER_LABELS,
        percent_labels=RESEARCH_PERCENT_LABELS,
        count_labels=RESEARCH_COUNT_LABELS,
    )


def _render_research_table(frame: pd.DataFrame, *, height: int | None = None) -> None:
    render_research_table(frame, column_config=_research_column_config(frame), height=height)


def _research_bar_chart(
    frame: pd.DataFrame,
    index_column: str,
    value_column: str,
    *,
    title: str,
    color: str,
    height_per_row: int = 34,
) -> alt.Chart:
    return research_bar_chart(
        frame,
        index_column,
        value_column,
        title=title,
        color=color,
        percent_columns=RESEARCH_PERCENT_COLUMNS,
        column_labels=RESEARCH_COLUMN_LABELS,
        candidate_display_name=_candidate_display_name,
        height_per_row=height_per_row,
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
    render_page_header(page)
    section = render_secondary_navigation(page)

    if page.slug == "decision":
        decision.render(
            store=store,
            parquet_store=parquet_store,
            view=section,
            status=status,
            render_status_cards=render_status_cards,
            render_next_steps=render_next_steps,
            index_trend_display_frame=_index_trend_display_frame,
            render_research_table=_render_research_table,
            build_daily_advice_report=_build_daily_advice_report,
            watchlist_status_frame=_watchlist_status_frame,
        )
    elif page.slug == "market":
        market.render(
            store=store,
            parquet_store=parquet_store,
            view=section,
            index_summary=status["index_summary"],
            render_market_overview=_render_market_overview,
            render_index_filter_explorer=_render_index_filter_explorer,
            render_index_watch=_tab_index_watch,
        )
    elif page.slug == "portfolio":
        portfolio.render(
            store=store,
            parquet_store=parquet_store,
            view=section,
            render_data_overview=_render_etf_data_overview,
            render_etf_chart=_tab_chart,
            render_index_etf_pool=_render_portfolio_index_etf_pool,
            render_search_and_add=_render_etf_search_and_add,
            watchlist_status_frame=_watchlist_status_frame,
        )
    elif page.slug == "research":
        research.render(store=store, parquet_store=parquet_store, view=section, legacy_render=_tab_research)
    else:
        data_maintenance.render(
            store=store,
            parquet_store=parquet_store,
            service=service,
            view=section,
            status=status,
            render_data_overview=_render_data_coverage_overview,
            render_gap_detail=_render_data_gap_detail,
            render_repair_tasks=_render_data_repair_tasks,
            render_settings=_tab_settings,
        )


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
                "detail": "数据维护 -> 补齐任务 -> 主列表，先拉取全量 A 股 ETF 列表。",
            }
        )
    if index_history_count == 0:
        issues.append(
            {
                "title": "补齐指数历史",
                "detail": "数据维护 -> 补齐任务 -> 指数历史，执行一键初始化/补齐全部指数。",
            }
        )
    if watchlist.empty:
        issues.append(
            {
                "title": "建立每日计算池",
                "detail": "ETF数据 -> 搜索加入，保存常看的 ETF，然后今日行动才会生成建议。",
            }
        )
    if missing_etf_history:
        preview = "、".join(missing_etf_history[:5])
        suffix = " 等" if len(missing_etf_history) > 5 else ""
        issues.append(
            {
                "title": "补齐 ETF 历史行情",
                "detail": f"{preview}{suffix} 缺少本地行情；到数据维护 -> 补齐任务 -> ETF历史补齐。",
            }
        )
    return issues


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


def _render_index_quick_sync(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    quick_cols = st.columns([1, 2])
    if quick_cols[0].button("\u4e00\u952e\u8865\u9f50\u5168\u90e8\u6307\u6570", type="primary", width="stretch", key="data_quick_sync_indexes"):
        provider = _provider()
        sync_service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
        with st.spinner("\u6b63\u5728\u68c0\u67e5\u5e76\u8865\u9f50\u5168\u90e8\u6307\u6570\u5386\u53f2..."):
            summary = sync_service.ensure_all_index_history(date.today())
        level, message = _index_sync_status_message(summary)
        st.session_state["latest_index_sync_message"] = {"level": level, "message": message}
        st.session_state["latest_index_sync_summary"] = summary
    quick_cols[1].caption("\u6307\u6570\u5386\u53f2\u662f\u4eca\u65e5\u884c\u52a8\u548c\u7814\u7a76\u8fc7\u6ee4\u7684\u524d\u7f6e\u6570\u636e\uff1b\u8865\u9f50\u540e\u56de\u5230\u201c\u4eca\u65e5\u884c\u52a8\u201d\u67e5\u770b\u53ef\u53c2\u4e0e\u8303\u56f4\u3002")
    _render_latest_index_sync_result()


def _render_data_health(status: dict[str, object]) -> None:
    master = status["master"]
    watchlist = status["watchlist"]
    missing_etf_history = status["missing_etf_history"]
    cols = st.columns(4)
    cols[0].metric("ETF 主列表", "已初始化" if not master.empty else "缺失")
    cols[1].metric("指数历史", f"{int(status['index_history_count'])}/{len(DEFAULT_INDEXES)}")
    cols[2].metric("每日计算池", f"{len(watchlist)}")
    cols[3].metric("缺历史 ETF", f"{len(missing_etf_history)}")
    render_next_steps(status)


def _render_market_overview(index_summary: pd.DataFrame) -> None:
    if index_summary.empty:
        st.info("暂无指数趋势数据。请到“数据维护 -> 补齐任务”补齐指数历史。")
        return

    available = index_summary.copy()
    if "allows_new_position" not in available.columns:
        available["allows_new_position"] = False
    if "category" not in available.columns:
        available["category"] = ""

    allowed_mask = available["allows_new_position"].fillna(False).astype(bool)
    category_text = available["category"].fillna("").astype(str)
    category_count = int(category_text[category_text != ""].nunique())

    metric_cols = st.columns(4)
    metric_cols[0].metric("指数总数", f"{len(available)}")
    metric_cols[1].metric("可找买点", f"{int(allowed_mask.sum())}")
    metric_cols[2].metric("暂不参与", f"{int((~allowed_mask).sum())}")
    metric_cols[3].metric("覆盖分类", f"{category_count}")

    category_summary = (
        available.assign(_category=category_text.mask(category_text == "", "未分类"), _allowed=allowed_mask)
        .groupby("_category", sort=False)
        .agg(指数数量=("_category", "size"), 可参与数量=("_allowed", "sum"))
        .reset_index()
        .rename(columns={"_category": "分类"})
    )
    category_summary["可参与数量"] = category_summary["可参与数量"].astype(int)

    st.markdown("### 分类参与状态")
    st.dataframe(
        category_summary,
        width="stretch",
        hide_index=True,
        height=_compact_dataframe_height(category_summary, max_height=260),
    )

    st.markdown("### 指数状态")
    _render_research_table(_index_trend_display_frame(index_summary), height=420)


def _build_ui_index_etf_universe(
    master: pd.DataFrame,
    parquet_store: ParquetStore,
    *,
    min_rows: int = 252,
) -> pd.DataFrame:
    return build_index_etf_universe(
        master,
        parquet_store,
        config=IndexEtfSampleConfig(max_per_index=10, min_history_rows=min_rows),
    )


def _render_etf_data_overview(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    master = store.list_etf_master()
    if master.empty:
        st.info("尚未初始化 ETF 主列表。请到“数据维护 -> 补齐任务”初始化。")
        return

    watchlist = store.list_watchlist()
    universe = _build_ui_index_etf_universe(master, parquet_store)
    overview = build_etf_data_overview(master, watchlist, parquet_store, universe)

    metric_cols = st.columns(4)
    metric_cols[0].metric("ETF总数", f"{len(overview)}")
    metric_cols[1].metric("每日计算池", f"{int((overview['每日计算池'] == '是').sum())}")
    metric_cols[2].metric("指数样本池", f"{int((overview['指数样本池'] == '是').sum())}")
    metric_cols[3].metric("缺历史", f"{int((overview['本地历史'] == '缺失').sum())}")

    filter_cols = st.columns([2, 1, 1, 1])
    query = filter_cols[0].text_input("搜索ETF", key="etf_data_overview_query")
    history_status = filter_cols[1].selectbox("历史状态", ["全部"] + sorted(overview["本地历史"].dropna().unique().tolist()), key="etf_data_history_status")
    watchlist_status = filter_cols[2].selectbox("每日计算池", ["全部", "是", "否"], key="etf_data_watchlist_status")
    sample_status = filter_cols[3].selectbox("指数样本池", ["全部", "是", "否"], key="etf_data_sample_status")

    view = overview.copy()
    if query:
        text = query.strip()
        view = view[
            view["ETF代码"].astype(str).str.contains(text, case=False, regex=False)
            | view["ETF名称"].astype(str).str.contains(text, case=False, regex=False)
            | view["追踪指数"].astype(str).str.contains(text, case=False, regex=False)
        ]
    if history_status != "全部":
        view = view[view["本地历史"] == history_status]
    if watchlist_status != "全部":
        view = view[view["每日计算池"] == watchlist_status]
    if sample_status != "全部":
        view = view[view["指数样本池"] == sample_status]

    st.dataframe(view, width="stretch", hide_index=True, height=560)


def _render_portfolio_index_etf_pool(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    universe = _build_ui_index_etf_universe(store.list_etf_master(), parquet_store)
    _render_index_etf_pool(universe)


def _data_maintenance_context(
    store: SQLiteStore,
    parquet_store: ParquetStore,
    status: dict[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    master = status.get("master")
    if not isinstance(master, pd.DataFrame):
        master = store.list_etf_master()
    watchlist = status.get("watchlist")
    if not isinstance(watchlist, pd.DataFrame):
        watchlist = store.list_watchlist()
    index_summary = status.get("index_summary")
    if not isinstance(index_summary, pd.DataFrame):
        index_summary = _build_index_trend_summary(parquet_store)
    universe = _build_ui_index_etf_universe(master, parquet_store)
    gaps = build_data_gap_detail(master, watchlist, index_summary, universe, parquet_store)
    return gaps, universe, index_summary


def _compact_dataframe_height(frame: pd.DataFrame, *, max_height: int) -> int:
    visible_rows = max(1, len(frame))
    content_height = COMPACT_DATAFRAME_HEADER_HEIGHT + COMPACT_DATAFRAME_ROW_HEIGHT * visible_rows
    return min(max_height, content_height)


def _render_data_coverage_overview(
    store: SQLiteStore,
    parquet_store: ParquetStore,
    status: dict[str, object],
) -> None:
    master = status["master"]
    watchlist = status["watchlist"]
    gaps, universe, index_summary = _data_maintenance_context(store, parquet_store, status)
    summary = build_data_coverage_summary(gaps, master, watchlist, index_summary, universe)

    issue_count = int(summary[["缺失", "缺少", "历史不足", "读取失败"]].sum().sum()) if not summary.empty else 0
    metric_cols = st.columns(4)
    metric_cols[0].metric("ETF主列表", "已初始化" if not master.empty else "缺失")
    metric_cols[1].metric("ETF历史缺口", f"{len(gaps[gaps['数据类型'] == 'ETF历史']) if not gaps.empty else 0}")
    metric_cols[2].metric("指数历史缺口", f"{len(gaps[gaps['数据类型'] == '指数历史']) if not gaps.empty else 0}")
    metric_cols[3].metric("总缺口", f"{issue_count}")

    st.dataframe(
        summary,
        width="stretch",
        hide_index=True,
        height=_compact_dataframe_height(summary, max_height=320),
        row_height=COMPACT_DATAFRAME_ROW_HEIGHT,
    )
    if not gaps.empty:
        st.markdown("### 主要缺口")
        gap_preview = gaps.head(12)
        st.dataframe(
            gap_preview,
            width="stretch",
            hide_index=True,
            height=_compact_dataframe_height(gap_preview, max_height=360),
            row_height=COMPACT_DATAFRAME_ROW_HEIGHT,
        )


def _render_data_gap_detail(
    store: SQLiteStore,
    parquet_store: ParquetStore,
    status: dict[str, object],
) -> None:
    gaps, _, _ = _data_maintenance_context(store, parquet_store, status)
    if gaps.empty:
        st.success("当前没有明显数据缺口。")
        return

    filter_cols = st.columns([1, 1, 2])
    data_type = filter_cols[0].selectbox("数据类型", ["全部"] + sorted(gaps["数据类型"].dropna().unique().tolist()), key="data_gap_type")
    state = filter_cols[1].selectbox("状态", ["全部"] + sorted(gaps["状态"].dropna().unique().tolist()), key="data_gap_state")
    query = filter_cols[2].text_input("搜索代码或名称", key="data_gap_query")

    view = gaps.copy()
    if data_type != "全部":
        view = view[view["数据类型"] == data_type]
    if state != "全部":
        view = view[view["状态"] == state]
    if query:
        text = query.strip()
        view = view[
            view["代码"].astype(str).str.contains(text, case=False, regex=False)
            | view["名称"].astype(str).str.contains(text, case=False, regex=False)
        ]
    st.dataframe(view, width="stretch", hide_index=True, height=560)


def _render_data_repair_tasks(store: SQLiteStore, parquet_store: ParquetStore) -> None:
    _tab_data_center(store, parquet_store)


def _render_etf_search_and_add(store: SQLiteStore) -> None:
    master = store.list_etf_master()
    if master.empty:
        st.info("尚未初始化 ETF 主列表。请到“数据维护 -> 补齐任务”执行轻量初始化。")
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
        st.info("尚未初始化 ETF 主列表。请到“数据维护 -> 补齐任务”执行轻量初始化。")
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
        st.warning("本地尚无该 ETF 历史行情，请先到“数据维护 -> 补齐任务”初始化历史。")
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
    index_code = _select_index_for_watch()
    definition = get_index_definition(index_code)
    st.info(f"指数：{definition.name} ｜ 市场：{definition.market} ｜ 分类：{definition.category}")

    prices = parquet_store.read_index_prices(index_code)
    if prices.empty:
        st.warning("本地尚无该指数历史数据。请在“数据维护 -> 补齐任务”拉取指数历史。")
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


def _render_research_run_controls(
    *,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    index_summary: pd.DataFrame,
    min_rows: int,
    job_manager: ResearchJobManager,
    output_dir: Path,
) -> None:
    with st.expander("\u8fd0\u884c\u7814\u7a76", expanded=True):
        st.caption("\u91cd\u65b0\u8fd0\u884c\u4f1a\u5728\u540e\u53f0\u6267\u884c\uff1b\u505c\u6b62\u4e0d\u4f1a\u8986\u76d6\u65e7\u7ed3\u679c\u3002\u5efa\u8bae\u5148\u540c\u6b65\u6307\u6570\u6570\u636e\uff0c\u518d\u8fd0\u884c\u8d8b\u52bf\u7814\u7a76\u3002")
        col1, col2, col3 = st.columns([1, 1, 2])
        min_rows = int(col1.number_input("\u6700\u5c11\u5386\u53f2\u884c\u6570", min_value=120, max_value=1200, value=min_rows, step=20))
        limit_input = col2.number_input("\u6700\u591aETF\u6570\u91cf", min_value=0, max_value=1000, value=0, step=10)
        limit = int(limit_input) or None
        use_index_filter = col3.checkbox("\u5148\u6309ETF\u6307\u6570\u8d8b\u52bf\u7b5b\u9009\u8303\u56f4", value=True, key="research_use_index_filter")

        sync_cols = st.columns([1, 1, 2])
        sync_end = sync_cols[1].date_input("\u6307\u6570\u540c\u6b65\u5230", value=date.today(), key="research_index_sync_end")
        if sync_cols[0].button("\u5148\u540c\u6b65\u6307\u6570\u5386\u53f2", key="research_sync_indexes"):
            with st.spinner("\u6b63\u5728\u540c\u6b65\u6307\u6570\u5386\u53f2\u5230\u4eca\u5929..."):
                try:
                    provider = _provider()
                    service = InitializationService(store=store, provider=provider, parquet_store=parquet_store)
                    sync_summary = service.ensure_all_index_history(sync_end)
                except Exception as exc:  # noqa: BLE001 - UI should preserve provider failure text
                    st.session_state["latest_index_sync_message"] = {
                        "level": "error",
                        "message": f"\u6307\u6570\u540c\u6b65\u5931\u8d25\uff1a{exc}",
                    }
                    st.session_state.pop("latest_index_sync_summary", None)
                else:
                    level, message = _index_sync_status_message(sync_summary)
                    st.session_state["latest_index_sync_message"] = {"level": level, "message": message}
                    st.session_state["latest_index_sync_summary"] = sync_summary
            st.rerun()
        sync_cols[2].caption("\u8d8b\u52bf\u7814\u7a76\u4f9d\u8d56\u6307\u6570\u8fc7\u6ee4\u3002\u82e5\u6307\u6570\u5386\u53f2\u6ede\u540e\uff0c\u5148\u540c\u6b65\u518d\u8fd0\u884c\u3002")
        _render_latest_index_sync_result()

        candidates = load_research_candidates(RESEARCH_CONFIG)
        categories = _category_map(store)
        research_codes = None
        if use_index_filter:
            eligible_categories = _eligible_index_categories(index_summary)
            research_codes = _filter_etf_codes_by_categories(store.list_etf_master(), eligible_categories)

        confirm_nonce = int(st.session_state.setdefault("research_run_confirm_nonce", 0))
        confirm_run = st.checkbox("\u786e\u8ba4\u8fd0\u884c\u672c\u6b21\u8d8b\u52bf\u7814\u7a76", value=False, key=f"confirm_research_run_{confirm_nonce}")
        if st.button("\u5f00\u59cb\u8fd0\u884c\u8d8b\u52bf\u7814\u7a76", width="stretch", disabled=job_manager.is_running() or not confirm_run):
            if use_index_filter and not research_codes:
                st.error("\u6307\u6570\u8d8b\u52bf\u8fc7\u6ee4\u540e\u6ca1\u6709\u53ef\u56de\u6d4bETF\uff0c\u672c\u6b21\u4e0d\u8fd0\u884c\u7b56\u7565\u56de\u6d4b\u3002")
                return
            scope_text = "\u6307\u6570\u8d8b\u52bf\u8fc7\u6ee4\u540e" if use_index_filter else "\u5168\u5e02\u573a\u6a21\u5f0f"
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
                st.success("\u8d8b\u52bf\u7814\u7a76\u5df2\u5728\u540e\u53f0\u542f\u52a8\u3002\u8fd0\u884c\u4e2d\u53ef\u4ee5\u70b9\u51fb\u505c\u6b62\uff0c\u4e0d\u4f1a\u8986\u76d6\u65e7\u7ed3\u679c\uff0c\u5b8c\u6210\u540e\u5237\u65b0\u672c\u9875\u5373\u53ef\u67e5\u770b\u65b0\u7ed3\u679c\u3002")
                st.session_state["research_run_confirm_nonce"] = confirm_nonce + 1
                st.rerun()
            else:
                st.warning("\u5df2\u6709\u8d8b\u52bf\u7814\u7a76\u6b63\u5728\u8fd0\u884c\u3002")


def _tab_research(store: SQLiteStore, parquet_store: ParquetStore, research_view: str | None = None) -> None:
    return _tab_strategy_lab(store, parquet_store, research_view)

    st.subheader("\u7814\u7a76\u590d\u76d8")
    st.caption("\u8bfb\u53d6\u5df2\u6709\u7814\u7a76\u7ed3\u679c\uff0c\u590d\u76d8\u7b56\u7565\u8868\u73b0\uff1b\u9700\u8981\u91cd\u65b0\u8ba1\u7b97\u65f6\u518d\u5c55\u5f00\u8fd0\u884c\u7814\u7a76\u3002")
    _inject_research_styles()
    job_manager = _research_job_manager()
    output_dir = RESEARCH_REPORT_DIR
    master = store.list_etf_master()
    index_summary = _build_index_trend_summary(parquet_store)
    eligible_categories = _eligible_index_categories(index_summary)
    eligible_codes = _filter_etf_codes_by_categories(master, eligible_categories)
    min_rows = 252

    index_cols = st.columns(4)
    eligible_index_count = int(index_summary["allows_new_position"].sum()) if "allows_new_position" in index_summary.columns else 0
    index_cols[0].metric("\u53ef\u5f00\u4ed3\u6307\u6570 Eligible Indexes", f"{eligible_index_count}")
    index_cols[1].metric("\u8d8b\u52bf\u5206\u7c7b Categories", f"{len(eligible_categories)}")
    index_cols[2].metric("\u7b5b\u540eETF Filtered ETFs", f"{len(eligible_codes)}")
    index_cols[3].metric("\u5168\u5e02\u573aETF All ETFs", f"{len(master)}")
    if eligible_categories:
        st.info("\u5f53\u524d\u8fdb\u5165\u56de\u6d4b\u7684\u6307\u6570\u5206\u7c7b\uff1a" + "\u3001".join(eligible_categories))
    else:
        st.warning("\u5f53\u524d\u6ca1\u6709\u6307\u6570\u5206\u7c7b\u6ee1\u8db3\u65b0\u5f00\u4ed3\u6761\u4ef6\uff1b\u6309\u4e24\u9636\u6bb5\u89c4\u5219\uff0c\u6b64\u65f6\u4e0d\u5e94\u5f3a\u884c\u6269\u5927ETF\u5019\u9009\u6c60\u3002")

    research_view = research_view or st.radio(
        "\u7814\u7a76\u89c6\u56fe",
        ["\u7814\u7a76\u603b\u89c8", "\u7b56\u7565\u5bf9\u6bd4", "ETF\u590d\u76d8", "\u660e\u7ec6\u8868", "\u8fd0\u884c\u7814\u7a76"],
        horizontal=True,
        key="research_view",
    )

    _render_research_job_status(job_manager)

    extra_tool = st.selectbox("\u7814\u7a76\u8f85\u52a9\u5de5\u5177", ["\u4e0d\u542f\u7528", "\u6307\u6570\u8fc7\u6ee4", "\u624b\u52a8\u56de\u6d4b"], key="research_extra_tool")

    if research_view == "\u8fd0\u884c\u7814\u7a76":
        _render_research_run_controls(
            store=store,
            parquet_store=parquet_store,
            index_summary=index_summary,
            min_rows=min_rows,
            job_manager=job_manager,
            output_dir=output_dir,
        )
    else:
        results_path = output_dir / "research_results.csv"
        ranking_path = output_dir / "candidate_ranking.csv"
        if not results_path.exists() or not ranking_path.exists():
            st.info("\u6682\u65e0\u8d8b\u52bf\u7814\u7a76\u7ed3\u679c\u3002\u70b9\u51fb\u201c\u8fd0\u884c\u8d8b\u52bf\u7814\u7a76\u201d\u751f\u6210\u672c\u5730\u7ed3\u679c\u3002")
        else:
            results = pd.read_csv(results_path)
            ranking = pd.read_csv(ranking_path)
            if results.empty or ranking.empty:
                st.warning("\u8d8b\u52bf\u7814\u7a76\u7ed3\u679c\u4e3a\u7a7a\u3002")
            elif research_view == "\u7814\u7a76\u603b\u89c8":
                _render_research_overview(results, ranking)
            elif research_view == "\u7b56\u7565\u5bf9\u6bd4":
                _render_research_comparison_and_category(results)
            elif research_view == "ETF\u590d\u76d8":
                _render_research_replay(results, store, parquet_store, min_rows)
            else:
                _render_research_detail_table(results, store)

    if extra_tool != "\u4e0d\u542f\u7528":
        with st.expander(f"\u8f85\u52a9\u5de5\u5177\uff1a{extra_tool}", expanded=False):
            if extra_tool == "\u6307\u6570\u8fc7\u6ee4":
                _render_index_filter_explorer(index_summary, parquet_store)
            else:
                _tab_backtest(store, parquet_store)


def _tab_strategy_lab(store: SQLiteStore, parquet_store: ParquetStore, research_view: str | None = None) -> None:
    st.subheader("策略实验室")
    st.caption("创建策略、按指数样本池回测、比较策略表现，并复盘 ETF 的 B/S 点。")
    _inject_research_styles()
    job_manager = _research_job_manager()
    output_dir = RESEARCH_REPORT_DIR
    master = store.list_etf_master()
    min_rows = 252
    index_summary = _build_index_trend_summary(parquet_store)
    universe = build_index_etf_universe(
        master,
        parquet_store,
        config=IndexEtfSampleConfig(max_per_index=10, min_history_rows=min_rows),
    )
    candidates = load_research_candidates(RESEARCH_CONFIG)

    summary_cols = st.columns(4)
    summary_cols[0].metric("策略数", f"{len(candidates)}")
    summary_cols[1].metric("已采用", f"{sum(1 for candidate in candidates if candidate.status == 'adopted')}")
    summary_cols[2].metric("覆盖指数", f"{universe['index_code'].nunique() if not universe.empty else 0}")
    summary_cols[3].metric("默认ETF样本", f"{int(universe['is_top_sample'].sum()) if not universe.empty else 0}")

    _render_research_job_status(job_manager)
    view = research_view or "策略库"
    if view == "策略库":
        _render_strategy_library(candidates)
    elif view == "新建策略":
        _render_strategy_form()
    elif view == "运行回测":
        _render_strategy_lab_run_controls(
            store=store,
            index_summary=index_summary,
            universe=universe,
            min_rows=min_rows,
            job_manager=job_manager,
            output_dir=output_dir,
        )
    elif view == "指数过滤实验":
        _render_index_filter_explorer(index_summary, parquet_store)
    else:
        _render_strategy_lab_results(view, store, parquet_store, min_rows, output_dir)


def _render_strategy_library(candidates: list[StrategyCandidate]) -> None:
    st.markdown("### 策略库")
    if not candidates:
        st.info("当前没有策略。")
        return
    rows = []
    for candidate in candidates:
        rows.append(
            {
                "策略名称": _candidate_display_name(candidate.name),
                "状态": _strategy_status_name(candidate.status),
                "入场均线": candidate.entry_ma.upper(),
                "趋势均线": candidate.trend_ma.upper(),
                "退出均线": candidate.exit_ma.upper(),
                "动量窗口": ",".join(str(item) for item in candidate.momentum_windows) or "不启用",
                "相对强度": "不启用" if candidate.rs_rank_max is None else f"前{int(candidate.rs_rank_max * 100)}%",
                "指数过滤": "启用" if candidate.require_trend_regime else "不启用",
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=420)


def _strategy_status_name(status: str) -> str:
    return {
        "experimental": "实验中",
        "adopted": "已采用",
        "disabled": "停用",
    }.get(status, status)


def _render_strategy_form() -> None:
    st.markdown("### 新建参数化策略")
    with st.form("new_strategy_candidate_form"):
        name = st.text_input("策略名称", value="")
        cols = st.columns(3)
        entry_ma = cols[0].selectbox("入场均线", ["ma20", "ma51", "ma60", "ma120"], index=1)
        trend_ma = cols[1].selectbox("趋势均线", ["ma60", "ma120", "ma250"], index=1)
        exit_ma = cols[2].selectbox("退出均线", ["ma51", "ma60", "ma120"], index=2)
        momentum_windows = st.multiselect("动量窗口", [20, 60, 120], default=[20, 60])
        skip_momentum_windows = st.multiselect("跳过近5日动量窗口", [60, 120], default=[])
        relation_enabled = st.checkbox("要求 MA20 > MA60", value=False)
        slope_field = st.selectbox("斜率要求", ["不启用", "ma60_slope_20", "ma120_slope_20", "ma250_slope_60"])

        filter_cols = st.columns(4)
        rs_rank_label = filter_cols[0].selectbox("相对强度排名", ["不启用", "前20%", "前30%", "前40%"], index=2)
        max_recent_return_20 = filter_cols[1].number_input("20日涨幅上限", min_value=0.0, max_value=1.0, value=0.25, step=0.01)
        max_distance = filter_cols[2].number_input("距入场均线最大乖离", min_value=0.0, max_value=1.0, value=0.12, step=0.01)
        min_interval = int(filter_cols[3].number_input("最小交易间隔", min_value=1, max_value=120, value=10, step=1))

        atr_cols = st.columns(3)
        max_atr_distance = atr_cols[0].selectbox("ATR过热过滤", ["不启用", "1.5ATR", "2ATR", "3ATR"], index=0)
        trailing_atr = atr_cols[1].selectbox("ATR移动止损", ["不启用", "1.5ATR", "2ATR", "3ATR"], index=0)
        target_weight = atr_cols[2].number_input("目标仓位", min_value=0.01, max_value=1.0, value=1.0, step=0.01)
        require_trend_regime = st.checkbox("启用指数过滤实验因子", value=False)
        submitted = st.form_submit_button("保存策略")

    if not submitted:
        return
    strategy_name = name.strip()
    if not strategy_name:
        st.error("策略名称不能为空。")
        return
    candidate = StrategyCandidate(
        name=strategy_name,
        entry_ma=entry_ma,
        trend_ma=trend_ma,
        exit_ma=exit_ma,
        momentum_windows=tuple(int(item) for item in momentum_windows),
        skip_momentum_windows=tuple(int(item) for item in skip_momentum_windows),
        required_ma_relations=(("ma20", "ma60"),) if relation_enabled else (),
        slope_field=None if slope_field == "不启用" else slope_field,
        rs_rank_max=_parse_rank_limit(rs_rank_label),
        max_distance_from_entry_ma=float(max_distance),
        max_recent_return_20=float(max_recent_return_20),
        max_atr_distance_from_ma=_parse_atr_value(max_atr_distance),
        trailing_atr_multiple=_parse_atr_value(trailing_atr),
        min_trade_interval_days=min_interval,
        target_weight=float(target_weight),
        require_trend_regime=require_trend_regime,
        status="experimental",
    )
    try:
        append_research_candidate(RESEARCH_CONFIG, candidate)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.success("策略已保存为实验中。")


def _parse_rank_limit(label: str) -> float | None:
    if label == "不启用":
        return None
    return int(label.removeprefix("前").removesuffix("%")) / 100


def _parse_atr_value(label: str) -> float | None:
    if label == "不启用":
        return None
    return float(label.removesuffix("ATR"))


def _render_strategy_lab_run_controls(
    *,
    store: SQLiteStore,
    index_summary: pd.DataFrame,
    universe: pd.DataFrame,
    min_rows: int,
    job_manager: ResearchJobManager,
    output_dir: Path,
) -> None:
    st.markdown("### 运行回测")
    candidates = load_research_candidates(RESEARCH_CONFIG)
    if not candidates:
        st.warning("当前没有可回测策略。")
        return
    if universe.empty:
        st.warning("当前没有可用指数样本池。请先初始化ETF主数据和历史行情。")
        return

    candidate_names = [candidate.name for candidate in candidates]
    selected_candidate_names = st.multiselect(
        "选择策略",
        candidate_names,
        default=candidate_names[: min(3, len(candidate_names))],
        format_func=_candidate_display_name,
        key="research_run_candidates",
    )
    selected_candidates = [candidate for candidate in candidates if candidate.name in selected_candidate_names]

    label_to_index = _index_pool_label_map(universe)
    selected_index_labels = st.multiselect(
        "选择指数样本池",
        list(label_to_index),
        default=list(label_to_index)[:1],
        key="research_run_indexes",
    )
    selected_index_codes = [label_to_index[label] for label in selected_index_labels]
    research_codes = selected_etf_codes(universe, selected_index_codes)
    task_count = len(research_codes) * len(selected_candidates)
    st.info(
        f"本次将测试：{len(selected_index_codes)} 个指数 / {len(research_codes)} 只 ETF / "
        f"{len(selected_candidates)} 个策略 = {task_count} 个回测任务。"
    )

    confirm_nonce = int(st.session_state.setdefault("research_run_confirm_nonce", 0))
    confirm_run = st.checkbox("确认运行本次策略回测", value=False, key=f"confirm_research_run_{confirm_nonce}")
    if st.button("开始回测", width="stretch", disabled=job_manager.is_running() or not confirm_run):
        if not selected_candidates:
            st.error("请至少选择一个策略。")
            return
        if not research_codes:
            st.error("所选指数样本池没有可回测ETF。")
            return
        started = job_manager.start(
            parquet_root=PARQUET_ROOT,
            candidates=selected_candidates,
            categories=_category_map(store),
            min_rows=min_rows,
            limit=None,
            etf_codes=research_codes,
            output_dir=output_dir,
            index_summary=index_summary,
            scope_text="指数样本池",
        )
        if started:
            st.success("策略回测已在后台启动。运行中可以停止；完成后刷新本页查看新结果。")
            st.session_state["research_run_confirm_nonce"] = confirm_nonce + 1
            st.rerun()
        else:
            st.warning("已有策略回测正在运行。")


def _index_pool_label_map(universe: pd.DataFrame) -> dict[str, str]:
    if universe.empty:
        return {}
    top = universe[universe["is_top_sample"].fillna(False).astype(bool)].copy()
    if top.empty:
        return {}
    counts = top.groupby(["index_code", "index_name"], as_index=False).agg(etf_count=("etf_code", "nunique"))
    labels: dict[str, str] = {}
    for row in counts.sort_values(["index_code"]).itertuples(index=False):
        labels[f"{row.index_code} {row.index_name}（{int(row.etf_count)}只ETF）"] = str(row.index_code)
    return labels


def _render_index_etf_pool(universe: pd.DataFrame) -> None:
    st.markdown("### 指数样本池")
    if universe.empty:
        st.info("当前没有可用指数样本池。请先初始化 ETF 主数据和历史行情。")
        return
    market_options = ["全部市场"] + sorted(universe["market"].dropna().astype(str).unique().tolist())
    market_filter = st.selectbox("市场", market_options, key="index_etf_pool_market")
    top_only = st.checkbox("只看默认Top样本", value=True, key="index_etf_pool_top_only")
    view = universe.copy()
    if market_filter != "全部市场":
        view = view[view["market"].astype(str) == market_filter]
    if top_only:
        view = view[view["is_top_sample"].fillna(False).astype(bool)]
    _render_research_table(_index_etf_universe_display_frame(view), height=520)


def _render_strategy_lab_results(
    view: str,
    store: SQLiteStore,
    parquet_store: ParquetStore,
    min_rows: int,
    output_dir: Path,
) -> None:
    results_path = output_dir / "research_results.csv"
    ranking_path = output_dir / "candidate_ranking.csv"
    if not results_path.exists() or not ranking_path.exists():
        st.info("暂无策略回测结果。请先在“运行回测”生成本地结果。")
        return
    results = pd.read_csv(results_path)
    ranking = pd.read_csv(ranking_path)
    if results.empty or ranking.empty:
        st.warning("策略回测结果为空。")
    elif view == "策略比较":
        _render_research_overview(results, ranking)
        _render_research_comparison_and_category(results)
    elif view == "ETF复盘":
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
    st.subheader("补齐任务")
    st.caption("初始化采用“主列表 -> ETF历史 -> 指数历史 -> 批量任务”的顺序。")
    data_view = st.radio("任务类型", ["主列表", "ETF历史", "指数历史", "批量任务"], horizontal=True, key="data_center_view")

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
