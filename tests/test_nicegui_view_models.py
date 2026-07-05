from datetime import datetime

import pandas as pd

from etf_trading.nicegui_app.view_models import (
    PlatformSnapshot,
    current_ui_audit_findings,
    etf_overview_rows,
    maintenance_rows,
    market_overview,
    status_metrics,
)


def _snapshot() -> PlatformSnapshot:
    return PlatformSnapshot(
        master=pd.DataFrame(
            {
                "ETF代码": ["510300", "512880"],
                "ETF名称": ["沪深300ETF", "证券ETF"],
                "分类": ["A股宽基", "A股行业"],
                "交易所": ["SH", "SH"],
                "成交额": [120000000.0, 80000000.0],
            }
        ),
        watchlist=pd.DataFrame({"etf_code": ["510300"], "allow_buy": [True], "enabled": [True]}),
        index_summary=pd.DataFrame(
            {
                "index_code": ["000300", "000905"],
                "index_name": ["沪深300", "中证500"],
                "category": ["A股宽基", "A股宽基"],
                "allows_new_position": [True, False],
                "history_rows": [300, 30],
                "latest_date": ["2026-07-03", "2026-07-03"],
            }
        ),
        universe=pd.DataFrame({"etf_code": ["510300"], "is_top_sample": [True]}),
        gaps=pd.DataFrame({"数据类型": ["指数历史"], "状态": ["历史不足"]}),
        coverage=pd.DataFrame({"数据类型": ["ETF历史"], "覆盖率": ["50.0%"]}),
        generated_at=datetime(2026, 7, 5, 10, 0, 0),
    )


def test_status_metrics_are_dense_and_human_readable():
    metrics = status_metrics(_snapshot())

    assert [metric.label for metric in metrics] == ["ETF总数", "计算池", "可参与指数", "数据缺口"]
    assert [metric.value for metric in metrics] == ["2", "1", "1", "1"]
    assert metrics[-1].tone == "warning"


def test_current_ui_audit_findings_cover_high_frequency_pages():
    findings = current_ui_audit_findings()
    pages = {finding.page_slug for finding in findings}

    assert {"action", "market", "etf-data", "maintenance"}.issubset(pages)
    assert all(finding.problem and finding.fix for finding in findings)


def test_market_overview_groups_index_state():
    overview = market_overview(_snapshot())

    assert overview["total_indexes"] == 2
    assert overview["allowed_indexes"] == 1
    assert overview["categories"] == [{"category": "A股宽基", "total": 2, "allowed": 1}]


def test_table_rows_convert_dataframes_to_records():
    snapshot = _snapshot()

    assert etf_overview_rows(snapshot)[0]["ETF代码"] == "510300"
    assert maintenance_rows(snapshot) == [{"数据类型": "指数历史", "状态": "历史不足"}]


def test_market_audit_names_density_and_chart_fixes():
    market_findings = [item for item in current_ui_audit_findings() if item.page_slug == "market"]

    assert any("K线" in item.problem or "图表" in item.problem for item in market_findings)
    assert any("工具栏" in item.fix or "图表" in item.fix for item in market_findings)


def test_etf_and_maintenance_audit_notes_are_explicit():
    findings = current_ui_audit_findings()
    by_page = {}
    for finding in findings:
        by_page.setdefault(finding.page_slug, []).append(finding)

    assert any("ETF" in item.problem for item in by_page["etf-data"])
    assert any("健康" in item.problem or "补齐" in item.fix for item in by_page["maintenance"])
