"""Strategy lab page."""

from __future__ import annotations

from pathlib import Path

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
from etf_trading.research.models import StrategyCandidate
from etf_trading.research.runner import run_research
from etf_trading.research.signals import generate_candidate_signals
from etf_trading.strategy.features import add_technical_features
from etf_trading.strategy.models import StrategySignal

RESEARCH_CONFIG = Path("configs/research.yaml")
RESEARCH_REPORT_DIR = Path("reports/research_dashboard")
MIN_RESEARCH_ROWS = 252
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
