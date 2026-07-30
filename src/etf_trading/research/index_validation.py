"""Deterministic historical validation for the locked index-trend V1 rule."""

from __future__ import annotations

import math
from dataclasses import asdict
from datetime import date
from typing import Callable, NamedTuple

import pandas as pd

from etf_trading.research.index_backtest import run_buy_hold, run_index_backtest
from etf_trading.research.index_metrics import summarize_index_result
from etf_trading.research.index_models import (
    EffectivenessAssessment,
    IndexAdmissionResult,
    IndexBacktestCosts,
    IndexBacktestResult,
    IndexResearchConfig,
    IndexResearchOutput,
)
from etf_trading.research.index_trend_v1 import IndexTrendV1


class IndexResearchCancelled(RuntimeError):
    """Raised before an index starts when a caller cancels the research run."""


class RollingWindow(NamedTuple):
    """An inclusive calendar-year evaluation window."""

    start: pd.Timestamp
    end: pd.Timestamp


_RESULT_COLUMNS = [
    "index_code", "name", "cohort", "market", "index_type", "period_type", "period_label",
    "period_start", "period_end", "strategy_name",
]


def build_rolling_windows(frame: pd.DataFrame, *, years: int = 5, step_years: int = 1) -> list[RollingWindow]:
    """Return only complete, inclusive calendar-year rolling windows.

    The input's earliest date establishes the first calendar year.  A partial final
    calendar year is deliberately never represented as a complete window.
    """

    if years <= 0 or step_years <= 0 or frame.empty:
        return []
    dates = pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
    if dates.empty:
        return []
    first_year = int(dates.min().year)
    last = pd.Timestamp(dates.max()).normalize()
    last_complete_year = last.year if last == pd.Timestamp(last.year, 12, 31) else last.year - 1
    windows: list[RollingWindow] = []
    for start_year in range(first_year, last_complete_year - years + 2, step_years):
        end_year = start_year + years - 1
        windows.append(RollingWindow(pd.Timestamp(start_year, 1, 1), pd.Timestamp(end_year, 12, 31)))
    return windows


def run_index_research(
    admission: IndexAdmissionResult,
    config: IndexResearchConfig,
    progress: Callable[[int, int, str, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> IndexResearchOutput:
    """Execute the fixed V1 matrix once for every admitted index.

    Backtests always begin flat at the requested evaluation date.  The immediately
    preceding observation is retained solely to evaluate a fresh crossover on the
    first date; indicators themselves already contain their historical warm-up.
    """

    results: list[dict[str, object]] = []
    nav_rows: list[pd.DataFrame] = []
    trade_rows: list[pd.DataFrame] = []
    yearly_rows: list[dict[str, object]] = []
    rolling_rows: list[dict[str, object]] = []
    buffer_rows: list[dict[str, object]] = []
    stress_rows: list[dict[str, object]] = []
    prospective_rows: list[dict[str, object]] = []

    metadata = _metadata_by_code(admission.metadata)
    codes = sorted(admission.frames)
    total = len(codes)
    default_costs = IndexBacktestCosts.from_config(config)
    stress_costs = IndexBacktestCosts.from_config(config, stress=True)
    for done, code in enumerate(codes, start=1):
        if should_stop is not None and should_stop():
            raise IndexResearchCancelled("index research cancelled before publishing a partial output")
        frame = _prepared_frame(admission.frames[code])
        context = _context(code, metadata)
        start = _first_evaluable_date(frame)
        if start is not None:
            end = pd.Timestamp(frame["trade_date"].iloc[-1]).normalize()
            full = _run_pair(code, frame, start, end, config, default_costs)
            results.extend(_result_records(context, "full_history", "full_history", start, end, full, config))
            nav_rows.extend(_nav_records(context, "full_history", "full_history", full))
            trade_rows.extend(_trade_records(context, "full_history", "full_history", full))

            for year in sorted(frame.loc[frame["trade_date"] >= start, "trade_date"].dt.year.unique()):
                year_start = max(start, pd.Timestamp(int(year), 1, 1))
                year_end = min(end, pd.Timestamp(int(year), 12, 31))
                annual = _run_pair(code, frame, year_start, year_end, config, default_costs)
                label = str(int(year))
                records = _result_records(context, "calendar_year", label, year_start, year_end, annual, config)
                results.extend(records)
                yearly_rows.extend(records)
                nav_rows.extend(_nav_records(context, "calendar_year", label, annual))
                trade_rows.extend(_trade_records(context, "calendar_year", label, annual))

            for year in config.stage_years:
                stage_start = max(start, pd.Timestamp(year, 1, 1))
                stage_end = min(end, pd.Timestamp(year, 12, 31))
                if stage_start <= stage_end:
                    stage = _run_pair(code, frame, stage_start, stage_end, config, default_costs)
                    label = f"stage_{year}"
                    results.extend(_result_records(context, "stage", label, stage_start, stage_end, stage, config))
                    nav_rows.extend(_nav_records(context, "stage", label, stage))
                    trade_rows.extend(_trade_records(context, "stage", label, stage))

            for window in build_rolling_windows(frame.loc[frame["trade_date"] >= start], years=config.rolling_years, step_years=config.rolling_step_years):
                rolling = _run_pair(code, frame, window.start, window.end, config, default_costs)
                label = f"{window.start.year}-{window.end.year}"
                records = _result_records(context, "rolling_5y", label, window.start, window.end, rolling, config)
                results.extend(records)
                rolling_rows.extend(records)
                nav_rows.extend(_nav_records(context, "rolling_5y", label, rolling))
                trade_rows.extend(_trade_records(context, "rolling_5y", label, rolling))

            for buffer_rate in config.buffer_ablation:
                result = _run_strategy(code, frame, start, end, IndexTrendV1(buffer_rate, config.atr_multiple), default_costs)
                row = {**context, "buffer_rate": buffer_rate, "period_type": "full_history"}
                row.update(summarize_index_result(result, config.whipsaw_max_holding_days))
                buffer_rows.append(row)

            stress = _run_pair(code, frame, start, end, config, stress_costs)
            stress_rows.extend(_result_records(context, "full_history", "stress_double_cost", start, end, stress, config))

            post_lock = frame[frame["trade_date"].dt.date > config.locked_at]
            if post_lock.empty:
                prospective_rows.append({**context, "status": "no_prospective_sample", "reason": "no_data_strictly_after_locked_at"})
            else:
                prospective_start = pd.Timestamp(post_lock["trade_date"].iloc[0]).normalize()
                prospective = _run_pair(code, frame, prospective_start, end, config, default_costs)
                results.extend(_result_records(context, "prospective_oos", "prospective_oos", prospective_start, end, prospective, config))
                nav_rows.extend(_nav_records(context, "prospective_oos", "prospective_oos", prospective))
                trade_rows.extend(_trade_records(context, "prospective_oos", "prospective_oos", prospective))
                prospective_rows.append({**context, "status": "available", "reason": None})
        else:
            prospective_rows.append({**context, "status": "no_evaluable_history", "reason": "no_complete_indicator_row"})
        if progress is not None:
            progress(done, total, code, "completed")

    result_frame = _stable_frame(results, _RESULT_COLUMNS)
    buffer_frame = _stable_frame(buffer_rows, ["index_code", "cohort", "buffer_rate"])
    stress_frame = _stable_frame(stress_rows, _RESULT_COLUMNS)
    assessment = evaluate_effectiveness(result_frame, buffer_frame, stress_frame, config)
    rolling_frame = _stable_frame(rolling_rows, _RESULT_COLUMNS)
    return IndexResearchOutput(
        results=result_frame,
        nav=_concat_frames(nav_rows, ["index_code", "period_type", "period_label", "strategy_name", "trade_date", "nav", "weight"]),
        trades=_concat_frames(trade_rows, ["index_code", "period_type", "period_label", "strategy_name"]),
        yearly=_stable_frame(yearly_rows, _RESULT_COLUMNS),
        rolling=rolling_frame,
        buffer_comparison=buffer_frame,
        stress_results=stress_frame,
        prospective_status=_stable_frame(prospective_rows, ["index_code", "cohort", "status", "reason"]),
        group_statistics=_group_statistics(result_frame),
        worst_indices=_worst_indices(result_frame),
        rolling_gate_summary=_rolling_gate_summary(rolling_frame, config),
        effectiveness=assessment,
    )


def evaluate_effectiveness(
    results: pd.DataFrame,
    buffer_comparison: pd.DataFrame,
    stress_results: pd.DataFrame,
    config: IndexResearchConfig,
) -> EffectivenessAssessment:
    """Evaluate the six pre-committed gates, failing closed on unusable evidence."""

    reasons: list[str] = []
    official = _paired_full_history(results, reasons)
    first_four, values = _first_four_gates(official, config, reasons)
    gates = {
        "drawdown_win_rate": first_four["drawdown_win_rate"],
        "median_drawdown_reduction": first_four["median_drawdown_reduction"],
        "median_calmar_improves": first_four["median_calmar_improves"],
        "median_return_is_retained": first_four["median_return_is_retained"],
        "buffer_reduces_whipsaw_rate_and_trades": _buffer_gate(buffer_comparison, config, reasons, values),
        "stress_keeps_first_four_gates": _stress_gate(stress_results, config, reasons, values),
    }
    values["official_index_count"] = int(len(official))
    return EffectivenessAssessment(
        status="passed" if all(gates.values()) else "failed",
        gates=gates,
        values=values,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def _prepared_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="coerce").dt.normalize()
    return result.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)


def _first_evaluable_date(frame: pd.DataFrame) -> pd.Timestamp | None:
    needed = ["close", "ma60", "ma60_slope_20", "atr20"]
    if any(column not in frame for column in needed):
        return None
    complete = frame[needed].apply(pd.to_numeric, errors="coerce").apply(lambda col: col.map(_finite)).all(axis=1)
    if not complete.any():
        return None
    return pd.Timestamp(frame.loc[complete, "trade_date"].iloc[0]).normalize()


def _run_pair(code: str, frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, config: IndexResearchConfig, costs: IndexBacktestCosts) -> dict[str, IndexBacktestResult]:
    evaluation = _evaluation_frame(frame, start, end)
    return {
        "index_trend_v1": _run_strategy(code, frame, start, end, IndexTrendV1(config.buffer_rate, config.atr_multiple), costs),
        "buy_hold": run_buy_hold(code, evaluation, costs),
    }


def _run_strategy(code: str, frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, strategy: IndexTrendV1, costs: IndexBacktestCosts) -> IndexBacktestResult:
    result = run_index_backtest(code, _period_frame(frame, start, end), strategy, costs)
    nav = result.nav[result.nav["trade_date"] >= start].reset_index(drop=True)
    return IndexBacktestResult(trades=result.trades, nav=nav, cancelled_signals=result.cancelled_signals)


def _period_frame(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    eligible = _evaluation_frame(frame, start, end)
    preceding = frame[frame["trade_date"] < start].tail(1)
    return pd.concat([preceding, eligible], ignore_index=True)


def _evaluation_frame(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return frame[(frame["trade_date"] >= start) & (frame["trade_date"] <= end)].reset_index(drop=True)


def _result_records(context: dict[str, object], period_type: str, label: str, start: pd.Timestamp, end: pd.Timestamp, pair: dict[str, IndexBacktestResult], config: IndexResearchConfig) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for strategy_name, result in pair.items():
        row = {
            **context, "period_type": period_type, "period_label": label,
            "period_start": start, "period_end": end, "strategy_name": strategy_name,
        }
        row.update(summarize_index_result(result, config.whipsaw_max_holding_days))
        rows.append(row)
    return rows


def _nav_records(context: dict[str, object], period_type: str, label: str, pair: dict[str, IndexBacktestResult]) -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for strategy_name, result in pair.items():
        if not result.nav.empty:
            nav = result.nav.copy()
            nav.insert(0, "strategy_name", strategy_name)
            nav.insert(0, "period_label", label)
            nav.insert(0, "period_type", period_type)
            nav.insert(0, "index_code", context["index_code"])
            frames.append(nav)
    return frames


def _trade_records(context: dict[str, object], period_type: str, label: str, pair: dict[str, IndexBacktestResult]) -> list[pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for strategy_name, result in pair.items():
        if result.trades:
            trades = pd.DataFrame([asdict(trade) for trade in result.trades])
            trades.insert(0, "strategy_name", strategy_name)
            trades.insert(0, "period_label", label)
            trades.insert(0, "period_type", period_type)
            frames.append(trades)
    return frames


def _metadata_by_code(metadata: pd.DataFrame) -> dict[str, dict[str, object]]:
    if metadata.empty or "index_code" not in metadata:
        return {}
    return {str(row["index_code"]): row.to_dict() for _, row in metadata.sort_values("index_code").iterrows()}


def _context(code: str, metadata: dict[str, dict[str, object]]) -> dict[str, object]:
    row = metadata.get(code, {})
    return {
        "index_code": code,
        "name": row.get("name", code),
        "cohort": row.get("cohort", "unknown"),
        "market": row.get("market", "unknown"),
        "index_type": row.get("index_type", "unknown"),
    }


def _concat_frames(frames: list[pd.DataFrame], columns: list[str]) -> pd.DataFrame:
    if not frames:
        return pd.DataFrame(columns=columns)
    return _stable_frame(pd.concat(frames, ignore_index=True).to_dict("records"), columns)


def _stable_frame(rows: list[dict[str, object]], leading_columns: list[str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=leading_columns)
    frame = pd.DataFrame(rows)
    ordered = [column for column in leading_columns if column in frame] + sorted(column for column in frame if column not in leading_columns)
    sort_columns = [column for column in ("index_code", "period_type", "strategy_name", "period_label", "trade_date", "buffer_rate") if column in frame]
    return frame.loc[:, ordered].sort_values(sort_columns, kind="stable").reset_index(drop=True) if sort_columns else frame.loc[:, ordered]


def _paired_full_history(results: pd.DataFrame, reasons: list[str]) -> pd.DataFrame:
    required = {"index_code", "cohort", "period_type", "strategy_name", "max_drawdown", "calmar", "annualized_return"}
    if results.empty or not required.issubset(results.columns):
        reasons.append("no_official_full_history_pairs")
        return pd.DataFrame()
    rows = results[(results["cohort"] == "official") & (results["period_type"] == "full_history")]
    rows = rows[rows["strategy_name"].isin(["index_trend_v1", "buy_hold"])]
    if rows.empty:
        reasons.append("no_official_full_history_pairs")
        return pd.DataFrame()
    # ``pivot_table`` silently drops an all-NaN metric column.  A direct pivot
    # preserves it so the gate can record a non-finite audit failure instead.
    try:
        pivot = rows.pivot(index="index_code", columns="strategy_name", values=["max_drawdown", "calmar", "annualized_return"])
    except ValueError:
        reasons.append("duplicate_official_full_history_pair")
        return pd.DataFrame()
    needed = [(metric, strategy) for metric in ("max_drawdown", "calmar", "annualized_return") for strategy in ("index_trend_v1", "buy_hold")]
    if any(column not in pivot for column in needed):
        reasons.append("no_official_full_history_pairs")
        return pd.DataFrame()
    return pivot.loc[:, needed]


def _first_four_gates(pairs: pd.DataFrame, config: IndexResearchConfig, reasons: list[str]) -> tuple[dict[str, bool], dict[str, object]]:
    names = ("drawdown_win_rate", "median_drawdown_reduction", "median_calmar_improves", "median_return_is_retained")
    failed = {name: False for name in names}
    if pairs.empty:
        return failed, {}
    values = pairs.to_numpy(dtype=float)
    if not all(math.isfinite(value) for value in values.flat):
        for metric in ("max_drawdown", "calmar", "annualized_return"):
            if not all(math.isfinite(float(value)) for value in pairs[metric].to_numpy().flat):
                reasons.append(f"non_finite_metric:{metric}")
                break
        return failed, {}
    v1_mdd = pairs[("max_drawdown", "index_trend_v1")]
    buy_mdd = pairs[("max_drawdown", "buy_hold")]
    denominator = float(buy_mdd.abs().median())
    if denominator == 0:
        reasons.append("zero_buy_hold_drawdown")
        return failed, {}
    drawdown_win_rate = float((v1_mdd > buy_mdd).mean())
    reduction = 1.0 - float(v1_mdd.abs().median()) / denominator
    v1_calmar = float(pairs[("calmar", "index_trend_v1")].median())
    buy_calmar = float(pairs[("calmar", "buy_hold")].median())
    v1_return = float(pairs[("annualized_return", "index_trend_v1")].median())
    buy_return = float(pairs[("annualized_return", "buy_hold")].median())
    values_out: dict[str, object] = {
        "drawdown_win_rate": drawdown_win_rate,
        "median_drawdown_reduction": reduction,
        "median_calmar_v1": v1_calmar,
        "median_calmar_buy_hold": buy_calmar,
        "median_annual_return_v1": v1_return,
        "median_annual_return_buy_hold": buy_return,
    }
    return {
        "drawdown_win_rate": drawdown_win_rate >= config.min_drawdown_win_rate,
        "median_drawdown_reduction": reduction >= config.min_median_drawdown_reduction,
        "median_calmar_improves": v1_calmar > buy_calmar,
        "median_return_is_retained": v1_return >= buy_return - config.max_median_annual_return_lag,
    }, values_out


def _buffer_gate(buffer: pd.DataFrame, config: IndexResearchConfig, reasons: list[str], values: dict[str, object]) -> bool:
    needed = {"cohort", "buffer_rate", "whipsaw_trade_rate", "annualized_trade_count"}
    if buffer.empty or not needed.issubset(buffer.columns):
        reasons.append("missing_buffer_comparison")
        return False
    official = buffer[buffer["cohort"] == "official"]
    rates: dict[float, tuple[float, float]] = {}
    for rate in (0.0, config.buffer_rate):
        group = official[official["buffer_rate"] == rate]
        if group.empty:
            reasons.append(f"missing_buffer_rate:{rate:g}")
            return False
        rate_value = float(pd.to_numeric(group["whipsaw_trade_rate"], errors="coerce").mean())
        trade_value = float(pd.to_numeric(group["annualized_trade_count"], errors="coerce").mean())
        if not (math.isfinite(rate_value) and math.isfinite(trade_value)):
            reasons.append("non_finite_buffer_metric")
            return False
        rates[rate] = (rate_value, trade_value)
    values.update({"whipsaw_rate_0": rates[0.0][0], "whipsaw_rate_2": rates[config.buffer_rate][0], "trades_per_year_0": rates[0.0][1], "trades_per_year_2": rates[config.buffer_rate][1]})
    return rates[config.buffer_rate][0] < rates[0.0][0] and rates[config.buffer_rate][1] < rates[0.0][1]


def _stress_gate(stress: pd.DataFrame, config: IndexResearchConfig, reasons: list[str], values: dict[str, object]) -> bool:
    pairs = _paired_full_history(stress, reasons)
    gates, stress_values = _first_four_gates(pairs, config, reasons)
    values["stress_first_four_gates"] = gates
    values.update({f"stress_{key}": value for key, value in stress_values.items()})
    return all(gates.values())


def _group_statistics(results: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    metric_columns = [column for column in ("annualized_return", "max_drawdown", "calmar") if column in results]
    full = results[(results.get("period_type") == "full_history") & (results.get("strategy_name") == "index_trend_v1")] if not results.empty else results
    for group_type in ("cohort", "market", "index_type"):
        if group_type not in full:
            continue
        for group_value, values in full.groupby(group_type, sort=True):
            for metric in metric_columns:
                numeric = pd.to_numeric(values[metric], errors="coerce").dropna()
                if not numeric.empty:
                    rows.append({"group_type": group_type, "group_value": group_value, "metric": metric, "mean": float(numeric.mean()), "median": float(numeric.median()), "q25": float(numeric.quantile(.25)), "q75": float(numeric.quantile(.75)), "count": int(len(numeric))})
    return _stable_frame(rows, ["group_type", "group_value", "metric", "mean", "median", "q25", "q75", "count"])


def _worst_indices(results: pd.DataFrame) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame(columns=["index_code", "cohort", "max_drawdown"])
    subset = results[(results["period_type"] == "full_history") & (results["strategy_name"] == "index_trend_v1")].copy()
    if subset.empty:
        return subset
    return subset.sort_values(["max_drawdown", "index_code"], ascending=[True, True], kind="stable").head(10).reset_index(drop=True)


def _rolling_gate_summary(rolling: pd.DataFrame, config: IndexResearchConfig) -> pd.DataFrame:
    if rolling.empty:
        return pd.DataFrame(columns=["eligible_windows", "passing_windows", "pass_rate"])
    rows: list[dict[str, object]] = []
    for label, window in rolling[rolling["cohort"] == "official"].groupby("period_label", sort=True):
        gates, _ = _first_four_gates(_paired_full_history(window, []), config, [])
        passed = all(gates.values())
        rows.append({"period_label": label, "eligible_windows": 1, "passing_windows": int(passed), "pass_rate": float(passed), **gates})
    if not rows:
        return pd.DataFrame(columns=["eligible_windows", "passing_windows", "pass_rate"])
    summary = pd.DataFrame(rows)
    return pd.DataFrame([{"eligible_windows": int(summary["eligible_windows"].sum()), "passing_windows": int(summary["passing_windows"].sum()), "pass_rate": float(summary["passing_windows"].mean())}])


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False
