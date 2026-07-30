import inspect
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


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
    assert "IndexResearchPageController" in section
    assert "run_index_research(" not in section
    assert "run_and_publish_index_research(" not in section


def test_selector_filters_nav_to_full_history_and_all_linked_evidence_to_selected_index():
    from etf_trading.nicegui_app.pages.research import _filtered_index_research_evidence

    loaded = SimpleNamespace(
        nav=pd.DataFrame([
            {"index_code": "A", "period_type": "full_history", "strategy_name": "index_trend_v1", "trade_date": "2026-01-01", "nav": 1.0},
            {"index_code": "A", "period_type": "calendar_year", "strategy_name": "index_trend_v1", "trade_date": "2026-01-02", "nav": 1.1},
            {"index_code": "B", "period_type": "full_history", "strategy_name": "buy_hold", "trade_date": "2026-01-01", "nav": 1.0},
        ]),
        trades=pd.DataFrame([{"index_code": "A", "period_type": "full_history"}, {"index_code": "B", "period_type": "full_history"}]),
        yearly=pd.DataFrame([{"index_code": "A"}, {"index_code": "B"}]),
        rolling=pd.DataFrame([{"index_code": "A"}, {"index_code": "B"}]),
    )

    evidence = _filtered_index_research_evidence(loaded, "A")

    assert set(evidence) == {"nav", "trades", "yearly", "rolling"}
    assert set(evidence["nav"]["index_code"]) == {"A"}
    assert set(evidence["nav"]["period_type"]) == {"full_history"}
    for key in ("trades", "yearly", "rolling"):
        assert set(evidence[key]["index_code"]) == {"A"}


def test_nav_chart_keeps_each_strategy_separate_and_has_no_duplicate_dates():
    from etf_trading.nicegui_app.pages.research import _index_research_nav_payload

    payload = _index_research_nav_payload(pd.DataFrame([
        {"strategy_name": "index_trend_v1", "trade_date": "2026-01-01", "nav": 1.0},
        {"strategy_name": "index_trend_v1", "trade_date": "2026-01-01", "nav": 1.1},
        {"strategy_name": "buy_hold", "trade_date": "2026-01-01", "nav": 1.0},
    ]))

    lines = [item for item in payload[0]["series"] if "回撤" not in item["options"]["title"]]
    assert {item["options"]["title"] for item in lines} == {"index_trend_v1", "buy_hold"}
    assert len(next(item for item in lines if item["options"]["title"] == "index_trend_v1")["data"]) == 1


@pytest.mark.parametrize("exc", [OSError("<disk failure>"), PermissionError("<denied>"), TypeError("<bad type>")])
def test_strict_loader_converts_expected_read_errors_to_safe_invalid_state(monkeypatch, exc):
    from etf_trading.nicegui_app.pages import research

    monkeypatch.setattr(research, "load_latest_index_research", lambda _root: (_ for _ in ()).throw(exc))

    loaded, state, diagnostic = research._load_index_research_for_page("unused")

    assert loaded is None
    assert state == "invalid"
    assert "<" not in diagnostic and ">" not in diagnostic


def test_page_controller_polls_jobs_without_reloading_evidence_until_completed_transition():
    from etf_trading.nicegui_app.pages.research import IndexResearchPageController

    class Manager:
        def __init__(self):
            self.current = SimpleNamespace(status="queued")

        def snapshot(self):
            return self.current

    calls = {"loader": 0, "stale": 0}
    loaded = SimpleNamespace(run_meta={"limited_run": False})

    def loader(_root):
        calls["loader"] += 1
        return loaded

    def stale(_meta, _store):
        calls["stale"] += 1
        return False

    manager = Manager()
    controller = IndexResearchPageController("reports", object(), manager, loader=loader, stale_checker=stale)
    controller.load_evidence()
    controller.poll()
    controller.poll()
    assert calls == {"loader": 1, "stale": 1}

    manager.current = SimpleNamespace(status="completed")
    assert controller.poll() is True
    controller.poll()
    assert calls == {"loader": 2, "stale": 2}


@pytest.mark.parametrize(
    ("evidence_status", "limited", "job_status"),
    [
        ("missing", False, "idle"), ("invalid", False, "idle"), ("stale", False, "idle"),
        ("available", False, "idle"), ("available", True, "idle"), ("available", False, "queued"),
        ("available", False, "running"), ("available", False, "completed"), ("available", False, "failed"),
        ("available", False, "cancelled"),
    ],
)
def test_page_state_exposes_evidence_and_job_states(evidence_status, limited, job_status):
    from etf_trading.nicegui_app.pages.research import IndexResearchPageState

    state = IndexResearchPageState(
        evidence_status=evidence_status,
        limited=limited,
        job=SimpleNamespace(status=job_status),
        diagnostic="",
        loaded=None,
    )

    assert state.evidence_status == evidence_status
    assert state.limited is limited
    assert state.job.status == job_status
    assert state.can_start is (job_status not in {"queued", "running"})
    assert state.can_cancel is (job_status in {"queued", "running"})
