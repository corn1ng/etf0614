from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest

from etf_trading.research.index_backtest import run_buy_hold
from etf_trading.research.index_metrics import summarize_index_result
from etf_trading.research.index_models import IndexAdmissionResult, IndexBacktestCosts, IndexResearchConfig
from etf_trading.research.index_validation import (
    IndexResearchCancelled,
    build_rolling_windows,
    evaluate_effectiveness,
    run_index_research,
    summarize_rolling_gates,
)


def test_every_admitted_index_gets_full_history_v1_and_buy_hold_rows():
    output = run_index_research(two_index_admission(), make_config())

    full = output.results[output.results["period_type"] == "full_history"]
    assert set(full["index_code"]) == {"000300", "000905"}
    assert set(full["strategy_name"]) == {"index_trend_v1", "buy_hold"}
    assert set(full["cohort"]) == {"official", "reference"}


def test_five_year_windows_use_calendar_boundaries_and_exclude_incomplete_tail():
    windows = build_rolling_windows(long_frame("2005-01-01", "2020-06-30"), years=5, step_years=1)

    assert [(window.start.year, window.end.year) for window in windows] == [
        (2005, 2009),
        (2006, 2010),
        (2007, 2011),
        (2008, 2012),
        (2009, 2013),
        (2010, 2014),
        (2011, 2015),
        (2012, 2016),
        (2013, 2017),
        (2014, 2018),
        (2015, 2019),
    ]
    assert all(window.end.month == 12 and window.end.day == 31 for window in windows)


def test_rolling_windows_require_january_and_december_coverage_for_every_year():
    half_first_year = long_frame("2005-06-01", "2010-12-30")
    assert [(window.start.year, window.end.year) for window in build_rolling_windows(half_first_year)] == [(2006, 2010)]

    missing_2007 = long_frame("2005-01-03", "2009-12-30")
    missing_2007 = missing_2007[missing_2007["trade_date"].dt.year != 2007]
    assert build_rolling_windows(missing_2007) == []


def test_rolling_gate_summary_counts_passing_official_windows():
    rolling = pd.concat(
        [
            paired_results().assign(period_type="rolling_5y", period_label="2005-2009"),
            paired_results().assign(period_type="rolling_5y", period_label="2006-2010"),
        ],
        ignore_index=True,
    )

    summary = summarize_rolling_gates(rolling, make_config())

    assert summary.iloc[0][["eligible_windows", "passing_windows"]].tolist() == [2, 2]
    assert summary.iloc[0]["pass_rate"] == 1.0


def test_prospective_rows_are_strictly_post_lock_but_have_pre_lock_warmup():
    config = make_config()
    frame = long_frame("2026-03-01", "2026-08-07")
    frame.loc[:, "close"] = np.linspace(100.0, 130.0, len(frame))
    frame.loc[:, "open"] = frame["close"] - 0.25
    admission = admission_for({"000300": frame}, cohorts={"000300": "official"})

    output = run_index_research(admission, config)

    prospective = output.nav[output.nav["period_type"] == "prospective_oos"]
    assert not prospective.empty
    assert (pd.to_datetime(prospective["trade_date"]).dt.date > config.locked_at).all()
    assert prospective["trade_date"].min() == pd.Timestamp("2026-07-31")
    assert output.prospective_status.set_index("index_code").loc["000300", "status"] == "available"


def test_official_only_effectiveness_ignores_failing_reference_cohort():
    results = paired_results(cohort="official")
    reference = paired_results(cohort="reference", v1_drawdown=-0.80, buy_hold_drawdown=-0.20)
    assessment = evaluate_effectiveness(
        pd.concat([results, reference], ignore_index=True),
        buffer_rows(),
        paired_results(cohort="official"),
        make_config(),
    )

    assert assessment.status == "passed"
    assert all(assessment.gates.values())
    assert assessment.values["official_index_count"] == 2


def test_effectiveness_requires_both_lower_whipsaw_rate_and_trades():
    assessment = evaluate_effectiveness(
        paired_results(cohort="official"),
        buffer_rows(rate_0=0.10, rate_2=0.10, trades_0=4.0, trades_2=3.0),
        paired_results(cohort="official"),
        make_config(),
    )

    assert assessment.status == "failed"
    assert assessment.gates["buffer_reduces_whipsaw_rate_and_trades"] is False


@pytest.mark.parametrize(
    "variant, expected_reason",
    [
        ("nan", "non_finite_buffer_metric"),
        ("unpaired", "unpaired_buffer_index:000905"),
        ("duplicate", "duplicate_buffer_index:000300:0"),
    ],
)
def test_buffer_gate_rejects_invalid_or_unpaired_official_evidence(variant, expected_reason):
    buffer = buffer_rows()
    if variant == "nan":
        buffer = buffer.assign(whipsaw_trade_rate=np.nan)
    elif variant == "unpaired":
        buffer = buffer.query("index_code != '000905' | buffer_rate != 0.02")
    else:
        buffer = pd.concat([buffer, buffer.iloc[[0]]], ignore_index=True)
    assessment = evaluate_effectiveness(paired_results(), buffer, paired_results(), make_config())

    assert assessment.gates["buffer_reduces_whipsaw_rate_and_trades"] is False
    assert any(expected_reason in reason for reason in assessment.reasons)


@pytest.mark.parametrize(
    "mutator, reason",
    [
        (lambda rows: rows.assign(cohort="reference"), "no_official_full_history_pairs"),
        (lambda rows: rows.assign(max_drawdown=np.nan), "non_finite_metric:max_drawdown"),
        (
            lambda rows: rows.assign(
                max_drawdown=lambda value: np.where(value["strategy_name"] == "buy_hold", 0.0, -0.1)
            ),
            "zero_buy_hold_drawdown",
        ),
    ],
)
def test_effectiveness_fails_safely_for_invalid_or_unusable_gate_inputs(mutator, reason):
    assessment = evaluate_effectiveness(mutator(paired_results(cohort="official")), buffer_rows(), paired_results(), make_config())

    assert assessment.status == "failed"
    assert not all(assessment.gates.values())
    assert reason in assessment.reasons


def test_stress_gate_recomputes_first_four_gates_under_stress_costs():
    stress = paired_results(cohort="official", v1_return=0.01, buy_hold_return=0.10)
    assessment = evaluate_effectiveness(paired_results(), buffer_rows(), stress, make_config())

    assert assessment.gates["stress_keeps_first_four_gates"] is False
    assert assessment.status == "failed"


def test_each_failed_gate_has_an_auditable_reason_with_its_name():
    failed = paired_results(v1_drawdown=-0.60, v1_return=0.01).assign(
        calmar=lambda rows: np.where(rows["strategy_name"] == "index_trend_v1", 0.5, 0.8)
    )
    assessment = evaluate_effectiveness(
        failed,
        buffer_rows(rate_0=0.10, rate_2=0.10),
        failed,
        make_config(),
    )

    assert not any(assessment.gates.values())
    for name, passed in assessment.gates.items():
        assert passed or any(reason.startswith(f"{name}:") for reason in assessment.reasons)


def test_output_is_deterministic_and_reports_progress_at_index_boundaries():
    admission = two_index_admission()
    events: list[tuple[int, int, str, str]] = []
    first = run_index_research(admission, make_config(), progress=lambda *event: events.append(event))
    second = run_index_research(reverse_admission(admission), make_config())

    pd.testing.assert_frame_equal(first.results, second.results)
    assert events == [(1, 2, "000300", "completed"), (2, 2, "000905", "completed")]
    assert list(first.results[["index_code", "period_type", "strategy_name"]].itertuples(index=False, name=None)) == sorted(
        first.results[["index_code", "period_type", "strategy_name"]].itertuples(index=False, name=None)
    )


def test_cancellation_is_checked_at_index_boundary_and_never_returns_partial_output():
    calls = 0

    def should_stop() -> bool:
        nonlocal calls
        calls += 1
        return calls == 2

    with pytest.raises(IndexResearchCancelled):
        run_index_research(two_index_admission(), make_config(), should_stop=should_stop)


def test_cancellation_after_the_last_index_is_not_published_as_a_completed_output():
    stop = False

    def progress(*_event):
        nonlocal stop
        stop = True

    with pytest.raises(IndexResearchCancelled):
        run_index_research(
            admission_for({"000300": long_frame("2005-01-01", "2011-12-31")}, cohorts={"000300": "official"}),
            make_config(),
            progress=progress,
            should_stop=lambda: stop,
        )


def test_run_output_contains_group_statistics_worst_ten_and_rolling_gate_rate():
    output = run_index_research(two_index_admission(), make_config())

    assert {"cohort", "market", "index_type"}.issubset(set(output.group_statistics["group_type"]))
    assert {"mean", "median", "q25", "q75"}.issubset(output.group_statistics.columns)
    assert len(output.worst_indices) <= 10
    assert {"eligible_windows", "passing_windows", "pass_rate"}.issubset(output.rolling_gate_summary.columns)


def test_buy_hold_summary_includes_initial_execution_cost_in_returns():
    frame = pd.DataFrame(
        {
            "trade_date": pd.date_range("2024-01-02", periods=3, freq="B"),
            "open": [100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 101.0],
            "low": [99.0, 99.0, 99.0],
            "close": [100.0, 100.0, 100.0],
        }
    )
    result = run_buy_hold("000300", frame, IndexBacktestCosts(commission_rate=0.001, slippage_rate=0.001))

    summary = summarize_index_result(result)

    assert summary["total_return"] < 0
    assert summary["annualized_return"] < 0


def make_config() -> IndexResearchConfig:
    return IndexResearchConfig(
        strategy_version="index_trend_v1",
        locked_at=date(2026, 7, 30),
        ma_window=60,
        slope_lookback=20,
        buffer_rate=0.02,
        atr_window=20,
        atr_multiple=3.0,
        buffer_ablation=(0.0, 0.02, 0.03),
        commission_rate=0.00015,
        slippage_rate=0.0002,
        stress_multiplier=2.0,
        min_valid_rows=1000,
        rolling_years=5,
        rolling_step_years=1,
        whipsaw_max_holding_days=20,
        stage_years=(2015, 2018, 2020, 2022),
        min_drawdown_win_rate=0.60,
        min_median_drawdown_reduction=0.20,
        max_median_annual_return_lag=0.02,
    )


def long_frame(start: str, end: str) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="B")
    close = np.linspace(100.0, 140.0, len(dates))
    frame = pd.DataFrame({"trade_date": dates, "open": close - 0.25, "high": close + 1.0, "low": close - 1.0, "close": close})
    frame["ma60"] = frame["close"].rolling(60, min_periods=60).mean()
    frame["ma60_slope_20"] = frame["ma60"] / frame["ma60"].shift(20) - 1.0
    frame["atr20"] = 2.0
    return frame


def two_index_admission() -> IndexAdmissionResult:
    return admission_for(
        {"000905": long_frame("2005-01-01", "2011-12-31"), "000300": long_frame("2005-01-01", "2011-12-31")},
        cohorts={"000300": "official", "000905": "reference"},
    )


def admission_for(frames: dict[str, pd.DataFrame], *, cohorts: dict[str, str]) -> IndexAdmissionResult:
    metadata = pd.DataFrame(
        [
            {"index_code": code, "name": code, "cohort": cohorts[code], "market": "CN", "index_type": "broad"}
            for code in frames
        ]
    )
    return IndexAdmissionResult(frames=frames, metadata=metadata, exclusions=pd.DataFrame())


def reverse_admission(admission: IndexAdmissionResult) -> IndexAdmissionResult:
    return replace(
        admission,
        frames=dict(reversed(list(admission.frames.items()))),
        metadata=admission.metadata.iloc[::-1].reset_index(drop=True),
    )


def paired_results(
    *,
    cohort: str = "official",
    v1_drawdown: float = -0.20,
    buy_hold_drawdown: float = -0.50,
    v1_return: float = 0.10,
    buy_hold_return: float = 0.10,
) -> pd.DataFrame:
    rows = []
    for code in ("000300", "000905"):
        rows.extend(
            [
                {"index_code": code, "cohort": cohort, "period_type": "full_history", "strategy_name": "index_trend_v1", "max_drawdown": v1_drawdown, "calmar": 1.2, "annualized_return": v1_return, "market": "CN", "index_type": "broad"},
                {"index_code": code, "cohort": cohort, "period_type": "full_history", "strategy_name": "buy_hold", "max_drawdown": buy_hold_drawdown, "calmar": 0.8, "annualized_return": buy_hold_return, "market": "CN", "index_type": "broad"},
            ]
        )
    return pd.DataFrame(rows)


def buffer_rows(*, rate_0: float = 0.10, rate_2: float = 0.05, trades_0: float = 4.0, trades_2: float = 3.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"index_code": "000300", "cohort": "official", "buffer_rate": 0.0, "whipsaw_trade_rate": rate_0, "annualized_trade_count": trades_0},
            {"index_code": "000300", "cohort": "official", "buffer_rate": 0.02, "whipsaw_trade_rate": rate_2, "annualized_trade_count": trades_2},
            {"index_code": "000905", "cohort": "official", "buffer_rate": 0.0, "whipsaw_trade_rate": rate_0, "annualized_trade_count": trades_0},
            {"index_code": "000905", "cohort": "official", "buffer_rate": 0.02, "whipsaw_trade_rate": rate_2, "annualized_trade_count": trades_2},
        ]
    )
