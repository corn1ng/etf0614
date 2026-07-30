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
from etf_trading.research.index_models import IndexAdmissionResult, IndexResearchConfig, IndexResearchOutput
from etf_trading.research.index_models import load_index_research_config
from etf_trading.research.index_validation import run_index_research


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
_CSV_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "index_backtest_results.csv": frozenset({"index_code", "period_type", "strategy_name"}),
    "index_backtest_trades.csv": frozenset({"index_code"}),
    "index_strategy_summary.csv": frozenset({"section"}),
    "index_strategy_yearly.csv": frozenset({"index_code", "period_type", "strategy_name"}),
    "index_strategy_rolling_5y.csv": frozenset({"index_code", "period_type", "strategy_name"}),
    "index_strategy_buffer_comparison.csv": frozenset({"index_code", "buffer_rate"}),
    "index_strategy_exclusions.csv": frozenset({"index_code", "name", "reason_code"}),
}


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
    return LoadedIndexResearch(
        run_id=run_id,
        run_dir=run_dir,
        run_meta=meta,
        results=_read_csv(run_dir / "index_backtest_results.csv"),
        trades=_read_csv(run_dir / "index_backtest_trades.csv"),
        summary=_read_csv(run_dir / "index_strategy_summary.csv"),
        yearly=_read_csv(run_dir / "index_strategy_yearly.csv"),
        rolling=_read_csv(run_dir / "index_strategy_rolling_5y.csv"),
        buffer_comparison=_read_csv(run_dir / "index_strategy_buffer_comparison.csv"),
        exclusions=_read_csv(run_dir / "index_strategy_exclusions.csv"),
        nav=pd.read_parquet(run_dir / "index_strategy_nav.parquet"),
        report_markdown=(run_dir / "index_trend_strategy_report.md").read_text(encoding="utf-8"),
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
    for name, passed in assessment.gates.items():
        value, threshold = _gate_detail(name, assessment.values)
        reason = "; ".join(reason for reason in assessment.reasons if reason.startswith(f"{name}:")) or "通过"
        lines.append(f"- `{name}`：{'通过' if passed else '失败'}；实际值：`{value}`；阈值：`{threshold}`；原因：{reason}。")
    full_history = output.results[output.results["period_type"] == "full_history"] if "period_type" in output.results else output.results
    lines.extend(_table_section("全历史配对结果", full_history))
    lines.extend(_table_section("五年滚动稳定性", output.rolling))
    lines.extend(_table_section("0/2/3% 缓冲诊断", output.buffer_comparison))
    lines.extend(_table_section("双倍费用", output.stress_results))
    lines.extend(_table_section("年度/阶段", output.yearly))
    lines.extend(_table_section("最好与最差指数", output.worst_indices))
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
    output = research_runner(admission, config)
    return publish_index_research(output, report_root, _build_run_meta(config_file, config, admission, output, limit))


def _write_artifacts(directory: Path, output: IndexResearchOutput, meta: dict[str, object]) -> None:
    _write_csv(directory / "index_backtest_results.csv", output.results)
    _write_csv(directory / "index_backtest_trades.csv", output.trades)
    _write_csv(directory / "index_strategy_summary.csv", _summary_frame(output))
    _write_csv(directory / "index_strategy_yearly.csv", output.yearly)
    _write_csv(directory / "index_strategy_rolling_5y.csv", output.rolling)
    _write_csv(directory / "index_strategy_buffer_comparison.csv", output.buffer_comparison)
    _write_csv(directory / "index_strategy_exclusions.csv", _exclusions_frame(meta))
    output.nav.to_parquet(directory / "index_strategy_nav.parquet", index=False)
    (directory / "index_trend_strategy_report.md").write_text(render_index_research_markdown(output, meta), encoding="utf-8")
    (directory / "index_trend_strategy_run.json").write_text(_json_dumps(meta), encoding="utf-8")


def _summary_frame(output: IndexResearchOutput) -> pd.DataFrame:
    gate_rows = pd.DataFrame([
        {"section": "effectiveness_gate", "name": name, "passed": passed,
         "value": output.effectiveness.values.get(name),
         "reason": "; ".join(reason for reason in output.effectiveness.reasons if reason.startswith(f"{name}:"))}
        for name, passed in output.effectiveness.gates.items()
    ])
    status = pd.DataFrame([{"section": "effectiveness_status", "name": "overall", "passed": output.effectiveness.status == "passed", "value": output.effectiveness.status, "reason": "; ".join(output.effectiveness.reasons)}])
    groups = output.group_statistics.copy()
    if not groups.empty:
        groups.insert(0, "section", "group_statistics")
    rolling = output.rolling_gate_summary.copy()
    if not rolling.empty:
        rolling.insert(0, "section", "rolling_gate_summary")
    worst = output.worst_indices.copy()
    if not worst.empty:
        worst.insert(0, "section", "worst_indices")
    return pd.concat([status, gate_rows, groups, rolling, worst], ignore_index=True, sort=False)


def _table_section(title: str, frame: pd.DataFrame) -> list[str]:
    lines = ["", f"## {title}"]
    if frame.empty:
        return [*lines, "- 无可报告数据。"]
    preview = frame.head(10).copy()
    for column in preview.select_dtypes(include=["datetime", "datetimetz"]).columns:
        preview[column] = preview[column].astype(str)
    return [*lines, preview.to_markdown(index=False)]


def _gate_detail(name: str, values: Mapping[str, object]) -> tuple[object, str]:
    """Make each locked gate's observed evidence and pre-set rule visible."""

    if name == "drawdown_win_rate":
        return values.get("drawdown_win_rate", "未提供"), "至少 0.60"
    if name == "median_drawdown_reduction":
        return values.get("median_drawdown_reduction", "未提供"), "至少 0.20"
    if name == "median_calmar_improves":
        return f"V1={values.get('median_calmar_v1', '未提供')}; 买入持有={values.get('median_calmar_buy_hold', '未提供')}", "V1 中位 Calmar 高于买入持有"
    if name == "median_return_is_retained":
        return f"V1={values.get('median_annual_return_v1', '未提供')}; 买入持有={values.get('median_annual_return_buy_hold', '未提供')}", "V1 中位年化收益不低于买入持有减 0.02"
    if name == "buffer_reduces_whipsaw_rate_and_trades":
        return f"假突破率 0%={values.get('whipsaw_rate_0', '未提供')}, 2%={values.get('whipsaw_rate_2', '未提供')}; 交易/年 0%={values.get('trades_per_year_0', '未提供')}, 2%={values.get('trades_per_year_2', '未提供')}", "2% 两项均严格低于 0%"
    if name == "stress_keeps_first_four_gates":
        return values.get("stress_first_four_gates", "未提供"), "双倍费用下前四项均通过"
    return values.get(name, "未提供"), "预设门槛"


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
    if not isinstance(meta["gates"], dict) or len(meta["gates"]) != 6 or not all(type(value) is bool for value in meta["gates"].values()):
        raise ValueError("run metadata must contain six boolean gates")
    if not isinstance(meta["gate_values"], dict) or not isinstance(meta["gate_reasons"], list) or not isinstance(meta["exclusions"], list):
        raise ValueError("run metadata has invalid audit fields")
    return _json_safe(meta)


def _build_run_meta(config_path: Path, config: IndexResearchConfig, admission: IndexAdmissionResult, output: IndexResearchOutput, limit: int | None) -> dict[str, object]:
    metadata = admission.metadata if not admission.metadata.empty else pd.DataFrame(columns=["cohort"])
    cutoff_dates = [pd.to_datetime(frame["trade_date"], errors="coerce").max() for frame in admission.frames.values() if not frame.empty]
    cutoff = max((value for value in cutoff_dates if pd.notna(value)), default=pd.Timestamp(config.locked_at)).date().isoformat()
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
    _read_meta(directory / "index_trend_strategy_run.json", run_id)
    for name in REQUIRED_ARTIFACTS:
        path = directory / name
        if name.endswith(".csv"):
            _read_csv(path)
    pd.read_parquet(directory / "index_strategy_nav.parquet")
    (directory / "index_trend_strategy_report.md").read_text(encoding="utf-8")


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
    return frame


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")


def _replace_latest_pointer(root: Path, run_id: str) -> None:
    temporary = root / f".latest-{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(_json_dumps({"run_id": run_id}), encoding="utf-8")
        os.replace(temporary, root / "latest.json")
    finally:
        if temporary.exists():
            temporary.unlink()


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
