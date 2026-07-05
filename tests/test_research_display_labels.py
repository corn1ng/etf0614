import pandas as pd
import pytest

from etf_trading.data.indexes import IndexDefinition
from etf_trading.data.storage import ParquetStore
from etf_trading.ui.app import (
    WORKFLOW_TABS,
    _backtest_index_signal_markers,
    _build_index_trend_summary,
    _candidate_display_name,
    _eligible_index_categories,
    _filter_index_picker_frame,
    _filter_date_range_frame,
    _filter_etf_codes_by_categories,
    _format_index_rule_names,
    _format_index_risk_names,
    _index_etf_universe_display_frame,
    _index_gate_markers,
    _index_trend_display_frame,
    _index_signal_diagnostic_display_frame,
    _index_signal_markers_for_rule,
    _index_sync_display_frame,
    _index_sync_status_message,
    _index_signal_problem_diagnostics,
    _index_option_label,
    _index_status_code_items,
    _long_trend_index_signal_markers,
    _number_index_signal_segments,
    _research_attach_etf_names,
    _research_display_frame,
    _research_select_columns,
    _stable_index_signal_markers,
    _trend_hold_index_signal_markers,
)


def test_workspace_tabs_follow_investment_workflow():
    assert WORKFLOW_TABS == ["今日行动", "市场地图", "ETF数据", "策略实验室", "数据维护"]


def test_filter_date_range_frame_keeps_arbitrary_chart_window():
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-02-01", "2024-03-01"]),
            "close": [1.0, 1.1, 1.2],
        }
    )

    result = _filter_date_range_frame(frame, pd.Timestamp("2024-01-15").date(), pd.Timestamp("2024-02-15").date())

    assert result["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-02-01"]


def test_candidate_display_name_uses_standard_chinese_and_english_names():
    assert _candidate_display_name("balanced_breakout") == "平衡突破 Balanced Breakout"
    assert _candidate_display_name("regime_balanced_breakout") == "趋势过滤平衡突破 Regime-Gated Balanced Breakout"


def test_research_display_frame_renames_columns_and_candidate_values():
    frame = pd.DataFrame(
        {
            "candidate_name": ["early_breakout_tight_heat_filter"],
            "sample_count": [40],
            "mean_total_return": [0.259],
            "median_sharpe": [0.34],
            "worst_max_drawdown": [-0.64],
        }
    )

    display = _research_display_frame(frame)

    assert list(display.columns) == [
        "候选策略 Strategy",
        "样本数 Samples",
        "平均总收益 Mean Total Return",
        "中位夏普 Median Sharpe",
        "最差最大回撤 Worst Max Drawdown",
    ]
    assert display.iloc[0]["候选策略 Strategy"] == "早期突破 + 过热过滤 Early Breakout + Heat Filter"
    assert display.iloc[0]["平均总收益 Mean Total Return"] == 25.9
    assert display.iloc[0]["最差最大回撤 Worst Max Drawdown"] == -64.0


def test_research_select_columns_keeps_core_metrics_without_wide_scroll():
    frame = pd.DataFrame(
        {
            "candidate_name": ["balanced_breakout"],
            "sample_count": [84],
            "mean_total_return": [0.25],
            "median_annualized_return": [0.02],
            "median_sharpe": [0.21],
            "median_calmar": [0.1],
            "worst_max_drawdown": [-0.83],
            "mean_trade_count": [10.4],
            "score": [0.5],
            "unused_internal_metric": [123],
        }
    )

    selected = _research_select_columns(
        frame,
        [
            "candidate_name",
            "sample_count",
            "mean_total_return",
            "median_annualized_return",
            "worst_max_drawdown",
            "median_sharpe",
            "mean_trade_count",
            "score",
        ],
    )

    assert "unused_internal_metric" not in selected.columns
    assert list(selected.columns) == [
        "candidate_name",
        "sample_count",
        "mean_total_return",
        "median_annualized_return",
        "worst_max_drawdown",
        "median_sharpe",
        "mean_trade_count",
        "score",
    ]


def test_research_attach_etf_names_adds_name_after_code():
    frame = pd.DataFrame(
        {
            "etf_code": [159008],
            "category": ["A股行业"],
            "total_return": [0.12],
        }
    )
    master = pd.DataFrame(
        {
            "etf_code": ["159008"],
            "name": ["证券ETF景顺"],
        }
    )

    enriched = _research_attach_etf_names(frame, master)
    display = _research_display_frame(enriched)

    assert list(display.columns) == [
        "ETF代码 ETF Code",
        "ETF名称",
        "分类 Category",
        "总收益 Total Return",
    ]
    assert display.iloc[0]["ETF代码 ETF Code"] == "159008"
    assert display.iloc[0]["ETF名称"] == "证券ETF景顺"


def test_index_trend_filter_keeps_only_etfs_in_trending_categories():
    summary = pd.DataFrame(
        {
            "category": ["A股行业", "港股科技"],
            "allows_new_position": [True, False],
        }
    )
    master = pd.DataFrame(
        {
            "etf_code": ["512880", "513180", "510300"],
            "category": ["A股行业", "港股科技", "A股宽基"],
        }
    )

    categories = _eligible_index_categories(summary)
    codes = _filter_etf_codes_by_categories(master, categories)

    assert categories == ["A股行业"]
    assert codes == ["512880"]


def test_build_index_trend_summary_classifies_latest_index_regime(tmp_path):
    store = ParquetStore(tmp_path)
    dates = pd.bdate_range("2020-01-01", periods=900)
    close = pd.Series(range(1000, 1900), dtype=float) / 1000
    store.write_index_prices(
        "000300",
        pd.DataFrame(
            {
                "index_code": "000300",
                "trade_date": dates,
                "open": close * 0.99,
                "high": close * 1.01,
                "low": close * 0.98,
                "close": close,
                "volume": 1000,
                "amount": 2000,
            }
        ),
    )

    summary = _build_index_trend_summary(
        store,
        definitions=(IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),),
    )

    assert summary.iloc[0]["index_name"] == "沪深300"
    assert summary.iloc[0]["latest_date"] == dates[-1].strftime("%Y-%m-%d")
    assert bool(summary.iloc[0]["allows_new_position"]) is True


def test_index_trend_display_uses_chinese_index_names_and_headers():
    summary = pd.DataFrame(
        {
            "index_code": ["000905", "399001"],
            "index_name": ["中证500", "深证成指"],
            "market": ["A股", "A股"],
            "category": ["A股宽基", "A股综合"],
            "large_trend": ["上升 UP", "上升 UP"],
            "medium_trend": ["上升 UP", "上升 UP"],
            "small_trend": ["右侧开始 RIGHT SIDE", "回踩 PULLBACK"],
            "allows_new_position": [True, True],
            "latest_date": ["2026-07-03", "2026-07-03"],
        }
    )

    display = _index_trend_display_frame(summary)

    assert "指数名称" in display.columns
    assert "指数 Name" not in display.columns
    assert display["指数名称"].tolist() == ["中证500", "深证成指"]


def test_index_etf_universe_display_uses_chinese_headers():
    frame = pd.DataFrame(
        {
            "index_code": ["000300"],
            "index_name": ["沪深300"],
            "etf_code": ["510300"],
            "etf_name": ["沪深300ETF华泰柏瑞"],
            "mapping_source": ["name_inferred"],
            "confidence": ["medium"],
            "amount": [100_000_000],
            "history_rows": [300],
            "is_top_sample": [True],
        }
    )

    display = _index_etf_universe_display_frame(frame)

    assert "追踪指数" in display.columns
    assert "映射来源" in display.columns
    assert "置信度" in display.columns
    assert display.iloc[0]["追踪指数"] == "沪深300"
    assert display.iloc[0]["映射来源"] == "名称推断"
    assert display.iloc[0]["置信度"] == "中"


def test_index_sync_summary_displays_status_counts_and_latest_date():
    summary = pd.DataFrame(
        {
            "index_code": ["000300", "000905", "399006"],
            "status": ["UPDATED", "SKIPPED", "FAILED"],
            "fetched_rows": [2, 0, 0],
            "total_rows": [900, 880, 0],
            "start_date": [pd.Timestamp("2020-01-01").date(), pd.Timestamp("2020-01-01").date(), None],
            "end_date": [pd.Timestamp("2024-01-05").date(), pd.Timestamp("2024-01-04").date(), None],
            "error_message": [None, None, "provider timeout"],
        }
    )

    level, message = _index_sync_status_message(summary)
    display = _index_sync_display_frame(summary)

    assert level == "warning"
    assert message == "指数同步完成：1 个写入/补齐，1 个已是最新，1 个失败。最新本地交易日 2024-01-05。"
    assert list(display.columns) == [
        "指数代码 Index Code",
        "同步状态 Sync Status",
        "新增行数 Fetched Rows",
        "本地总行数 Total Rows",
        "最新日期 Latest Date",
        "错误信息 Error",
    ]
    assert display.iloc[0]["同步状态 Sync Status"] == "已补齐 Updated"
    assert display.iloc[1]["同步状态 Sync Status"] == "已是最新 Current"
    assert display.iloc[2]["同步状态 Sync Status"] == "同步失败 Failed"


def test_index_rule_names_are_displayed_as_chinese_explanations():
    names = _format_index_rule_names(["large_uptrend", "medium_uptrend", "small_right_side_start"])

    assert names == [
        "大趋势向上：价格站上长期均线，长期均线继续上行",
        "中趋势向上：价格站上中期均线，60日动量为正",
        "小趋势右侧开始：价格重新站上短期均线，离中期均线不远",
    ]


def test_unknown_index_rule_names_are_not_shown_as_raw_code():
    assert _format_index_rule_names(["custom_rule"]) == ["未识别规则：custom_rule"]
    assert _format_index_risk_names(["small_trend_extended"]) == ["短线过热：离中期均线太远，追高风险增加"]


def test_index_picker_filters_by_status_and_category():
    summary = pd.DataFrame(
        {
            "index_code": ["000300", "399006", "399975"],
            "index_name": ["沪深300", "创业板指", "证券公司"],
            "category": ["A股宽基", "A股成长", "A股行业"],
            "allows_new_position": [True, True, False],
        }
    )

    picked = _filter_index_picker_frame(summary, status_filter="可找买点", category_filter="A股成长")

    assert picked["index_code"].tolist() == ["399006"]
    assert _index_option_label(picked.iloc[0]) == "399006 创业板指｜A股成长｜可找买点"


def test_index_status_code_items_describe_current_index_state():
    regime = type(
        "Regime",
        (),
        {
            "allows_new_position": True,
            "large_trend": "UP",
            "medium_trend": "TURNING_UP",
            "small_trend": "PULLBACK",
        },
    )()
    last = pd.Series({"close": 4941.6})

    items = _index_status_code_items(regime, last)

    assert [item["label"] for item in items] == ["指数状态", "大趋势", "中趋势", "小趋势", "最新收盘"]
    assert [item["value"] for item in items] == ["可找买点", "上升", "转强", "回踩", "4941.60"]


def test_index_gate_markers_show_when_index_filter_opens_and_closes():
    frame = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "close": [8.0, 12.0, 8.0],
            "ma20": [9.0, 11.5, 9.0],
            "ma51": [10.0, 11.0, 10.0],
            "ma120": [10.5, 10.0, 10.5],
            "ma250": [11.0, 9.0, 11.0],
            "ma850": [12.0, 8.0, 12.0],
            "ma51_slope_20": [-0.02, 0.03, -0.02],
            "ma120_slope_20": [-0.02, 0.03, -0.02],
            "ma250_slope_60": [-0.03, 0.05, -0.03],
            "momentum_20": [-0.05, 0.08, -0.04],
            "momentum_60": [-0.08, 0.10, -0.08],
            "drawdown_120": [-0.25, -0.02, -0.25],
        }
    )

    markers = _index_gate_markers(frame)

    assert [marker["action"] for marker in markers] == ["BUY", "SELL"]
    assert markers[0]["trade_date"] == pd.Timestamp("2024-01-03")
    assert markers[0]["marker_text"] == "BUY"
    assert markers[1]["marker_text"] == "SELL"


def test_number_index_signal_segments_labels_all_visible_pairs_and_open_buy():
    markers = [
        {"trade_date": pd.Timestamp("2024-01-02"), "action": "SELL"},
        {"trade_date": pd.Timestamp("2024-01-03"), "action": "BUY"},
        {"trade_date": pd.Timestamp("2024-01-04"), "action": "SELL"},
        {"trade_date": pd.Timestamp("2024-01-05"), "action": "BUY"},
    ]

    numbered = _number_index_signal_segments(markers)

    assert [marker["action"] for marker in numbered] == ["SELL", "BUY", "SELL", "BUY"]
    assert [marker["marker_text"] for marker in numbered] == ["SELL1", "BUY2", "SELL2", "BUY3"]
    assert numbered[0]["trade_date"] == pd.Timestamp("2024-01-02")
    assert _number_index_signal_segments([]) == []


def test_number_index_signal_segments_numbers_completed_pairs():
    markers = [
        {"trade_date": pd.Timestamp("2024-01-02"), "action": "BUY"},
        {"trade_date": pd.Timestamp("2024-01-03"), "action": "SELL"},
        {"trade_date": pd.Timestamp("2024-01-04"), "action": "BUY"},
        {"trade_date": pd.Timestamp("2024-01-05"), "action": "SELL"},
    ]

    numbered = _number_index_signal_segments(markers)

    assert [marker["marker_text"] for marker in numbered] == ["BUY1", "SELL1", "BUY2", "SELL2"]


def test_stable_index_signal_markers_ignore_one_day_whipsaws():
    states = [
        {"trade_date": pd.Timestamp("2024-01-01"), "allowed": False, "price": 100.0},
        {"trade_date": pd.Timestamp("2024-01-02"), "allowed": True, "price": 101.0},
        {"trade_date": pd.Timestamp("2024-01-03"), "allowed": False, "price": 99.0},
        {"trade_date": pd.Timestamp("2024-01-04"), "allowed": True, "price": 102.0},
        {"trade_date": pd.Timestamp("2024-01-05"), "allowed": True, "price": 103.0},
        {"trade_date": pd.Timestamp("2024-01-08"), "allowed": True, "price": 104.0},
        {"trade_date": pd.Timestamp("2024-01-09"), "allowed": False, "price": 101.0},
        {"trade_date": pd.Timestamp("2024-01-10"), "allowed": True, "price": 103.0},
        {"trade_date": pd.Timestamp("2024-01-11"), "allowed": False, "price": 100.0},
        {"trade_date": pd.Timestamp("2024-01-12"), "allowed": False, "price": 98.0},
    ]

    markers = _stable_index_signal_markers(
        states,
        entry_confirm_days=2,
        exit_confirm_days=2,
        min_hold_days=1,
        cooldown_days=0,
    )

    assert [(marker["trade_date"], marker["action"]) for marker in markers] == [
        (pd.Timestamp("2024-01-05"), "BUY"),
        (pd.Timestamp("2024-01-12"), "SELL"),
    ]
    assert markers[0]["note"] == "稳定确认：连续2个交易日允许参与"


def test_stable_index_signal_markers_are_less_dense_than_raw_switches():
    states = [
        {"trade_date": pd.Timestamp("2024-01-01"), "allowed": False, "price": 100.0},
        {"trade_date": pd.Timestamp("2024-01-02"), "allowed": True, "price": 101.0},
        {"trade_date": pd.Timestamp("2024-01-03"), "allowed": False, "price": 99.0},
        {"trade_date": pd.Timestamp("2024-01-04"), "allowed": True, "price": 102.0},
        {"trade_date": pd.Timestamp("2024-01-05"), "allowed": True, "price": 103.0},
        {"trade_date": pd.Timestamp("2024-01-08"), "allowed": False, "price": 101.0},
        {"trade_date": pd.Timestamp("2024-01-09"), "allowed": False, "price": 100.0},
    ]

    raw_switch_count = sum(
        bool(previous["allowed"]) != bool(current["allowed"])
        for previous, current in zip(states, states[1:], strict=False)
    )
    stable = _stable_index_signal_markers(
        states,
        entry_confirm_days=2,
        exit_confirm_days=2,
        min_hold_days=1,
        cooldown_days=0,
    )

    assert raw_switch_count == 4
    assert len(stable) == 2


def test_trend_hold_index_signal_markers_do_not_sell_only_because_entry_window_closes():
    states = [
        {"trade_date": pd.Timestamp("2024-01-01"), "entry_allowed": False, "hold_allowed": False, "price": 100.0},
        {"trade_date": pd.Timestamp("2024-01-02"), "entry_allowed": True, "hold_allowed": True, "price": 101.0},
        {"trade_date": pd.Timestamp("2024-01-03"), "entry_allowed": True, "hold_allowed": True, "price": 102.0},
        {"trade_date": pd.Timestamp("2024-01-04"), "entry_allowed": False, "hold_allowed": True, "price": 108.0},
        {"trade_date": pd.Timestamp("2024-01-05"), "entry_allowed": False, "hold_allowed": True, "price": 112.0},
        {"trade_date": pd.Timestamp("2024-01-08"), "entry_allowed": False, "hold_allowed": False, "price": 106.0},
        {"trade_date": pd.Timestamp("2024-01-09"), "entry_allowed": False, "hold_allowed": False, "price": 104.0},
    ]

    markers = _trend_hold_index_signal_markers(
        states,
        entry_confirm_days=2,
        exit_confirm_days=2,
        min_hold_days=1,
        cooldown_days=0,
    )

    assert [(marker["trade_date"], marker["action"]) for marker in markers] == [
        (pd.Timestamp("2024-01-03"), "BUY"),
        (pd.Timestamp("2024-01-09"), "SELL"),
    ]
    assert "持有条件连续2日失效" in markers[1]["note"]


def test_long_trend_index_signal_markers_exit_only_after_long_trend_breaks():
    states = [
        {"trade_date": pd.Timestamp("2024-01-01"), "entry_allowed": False, "long_hold_allowed": False, "price": 100.0},
        {"trade_date": pd.Timestamp("2024-01-02"), "entry_allowed": True, "long_hold_allowed": True, "price": 101.0},
        {"trade_date": pd.Timestamp("2024-01-03"), "entry_allowed": True, "long_hold_allowed": True, "price": 102.0},
        {"trade_date": pd.Timestamp("2024-01-04"), "entry_allowed": False, "long_hold_allowed": True, "price": 108.0},
        {"trade_date": pd.Timestamp("2024-01-05"), "entry_allowed": False, "long_hold_allowed": True, "price": 112.0},
        {"trade_date": pd.Timestamp("2024-01-08"), "entry_allowed": False, "long_hold_allowed": False, "price": 106.0},
        {"trade_date": pd.Timestamp("2024-01-09"), "entry_allowed": False, "long_hold_allowed": False, "price": 104.0},
    ]

    markers = _long_trend_index_signal_markers(
        states,
        entry_confirm_days=2,
        exit_confirm_days=2,
        min_hold_days=1,
        cooldown_days=0,
    )

    assert [(marker["trade_date"], marker["action"]) for marker in markers] == [
        (pd.Timestamp("2024-01-03"), "BUY"),
        (pd.Timestamp("2024-01-09"), "SELL"),
    ]
    assert "长期趋势连续2日失效" in markers[1]["note"]


def test_index_signal_markers_for_rule_uses_selected_rule_from_shared_states():
    states = [
        {"trade_date": pd.Timestamp("2024-01-01"), "entry_allowed": False, "hold_allowed": False, "long_hold_allowed": False, "price": 100.0},
        {"trade_date": pd.Timestamp("2024-01-02"), "entry_allowed": True, "hold_allowed": True, "long_hold_allowed": True, "price": 101.0},
        {"trade_date": pd.Timestamp("2024-01-03"), "entry_allowed": True, "hold_allowed": True, "long_hold_allowed": True, "price": 102.0},
        {"trade_date": pd.Timestamp("2024-01-04"), "entry_allowed": False, "hold_allowed": True, "long_hold_allowed": True, "price": 108.0},
        {"trade_date": pd.Timestamp("2024-01-05"), "entry_allowed": False, "hold_allowed": False, "long_hold_allowed": True, "price": 106.0},
        {"trade_date": pd.Timestamp("2024-01-08"), "entry_allowed": False, "hold_allowed": False, "long_hold_allowed": False, "price": 104.0},
        {"trade_date": pd.Timestamp("2024-01-09"), "entry_allowed": False, "hold_allowed": False, "long_hold_allowed": False, "price": 102.0},
    ]

    raw = _index_signal_markers_for_rule("raw", states, entry_confirm_days=2, exit_confirm_days=2, min_hold_days=1, cooldown_days=0)
    stable = _index_signal_markers_for_rule("stable", states, entry_confirm_days=2, exit_confirm_days=2, min_hold_days=1, cooldown_days=0)
    long_trend = _index_signal_markers_for_rule("long_trend", states, entry_confirm_days=2, exit_confirm_days=2, min_hold_days=1, cooldown_days=0)

    assert [(marker["trade_date"], marker["action"]) for marker in raw] == [
        (pd.Timestamp("2024-01-02"), "BUY"),
        (pd.Timestamp("2024-01-04"), "SELL"),
    ]
    assert [(marker["trade_date"], marker["action"]) for marker in stable] == [
        (pd.Timestamp("2024-01-03"), "BUY"),
        (pd.Timestamp("2024-01-05"), "SELL"),
    ]
    assert [(marker["trade_date"], marker["action"]) for marker in long_trend] == [
        (pd.Timestamp("2024-01-03"), "BUY"),
        (pd.Timestamp("2024-01-09"), "SELL"),
    ]


def test_backtest_index_signal_markers_executes_next_open_and_compares_buy_hold():
    prices = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]
            ),
            "open": [100.0, 110.0, 120.0, 90.0, 100.0],
            "high": [106.0, 116.0, 121.0, 96.0, 106.0],
            "low": [99.0, 109.0, 99.0, 89.0, 99.0],
            "close": [105.0, 115.0, 100.0, 95.0, 105.0],
        }
    )
    markers = [
        {"trade_date": pd.Timestamp("2024-01-02"), "action": "BUY"},
        {"trade_date": pd.Timestamp("2024-01-04"), "action": "SELL"},
    ]

    result = _backtest_index_signal_markers(prices, markers)
    trades = result["trades"]
    metrics = result["metrics"]

    assert trades["trade_date"].tolist() == [pd.Timestamp("2024-01-03"), pd.Timestamp("2024-01-05")]
    assert trades["action"].tolist() == ["BUY", "SELL"]
    assert trades["price"].tolist() == [110.0, 90.0]
    assert metrics["trade_count"] == 2
    assert metrics["closed_trade_count"] == 1
    assert metrics["strategy_total_return"] == pytest.approx(-0.181818, abs=0.000001)
    assert metrics["buy_hold_total_return"] == pytest.approx(0.0, abs=0.000001)
    assert metrics["excess_return"] == pytest.approx(-0.181818, abs=0.000001)
    assert metrics["avg_trade_return"] == pytest.approx(-0.181818, abs=0.000001)


def test_index_signal_problem_diagnostics_explain_weak_strategy_in_chinese():
    metrics = {
        "strategy_total_return": -0.18,
        "buy_hold_total_return": 0.20,
        "excess_return": -0.38,
        "strategy_max_drawdown": -0.24,
        "buy_hold_max_drawdown": -0.20,
        "drawdown_improvement": -0.04,
        "trade_count": 36,
        "trades_per_year": 36,
        "win_rate": 0.28,
        "avg_trade_return": -0.02,
        "avg_holding_days": 3,
    }

    diagnostics = _index_signal_problem_diagnostics(metrics)

    assert any("跑输买入持有" in item for item in diagnostics)
    assert any("交易过密" in item for item in diagnostics)
    assert any("买卖点质量偏弱" in item for item in diagnostics)
    assert any("持有期过短" in item for item in diagnostics)
    assert any("回撤没有改善" in item for item in diagnostics)


def test_index_signal_diagnostic_display_frame_formats_metrics_for_page():
    display = _index_signal_diagnostic_display_frame(
        {
            "strategy_total_return": -0.181818,
            "buy_hold_total_return": 0.0,
            "excess_return": -0.181818,
            "strategy_max_drawdown": -0.24,
            "trade_count": 2,
            "trades_per_year": 18.4,
            "win_rate": 0.0,
            "avg_trade_return": -0.181818,
            "avg_holding_days": 2.0,
            "avg_exposure": 0.4,
        }
    )

    assert list(display.columns) == ["指标", "数值"]
    assert display.iloc[0].to_dict() == {"指标": "策略收益", "数值": "-18.18%"}
    assert {"指标": "买入持有收益", "数值": "0.00%"} in display.to_dict("records")
    assert {"指标": "年化交易次数", "数值": "18.4"} in display.to_dict("records")
