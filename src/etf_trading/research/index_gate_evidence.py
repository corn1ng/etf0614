"""Shared, presentation-ready evidence for the six locked effectiveness gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


EFFECTIVENESS_GATE_NAMES = (
    "drawdown_win_rate",
    "median_drawdown_reduction",
    "median_calmar_improves",
    "median_return_is_retained",
    "buffer_reduces_whipsaw_rate_and_trades",
    "stress_keeps_first_four_gates",
)


@dataclass(frozen=True)
class GateEvidence:
    """One gate's complete observed value, locked threshold, and audit reason."""

    name: str
    passed: bool
    actual: object
    threshold: str
    reason: str


def format_gate_evidence(
    gates: Mapping[str, bool],
    values: Mapping[str, object],
    reasons: Sequence[str],
) -> tuple[GateEvidence, ...]:
    """Format structured gate evidence identically for reports and UI surfaces."""

    evidence: list[GateEvidence] = []
    for name in EFFECTIVENESS_GATE_NAMES:
        actual, threshold = _gate_detail(name, values)
        reason = "; ".join(item for item in reasons if item.startswith(f"{name}:")) or "通过"
        evidence.append(GateEvidence(name, bool(gates[name]), actual, threshold, reason))
    return tuple(evidence)


def _gate_detail(name: str, values: Mapping[str, object]) -> tuple[object, str]:
    if name == "drawdown_win_rate":
        return values.get("drawdown_win_rate", "未提供"), "至少 0.60"
    if name == "median_drawdown_reduction":
        return values.get("median_drawdown_reduction", "未提供"), "至少 0.20"
    if name == "median_calmar_improves":
        return (
            f"V1={values.get('median_calmar_v1', '未提供')}; "
            f"买入持有={values.get('median_calmar_buy_hold', '未提供')}",
            "V1 中位 Calmar 高于买入持有",
        )
    if name == "median_return_is_retained":
        return (
            f"V1={values.get('median_annual_return_v1', '未提供')}; "
            f"买入持有={values.get('median_annual_return_buy_hold', '未提供')}",
            "V1 中位年化收益不低于买入持有减 0.02",
        )
    if name == "buffer_reduces_whipsaw_rate_and_trades":
        return (
            f"假突破率 0%={values.get('whipsaw_rate_0', '未提供')}, "
            f"2%={values.get('whipsaw_rate_2', '未提供')}; "
            f"交易/年 0%={values.get('trades_per_year_0', '未提供')}, "
            f"2%={values.get('trades_per_year_2', '未提供')}",
            "2% 两项均严格低于 0%",
        )
    if name == "stress_keeps_first_four_gates":
        return _format_stress_first_four_gates(values.get("stress_first_four_gates")), "双倍费用下前四项均通过"
    return values.get(name, "未提供"), "预设门槛"


def _format_stress_first_four_gates(value: object) -> object:
    if not isinstance(value, Mapping):
        return "未提供" if value is None else value
    first_four = EFFECTIVENESS_GATE_NAMES[:4]
    ordered = {name: value[name] for name in first_four if name in value}
    ordered.update({name: value[name] for name in sorted(set(value).difference(ordered))})
    return ordered
