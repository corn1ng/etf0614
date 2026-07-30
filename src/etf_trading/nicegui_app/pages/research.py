"""Strategy lab page."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from threading import RLock

import pandas as pd
from nicegui import ui

from etf_trading.backtest.engine import BacktestEngine
from etf_trading.nicegui_app.components.alerts import empty_state
from etf_trading.nicegui_app.components.charts import render_ranged_lightweight_chart
from etf_trading.nicegui_app.components.tables import render_table
from etf_trading.nicegui_app.state import index_chart_payload
from etf_trading.nicegui_app.view_models import (
    PlatformSnapshot,
    code_from_option,
    current_ui_audit_findings,
    etf_choice_options,
    etf_overview_rows,
    index_choice_options,
)
from etf_trading.research.comparison import compare_regime_pairs
from etf_trading.research.config import append_research_candidate, load_research_candidates
from etf_trading.research.index_etf_universe import selected_etf_codes
from etf_trading.research.index_jobs import IndexResearchAlreadyRunning, IndexResearchJobManager, index_research_is_stale
from etf_trading.research.index_report import LoadedIndexResearch, load_latest_index_research, run_and_publish_index_research
from etf_trading.research.models import StrategyCandidate
from etf_trading.research.runner import run_research
from etf_trading.research.signals import generate_candidate_signals
from etf_trading.strategy.features import add_technical_features
from etf_trading.strategy.models import StrategySignal

RESEARCH_CONFIG = Path("configs/research.yaml")
RESEARCH_REPORT_DIR = Path("reports/research_dashboard")
INDEX_RESEARCH_REPORT_DIR = Path("reports/index_research")
MIN_RESEARCH_ROWS = 252
_INDEX_RESEARCH_JOB_MANAGERS: dict[tuple[str, str], IndexResearchJobManager] = {}
_INDEX_RESEARCH_JOB_MANAGERS_LOCK = RLock()
MA_OPTIONS = {
    "20日线": "ma20",
    "51日线": "ma51",
    "60日线": "ma60",
    "120日线": "ma120",
    "250日线": "ma250",
}
SLOPE_FIELD_OPTIONS = {
    "不启用": None,
    "60日线20日斜率": "ma60_slope_20",
    "120日线20日斜率": "ma120_slope_20",
    "250日线60日斜率": "ma250_slope_60",
}
ATR_OPTIONS = {
    "不启用": None,
    "1.5倍真实波幅": 1.5,
    "2倍真实波幅": 2.0,
    "3倍真实波幅": 3.0,
}
CANDIDATE_DISPLAY_NAMES = {
    "balanced_breakout": "平衡突破",
    "regime_balanced_breakout": "趋势过滤平衡突破",
    "early_breakout_tight_heat_filter": "早期突破 + 过热过滤",
    "regime_early_breakout_tight_heat_filter": "趋势过滤早期突破 + 过热过滤",
    "relative_strength_momentum": "相对强度动量",
    "regime_relative_strength_momentum": "趋势过滤相对强度动量",
    "etf_trend_v1_standard": "ETF趋势标准版",
    "etf_trend_v1_width_filtered": "ETF趋势宽度过滤版",
    "etf_trend_v1_tight_heat_filter": "ETF趋势严格过热过滤版",
}


def render(snapshot: PlatformSnapshot, section: str, store=None, parquet_store=None) -> None:
    candidates = _load_candidates()
    _render_summary(snapshot, candidates)

    if section == "策略库":
        _render_strategy_library(candidates)
    elif section == "新建策略":
        _render_strategy_form()
    elif section == "运行回测":
        _render_run_controls(snapshot, candidates, store, parquet_store)
    elif section == "策略比较":
        _render_strategy_results("策略比较", store, parquet_store)
    elif section == "ETF复盘":
        _render_strategy_results("ETF复盘", store, parquet_store)
    elif section == "指数趋势回测":
        render_index_trend_research(INDEX_RESEARCH_REPORT_DIR, parquet_store, _index_research_job_manager(INDEX_RESEARCH_REPORT_DIR, parquet_store))
    else:
        _render_index_filter_experiment(snapshot, parquet_store)

    _render_audit()


def _render_summary(snapshot: PlatformSnapshot, candidates: list[StrategyCandidate]) -> None:
    with ui.row().classes("w-full gap-2"):
        _metric("策略数", len(candidates), "配置候选")
        _metric("已采用", sum(1 for candidate in candidates if candidate.status == "adopted"), "当前启用")
        _metric("覆盖指数", snapshot.universe["index_code"].nunique() if not snapshot.universe.empty else 0, "样本池")
        _metric("默认ETF样本", int(snapshot.universe["is_top_sample"].sum()) if not snapshot.universe.empty and "is_top_sample" in snapshot.universe else 0, "默认样本")


def _render_strategy_library(candidates: list[StrategyCandidate]) -> None:
    if not candidates:
        empty_state("当前没有策略", "请到新建策略保存一个实验策略。")
        return
    rows = [
        {
            "策略名称": _candidate_display_name(candidate.name),
            "状态": _strategy_status_name(candidate.status),
            "入场均线": _ma_display_name(candidate.entry_ma),
            "趋势均线": _ma_display_name(candidate.trend_ma),
            "退出均线": _ma_display_name(candidate.exit_ma),
            "动量窗口": ",".join(str(item) for item in candidate.momentum_windows) or "不启用",
            "相对强度": "不启用" if candidate.rs_rank_max is None else f"前{int(candidate.rs_rank_max * 100)}%",
            "指数过滤": "启用" if candidate.require_trend_regime else "不启用",
        }
        for candidate in candidates
    ]
    render_table(rows, pagination=12, ui_module=ui).classes("workbench-data-table w-full")


def _render_strategy_form() -> None:
    with ui.column().classes("workbench-action-panel workbench-form-panel gap-2"):
        ui.label("新建参数化策略").classes("text-sm font-semibold text-slate-700")
        name = ui.input("策略名称").props("dense outlined").classes("w-full")
        with ui.row().classes("workbench-toolbar w-full"):
            entry_ma = ui.select(["20日线", "51日线", "60日线", "120日线"], value="51日线", label="入场均线").props("dense outlined").classes("w-44")
            trend_ma = ui.select(["60日线", "120日线", "250日线"], value="120日线", label="趋势均线").props("dense outlined").classes("w-44")
            exit_ma = ui.select(["51日线", "60日线", "120日线"], value="120日线", label="退出均线").props("dense outlined").classes("w-44")
        with ui.row().classes("workbench-toolbar w-full"):
            momentum_20 = ui.checkbox("动量20", value=True)
            momentum_60 = ui.checkbox("动量60", value=True)
            momentum_120 = ui.checkbox("动量120", value=False)
            skip_60 = ui.checkbox("跳过近5日动量60", value=False)
            skip_120 = ui.checkbox("跳过近5日动量120", value=False)
        with ui.row().classes("workbench-toolbar w-full"):
            relation_enabled = ui.checkbox("要求20日线高于60日线", value=False)
            slope_field = ui.select(list(SLOPE_FIELD_OPTIONS), value="不启用", label="斜率要求").props("dense outlined").classes("w-52")
            require_trend_regime = ui.checkbox("启用指数过滤实验因子", value=False)
        with ui.row().classes("workbench-toolbar w-full"):
            rs_rank = ui.select(["不启用", "前20%", "前30%", "前40%"], value="前30%", label="相对强度排名").props("dense outlined").classes("w-44")
            max_recent_return = ui.number("20日涨幅上限", value=0.25, min=0, max=1, step=0.01).props("dense outlined").classes("w-44")
            max_distance = ui.number("距入场均线最大乖离", value=0.12, min=0, max=1, step=0.01).props("dense outlined").classes("w-52")
            min_interval = ui.number("最小交易间隔", value=10, min=1, max=120, step=1).props("dense outlined").classes("w-44")
        with ui.row().classes("workbench-toolbar w-full"):
            max_atr = ui.select(list(ATR_OPTIONS), value="不启用", label="真实波幅过热过滤").props("dense outlined").classes("w-44")
            trailing_atr = ui.select(list(ATR_OPTIONS), value="不启用", label="真实波幅移动止损").props("dense outlined").classes("w-44")
            target_weight = ui.number("目标仓位", value=1.0, min=0.01, max=1.0, step=0.01).props("dense outlined").classes("w-44")
        result_area = ui.column().classes("w-full")

        def save() -> None:
            result_area.clear()
            strategy_name = str(name.value or "").strip()
            if not strategy_name:
                ui.notify("策略名称不能为空", type="warning")
                return
            momentum = tuple(window for enabled, window in ((momentum_20.value, 20), (momentum_60.value, 60), (momentum_120.value, 120)) if enabled)
            skip_momentum = tuple(window for enabled, window in ((skip_60.value, 60), (skip_120.value, 120)) if enabled)
            candidate = StrategyCandidate(
                name=strategy_name,
                entry_ma=_ma_code(str(entry_ma.value)),
                trend_ma=_ma_code(str(trend_ma.value)),
                exit_ma=_ma_code(str(exit_ma.value)),
                momentum_windows=momentum,
                skip_momentum_windows=skip_momentum,
                required_ma_relations=(("ma20", "ma60"),) if relation_enabled.value else (),
                slope_field=_slope_field_code(str(slope_field.value)),
                rs_rank_max=_parse_rank_limit(str(rs_rank.value)),
                max_distance_from_entry_ma=float(max_distance.value or 0),
                max_recent_return_20=float(max_recent_return.value or 0),
                max_atr_distance_from_ma=_parse_atr_value(str(max_atr.value)),
                trailing_atr_multiple=_parse_atr_value(str(trailing_atr.value)),
                min_trade_interval_days=int(min_interval.value or 1),
                target_weight=float(target_weight.value or 1.0),
                require_trend_regime=bool(require_trend_regime.value),
                status="experimental",
            )
            try:
                append_research_candidate(RESEARCH_CONFIG, candidate)
            except ValueError as exc:
                ui.notify(str(exc), type="negative")
                with result_area:
                    empty_state("策略保存失败", str(exc))
                return
            ui.notify("策略已保存为实验中", type="positive")
            with result_area:
                ui.label("策略已保存为实验中。刷新策略库即可查看。").classes("text-sm font-semibold text-slate-700")

        ui.button("保存策略", icon="save", on_click=save).props("dense unelevated color=primary")


def _render_run_controls(snapshot: PlatformSnapshot, candidates: list[StrategyCandidate], store, parquet_store) -> None:
    if not candidates:
        empty_state("当前没有可回测策略", "请先在新建策略中保存策略。")
        return
    if snapshot.universe.empty:
        empty_state("当前没有可用指数样本池", "请先初始化 ETF 主数据和历史行情。")
        return

    candidate_labels = [_candidate_display_name(candidate.name) for candidate in candidates]
    label_to_candidate = dict(zip(candidate_labels, candidates, strict=False))
    index_labels = _index_pool_labels(snapshot.universe)
    if not index_labels:
        empty_state("当前没有默认样本", "请先补齐 ETF 历史，让指数样本池生成默认样本。")
        return

    result_area = ui.column().classes("w-full gap-2")
    with ui.row().classes("workbench-toolbar w-full"):
        candidate_scope = ui.select(["当前策略", "全部策略"], value="当前策略", label="策略范围").props("dense outlined").classes("w-40")
        candidate_select = ui.select(candidate_labels, value=candidate_labels[0], label="选择策略").props("dense outlined").classes("w-72")
        index_select = ui.select(index_labels, value=index_labels[0], label="指数样本池").props("dense outlined").classes("w-96")
        confirm = ui.checkbox("确认运行本次策略回测", value=False)
        run_button = ui.button(
            "开始回测",
            icon="play_arrow",
            on_click=lambda: _run_research(
                run_button,
                result_area,
                snapshot,
                store,
                parquet_store,
                candidates if candidate_scope.value == "全部策略" else [label_to_candidate[str(candidate_select.value)]],
                code_from_option(str(index_select.value)),
                bool(confirm.value),
            ),
        ).props("dense unelevated color=primary")

    ui.label("回测结果会保存到本地研究报告目录，完成后可在策略比较和 ETF复盘查看。").classes("text-xs text-slate-500")
    _render_manual_backtest(snapshot, store, parquet_store)


def _render_manual_backtest(snapshot: PlatformSnapshot, store, parquet_store) -> None:
    options = etf_choice_options(etf_overview_rows(snapshot))
    with ui.expansion("单 ETF 手动回测", icon="science").classes("workbench-task-panel w-full"):
        if not options:
            empty_state("暂无 ETF 主列表", "请先初始化 ETF 主列表。")
            return
        result_area = ui.column().classes("w-full gap-2")
        with ui.row().classes("workbench-toolbar w-full"):
            selected = ui.select(options, value=options[0], label="ETF").props("dense outlined").classes("w-96")
            target_weight = ui.number("测试目标仓位", value=0.06, min=0.01, max=0.15, step=0.01).props("dense outlined").classes("w-44")
            signal_date = ui.input("首个买入信号日期", value="").props("dense outlined type=date").classes("w-44")
            backtest_button = ui.button(
                "运行单 ETF 回测",
                icon="play_arrow",
                on_click=lambda: _run_manual_backtest(
                    backtest_button,
                    result_area,
                    store,
                    parquet_store,
                    code_from_option(selected.value),
                    float(target_weight.value or 0.06),
                    str(signal_date.value or ""),
                ),
            ).props("dense outline")
        ui.label("不写入研究结果文件，只用于快速验证单只 ETF 的手动买入信号表现。").classes("text-xs text-slate-500")


def _run_manual_backtest(button, result_area, store, parquet_store, etf_code: str, target_weight: float, first_signal_date: str) -> None:
    if store is None or parquet_store is None:
        ui.notify("当前页面没有可用数据连接", type="negative")
        return
    result_area.clear()
    button.disable()
    try:
        prices = parquet_store.read_prices(etf_code)
        if prices.empty:
            raise ValueError("本地尚无该 ETF 历史行情，请先初始化历史。")
        featured = add_technical_features(prices)
        start = pd.Timestamp(first_signal_date).normalize() if first_signal_date else pd.Timestamp(featured["trade_date"].min()).normalize()
        category = _category_for_code(store, etf_code)
        signal = StrategySignal(
            etf_code=etf_code,
            trade_date=start,
            action="BUY",
            target_weight=target_weight,
            reason="手动回测信号",
            trigger_rules=["manual_backtest"],
        )
        result = BacktestEngine().run_single_etf(etf_code, featured, [signal], category=category)
    except Exception as exc:  # noqa: BLE001 - UI should show manual backtest failures clearly
        ui.notify(f"单 ETF 回测失败：{exc}", type="negative")
        with result_area:
            empty_state("单 ETF 回测失败", str(exc))
    else:
        with result_area:
            with ui.row().classes("w-full gap-2"):
                _metric("总收益", f"{result.metrics.get('total_return', 0) * 100:.2f}%", "累计表现")
                _metric("最大回撤", f"{result.metrics.get('max_drawdown', 0) * 100:.2f}%", "风险回撤")
                _metric("港股跨境暴露", f"{result.metrics.get('max_hk_cross_market_exposure', 0) * 100:.2f}%", "跨境风控")
            payload = _chart_payload_with_trades(featured, result.trades, etf_code)
            render_ranged_lightweight_chart(payload, element_id=f"manual-backtest-{etf_code}", title=f"ETF：{etf_code}")
            _render_rows(_trade_rows(result.trades), "该回测没有产生交易", "检查信号日期是否落在历史区间内。")
        ui.notify("单 ETF 回测完成", type="positive")
    finally:
        button.enable()


def _run_research(button, result_area, snapshot: PlatformSnapshot, store, parquet_store, candidates: list[StrategyCandidate], index_code: str, confirmed: bool) -> None:
    if not confirmed:
        ui.notify("请先勾选确认运行", type="warning")
        return
    if store is None or parquet_store is None:
        ui.notify("当前页面没有可用数据连接", type="negative")
        return
    research_codes = selected_etf_codes(snapshot.universe, [index_code])
    if not research_codes:
        ui.notify("所选指数样本池没有可回测 ETF", type="warning")
        return
    result_area.clear()
    button.disable()
    try:
        output = run_research(
            parquet_store.root,
            candidates=candidates,
            categories=_category_map(store),
            min_rows=MIN_RESEARCH_ROWS,
            etf_codes=research_codes,
        )
        _write_research_outputs(RESEARCH_REPORT_DIR, output, snapshot.index_summary)
    except Exception as exc:  # noqa: BLE001 - UI should show research failures clearly
        ui.notify(f"回测失败：{exc}", type="negative")
        with result_area:
            empty_state("回测失败", str(exc))
    else:
        message = f"完成 {len(candidates)} 个策略 / {len(research_codes)} 只 ETF，使用 {output.used_count} 个本地价格序列。"
        ui.notify(message, type="positive")
        with result_area:
            ui.label(message).classes("text-sm font-semibold text-slate-700")
            rows = output.ranking.fillna("").to_dict("records") if not output.ranking.empty else []
            _render_rows(rows, "回测结果为空", "本地历史可能不足。")
    finally:
        button.enable()


def _render_strategy_results(view: str, store, parquet_store) -> None:
    results, ranking = _load_research_results()
    if results.empty or ranking.empty:
        empty_state("暂无策略回测结果", "请先在“运行回测”生成本地结果。")
        return
    if view == "策略比较":
        _render_research_overview(results, ranking)
        _render_research_comparison_and_category(results)
    else:
        _render_research_replay(results, store, parquet_store)


def _render_research_overview(results: pd.DataFrame, ranking: pd.DataFrame) -> None:
    with ui.row().classes("w-full gap-2"):
        _metric("ETF样本", results["etf_code"].nunique(), "样本数")
        _metric("候选策略", results["candidate_name"].nunique(), "策略数")
        _metric("最佳中位夏普", f"{ranking['median_sharpe'].max():.3f}" if "median_sharpe" in ranking else "", "收益风险比")
        _metric("最差最大回撤", f"{ranking['worst_max_drawdown'].min() * 100:.1f}%" if "worst_max_drawdown" in ranking else "", "回撤")
    ui.label("候选策略排名").classes("text-sm font-semibold text-slate-700")
    _render_rows(_display_rows(ranking), "暂无排名结果", "回测结果为空。")


def _render_research_comparison_and_category(results: pd.DataFrame) -> None:
    comparison = compare_regime_pairs(results)
    ui.label("趋势过滤前后对比").classes("text-sm font-semibold text-slate-700")
    if comparison.empty:
        empty_state("没有配对结果", "没有找到趋势过滤策略与原始策略的配对结果。")
    else:
        _render_rows(_display_rows(comparison), "暂无对比结果", "没有找到配对结果。")

    category = (
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
    ui.label("分类表现").classes("text-sm font-semibold text-slate-700")
    _render_rows(_display_rows(category), "暂无分类表现", "回测结果为空。")


def _render_research_replay(results: pd.DataFrame, store, parquet_store) -> None:
    if store is None or parquet_store is None:
        empty_state("无法复盘", "当前页面没有可用数据连接。")
        return

    candidates = sorted(results["candidate_name"].dropna().astype(str).unique())
    categories = ["全部", *sorted(results["category"].dropna().astype(str).unique())]
    with ui.row().classes("workbench-toolbar w-full"):
        candidate = ui.select(candidates, value=candidates[0], label="候选策略").props("dense outlined").classes("w-72")
        category = ui.select(categories, value=categories[0], label="分类").props("dense outlined").classes("w-44")
    control_area = ui.column().classes("w-full")

    def render_detail() -> None:
        control_area.clear()
        detail = results[results["candidate_name"] == candidate.value].copy()
        if category.value != "全部":
            detail = detail[detail["category"] == category.value]
        if detail.empty:
            with control_area:
                empty_state("没有匹配 ETF", "换一个策略或分类再试。")
            return
        detail = detail.sort_values("sharpe", ascending=False)
        master = store.list_etf_master()
        detail = _attach_etf_names(detail, master)
        option_rows = detail[["etf_code", "etf_name", "category"]].drop_duplicates().sort_values("etf_code")
        option_labels = [f"{row.etf_code} {row.etf_name} · {row.category}" for row in option_rows.itertuples(index=False)]
        with control_area:
            selected = ui.select(option_labels, value=option_labels[0], label="选择复盘ETF").props("dense outlined").classes("w-96")
            replay_area = ui.column().classes("w-full gap-2")

            def draw_replay() -> None:
                _draw_replay_chart(replay_area, str(candidate.value), code_from_option(selected.value), str(option_rows[option_rows["etf_code"] == code_from_option(selected.value)].iloc[0]["category"]), parquet_store)

            selected.on_value_change(lambda event: draw_replay())
            draw_replay()
            ui.label("单 ETF 明细").classes("text-sm font-semibold text-slate-700")
            _render_rows(_display_rows(detail), "暂无明细", "没有匹配结果。")

    candidate.on_value_change(lambda event: render_detail())
    category.on_value_change(lambda event: render_detail())
    render_detail()


def _draw_replay_chart(container, candidate_name: str, etf_code: str, category: str, parquet_store) -> None:
    container.clear()
    candidates = {item.name: item for item in _load_candidates()}
    candidate = candidates.get(candidate_name)
    with container:
        if candidate is None:
            empty_state("无法复盘", "没有找到该候选策略配置。")
            return
        prices = parquet_store.read_prices(etf_code)
        if prices.empty:
            empty_state("无法复盘", "本地尚无该 ETF 历史行情。")
            return
        featured = add_technical_features(prices)
        if "relative_strength_rank" not in featured:
            featured["relative_strength_rank"] = 0.2
        signals = generate_candidate_signals(etf_code, featured, candidate, category=category)
        result = BacktestEngine().run_single_etf(etf_code, featured, signals, category=category)
        with ui.row().classes("w-full gap-2"):
            _metric("策略交易", len(result.trades), "交易信号")
            _metric("总收益", f"{result.metrics.get('total_return', 0) * 100:.1f}%", "累计表现")
            _metric("最大回撤", f"{result.metrics.get('max_drawdown', 0) * 100:.1f}%", "风险回撤")
        payload = _chart_payload_with_trades(featured, result.trades, etf_code)
        render_ranged_lightweight_chart(payload, element_id=f"research-replay-{candidate_name}-{etf_code}", title=f"ETF：{etf_code}")
        trades = _trade_rows(result.trades)
        _render_rows(trades, "该策略没有产生交易", "当前 ETF 历史区间没有买卖点。")


def _index_research_job_manager(report_root: str | Path, parquet_store) -> IndexResearchJobManager:
    """Keep one job manager for each page data location, not one per render."""

    parquet_root = Path(getattr(parquet_store, "root", "data/parquet"))
    key = (str(Path(report_root).resolve()), str(parquet_root.resolve()))
    with _INDEX_RESEARCH_JOB_MANAGERS_LOCK:
        manager = _INDEX_RESEARCH_JOB_MANAGERS.get(key)
        if manager is None:
            manager = IndexResearchJobManager(
                lambda *, progress, should_stop: run_and_publish_index_research(
                    report_root=report_root,
                    parquet_root=parquet_root,
                    progress=progress,
                    should_stop=should_stop,
                )
            )
            _INDEX_RESEARCH_JOB_MANAGERS[key] = manager
        return manager


@dataclass(frozen=True)
class IndexResearchPageState:
    """Pure page decision state; dynamic job status is kept separate from evidence."""

    evidence_status: str
    limited: bool
    job: object
    diagnostic: str
    loaded: LoadedIndexResearch | None

    @property
    def can_start(self) -> bool:
        return getattr(self.job, "status", "idle") not in {"queued", "running"}

    @property
    def can_cancel(self) -> bool:
        return not self.can_start


class IndexResearchPageController:
    """Cache expensive evidence reads while cheaply polling only the job snapshot."""

    def __init__(self, report_root: str | Path, parquet_store, job_manager, *, loader=None, stale_checker=None) -> None:
        self.report_root = report_root
        self.parquet_store = parquet_store
        self.job_manager = job_manager
        self.loader = loader
        self.stale_checker = stale_checker or index_research_is_stale
        self._loaded: LoadedIndexResearch | None = None
        self._evidence_status = "missing"
        self._diagnostic = ""
        self._limited = False
        self.last_loaded_completed_job_id: str | None = None
        self.last_loaded_completed_run_id: str | None = None
        self.last_attempted_completed_identity: tuple[str | None, str | None] | None = None

    @property
    def state(self) -> IndexResearchPageState:
        return IndexResearchPageState(
            evidence_status=self._evidence_status,
            limited=self._limited,
            job=self.job_manager.snapshot(),
            diagnostic=self._diagnostic,
            loaded=self._loaded,
        )

    def load_evidence(self) -> IndexResearchPageState:
        expected_completed_identity = _current_completed_identity(self.job_manager.snapshot())
        loaded, status, diagnostic = _load_index_research_for_page(self.report_root, loader=self.loader)
        stale = False
        if loaded is not None:
            try:
                stale = bool(self.stale_checker(loaded.run_meta, self.parquet_store))
            except (ValueError, OSError, PermissionError, TypeError) as exc:
                loaded, status, diagnostic = None, "invalid", _safe_page_diagnostic(exc)
        self._loaded = loaded
        self._evidence_status = "stale" if loaded is not None and stale else status
        self._diagnostic = diagnostic
        self._limited = bool(loaded is not None and loaded.run_meta.get("limited_run"))
        current_completed_identity = _current_completed_identity(self.job_manager.snapshot())
        if expected_completed_identity is not None and current_completed_identity == expected_completed_identity:
            self.last_attempted_completed_identity = expected_completed_identity
        if (
            loaded is not None
            and expected_completed_identity is not None
            and current_completed_identity == expected_completed_identity
            and str(getattr(loaded, "run_id", "")) == str(expected_completed_identity[1] or "")
        ):
            self.last_loaded_completed_job_id, self.last_loaded_completed_run_id = expected_completed_identity
        return self.state

    def poll(self) -> bool:
        """Return whether a completed transition requires exactly one evidence reload."""

        snapshot = self.job_manager.snapshot()
        completed_identity = _completed_job_identity(snapshot)
        needs_evidence_attempt = (
            getattr(snapshot, "status", "idle") == "completed"
            and completed_identity != self.last_attempted_completed_identity
        )
        if needs_evidence_attempt:
            self.load_evidence()
        return needs_evidence_attempt


def _completed_job_identity(snapshot) -> tuple[str | None, str | None]:
    job_id = getattr(snapshot, "job_id", None)
    run_id = getattr(snapshot, "run_id", None)
    if job_id is None and run_id is None:
        return (f"legacy-snapshot:{id(snapshot)}", None)
    return (job_id, run_id)


def _current_completed_identity(snapshot) -> tuple[str | None, str | None] | None:
    return _completed_job_identity(snapshot) if getattr(snapshot, "status", "idle") == "completed" else None


def index_research_layout_order() -> tuple[str, str, str]:
    """The fixed visual hierarchy for the index research surface."""

    return ("metadata", "controls", "results")


def render_index_trend_research(report_root: str | Path, parquet_store, job_manager: IndexResearchJobManager) -> None:
    """Render cached validated evidence; timer ticks only update lightweight job controls."""

    controller = IndexResearchPageController(report_root, parquet_store, job_manager)
    controller.load_evidence()
    ui.label("指数理论回测").classes("text-base font-semibold text-slate-800")
    metadata_area = ui.column().classes("w-full gap-3 index-trend-research-metadata")

    with ui.row().classes("workbench-toolbar w-full gap-2 flex-wrap"):
        rerun = ui.button("重新回测", icon="play_arrow", on_click=lambda: _start_index_research_job(job_manager, update_job_widgets)).props("dense outline")
        ui.button("刷新结果", icon="refresh", on_click=lambda: _refresh_index_research_evidence(controller, render_evidence)).props("dense outline")
        cancel = ui.button("取消重算", icon="cancel", on_click=lambda: _cancel_index_research_job(job_manager, update_job_widgets)).props("dense outline")
    progress = ui.linear_progress(value=0).props("instant-feedback").classes("w-full")
    job_label = ui.label("").classes("text-sm text-slate-600")
    results_area = ui.column().classes("w-full gap-3 index-trend-research-results")

    def render_evidence() -> None:
        metadata_area.clear()
        results_area.clear()
        with metadata_area:
            _render_index_research_metadata(controller.state)
        with results_area:
            if controller.state.loaded is not None:
                _render_index_research_evidence(controller.state.loaded)

    render_evidence()

    def update_job_widgets() -> None:
        if controller.poll():
            render_evidence()
        state = controller.state
        if state.can_start:
            rerun.enable()
        else:
            rerun.disable()
        cancel.set_visibility(state.can_cancel)
        progress.set_visibility(state.can_cancel and bool(getattr(state.job, "total", 0)))
        total = int(getattr(state.job, "total", 0) or 0)
        if total > 0:
            progress.value = max(0.0, min(1.0, int(getattr(state.job, "done", 0) or 0) / total))
            progress.update()
        job_label.set_text(_index_research_job_state_text(state.job))

    update_job_widgets()
    # This timer does not call the loader, stale scan, or rebuild the evidence area.
    ui.timer(1.0, update_job_widgets)


def _load_index_research_for_page(report_root: str | Path, *, loader=None) -> tuple[LoadedIndexResearch | None, str, str]:
    selected_loader = loader or load_latest_index_research
    try:
        return selected_loader(report_root), "available", ""
    except (ValueError, OSError, PermissionError, TypeError) as exc:
        message = str(exc)
        state = "missing" if isinstance(exc, ValueError) and "pointer is missing" in message else "invalid"
        return None, state, _safe_page_diagnostic(exc)


def _safe_page_diagnostic(exc: Exception) -> str:
    return escape(" ".join(str(exc).split())[:300]) or type(exc).__name__


def _refresh_index_research_evidence(controller: IndexResearchPageController, render_evidence) -> None:
    controller.load_evidence()
    render_evidence()


def _cancel_index_research_job(job_manager: IndexResearchJobManager, update_job_widgets) -> None:
    job_manager.cancel()
    update_job_widgets()


def _render_index_research_metadata(state: IndexResearchPageState) -> None:
    loaded = state.loaded
    if loaded is None:
        if state.evidence_status == "missing":
            empty_state("暂无指数趋势回测结果", "页面不会自动计算；请点击“重新回测”在后台生成完整证据包。")
        else:
            empty_state("指数趋势回测结果无效", f"已拒绝读取不完整或损坏的结果：{state.diagnostic}")
        return
    meta = loaded.run_meta
    with ui.row().classes("w-full gap-2 flex-wrap"):
        _metric("策略版本", meta.get("strategy_version", ""), "锁定规则")
        _metric("锁定日期", meta.get("locked_at", ""), "参数冻结日")
        _metric("数据截止日", meta.get("data_cutoff", ""), "已发布样本")
        _metric("运行时间", meta.get("run_at", ""), "证据包生成时间")
        _metric("结果状态", "结果已过期" if state.evidence_status == "stale" else "结果可用", "本地指数数据检查")
    if state.evidence_status == "stale":
        ui.label("结果已过期：本地指数 Parquet 存在严格晚于数据截止日的新数据，请重新回测。").classes("workbench-warning-line w-full")
    if state.limited:
        ui.label("醒目提示：这是有限样本运行，不构成全量历史有效性结论。").classes("workbench-warning-line w-full")


def _start_index_research_job(job_manager: IndexResearchJobManager, update_job_widgets) -> None:
    try:
        job_manager.start()
    except IndexResearchAlreadyRunning:
        ui.notify("指数趋势回测已在运行", type="warning")
    else:
        ui.notify("已在后台启动指数趋势回测", type="positive")
    update_job_widgets()


def _index_research_job_state_text(job) -> str:
    if job.status in {"queued", "running"}:
        suffix = f" · {job.message}" if getattr(job, "message", "") else ""
        return f"任务状态：{job.status} · {job.done}/{job.total} · {job.index_code or job.phase}{suffix}"
    elif job.status == "completed":
        return f"后台回测完成：run_id={job.run_id or ''}，数据截止日={job.data_cutoff or ''}。已重新读取最新完整结果。"
    elif job.status == "failed":
        return f"后台回测失败：{job.error}"
    elif job.status == "cancelled":
        return "后台回测已取消；最近一次成功发布的结果仍可查看。"
    return ""


def _render_index_research_evidence(loaded: LoadedIndexResearch) -> None:
    meta = loaded.run_meta
    gates = [
        {"门槛": name, "是否通过": "通过" if passed else "未通过", "证据": meta.get("gate_values", {}).get(name, "")}
        for name, passed in dict(meta.get("gates", {})).items()
    ]
    ui.label("总体结论").classes("text-sm font-semibold text-slate-700")
    conclusion = "通过历史有效性门槛" if meta.get("status") == "passed" else "未通过历史有效性门槛"
    ui.label(f"{conclusion}（这是策略证据结论，不等同于后台任务 failed）。").classes("text-sm text-slate-600")
    _render_rows(gates, "暂无六项门槛证据", "已发布结果缺少门槛行。")

    full = loaded.results[loaded.results.get("period_type", pd.Series(dtype="object")) == "full_history"]
    official = full[full.get("cohort", pd.Series(dtype="object")) == "official"] if not full.empty else full
    ui.label("官方样本 V1 / 买入持有").classes("text-sm font-semibold text-slate-700")
    _render_rows(_display_rows(official), "暂无官方样本", "该完整证据包没有官方样本结果。")
    _render_index_research_selector(loaded)

    ui.label("0/2/3% 缓冲带诊断").classes("text-sm font-semibold text-slate-700")
    _render_rows(_display_rows(loaded.buffer_comparison), "暂无缓冲带诊断", "没有可展示的缓冲带对照。")
    ui.label("双倍费用").classes("text-sm font-semibold text-slate-700")
    _render_rows(_display_rows(loaded.stress_results), "暂无双倍费用结果", "没有可展示的压力测试。")
    ui.label("扩展样本").classes("text-sm font-semibold text-slate-700")
    reference = full[full.get("cohort", pd.Series(dtype="object")) == "reference"] if not full.empty else full
    _render_rows(_display_rows(reference), "暂无扩展样本", "没有第三方基日扩展样本。")
    ui.label("排除原因").classes("text-sm font-semibold text-slate-700")
    _render_rows(_display_rows(loaded.exclusions), "暂无排除项", "所有已知样本均已准入，或无排除记录。")
    ui.label("前瞻状态与限制").classes("text-sm font-semibold text-slate-700")
    _render_rows(_display_rows(loaded.prospective_status), "暂无前瞻样本", "锁定日后尚无可用的前瞻样本。")
    ui.label("指数理论回测仅提供指数层面的历史证据，不代表 ETF 可实现收益。").classes("text-xs text-slate-500")


def _render_index_research_selector(loaded: LoadedIndexResearch) -> None:
    nav = loaded.nav[loaded.nav.get("period_type", pd.Series(dtype="object")) == "full_history"].copy()
    codes = sorted(nav.get("index_code", pd.Series(dtype="object")).dropna().astype(str).unique())
    detail_area = ui.column().classes("w-full gap-2")
    if not codes:
        with detail_area:
            _render_empty_index_research_detail()
        return
    with ui.row().classes("workbench-toolbar w-full"):
        selected = ui.select(codes, value=codes[0], label="选择指数").props("dense outlined").classes("w-72")

    def draw_detail() -> None:
        detail_area.clear()
        evidence = _filtered_index_research_evidence(loaded, str(selected.value))
        with detail_area:
            payload = _index_research_nav_payload(evidence["nav"])
            if payload[0]["series"]:
                render_ranged_lightweight_chart(payload, element_id=f"index-trend-nav-{selected.value}", title=f"指数净值与回撤：{selected.value}")
            ui.label("年度与五年滚动").classes("text-sm font-semibold text-slate-700")
            _render_rows(_display_rows(evidence["yearly"]), "暂无年度结果", "没有可展示的年度样本。")
            ui.label("五年滚动").classes("text-sm font-semibold text-slate-700")
            _render_rows(_display_rows(evidence["rolling"]), "暂无五年滚动结果", "没有满足完整五年覆盖的窗口。")
            ui.label("交易记录").classes("text-sm font-semibold text-slate-700")
            _render_rows(_display_rows(evidence["trades"]), "没有交易记录", "该指数在所选区间没有完成交易。")

    selected.on_value_change(lambda event: draw_detail())
    draw_detail()


def empty_index_research_detail_states() -> tuple[str, str, str, str]:
    return ("暂无净值曲线", "暂无年度数据", "暂无五年滚动", "没有交易记录")


def _render_empty_index_research_detail() -> None:
    nav_empty, yearly_empty, rolling_empty, trades_empty = empty_index_research_detail_states()
    empty_state(nav_empty, "完整证据包没有可绘制的 NAV 数据。")
    ui.label("年度与五年滚动").classes("text-sm font-semibold text-slate-700")
    empty_state(yearly_empty, "没有可展示的年度样本。")
    ui.label("五年滚动").classes("text-sm font-semibold text-slate-700")
    empty_state(rolling_empty, "没有满足完整五年覆盖的窗口。")
    ui.label("交易记录").classes("text-sm font-semibold text-slate-700")
    empty_state(trades_empty, "该指数在所选区间没有完成交易。")


def _filtered_index_research_evidence(loaded: LoadedIndexResearch, index_code: str) -> dict[str, pd.DataFrame]:
    """Filter all selector-dependent evidence together, without recalculating it."""

    def filter_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty or "index_code" not in frame:
            return frame.copy()
        return frame[frame["index_code"].astype(str) == str(index_code)].copy()

    nav = filter_frame(loaded.nav)
    if "period_type" in nav:
        nav = nav[nav["period_type"] == "full_history"].copy()
    return {"nav": nav, "trades": filter_frame(loaded.trades), "yearly": filter_frame(loaded.yearly), "rolling": filter_frame(loaded.rolling)}


def _index_research_nav_payload(nav: pd.DataFrame) -> list[dict]:
    if nav.empty or not {"trade_date", "nav", "strategy_name"}.issubset(nav.columns):
        return [{"chart": {"height": 320}, "series": []}]
    frame = nav.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["nav"] = pd.to_numeric(frame["nav"], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "nav"]).sort_values("trade_date")
    frame = frame.drop_duplicates(["strategy_name", "trade_date"], keep="last")
    series = []
    for strategy_name, rows in frame.groupby("strategy_name", sort=True):
        points = [{"time": date.strftime("%Y-%m-%d"), "value": float(value)} for date, value in zip(rows["trade_date"], rows["nav"], strict=False)]
        series.append({"type": "Line", "data": points, "options": {"title": str(strategy_name)}})
        drawdown = rows["nav"] / rows["nav"].cummax() - 1.0
        series.append({"type": "Line", "data": [{"time": date.strftime("%Y-%m-%d"), "value": float(value)} for date, value in zip(rows["trade_date"], drawdown, strict=False)], "options": {"title": f"{strategy_name} 回撤", "color": "#dc2626"}})
    return [{"chart": {"height": 360}, "series": series}]


def _render_index_filter_experiment(snapshot: PlatformSnapshot, parquet_store) -> None:
    options = index_choice_options(snapshot.index_summary)
    if not options:
        empty_state("暂无指数过滤数据", "请先补齐指数历史。")
        return
    with ui.row().classes("workbench-toolbar w-full"):
        selected = ui.select(options, value=options[0], label="指数").props("dense outlined").classes("w-96")
    chart_area = ui.column().classes("w-full gap-2")

    def draw() -> None:
        chart_area.clear()
        index_code = code_from_option(selected.value)
        with chart_area:
            if parquet_store is not None:
                payload = index_chart_payload(parquet_store, index_code)
                if payload[0]["series"]:
                    render_ranged_lightweight_chart(payload, element_id=f"research-index-filter-{index_code}", title=f"指数：{index_code}")
            rows = snapshot.index_summary.fillna("").to_dict("records") if not snapshot.index_summary.empty else []
            _render_rows(rows, "暂无指数过滤表", "请先补齐指数历史。")

    selected.on_value_change(lambda event: draw())
    draw()


def _chart_payload_with_trades(frame: pd.DataFrame, trades: list[object], etf_code: str) -> list[dict]:
    from etf_trading.ui.chart_renderer import build_lightweight_chart_payload

    return build_lightweight_chart_payload(frame, trades=trades, chart_type="candlestick", price_scale_mode="normal", ma_columns=["ma51"])


def _write_research_outputs(output_dir: Path, output: object, index_summary: pd.DataFrame) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    output.results.to_csv(output_dir / "research_results.csv", index=False)
    output.ranking.to_csv(output_dir / "candidate_ranking.csv", index=False)
    index_summary.to_csv(output_dir / "index_trend_summary.csv", index=False)
    universe = sorted(output.results["etf_code"].astype(str).unique()) if not output.results.empty else []
    pd.DataFrame({"etf_code": universe}).to_csv(output_dir / "research_universe.csv", index=False)


def _load_research_results() -> tuple[pd.DataFrame, pd.DataFrame]:
    results_path = RESEARCH_REPORT_DIR / "research_results.csv"
    ranking_path = RESEARCH_REPORT_DIR / "candidate_ranking.csv"
    if not results_path.exists() or not ranking_path.exists():
        return pd.DataFrame(), pd.DataFrame()
    return pd.read_csv(results_path), pd.read_csv(ranking_path)


def _display_rows(frame: pd.DataFrame) -> list[dict[str, object]]:
    if frame.empty:
        return []
    result = frame.copy()
    for column in result.select_dtypes(include="number").columns:
        result[column] = result[column].round(4)
    for column in ("candidate_name", "base_candidate"):
        if column in result:
            result[column] = result[column].map(lambda value: _candidate_display_name(str(value)) if pd.notna(value) else value)
    return result.fillna("").to_dict("records")


def _attach_etf_names(frame: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["etf_code"] = result["etf_code"].astype(str).str.zfill(6)
    if master.empty:
        result["etf_name"] = result["etf_code"]
        return result
    names = master.assign(etf_code=master["etf_code"].astype(str).str.zfill(6))[["etf_code", "name"]]
    result = result.merge(names, on="etf_code", how="left")
    result["etf_name"] = result["name"].fillna(result["etf_code"])
    return result.drop(columns=["name"])


def _trade_rows(trades: list[object]) -> list[dict[str, object]]:
    rows = []
    for trade in trades:
        rows.append(
            {
                "ETF代码": trade.etf_code,
                "成交日": pd.Timestamp(trade.trade_date).strftime("%Y-%m-%d"),
                "动作": trade.action,
                "信号日": pd.Timestamp(trade.signal_date).strftime("%Y-%m-%d"),
                "成交前仓位": f"{trade.weight_before * 100:.1f}%",
                "成交后仓位": f"{trade.weight_after * 100:.1f}%",
                "成交价": f"{trade.price:.3f}",
            }
        )
    return rows


def _index_pool_labels(universe: pd.DataFrame) -> list[str]:
    if universe.empty or "is_top_sample" not in universe:
        return []
    top = universe[universe["is_top_sample"].fillna(False).astype(bool)].copy()
    if "pool" in top:
        top = top[top["pool"].fillna("").astype(str) == "core"]
    if "is_tradable" in top:
        top = top[top["is_tradable"].fillna(False).astype(bool)]
    if top.empty:
        return []
    counts = top.groupby(["index_code", "index_name"], as_index=False).agg(etf_count=("etf_code", "nunique"))
    return [f"{row.index_code} {row.index_name}（{int(row.etf_count)}只ETF）" for row in counts.sort_values("index_code").itertuples(index=False)]


def _category_map(store) -> dict[str, str]:
    master = store.list_etf_master()
    if master.empty:
        return {}
    return dict(zip(master["etf_code"].astype(str).str.zfill(6), master["category"].fillna("A股宽基").astype(str), strict=False))


def _category_for_code(store, etf_code: str) -> str:
    return _category_map(store).get(str(etf_code).zfill(6), "A股宽基")


def _load_candidates() -> list[StrategyCandidate]:
    try:
        return load_research_candidates(RESEARCH_CONFIG)
    except FileNotFoundError:
        return []


def _parse_rank_limit(label: str) -> float | None:
    if label == "不启用":
        return None
    return int(label.removeprefix("前").removesuffix("%")) / 100


def _ma_code(label: str) -> str:
    return MA_OPTIONS.get(label, label)


def _ma_display_name(code: str) -> str:
    for label, value in MA_OPTIONS.items():
        if value == code:
            return label
    return code


def _slope_field_code(label: str) -> str | None:
    return SLOPE_FIELD_OPTIONS.get(label)


def _parse_atr_value(label: str) -> float | None:
    return ATR_OPTIONS.get(label)


def _candidate_display_name(candidate_name: str) -> str:
    return CANDIDATE_DISPLAY_NAMES.get(candidate_name, f"自定义策略：{candidate_name}")


def _strategy_status_name(status: str) -> str:
    return {"experimental": "实验中", "adopted": "已采用", "disabled": "停用"}.get(status, status)


def _render_rows(rows: list[dict[str, object]], empty_title: str, empty_detail: str) -> None:
    if rows:
        render_table(rows, pagination=12, ui_module=ui).classes("workbench-data-table w-full")
    else:
        empty_state(empty_title, empty_detail)


def _metric(label: str, value: object, detail: str) -> None:
    with ui.column().classes("workbench-metric"):
        ui.label(label).classes("workbench-metric-label")
        ui.label(str(value)).classes("workbench-metric-value")
        ui.label(detail).classes("text-xs text-slate-400")


def _render_audit() -> None:
    with ui.expansion("本页 UI 修正点", icon="rule").classes("w-full text-sm"):
        for item in current_ui_audit_findings():
            if item.page_slug == "research":
                ui.label(f"{item.problem} -> {item.fix}").classes("text-xs text-slate-500")
