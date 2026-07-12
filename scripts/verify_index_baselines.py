"""Verify durable evidence for the formal index catalogue's history baselines."""

from __future__ import annotations

import argparse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from pathlib import Path
import sys

import pandas as pd

import etf_trading.data.initialization as initialization
from etf_trading.data.index_catalog import DEFAULT_BASELINE_EVIDENCE_PATH
from etf_trading.data.initialization import InitializationService
from etf_trading.data.storage import SQLiteStore


_STATUS_LABELS = {
    "OFFICIAL": "官方已核验",
    "THIRD_PARTY_BASE_DATE": "第三方参考基日",
    "THIRD_PARTY_PUBLICATION": "第三方发布日期参考",
    "UNRESOLVED": "起点无法确认",
}


class _ChineseArgumentParser(argparse.ArgumentParser):
    """Keep command-line guidance fully Chinese for local users."""

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "用法：")

    def format_help(self) -> str:
        return (
            super()
            .format_help()
            .replace("usage:", "用法：")
            .replace("\noptions:\n", "\n选项：\n")
            .replace("\noptional arguments:\n", "\n选项：\n")
        )

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        display_message = message if any("\u4e00" <= char <= "\u9fff" for char in message) else "命令行参数无效，请使用 --help 查看用法。"
        self.exit(2, f"{self.prog}: 错误：{display_message}\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Run formal-index baseline verification and print one durable result per code."""

    parser = _argument_parser()
    args = parser.parse_args(argv)
    if not args.formal:
        parser.error("必须提供 --formal 以确认仅核验正式指数池")
    if args.through is None:
        parser.error("必须提供 --through 作为证据核验日期")
    through = _parse_date(args.through, parser)
    evidence_path = Path(args.evidence_path) if args.evidence_path is not None else DEFAULT_BASELINE_EVIDENCE_PATH
    write_evidence = args.write_evidence or args.evidence_path is not None

    service = InitializationService(store=SQLiteStore(args.sqlite_path))
    with _evidence_path(evidence_path):
        results = service.verify_index_baseline_evidence(through, write_evidence=write_evidence)

    _print_results(results)
    return 0


def _argument_parser() -> argparse.ArgumentParser:
    parser = _ChineseArgumentParser(description="核验正式指数的历史起点证据。", add_help=False)
    parser.add_argument("-h", "--help", action="help", help="显示此帮助信息并退出。")
    parser.add_argument("--through", help="用于证据核验的日期，格式为 YYYY-MM-DD。")
    parser.add_argument(
        "--formal",
        action="store_true",
        help="仅核验核心池和研究池中的正式指数。",
    )
    parser.add_argument(
        "--write-evidence",
        action="store_true",
        help="将可信核验结果写入配置的证据 YAML 文件。",
    )
    parser.add_argument(
        "--evidence-path",
        help="可选的证据 YAML 目标路径；指定后也会写入结果。",
    )
    parser.add_argument(
        "--sqlite-path",
        default="database/etf_system.sqlite",
        help="SQLite 指数目录投影文件路径。",
    )
    return parser


def _parse_date(value: str, parser: argparse.ArgumentParser) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        parser.error("--through 必须为 YYYY-MM-DD 格式的日期")
        raise AssertionError("argparse.error does not return")


@contextmanager
def _evidence_path(path: Path) -> Iterator[None]:
    """Temporarily point the existing maintenance service at the requested YAML."""

    original_path = initialization.DEFAULT_BASELINE_EVIDENCE_PATH
    initialization.DEFAULT_BASELINE_EVIDENCE_PATH = path
    try:
        yield
    finally:
        initialization.DEFAULT_BASELINE_EVIDENCE_PATH = original_path


def _print_results(results: pd.DataFrame) -> None:
    statuses = results.get("evidence_status", pd.Series(dtype=str)).fillna("").astype(str)
    for status in ("OFFICIAL", "THIRD_PARTY_BASE_DATE", "THIRD_PARTY_PUBLICATION", "UNRESOLVED"):
        print(f"{_status_label(status)}（{status}）：{int((statuses == status).sum())}")

    for row in results.to_dict(orient="records"):
        code = str(row.get("index_code") or "")
        status = str(row.get("evidence_status") or "UNRESOLVED")
        reference_date = str(row.get("reference_date") or "未提供")
        detail = str(row.get("detail") or "无")
        print(
            f"{code}｜核验结果：{_status_label(status)}（{status}）"
            f"｜参考日期：{reference_date}｜说明：{detail}"
        )


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, "未知核验状态")


if __name__ == "__main__":
    raise SystemExit(main())
