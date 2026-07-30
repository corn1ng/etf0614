import inspect
from pathlib import Path


def test_page_source_contains_required_run_and_result_states():
    source = Path("src/etf_trading/nicegui_app/pages/research.py").read_text(encoding="utf-8")
    for label in (
        "重新回测", "结果已过期", "策略版本", "数据截止日", "总体结论",
        "五年滚动", "缓冲带诊断", "交易记录", "排除原因", "指数理论回测",
    ):
        assert label in source
    for state in ("missing", "invalid", "queued", "running", "completed", "failed", "cancelled"):
        assert state in source


def test_index_research_page_uses_strict_loader_without_render_time_research_execution():
    from etf_trading.nicegui_app.pages.research import render_index_trend_research

    section = inspect.getsource(render_index_trend_research)
    assert "_load_index_research_for_page" in section
    assert "run_index_research(" not in section
    assert "run_and_publish_index_research(" not in section
