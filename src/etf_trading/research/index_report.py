"""Versioned, atomic evidence packages for locked index-trend research."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from etf_trading.data.index_catalog import IndexCatalogEntry, default_index_catalog
from etf_trading.research.index_data import load_index_frames
from etf_trading.research.index_gate_evidence import EFFECTIVENESS_GATE_NAMES, format_gate_evidence
from etf_trading.research.index_models import EffectivenessAssessment, IndexAdmissionResult, IndexResearchConfig, IndexResearchOutput
from etf_trading.research.index_models import load_index_research_config
from etf_trading.research.index_validation import evaluate_effectiveness, run_index_research


REQUIRED_ARTIFACTS = (
    "index_backtest_results.csv",
    "index_backtest_trades.csv",
    "index_strategy_summary.csv",
    "index_strategy_yearly.csv",
    "index_strategy_rolling_5y.csv",
    "index_strategy_buffer_comparison.csv",
    "index_strategy_exclusions.csv",
    "index_strategy_nav.parquet",
    "index_trend_strategy_report.md",
    "index_trend_strategy_run.json",
)
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RUN_META_REQUIRED = frozenset({
    "run_id", "strategy_version", "config_sha256", "locked_at", "data_cutoff", "run_at",
    "official_count", "reference_count", "exclusion_count", "status", "gates", "gate_values",
    "gate_reasons", "exclusions",
})
_GATE_NAMES = EFFECTIVENESS_GATE_NAMES
_LOCKED_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "index_research.yaml"
_SUMMARY_SECTIONS = (
    "effectiveness_status", "effectiveness_gate", "group_statistics", "worst_indices",
    "rolling_gate_summary", "stress_results", "prospective_status",
)
_PERFORMANCE_COLUMNS = frozenset({
    "annualized_return", "volatility", "sharpe", "max_drawdown", "calmar", "total_return",
    "avg_exposure", "trade_count", "trades_per_year", "whipsaw_trade_rate",
})
_CSV_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "index_backtest_results.csv": frozenset({"index_code", "name", "cohort", "market", "index_type", "period_type", "period_label", "period_start", "period_end", "strategy_name"}) | _PERFORMANCE_COLUMNS,
    "index_backtest_trades.csv": frozenset({"index_code", "period_type", "period_label", "strategy_name", "signal_date", "trade_date", "action", "execution_price", "weight_before", "weight_after", "commission", "delay_days", "reason", "trigger_rules"}),
    "index_strategy_summary.csv": frozenset({"section", "columns_json", "dtypes_json", "is_empty"}),
    "index_strategy_yearly.csv": frozenset({"index_code", "period_type", "period_label", "period_start", "period_end", "strategy_name"}) | _PERFORMANCE_COLUMNS,
    "index_strategy_rolling_5y.csv": frozenset({"index_code", "period_type", "period_label", "period_start", "period_end", "strategy_name"}) | _PERFORMANCE_COLUMNS,
    "index_strategy_buffer_comparison.csv": frozenset({"index_code", "cohort", "buffer_rate", "whipsaw_trade_rate", "annualized_trade_count"}),
    "index_strategy_exclusions.csv": frozenset({"index_code", "name", "reason_code"}),
}
_NAV_REQUIRED_COLUMNS = frozenset({"index_code", "period_type", "period_label", "strategy_name", "trade_date", "nav", "weight"})


@dataclass(frozen=True)
class PublishedIndexResearch:
    """The immutable version selected by the latest pointer."""

    run_id: str
    run_dir: Path
    data_cutoff: str


@dataclass(frozen=True)
class LoadedIndexResearch:
    """Fully validated evidence read strictly from ``latest.json``."""

    run_id: str
    run_dir: Path
    run_meta: dict[str, object]
    results: pd.DataFrame
    trades: pd.DataFrame
    summary: pd.DataFrame
    yearly: pd.DataFrame
    rolling: pd.DataFrame
    buffer_comparison: pd.DataFrame
    exclusions: pd.DataFrame
    nav: pd.DataFrame
    report_markdown: str
    stress_results: pd.DataFrame
    prospective_status: pd.DataFrame
    group_statistics: pd.DataFrame
    worst_indices: pd.DataFrame
    rolling_gate_summary: pd.DataFrame


def publish_index_research(
    output: IndexResearchOutput,
    report_root: str | Path,
    run_meta: Mapping[str, object],
) -> PublishedIndexResearch:
    """Write all evidence to staging, validate it, then atomically publish it.

    No successful directory or latest pointer is exposed until every artifact is
    readable.  A failed write leaves an existing latest package untouched.
    """

    meta = _normalise_run_meta(run_meta)
    _validate_output_and_meta(output, meta)
    root = Path(report_root)
    runs = root / "runs"
    run_id = str(meta["run_id"])
    final_dir = runs / run_id
    staging_dir = runs / f"{run_id}.staging"
    if final_dir.exists() or staging_dir.exists():
        raise FileExistsError(f"run_id already exists: {run_id}")

    runs.mkdir(parents=True, exist_ok=True)
    try:
        staging_dir.mkdir()
        _write_artifacts(staging_dir, output, meta)
        _validate_run_directory(staging_dir, run_id)
        os.replace(staging_dir, final_dir)
        _replace_latest_pointer(root, run_id)
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return PublishedIndexResearch(run_id=run_id, run_dir=final_dir, data_cutoff=str(meta["data_cutoff"]))


def load_latest_index_research(report_root: str | Path) -> LoadedIndexResearch:
    """Load only the complete version named by the atomically written pointer."""

    root = Path(report_root)
    pointer = root / "latest.json"
    try:
        raw_pointer = json.loads(pointer.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("latest index research pointer is missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("latest index research pointer is corrupt") from exc
    if not isinstance(raw_pointer, dict) or set(raw_pointer) != {"run_id"}:
        raise ValueError("latest index research pointer has invalid schema")
    run_id = raw_pointer["run_id"]
    if not isinstance(run_id, str) or not _safe_run_id(run_id):
        raise ValueError("latest index research pointer has unsafe run_id")
    run_dir = root / "runs" / run_id
    _validate_run_directory(run_dir, run_id)
    meta = _read_meta(run_dir / "index_trend_strategy_run.json", run_id)
    summary = _read_csv(run_dir / "index_strategy_summary.csv")
    sections = _unpack_summary(summary)
    results = _read_csv(run_dir / "index_backtest_results.csv")
    trades = _read_csv(run_dir / "index_backtest_trades.csv")
    exclusions = _read_csv(run_dir / "index_strategy_exclusions.csv")
    nav = _read_nav(run_dir / "index_strategy_nav.parquet")
    _validate_cross_artifact_consistency(meta, results, trades, exclusions, nav, sections)
    return LoadedIndexResearch(
        run_id=run_id,
        run_dir=run_dir,
        run_meta=meta,
        results=results,
        trades=trades,
        summary=summary,
        yearly=_read_csv(run_dir / "index_strategy_yearly.csv"),
        rolling=_read_csv(run_dir / "index_strategy_rolling_5y.csv"),
        buffer_comparison=_read_csv(run_dir / "index_strategy_buffer_comparison.csv"),
        exclusions=exclusions,
        nav=nav,
        report_markdown=(run_dir / "index_trend_strategy_report.md").read_text(encoding="utf-8"),
        stress_results=sections["stress_results"],
        prospective_status=sections["prospective_status"],
        group_statistics=sections["group_statistics"],
        worst_indices=sections["worst_indices"],
        rolling_gate_summary=sections["rolling_gate_summary"],
    )


def render_index_research_markdown(output: IndexResearchOutput, run_meta: Mapping[str, object]) -> str:
    """Render the fixed-order, conclusion-first Chinese research disclosure."""

    meta = _normalise_run_meta(run_meta)
    assessment = output.effectiveness
    limited = "\n\n> 本次为有限样本冒烟运行，不构成全量历史有效性结论。" if meta.get("limited_run") else ""
    lines = [
        "# 指数趋势基准策略 V1 研究报告",
        "",
        "> **重要提示：这是指数理论回测，不是 ETF 可实现收益。** 未计入 ETF 跟踪误差、折溢价、流动性和真实成交约束。",
        limited,
        "",
        "## 历史有效性结论",
        f"- 结论：**{'通过历史有效性门槛' if assessment.status == 'passed' else '未通过历史有效性门槛'}**（状态：`{assessment.status}`）。",
        f"- 策略版本：`{meta['strategy_version']}`；锁定日：`{meta['locked_at']}`；数据截止日：`{meta['data_cutoff']}`。",
        "",
        "## 六项门槛",
    ]
    for evidence in format_gate_evidence(assessment.gates, assessment.values, assessment.reasons):
        lines.append(
            f"- `{evidence.name}`：{'通过' if evidence.passed else '失败'}；"
            f"实际值：`{evidence.actual}`；阈值：`{evidence.threshold}`；原因：{evidence.reason}。"
        )
    full_history = output.results[output.results["period_type"] == "full_history"] if "period_type" in output.results else output.results
    lines.extend(_table_section("全历史配对结果", full_history))
    lines.extend(_table_section("五年滚动稳定性", output.rolling))
    lines.extend(_table_section("0/2/3% 缓冲诊断", output.buffer_comparison))
    lines.extend(_table_section("双倍费用", output.stress_results))
    annual_and_stage = output.results[output.results["period_type"].isin(["calendar_year", "stage"])] if "period_type" in output.results else output.yearly
    calendar_years = annual_and_stage[annual_and_stage["period_type"] == "calendar_year"] if "period_type" in annual_and_stage else annual_and_stage
    stages = annual_and_stage[annual_and_stage["period_type"] == "stage"] if "period_type" in annual_and_stage else pd.DataFrame()
    lines.extend(["", "## 年度/阶段", "", "### 自然年"])
    lines.extend(_table_section_body(calendar_years, limit=10))
    lines.extend(["", "### 阶段"])
    lines.extend(_table_section_body(stages, limit=10))
    lines.extend(_table_section("最好与最差指数", _best_and_worst_indices(output.results), limit=20))
    reference = output.results[output.results.get("cohort", pd.Series(dtype="object")) == "reference"] if "cohort" in output.results else pd.DataFrame()
    lines.extend(_table_section("扩展样本", reference))
    exclusions = _exclusions_frame(meta)
    lines.extend(_table_section("排除项", exclusions))
    lines.extend(_table_section("前瞻样本状态", output.prospective_status))
    if "status" in output.prospective_status and (output.prospective_status["status"] == "no_prospective_sample").any():
        lines.append("- 尚无前瞻样本；不得将历史切分表述为 prospective OOS。")
    lines.extend([
        "## 研究限制",
        "- 历史开发表现与锁定日之后的 prospective OOS 证据等级不同；后者不能由任何历史切分替代。",
        "- 失败结论保持失败，不以解释性措辞包装为有效。",
        "- 指数之间可能高度相关，统计结果仅作描述性证据。",
        "",
    ])
    return "\n".join(line for line in lines if line is not None)


def run_and_publish_index_research(
    *,
    config_path: str | Path = "configs/index_research.yaml",
    parquet_root: str | Path = "data/parquet",
    report_root: str | Path = "reports/index_research",
    limit: int | None = None,
    catalog: Sequence[IndexCatalogEntry] | None = None,
    admission_loader: Callable[[str | Path, Sequence[IndexCatalogEntry], IndexResearchConfig], IndexAdmissionResult] = load_index_frames,
    research_runner: Callable[[IndexAdmissionResult, IndexResearchConfig], IndexResearchOutput] = run_index_research,
    progress: Callable[[int, int, str, str], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> PublishedIndexResearch:
    """Run the locked matrix and publish it through the sole reusable entry point."""

    if limit is not None and limit <= 0:
        raise ValueError("limit must be a positive integer")
    config_file = Path(config_path)
    config = load_index_research_config(config_file)
    selected_catalog = tuple(sorted(catalog if catalog is not None else default_index_catalog(), key=lambda item: getattr(item, "index_code", str(item))))
    if limit is not None:
        selected_catalog = selected_catalog[:limit]
    admission = admission_loader(parquet_root, selected_catalog, config)
    if not admission.frames:
        raise ValueError("没有可准入的本地指数数据；未发布任何研究结果")
    if should_stop is not None and should_stop():
        from etf_trading.research.index_validation import IndexResearchCancelled

        raise IndexResearchCancelled("index research cancelled before publishing a partial output")
    output = (
        research_runner(admission, config)
        if progress is None and should_stop is None
        else research_runner(admission, config, progress=progress, should_stop=should_stop)
    )
    if should_stop is not None and should_stop():
        from etf_trading.research.index_validation import IndexResearchCancelled

        raise IndexResearchCancelled("index research cancelled before publishing a partial output")
    return publish_index_research(output, report_root, _build_run_meta(config_file, config, admission, output, limit))


def _write_artifacts(directory: Path, output: IndexResearchOutput, meta: dict[str, object]) -> None:
    _write_csv(directory / "index_backtest_results.csv", output.results)
    _write_csv(directory / "index_backtest_trades.csv", _complete_empty_schema(output.trades, _CSV_REQUIRED_COLUMNS["index_backtest_trades.csv"]))
    _write_csv(directory / "index_strategy_summary.csv", _summary_frame(output))
    _write_csv(directory / "index_strategy_yearly.csv", output.yearly)
    _write_csv(directory / "index_strategy_rolling_5y.csv", output.rolling)
    _write_csv(directory / "index_strategy_buffer_comparison.csv", output.buffer_comparison)
    _write_csv(directory / "index_strategy_exclusions.csv", _exclusions_frame(meta))
    _complete_empty_schema(output.nav, _NAV_REQUIRED_COLUMNS).to_parquet(directory / "index_strategy_nav.parquet", index=False)
    (directory / "index_trend_strategy_report.md").write_text(render_index_research_markdown(output, meta), encoding="utf-8")
    (directory / "index_trend_strategy_run.json").write_text(_json_dumps(meta), encoding="utf-8")


def _summary_frame(output: IndexResearchOutput) -> pd.DataFrame:
    status = pd.DataFrame([{
        "status": output.effectiveness.status,
        "gates_json": _json_dumps(output.effectiveness.gates),
        "values_json": _json_dumps(output.effectiveness.values),
        "reasons_json": _json_dumps(list(output.effectiveness.reasons)),
    }])
    gates = pd.DataFrame([
        {"name": name, "passed": passed, "value": output.effectiveness.values.get(name), "value_json": _json_dumps({"value": output.effectiveness.values.get(name)}),
         "reason": "; ".join(reason for reason in output.effectiveness.reasons if reason.startswith(f"{name}:"))}
        for name, passed in output.effectiveness.gates.items()
    ])
    return pd.concat([
        _pack_summary_section("effectiveness_status", status),
        _pack_summary_section("effectiveness_gate", gates),
        _pack_summary_section("group_statistics", output.group_statistics),
        _pack_summary_section("worst_indices", output.worst_indices),
        _pack_summary_section("rolling_gate_summary", output.rolling_gate_summary),
        _pack_summary_section("stress_results", output.stress_results),
        _pack_summary_section("prospective_status", output.prospective_status),
    ], ignore_index=True, sort=False)


def _pack_summary_section(section: str, frame: pd.DataFrame) -> pd.DataFrame:
    """Store heterogeneous Task 4 tables losslessly in one sectioned CSV."""

    source = frame.copy()
    columns = list(source.columns)
    if source.empty:
        source = pd.DataFrame([{column: None for column in columns}])
        empty = True
    else:
        empty = False
    source.insert(0, "is_empty", empty)
    source.insert(0, "dtypes_json", _json_dumps({column: str(dtype) for column, dtype in frame.dtypes.items()}))
    source.insert(0, "columns_json", _json_dumps(columns))
    source.insert(0, "section", section)
    return source


def _unpack_summary(summary: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if set(summary["section"].dropna()) != set(_SUMMARY_SECTIONS):
        raise ValueError("index research summary section set is invalid")
    sections: dict[str, pd.DataFrame] = {}
    for section in _SUMMARY_SECTIONS:
        rows = summary[summary["section"] == section].copy()
        if rows.empty or rows["columns_json"].nunique(dropna=True) != 1 or rows["dtypes_json"].nunique(dropna=True) != 1 or rows["is_empty"].nunique(dropna=True) != 1:
            raise ValueError("index research summary section schema is invalid")
        try:
            columns = json.loads(str(rows["columns_json"].iloc[0]))
            dtypes = json.loads(str(rows["dtypes_json"].iloc[0]))
        except json.JSONDecodeError as exc:
            raise ValueError("index research summary columns_json is invalid") from exc
        if not isinstance(columns, list) or not all(isinstance(column, str) for column in columns) or not isinstance(dtypes, dict):
            raise ValueError("index research summary columns_json is invalid")
        missing = set(columns).difference(rows.columns)
        if missing:
            raise ValueError("index research summary section is missing stored columns")
        is_empty = bool(rows["is_empty"].iloc[0])
        payload = rows.loc[:, columns]
        if is_empty:
            if len(rows) != 1 or not payload.iloc[0].isna().all():
                raise ValueError("index research summary empty section payload is invalid")
            sections[section] = _restore_summary_dtypes(pd.DataFrame(columns=columns), dtypes)
        else:
            if payload.isna().all(axis=1).any():
                raise ValueError("index research summary non-empty section has placeholder payload")
            restored = payload.reset_index(drop=True)
            sections[section] = _restore_summary_dtypes(restored, dtypes)
    gates = sections["effectiveness_gate"]
    if set(gates.get("name", pd.Series(dtype="object"))) != set(_GATE_NAMES) or len(gates) != len(_GATE_NAMES):
        raise ValueError("index research summary must contain six unique effectiveness gates")
    required_by_section = {
        "effectiveness_status": {"status", "gates_json", "values_json", "reasons_json"},
        "effectiveness_gate": {"name", "passed", "value", "value_json", "reason"},
        "group_statistics": {"group_type", "group_value", "metric", "mean", "median", "q25", "q75", "count"},
        "worst_indices": {"index_code", "cohort"} | _PERFORMANCE_COLUMNS,
        "rolling_gate_summary": {"eligible_windows", "passing_windows", "pass_rate"},
        "stress_results": _CSV_REQUIRED_COLUMNS["index_backtest_results.csv"],
        "prospective_status": {"index_code", "cohort", "status", "reason"},
    }
    for section, required in required_by_section.items():
        if not required.issubset(sections[section].columns):
            raise ValueError("index research summary section schema is invalid")
    return sections


def _restore_summary_dtypes(frame: pd.DataFrame, dtypes: Mapping[str, object]) -> pd.DataFrame:
    result = frame.copy()
    for column, dtype in dtypes.items():
        if column not in result:
            continue
        dtype_name = str(dtype)
        if dtype_name.startswith("datetime"):
            result[column] = pd.to_datetime(result[column], errors="raise")
        elif dtype_name.startswith("int") or dtype_name.startswith("Int"):
            result[column] = pd.to_numeric(result[column], errors="raise").astype(dtype_name)
        elif dtype_name.startswith("float"):
            result[column] = pd.to_numeric(result[column], errors="raise").astype(dtype_name)
        elif dtype_name in {"bool", "boolean"}:
            result[column] = result[column].astype(dtype_name)
        elif dtype_name.startswith("string"):
            result[column] = result[column].astype("string")
        elif dtype_name == "str":
            result[column] = result[column].astype("str")
    return result


def _complete_empty_schema(frame: pd.DataFrame, required: frozenset[str]) -> pd.DataFrame:
    if frame.empty:
        result = frame.copy()
        for column in required:
            if column not in result:
                result[column] = pd.Series(dtype="object")
        return result
    return frame


def _table_section(title: str, frame: pd.DataFrame, *, limit: int = 10) -> list[str]:
    lines = ["", f"## {title}"]
    return [*lines, *_table_section_body(frame, limit=limit)]


def _table_section_body(frame: pd.DataFrame, *, limit: int = 10) -> list[str]:
    if frame.empty:
        return ["- 无可报告数据。"]
    preview = frame.head(limit).copy()
    preview = preview.apply(lambda column: column.map(_display_table_value))
    return [preview.to_markdown(index=False)]


def _display_table_value(value: object) -> object:
    """Keep human-readable reports free of non-finite dataframe sentinels."""

    try:
        if pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    try:
        if math.isinf(float(value)):
            return "—"
    except (TypeError, ValueError):
        pass
    return str(value) if isinstance(value, (pd.Timestamp, datetime)) else value


def _best_and_worst_indices(results: pd.DataFrame) -> pd.DataFrame:
    required = {"index_code", "cohort", "period_type", "strategy_name", "annualized_return"}
    if not required.issubset(results.columns):
        return pd.DataFrame(columns=["side", *sorted(required)])
    base = results[(results["cohort"] == "official") & (results["period_type"] == "full_history") & (results["strategy_name"] == "index_trend_v1")].copy()
    if base.empty:
        return pd.DataFrame(columns=["side", *results.columns])
    base["annualized_return"] = pd.to_numeric(base["annualized_return"], errors="coerce")
    base = base.dropna(subset=["annualized_return"])
    best = base.sort_values(["annualized_return", "index_code"], ascending=[False, True], kind="stable").head(10).assign(side="best")
    worst = base.sort_values(["annualized_return", "index_code"], ascending=[True, True], kind="stable").head(10).assign(side="worst")
    return pd.concat([best, worst], ignore_index=True)


def _normalise_run_meta(run_meta: Mapping[str, object]) -> dict[str, object]:
    meta = dict(run_meta)
    missing = _RUN_META_REQUIRED.difference(meta)
    if missing:
        raise ValueError(f"run metadata missing required fields: {sorted(missing)}")
    if not _safe_run_id(str(meta["run_id"])):
        raise ValueError("run_id must be a safe, non-empty filename")
    if str(meta["strategy_version"]) != "index_trend_v1":
        raise ValueError("run metadata strategy_version must be index_trend_v1")
    if not re.fullmatch(r"[0-9a-f]{64}", str(meta["config_sha256"])):
        raise ValueError("run metadata config_sha256 must be SHA-256")
    for key in ("locked_at", "data_cutoff"):
        try:
            pd.Timestamp(meta[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"run metadata {key} must be date-like") from exc
    run_at = pd.Timestamp(meta["run_at"])
    if run_at.tzinfo is None:
        raise ValueError("run metadata run_at must include a timezone")
    for key in ("official_count", "reference_count", "exclusion_count"):
        if type(meta[key]) is not int or int(meta[key]) < 0:
            raise ValueError(f"run metadata {key} must be a non-negative integer")
    if str(meta["status"]) not in {"passed", "failed"}:
        raise ValueError("run metadata status must be passed or failed")
    if not isinstance(meta["gates"], dict) or set(meta["gates"]) != set(_GATE_NAMES) or not all(type(value) is bool for value in meta["gates"].values()):
        raise ValueError("run metadata must contain six boolean gates")
    if meta["status"] != ("passed" if all(meta["gates"].values()) else "failed"):
        raise ValueError("run metadata effectiveness status disagrees with its gates")
    if not isinstance(meta["gate_values"], dict) or not isinstance(meta["gate_reasons"], list) or not isinstance(meta["exclusions"], list):
        raise ValueError("run metadata has invalid audit fields")
    gate_prefixes = tuple(f"{name}:" for name in _GATE_NAMES)
    if any(not isinstance(reason, str) or not reason.startswith(gate_prefixes) for reason in meta["gate_reasons"]):
        raise ValueError("run metadata gate reasons must name one of the six gates")
    return _json_safe(meta)


def _build_run_meta(config_path: Path, config: IndexResearchConfig, admission: IndexAdmissionResult, output: IndexResearchOutput, limit: int | None) -> dict[str, object]:
    metadata = admission.metadata if not admission.metadata.empty else pd.DataFrame(columns=["cohort"])
    result_ends = pd.to_datetime(output.results.get("period_end", pd.Series(dtype="object")), errors="coerce").dropna()
    if result_ends.empty:
        raise ValueError("research output has no period_end cutoff evidence")
    cutoff = result_ends.max().date().isoformat()
    exclusions = admission.exclusions.to_dict("records") if not admission.exclusions.empty else []
    return {
        "run_id": f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}-{uuid.uuid4().hex[:10]}",
        "strategy_version": config.strategy_version,
        "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
        "locked_at": config.locked_at,
        "data_cutoff": cutoff,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "official_count": int((metadata.get("cohort", pd.Series(dtype="object")) == "official").sum()),
        "reference_count": int((metadata.get("cohort", pd.Series(dtype="object")) == "reference").sum()),
        "exclusion_count": len(exclusions),
        "status": output.effectiveness.status,
        "gates": output.effectiveness.gates,
        "gate_values": output.effectiveness.values,
        "gate_reasons": list(output.effectiveness.reasons),
        "exclusions": exclusions,
        "limited_run": limit is not None,
        "limit": limit,
    }


def _validate_output_and_meta(output: IndexResearchOutput, meta: Mapping[str, object]) -> None:
    assessment = output.effectiveness
    if set(assessment.gates) != set(_GATE_NAMES) or not all(type(value) is bool for value in assessment.gates.values()):
        raise ValueError("output effectiveness must contain the fixed six boolean gates")
    expected_status = "passed" if all(assessment.gates.values()) else "failed"
    if assessment.status != expected_status or meta["status"] != expected_status:
        raise ValueError("effectiveness status must exactly match all six gates")
    if dict(meta["gates"]) != assessment.gates:
        raise ValueError("effectiveness gates in metadata disagree with output")
    if _json_safe(meta["gate_values"]) != _json_safe(assessment.values):
        raise ValueError("effectiveness values in metadata disagree with output")
    if list(meta["gate_reasons"]) != _json_safe(list(assessment.reasons)):
        raise ValueError("effectiveness reasons in metadata disagree with output")
    if {"index_code", "cohort"}.issubset(output.results.columns):
        cohorts = output.results[["index_code", "cohort"]].drop_duplicates()
        official_count = int((cohorts["cohort"] == "official").sum())
        reference_count = int((cohorts["cohort"] == "reference").sum())
        if meta["official_count"] != official_count or meta["reference_count"] != reference_count:
            raise ValueError("run metadata cohort counts disagree with structured results")
    exclusions = _exclusions_frame(meta)
    if meta["exclusion_count"] != len(exclusions):
        raise ValueError("run metadata exclusion count disagrees with exclusions")
    _validate_frame_schema(output.results, "index_backtest_results.csv")
    _validate_frame_schema(output.stress_results, "index_backtest_results.csv")
    _validate_frame_schema(_complete_empty_schema(output.trades, _CSV_REQUIRED_COLUMNS["index_backtest_trades.csv"]), "index_backtest_trades.csv")
    _validate_frame_schema(output.yearly, "index_strategy_yearly.csv")
    _validate_frame_schema(output.rolling, "index_strategy_rolling_5y.csv")
    _validate_frame_schema(output.buffer_comparison, "index_strategy_buffer_comparison.csv")
    _validate_frame_schema(exclusions, "index_strategy_exclusions.csv")
    _validate_nav(_complete_empty_schema(output.nav, _NAV_REQUIRED_COLUMNS))
    _validate_meta_cutoff(meta, output.results, output.trades, output.nav)


def _validate_cross_artifact_consistency(
    meta: Mapping[str, object], results: pd.DataFrame, trades: pd.DataFrame,
    exclusions: pd.DataFrame, nav: pd.DataFrame, sections: Mapping[str, pd.DataFrame],
) -> None:
    _validate_frame_schema(results, "index_backtest_results.csv")
    _validate_frame_schema(trades, "index_backtest_trades.csv")
    _validate_frame_schema(exclusions, "index_strategy_exclusions.csv")
    _validate_nav(nav)
    _validate_summary_numeric_sections(sections)
    status = sections["effectiveness_status"]
    if len(status) != 1:
        raise ValueError("index research summary must have one effectiveness status row")
    try:
        gates = json.loads(str(status["gates_json"].iloc[0]))
        values = json.loads(str(status["values_json"].iloc[0]))
        reasons = json.loads(str(status["reasons_json"].iloc[0]))
    except (KeyError, json.JSONDecodeError) as exc:
        raise ValueError("index research summary effectiveness payload is invalid") from exc
    if status["status"].iloc[0] != meta["status"] or gates != meta["gates"] or values != meta["gate_values"] or reasons != meta["gate_reasons"]:
        raise ValueError("index research summary effectiveness disagrees with metadata")
    gate_rows = sections["effectiveness_gate"]
    for row in gate_rows.itertuples(index=False):
        if type(row.passed) is not bool or row.passed != meta["gates"][row.name]:
            raise ValueError("index research summary gate rows disagree with metadata gates")
        expected_value = meta["gate_values"].get(row.name)
        expected_reason = "; ".join(reason for reason in meta["gate_reasons"] if reason.startswith(f"{row.name}:"))
        actual_reason = "" if pd.isna(row.reason) else str(row.reason)
        try:
            actual_value = json.loads(str(row.value_json))["value"]
        except json.JSONDecodeError as exc:
            raise ValueError("index research summary gate value payload is invalid") from exc
        if actual_value != _json_safe(expected_value) or actual_reason != expected_reason:
            raise ValueError("index research summary gate rows disagree with metadata evidence")
        display_value = None if pd.isna(row.value) else row.value
        if not _summary_values_match(display_value, actual_value):
            raise ValueError("index research summary gate display value disagrees with authoritative value_json")
    cohorts = results[["index_code", "cohort"]].drop_duplicates()
    official_count = int((cohorts["cohort"] == "official").sum())
    reference_count = int((cohorts["cohort"] == "reference").sum())
    if official_count != meta["official_count"] or reference_count != meta["reference_count"]:
        raise ValueError("index research metadata cohort counts disagree with results")
    if exclusions.fillna("").to_dict("records") != _exclusions_frame(meta).fillna("").to_dict("records"):
        raise ValueError("index research exclusions disagree with metadata")
    _validate_result_references(results, trades, nav)
    _validate_meta_cutoff(meta, results, trades, nav)


def _validate_frame_schema(frame: pd.DataFrame, artifact: str) -> None:
    required = _CSV_REQUIRED_COLUMNS[artifact]
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"index research {artifact} schema is invalid; missing={sorted(missing)}")
    for column in ("period_start", "period_end", "signal_date", "trade_date"):
        if column in frame and not frame.empty and pd.to_datetime(frame[column], errors="coerce").isna().any():
            raise ValueError(f"index research {artifact} has an invalid {column}")
    for column in ("buffer_rate", "whipsaw_trade_rate", "annualized_trade_count", "execution_price", "weight_before", "weight_after", "commission", "delay_days"):
        if column in frame and not frame.empty:
            values = pd.to_numeric(frame[column], errors="coerce")
            if values.isna().any() or not values.map(math.isfinite).all():
                raise ValueError(f"index research {artifact} has an invalid {column}")
    for column in _PERFORMANCE_COLUMNS.intersection(frame.columns):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or not values.map(math.isfinite).all():
            raise ValueError(f"index research {artifact} has an invalid {column}")


def _validate_summary_numeric_sections(sections: Mapping[str, pd.DataFrame]) -> None:
    _validate_frame_schema(sections["stress_results"], "index_backtest_results.csv")
    worst = sections["worst_indices"]
    for column in _PERFORMANCE_COLUMNS:
        values = pd.to_numeric(worst[column], errors="coerce")
        if values.isna().any() or not values.map(math.isfinite).all():
            raise ValueError("index research summary worst_indices has invalid performance evidence")
    for section, columns in (("group_statistics", ("mean", "median", "q25", "q75", "count")), ("rolling_gate_summary", ("eligible_windows", "passing_windows", "pass_rate"))):
        frame = sections[section]
        for column in columns:
            values = pd.to_numeric(frame[column], errors="coerce")
            if values.isna().any() or not values.map(math.isfinite).all():
                raise ValueError(f"index research summary {section} has invalid {column}")


def _summary_values_match(display: object, authoritative: object) -> bool:
    if display is None and authoritative is None:
        return True
    if isinstance(authoritative, (int, float)) and not isinstance(authoritative, bool):
        try:
            return math.isclose(float(display), float(authoritative), rel_tol=1e-12, abs_tol=1e-12)
        except (TypeError, ValueError):
            return False
    return display == authoritative


def _validate_nav(nav: pd.DataFrame) -> None:
    missing = _NAV_REQUIRED_COLUMNS.difference(nav.columns)
    if missing:
        raise ValueError(f"index research NAV schema is invalid; missing={sorted(missing)}")
    if nav.empty:
        return
    dates = pd.to_datetime(nav["trade_date"], errors="coerce")
    values = pd.to_numeric(nav["nav"], errors="coerce")
    weights = pd.to_numeric(nav["weight"], errors="coerce")
    if dates.isna().any() or values.isna().any() or weights.isna().any() or not values.map(math.isfinite).all() or not weights.map(math.isfinite).all():
        raise ValueError("index research NAV has invalid dates or numbers")


def _validate_result_references(results: pd.DataFrame, trades: pd.DataFrame, nav: pd.DataFrame) -> None:
    """Require every trade and NAV row to belong to a published result series."""

    keys = ("index_code", "period_type", "period_label", "strategy_name")
    available = set(map(tuple, results.loc[:, keys].itertuples(index=False, name=None)))
    for artifact, frame in (("trades", trades), ("NAV", nav)):
        referenced = set(map(tuple, frame.loc[:, keys].itertuples(index=False, name=None)))
        orphaned = referenced.difference(available)
        if orphaned:
            raise ValueError(f"index research {artifact} has orphan result reference: {sorted(orphaned)[0]}")


def _validate_meta_cutoff(meta: Mapping[str, object], results: pd.DataFrame, trades: pd.DataFrame, nav: pd.DataFrame) -> None:
    dates: list[pd.Timestamp] = []
    for frame, column in ((results, "period_end"), (trades, "signal_date"), (trades, "trade_date"), (nav, "trade_date")):
        if column in frame and not frame.empty:
            parsed = pd.to_datetime(frame[column], errors="coerce").dropna()
            dates.extend(pd.Timestamp(value).normalize() for value in parsed)
    if "period_end" not in results or results.empty:
        raise ValueError("index research results must provide period_end cutoff evidence")
    result_ends = pd.to_datetime(results["period_end"], errors="coerce")
    if result_ends.isna().any():
        raise ValueError("index research results has invalid period_end cutoff evidence")
    expected_cutoff = result_ends.max().normalize()
    actual_cutoff = pd.Timestamp(meta["data_cutoff"]).normalize()
    if actual_cutoff != expected_cutoff:
        raise ValueError("run metadata data_cutoff must exactly equal structured evidence cutoff")
    if dates and actual_cutoff < max(dates):
        raise ValueError("run metadata data_cutoff is earlier than structured evidence")


def _validate_run_directory(directory: Path, run_id: str) -> None:
    if not directory.is_dir():
        raise ValueError("latest index research run directory is missing")
    actual = {path.name for path in directory.iterdir() if path.is_file()}
    if actual != set(REQUIRED_ARTIFACTS):
        missing = sorted(set(REQUIRED_ARTIFACTS).difference(actual))
        unexpected = sorted(actual.difference(REQUIRED_ARTIFACTS))
        raise ValueError(f"index research artifacts invalid; missing={missing}; unexpected={unexpected}")
    for name in REQUIRED_ARTIFACTS:
        path = directory / name
        if not path.stat().st_size:
            raise ValueError(f"required index research artifact is empty: {name}")
    meta = _read_meta(directory / "index_trend_strategy_run.json", run_id)
    results = _read_csv(directory / "index_backtest_results.csv")
    trades = _read_csv(directory / "index_backtest_trades.csv")
    summary = _read_csv(directory / "index_strategy_summary.csv")
    exclusions = _read_csv(directory / "index_strategy_exclusions.csv")
    _read_csv(directory / "index_strategy_yearly.csv")
    _read_csv(directory / "index_strategy_rolling_5y.csv")
    buffer_comparison = _read_csv(directory / "index_strategy_buffer_comparison.csv")
    nav = _read_nav(directory / "index_strategy_nav.parquet")
    sections = _unpack_summary(summary)
    _validate_cross_artifact_consistency(meta, results, trades, exclusions, nav, sections)
    _validate_recalculated_effectiveness(meta, results, buffer_comparison, sections["stress_results"])
    _validate_markdown_consistency(
        (directory / "index_trend_strategy_report.md").read_text(encoding="utf-8"),
        meta,
    )


def _markdown_gate_evidence_lines(assessment: EffectivenessAssessment) -> list[str]:
    """Render the six visible gate disclosures from structured evidence only."""

    lines: list[str] = []
    for evidence in format_gate_evidence(assessment.gates, assessment.values, assessment.reasons):
        result = "\u901a\u8fc7" if evidence.passed else "\u5931\u8d25"
        lines.append(
            f"- `{evidence.name}`\uff1a{result}\uff1b\u5b9e\u9645\u503c\uff1a`{evidence.actual}`\uff1b"
            f"\u9608\u503c\uff1a`{evidence.threshold}`\uff1b\u539f\u56e0\uff1a{evidence.reason}\u3002"
        )
    return lines


def _validate_recalculated_effectiveness(
    meta: Mapping[str, object],
    results: pd.DataFrame,
    buffer_comparison: pd.DataFrame,
    stress_results: pd.DataFrame,
) -> None:
    """Recalculate all six gates from primary evidence under the audited lock."""

    try:
        config_bytes = _LOCKED_CONFIG_PATH.read_bytes()
    except OSError as exc:
        raise ValueError("locked index research config is unavailable") from exc
    if hashlib.sha256(config_bytes).hexdigest() != meta["config_sha256"]:
        raise ValueError("index research config_sha256 disagrees with locked config")
    config = load_index_research_config(_LOCKED_CONFIG_PATH)
    recalculated = evaluate_effectiveness(results, buffer_comparison, stress_results, config)
    if (
        recalculated.status != meta["status"]
        or recalculated.gates != meta["gates"]
        or not _audit_values_match(recalculated.values, meta["gate_values"])
        or list(recalculated.reasons) != meta["gate_reasons"]
    ):
        raise ValueError("recalculated effectiveness disagrees with published gate evidence")


def _audit_values_match(actual: object, expected: object) -> bool:
    """Compare JSON-like evidence with tight tolerance for CSV float round trips."""

    if isinstance(actual, Mapping) and isinstance(expected, Mapping):
        return set(actual) == set(expected) and all(_audit_values_match(actual[key], expected[key]) for key in actual)
    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(_audit_values_match(left, right) for left, right in zip(actual, expected))
    if (
        isinstance(actual, (int, float))
        and not isinstance(actual, bool)
        and isinstance(expected, (int, float))
        and not isinstance(expected, bool)
    ):
        return math.isfinite(float(actual)) and math.isfinite(float(expected)) and math.isclose(
            float(actual), float(expected), rel_tol=1e-12, abs_tol=1e-12
        )
    return type(actual) is type(expected) and actual == expected


def _extract_markdown_gate_evidence_lines(markdown: str) -> list[str]:
    """Extract exactly one visible line for each locked gate without parsing values."""

    lines: list[str] = []
    positions: list[int] = []
    for name in _GATE_NAMES:
        prefix = f"- `{name}`"
        if markdown.count(prefix) != 1:
            raise ValueError("index research markdown gate evidence is missing or duplicated")
        start = markdown.index(prefix)
        end = markdown.find("\n", start)
        lines.append(markdown[start:] if end == -1 else markdown[start:end])
        positions.append(start)
    if positions != sorted(positions):
        raise ValueError("index research markdown gate evidence is out of order")
    return lines


def _validate_markdown_consistency(
    markdown: str,
    meta: Mapping[str, object],
) -> None:
    """Strictly bind the visible gate evidence to the structured artifacts."""

    assessment = EffectivenessAssessment(
        status=str(meta["status"]),
        gates=dict(meta["gates"]),
        values=dict(meta["gate_values"]),
        reasons=tuple(meta["gate_reasons"]),
    )
    if _extract_markdown_gate_evidence_lines(markdown) != _markdown_gate_evidence_lines(assessment):
        raise ValueError("index research markdown gate evidence disagrees with structured evidence")


def _read_meta(path: Path, run_id: str) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("index research run metadata is corrupt") from exc
    if not isinstance(raw, dict):
        raise ValueError("index research run metadata must be an object")
    meta = _normalise_run_meta(raw)
    if meta["run_id"] != run_id:
        raise ValueError("index research metadata run_id does not match latest pointer")
    return meta


def _read_csv(path: Path) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            path,
            encoding="utf-8",
            dtype={
                "index_code": "string", "name": "string", "cohort": "string", "market": "string",
                "index_type": "string", "period_type": "string", "period_label": "string",
                "strategy_name": "string", "action": "string", "reason": "string", "reason_code": "string",
                "section": "string", "group_type": "string", "group_value": "string", "metric": "string",
                "status": "string",
            },
        )
    except (OSError, UnicodeError, pd.errors.ParserError) as exc:
        raise ValueError(f"index research CSV is unreadable: {path.name}") from exc
    required = _CSV_REQUIRED_COLUMNS.get(path.name, frozenset())
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"index research CSV schema is invalid: {path.name}; missing={sorted(missing)}")
    if path.name != "index_strategy_summary.csv":
        _validate_frame_schema(frame, path.name)
    return frame


def _read_nav(path: Path) -> pd.DataFrame:
    try:
        nav = pd.read_parquet(path)
    except (OSError, ValueError) as exc:
        raise ValueError("index research NAV is unreadable") from exc
    _validate_nav(nav)
    return nav


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def _replace_latest_pointer(root: Path, run_id: str) -> None:
    temporary = root / f".latest-{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(_json_dumps({"run_id": run_id}), encoding="utf-8")
        os.replace(temporary, root / "latest.json")
    except Exception:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
        raise


def _safe_run_id(run_id: str) -> bool:
    return bool(_RUN_ID_PATTERN.fullmatch(run_id)) and run_id not in {".", ".."} and not run_id.endswith(".staging")


def _json_dumps(value: object) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _json_safe(value: object) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON metadata values must be finite")
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if pd.isna(value):
        return None
    raise ValueError(f"JSON metadata value is not serializable: {type(value).__name__}")


def _exclusions_frame(meta: Mapping[str, object]) -> pd.DataFrame:
    exclusions = meta.get("exclusions", [])
    return pd.DataFrame(exclusions if isinstance(exclusions, list) else [], columns=["index_code", "name", "reason_code"])
