import pandas as pd

from etf_trading.ui.state import summarize_platform_status


def test_status_summary_marks_ready_platform_when_no_issues():
    status = {
        "eligible_index_count": 3,
        "eligible_categories": ["A股宽基", "A股行业"],
        "enabled_watchlist": pd.DataFrame({"etf_code": ["510300", "512880"]}),
        "issues": [],
    }

    summary = summarize_platform_status(status)

    assert summary.data_health == "已就绪"
    assert summary.eligible_index_count == 3
    assert summary.eligible_category_count == 2
    assert summary.enabled_watchlist_count == 2
    assert summary.issue_count == 0


def test_status_summary_marks_attention_when_issues_exist():
    status = {
        "eligible_index_count": 0,
        "eligible_categories": [],
        "enabled_watchlist": pd.DataFrame(),
        "issues": [
            {"title": "补齐指数历史", "detail": "数据维护中执行一键补齐。"},
            {"title": "建立每日计算池", "detail": "ETF数据中加入常看 ETF。"},
        ],
    }

    summary = summarize_platform_status(status)

    assert summary.data_health == "需处理"
    assert summary.eligible_index_count == 0
    assert summary.eligible_category_count == 0
    assert summary.enabled_watchlist_count == 0
    assert summary.issue_count == 2
