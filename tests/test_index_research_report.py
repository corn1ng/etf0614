from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from etf_trading.research.index_models import EffectivenessAssessment, IndexAdmissionResult, IndexResearchOutput
from etf_trading.research.index_report import (
    REQUIRED_ARTIFACTS,
    load_latest_index_research,
    publish_index_research,
    render_index_research_markdown,
    run_and_publish_index_research,
)


def test_publish_creates_all_versioned_artifacts_and_reloads_latest(tmp_path: Path):
    published = publish_index_research(sample_output(), tmp_path, sample_run_meta("first"))

    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest == {"run_id": published.run_id}
    run_dir = tmp_path / "runs" / published.run_id
    assert {path.name for path in run_dir.iterdir()} == set(REQUIRED_ARTIFACTS)
    loaded = load_latest_index_research(tmp_path)
    assert loaded.run_id == published.run_id
    assert loaded.results.to_dict("records") == sample_output().results.to_dict("records")
    pd.testing.assert_frame_equal(loaded.nav, sample_output().nav)
    assert loaded.run_meta["run_id"] == published.run_id


def test_publish_failure_at_each_artifact_keeps_previous_pointer_and_no_final_directory(tmp_path: Path, monkeypatch):
    first = publish_index_research(sample_output(), tmp_path, sample_run_meta("first"))

    def raise_disk_error(*_args, **_kwargs):
        raise OSError("injected write failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", raise_disk_error)
    with pytest.raises(OSError, match="injected write failure"):
        publish_index_research(sample_output(), tmp_path, sample_run_meta("second"))

    assert load_latest_index_research(tmp_path).run_id == first.run_id
    assert not (tmp_path / "runs" / "second").exists()


@pytest.mark.parametrize("run_id", ["../escape", "", ".", "a/b", "with space"])
def test_publish_rejects_unsafe_run_ids(tmp_path: Path, run_id: str):
    with pytest.raises(ValueError, match="run_id"):
        publish_index_research(sample_output(), tmp_path, sample_run_meta(run_id))


def test_publish_rejects_duplicate_run_id_without_overwriting(tmp_path: Path):
    publish_index_research(sample_output(), tmp_path, sample_run_meta("same-run"))
    with pytest.raises(FileExistsError):
        publish_index_research(sample_output(), tmp_path, sample_run_meta("same-run"))


@pytest.mark.parametrize("corruption", ["missing_artifact", "metadata_run_id"])
def test_loader_fails_closed_for_corrupt_latest_target(tmp_path: Path, corruption: str):
    published = publish_index_research(sample_output(), tmp_path, sample_run_meta("first"))
    run_dir = tmp_path / "runs" / published.run_id
    if corruption == "missing_artifact":
        (run_dir / "index_strategy_nav.parquet").unlink()
    else:
        meta_path = run_dir / "index_trend_strategy_run.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["run_id"] = "different"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

    with pytest.raises(ValueError, match="(missing|required|run_id)"):
        load_latest_index_research(tmp_path)


def test_loader_uses_latest_target_not_staging_or_an_older_run(tmp_path: Path):
    first = publish_index_research(sample_output("first"), tmp_path, sample_run_meta("first"))
    second = publish_index_research(sample_output("second"), tmp_path, sample_run_meta("second"))
    staging = tmp_path / "runs" / "intruder.staging"
    staging.mkdir()
    (staging / "index_backtest_results.csv").write_text("index_code\nINTRUDER\n", encoding="utf-8")

    loaded = load_latest_index_research(tmp_path)
    assert loaded.run_id == second.run_id
    assert loaded.results.iloc[0]["index_code"] == "second"
    assert loaded.run_id != first.run_id


def test_loader_rejects_latest_run_when_required_csv_schema_is_missing(tmp_path: Path):
    published = publish_index_research(sample_output(), tmp_path, sample_run_meta("first"))
    results = tmp_path / "runs" / published.run_id / "index_backtest_results.csv"
    results.write_text("index_code,period_type\n000300,full_history\n", encoding="utf-8")

    with pytest.raises(ValueError, match="schema"):
        load_latest_index_research(tmp_path)


def test_json_rejects_non_finite_metadata_values(tmp_path: Path):
    meta = sample_run_meta("bad")
    meta["gate_values"] = {"drawdown_win_rate": float("nan")}
    with pytest.raises(ValueError, match="finite"):
        publish_index_research(sample_output(), tmp_path, meta)


def test_summary_round_trip_restores_every_task4_structured_output(tmp_path: Path):
    output = sample_output()
    publish_index_research(output, tmp_path, sample_run_meta("full-round-trip"))
    loaded = load_latest_index_research(tmp_path)

    assert_records_equal(loaded.stress_results, output.stress_results)
    assert_records_equal(loaded.prospective_status, output.prospective_status)
    assert_records_equal(loaded.group_statistics, output.group_statistics)
    assert_records_equal(loaded.worst_indices, output.worst_indices)
    assert_records_equal(loaded.rolling_gate_summary, output.rolling_gate_summary)


def test_publish_rejects_effectiveness_metadata_that_disagrees_with_output_and_preserves_latest(tmp_path: Path):
    first = publish_index_research(sample_output(), tmp_path, sample_run_meta("first"))
    inconsistent = sample_run_meta("inconsistent")
    inconsistent["status"] = "passed"

    with pytest.raises(ValueError, match="effectiveness"):
        publish_index_research(sample_output(), tmp_path, inconsistent)

    assert load_latest_index_research(tmp_path).run_id == first.run_id


def test_loader_rejects_weak_trade_schema_and_missing_summary_section(tmp_path: Path):
    published = publish_index_research(sample_output(), tmp_path, sample_run_meta("first"))
    run_dir = tmp_path / "runs" / published.run_id
    (run_dir / "index_backtest_trades.csv").write_text("index_code\n000300\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        load_latest_index_research(tmp_path)

    publish_index_research(sample_output(), tmp_path, sample_run_meta("second"))
    second_dir = tmp_path / "runs" / "second"
    summary = pd.read_csv(second_dir / "index_strategy_summary.csv")
    summary = summary[summary["section"] != "prospective_status"]
    summary.to_csv(second_dir / "index_strategy_summary.csv", index=False)
    (tmp_path / "latest.json").write_text(json.dumps({"run_id": "second"}), encoding="utf-8")
    with pytest.raises(ValueError, match="summary"):
        load_latest_index_research(tmp_path)


def test_publisher_rejects_results_without_core_performance_evidence(tmp_path: Path):
    output = sample_output()
    output = replace(output, results=output.results.drop(columns=["annualized_return", "volatility", "sharpe", "max_drawdown", "calmar"]))
    with pytest.raises(ValueError, match="annualized_return"):
        publish_index_research(output, tmp_path, sample_run_meta("missing-performance"))


def test_loader_rejects_unknown_summary_section_and_conflicting_dtype_declaration(tmp_path: Path):
    published = publish_index_research(sample_output(), tmp_path, sample_run_meta("first"))
    summary_path = tmp_path / "runs" / published.run_id / "index_strategy_summary.csv"
    summary = pd.read_csv(summary_path)
    unknown = summary.iloc[[0]].copy()
    unknown["section"] = "unknown"
    pd.concat([summary, unknown], ignore_index=True).to_csv(summary_path, index=False)
    with pytest.raises(ValueError, match="summary"):
        load_latest_index_research(tmp_path)

    publish_index_research(sample_output(), tmp_path, sample_run_meta("second"))
    second_summary_path = tmp_path / "runs" / "second" / "index_strategy_summary.csv"
    second_summary = pd.read_csv(second_summary_path)
    rows = second_summary.index[second_summary["section"] == "stress_results"]
    second_summary.loc[rows[1], "dtypes_json"] = "{}"
    second_summary.to_csv(second_summary_path, index=False)
    (tmp_path / "latest.json").write_text(json.dumps({"run_id": "second"}), encoding="utf-8")
    with pytest.raises(ValueError, match="summary"):
        load_latest_index_research(tmp_path)


def test_empty_summary_section_round_trips_columns_and_dtypes(tmp_path: Path):
    output = sample_output()
    empty_groups = output.group_statistics.iloc[0:0].copy()
    published = publish_index_research(replace(output, group_statistics=empty_groups), tmp_path, sample_run_meta("empty-groups"))
    loaded = load_latest_index_research(tmp_path)
    assert list(loaded.group_statistics.columns) == list(empty_groups.columns)
    assert [str(dtype) for dtype in loaded.group_statistics.dtypes] == [str(dtype) for dtype in empty_groups.dtypes]


def test_loader_rejects_results_cohort_or_summary_gate_tampering(tmp_path: Path):
    published = publish_index_research(sample_output(), tmp_path, sample_run_meta("first"))
    run_dir = tmp_path / "runs" / published.run_id
    results_path = run_dir / "index_backtest_results.csv"
    results = pd.read_csv(results_path)
    results["cohort"] = "reference"
    results.to_csv(results_path, index=False)
    with pytest.raises(ValueError, match="cohort"):
        load_latest_index_research(tmp_path)

    publish_index_research(sample_output(), tmp_path, sample_run_meta("second"))
    second_dir = tmp_path / "runs" / "second"
    summary_path = second_dir / "index_strategy_summary.csv"
    summary = pd.read_csv(summary_path)
    gate = summary.index[summary["section"] == "effectiveness_gate"][0]
    summary.loc[gate, "passed"] = True
    summary.to_csv(summary_path, index=False)
    (tmp_path / "latest.json").write_text(json.dumps({"run_id": "second"}), encoding="utf-8")
    with pytest.raises(ValueError, match="gate"):
        load_latest_index_research(tmp_path)


def test_publish_rejects_future_or_non_exact_data_cutoff(tmp_path: Path):
    future = sample_run_meta("future")
    future["data_cutoff"] = "2099-01-01"
    with pytest.raises(ValueError, match="data_cutoff"):
        publish_index_research(sample_output(), tmp_path, future)


def test_chinese_report_has_ordered_sections_gates_failure_reason_and_index_warning():
    output = sample_output()
    markdown = render_index_research_markdown(output, sample_run_meta("report"))
    sections = [
        "历史有效性结论", "六项门槛", "全历史配对结果", "五年滚动稳定性", "0/2/3% 缓冲诊断",
        "双倍费用", "年度/阶段", "最好与最差指数", "扩展样本", "排除项", "前瞻样本状态", "研究限制",
    ]
    assert [markdown.index(f"## {section}") for section in sections] == sorted(markdown.index(f"## {section}") for section in sections)
    assert "drawdown_win_rate" in markdown and "样本不足" in markdown
    assert "阈值：`至少 0.60`" in markdown
    assert "median_calmar_improves" in markdown and "实际值" in markdown and "阈值" in markdown
    assert "指数理论回测" in markdown and "不是 ETF 可实现收益" in markdown
    assert "尚无前瞻样本" in markdown
    assert "stage_2020" in markdown
    assert "side" in markdown and "best" in markdown and "worst" in markdown


def test_report_keeps_best_and_worst_rows_when_more_than_ten_indexes():
    output = sample_output()
    rows = []
    for number in range(11):
        row = output.results.iloc[0].copy()
        row["index_code"] = f"IDX{number:02d}"
        row["annualized_return"] = number / 100
        row["period_type"] = "full_history"
        rows.append(row)
    markdown = render_index_research_markdown(replace(output, results=pd.DataFrame(rows)), sample_run_meta("eleven"))
    section = markdown.split("## 最好与最差指数", 1)[1].split("## 扩展样本", 1)[0]
    assert "best" in section and "worst" in section


def test_run_and_publish_marks_limited_run_and_uses_sorted_catalog(tmp_path: Path):
    calls: list[list[str]] = []

    def fake_loader(_root, catalog, _config):
        calls.append([entry for entry in catalog])
        return IndexAdmissionResult(
            frames={"a": pd.DataFrame({"trade_date": [pd.Timestamp("2026-07-30")]})},
            metadata=pd.DataFrame([{"index_code": "a", "cohort": "official"}]),
            exclusions=pd.DataFrame(),
        )

    published = run_and_publish_index_research(
        config_path=Path("configs/index_research.yaml"),
        parquet_root=tmp_path / "parquet",
        report_root=tmp_path / "reports",
        limit=2,
        catalog=("z", "a", "m"),
        admission_loader=fake_loader,
        research_runner=lambda _admission, _config: sample_output(),
    )

    assert calls == [["a", "m"]]
    assert load_latest_index_research(tmp_path / "reports").run_meta["limited_run"] is True
    assert published.run_id


def test_run_and_publish_rejects_zero_admitted_indexes(tmp_path: Path):
    with pytest.raises(ValueError, match="没有可准入"):
        run_and_publish_index_research(
            config_path=Path("configs/index_research.yaml"),
            parquet_root=tmp_path / "parquet",
            report_root=tmp_path / "reports",
            catalog=(),
        )


def test_cli_help_is_available_from_project_root():
    completed = subprocess.run(
        [".venv-win\\Scripts\\python.exe", "scripts\\run_index_research.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "运行指数趋势基准策略 V1 回测" in completed.stdout


def sample_output(code: str = "000300") -> IndexResearchOutput:
    results = pd.DataFrame([{
        "index_code": code, "name": code, "cohort": "official", "market": "CN", "index_type": "broad",
        "period_type": "full_history", "period_label": "full_history", "period_start": "2020-01-01",
        "period_end": "2020-12-31", "strategy_name": "index_trend_v1", "annualized_return": 0.08,
        "volatility": 0.12, "sharpe": 0.66, "max_drawdown": -0.20, "calmar": 0.4,
        "total_return": 0.1, "avg_exposure": 0.5, "trade_count": 2, "trades_per_year": 1.0,
        "whipsaw_trade_rate": 0.0,
    }])
    results = pd.concat([results, results.assign(period_type="stage", period_label="stage_2020")], ignore_index=True)
    assessment = EffectivenessAssessment(
        status="failed",
        gates={"drawdown_win_rate": False, "median_drawdown_reduction": True, "median_calmar_improves": True,
               "median_return_is_retained": True, "buffer_reduces_whipsaw_rate_and_trades": True,
               "stress_keeps_first_four_gates": True},
        values={"drawdown_win_rate": 0.4, "official_index_count": 1},
        reasons=("drawdown_win_rate:样本不足",),
    )
    return IndexResearchOutput(
        results=results,
        nav=pd.DataFrame([{"index_code": code, "period_type": "full_history", "period_label": "full_history", "strategy_name": "index_trend_v1", "trade_date": pd.Timestamp("2020-01-02"), "nav": 1.0, "weight": 0.0}]),
        trades=pd.DataFrame([{
            "index_code": code, "period_type": "full_history", "period_label": "full_history",
            "strategy_name": "index_trend_v1", "signal_date": "2020-01-01", "trade_date": "2020-01-02",
            "action": "BUY", "execution_price": 100.0, "weight_before": 0.0, "weight_after": 1.0,
            "commission": 0.01, "delay_days": 1, "reason": "test", "trigger_rules": "[]",
            "reference_price": 100.0, "slippage_cost": 0.02,
        }]),
        yearly=results[results["period_type"] == "full_history"].assign(period_type="calendar_year"),
        rolling=results.assign(period_type="rolling_5y"),
        buffer_comparison=pd.DataFrame([{"index_code": code, "cohort": "official", "buffer_rate": 0.02, "whipsaw_trade_rate": 0.1, "annualized_trade_count": 2.0}]),
        stress_results=results.assign(period_label="stress_double_cost"),
        prospective_status=pd.DataFrame([{"index_code": code, "cohort": "official", "status": "no_prospective_sample", "reason": "no_data_strictly_after_locked_at"}]),
        group_statistics=pd.DataFrame([{"group_type": "cohort", "group_value": "official", "metric": "calmar", "mean": 0.4, "median": 0.4, "q25": 0.4, "q75": 0.4, "count": 1}]),
        worst_indices=results.copy(),
        rolling_gate_summary=pd.DataFrame([{"eligible_windows": 0, "passing_windows": 0, "pass_rate": 0.0}]),
        effectiveness=assessment,
    )


def sample_run_meta(run_id: str) -> dict[str, object]:
    return {
        "run_id": run_id,
        "strategy_version": "index_trend_v1",
        "config_sha256": "a" * 64,
        "locked_at": date(2026, 7, 30),
        "data_cutoff": "2020-12-31",
        "run_at": "2026-07-30T00:00:00+00:00",
        "official_count": 1,
        "reference_count": 0,
        "exclusion_count": 0,
        "status": "failed",
        "gates": {
            "drawdown_win_rate": False,
            "median_drawdown_reduction": True,
            "median_calmar_improves": True,
            "median_return_is_retained": True,
            "buffer_reduces_whipsaw_rate_and_trades": True,
            "stress_keeps_first_four_gates": True,
        },
        "gate_values": {"drawdown_win_rate": 0.4, "official_index_count": 1},
        "gate_reasons": ["drawdown_win_rate:样本不足"],
        "exclusions": [],
    }


def assert_records_equal(actual: pd.DataFrame, expected: pd.DataFrame) -> None:
    assert actual.fillna("<NA>").astype(str).to_dict("records") == expected.fillna("<NA>").astype(str).to_dict("records")
