from __future__ import annotations

import asyncio
import inspect
from datetime import datetime

import pandas as pd


def test_task_center_renders_idle_and_running_states(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []

    class FakeContainer:
        def clear(self):
            events.append("center_clear")

        def __enter__(self):
            events.append("enter_center")
            return self

        def __exit__(self, *args):
            events.append("exit_center")
            return None

    class FakeElement:
        def __enter__(self):
            events.append("enter_element")
            return self

        def __exit__(self, *args):
            events.append("exit_element")
            return None

        def classes(self, value):
            events.append(f"classes:{value}")
            return self

    class FakeUi:
        def row(self):
            events.append("row")
            return FakeElement()

        def column(self):
            events.append("column")
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

        def badge(self, text):
            events.append(f"badge:{text}")
            return FakeElement()

        def icon(self, name):
            events.append(f"icon:{name}")
            return FakeElement()

    monkeypatch.setattr(maintenance, "ui", FakeUi())

    maintenance._render_task_center(FakeContainer(), maintenance.MaintenanceTaskStatus())
    maintenance._render_task_center(
        FakeContainer(),
        maintenance.MaintenanceTaskStatus(
            title="补齐全部指数历史",
            state="running",
            message="正在执行，请稍候...",
            started_at=datetime(2026, 7, 8, 22, 30, 0),
        ),
    )

    assert "label:任务中心" in events
    assert "badge:空闲" in events
    assert "label:暂无任务" in events
    assert "badge:运行中" in events
    assert "label:补齐全部指数历史" in events
    assert "label:正在执行，请稍候..." in events
    assert "label:开始 2026-07-08 22:30:00" in events


def test_task_center_renders_running_progress(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []

    class FakeContainer:
        def clear(self):
            events.append("center_clear")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeElement:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def classes(self, value):
            return self

        def props(self, value):
            return self

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

        def badge(self, text):
            events.append(f"badge:{text}")
            return FakeElement()

        def icon(self, name):
            return FakeElement()

        def linear_progress(self, value=0):
            events.append(f"progress:{value:.2f}")
            return FakeElement()

    monkeypatch.setattr(maintenance, "ui", FakeUi())

    maintenance._render_task_center(
        FakeContainer(),
        maintenance.MaintenanceTaskStatus(
            title="补齐全部ETF历史",
            state="running",
            message="补齐全部ETF历史正在执行，请稍候...",
            progress_done=2,
            progress_total=5,
            progress_detail="512880 INITIALIZED",
        ),
    )

    assert "progress:0.40" in events
    assert "label:2/5 · 512880 INITIALIZED" in events


def test_etf_history_tasks_include_resumable_all_etf_button(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []
    buttons = {}

    class FakeElement:
        value = None

        def __init__(self, value=None):
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def classes(self, value):
            return self

        def props(self, value):
            return self

    class FakeUi:
        def expansion(self, title, icon=None):
            events.append(f"expansion:{title}:{icon}")
            return FakeElement()

        def row(self):
            return FakeElement()

        def select(self, options, value=None, label=None):
            return FakeElement(value)

        def input(self, label, value=None):
            return FakeElement(value)

        def button(self, text, icon=None, on_click=None):
            events.append(f"button:{text}:{icon}")
            buttons[text] = on_click
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

    class FakeService:
        def __init__(self):
            self.calls = []

        def fetch_and_store_history(self, *args, **kwargs):
            return pd.DataFrame()

        def ensure_all_etf_history(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            kwargs["on_progress"](
                maintenance.EtfHistoryProgressView(done=1, total=2, etf_code="510300", status="SKIPPED")
            )
            return pd.DataFrame(
                [
                    {"etf_code": "510300", "status": "SKIPPED"},
                    {"etf_code": "512880", "status": "INITIALIZED"},
                ]
            )

    fake_service = FakeService()
    captured = {}

    def fake_run_task(button, task_center, task_status, title, action, success_message):
        result = action()
        captured["title"] = title
        captured["message"] = success_message(result)
        captured["progress_done"] = task_status.progress_done
        captured["progress_total"] = task_status.progress_total
        return result

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance, "etf_overview_rows", lambda snapshot: [])
    monkeypatch.setattr(maintenance, "etf_choice_options", lambda rows: ["510300 Fresh ETF"])
    monkeypatch.setattr(maintenance, "_service_with_provider", lambda store, parquet_store: fake_service)
    monkeypatch.setattr(maintenance, "_run_task", fake_run_task)

    task_status = maintenance.MaintenanceTaskStatus()
    maintenance._render_etf_history_tasks(object(), object(), object(), FakeElement(), task_status)
    buttons["一键初始化/补齐全部ETF"]()

    assert "button:一键初始化/补齐全部ETF:sync" in events
    assert captured["title"] == "补齐全部ETF历史"
    assert captured["message"] == "已检查 2 只 ETF：补齐 1，跳过 1，失败 0"
    assert captured["progress_done"] == 1
    assert captured["progress_total"] == 2
    args, kwargs = fake_service.calls[0]
    assert kwargs["refresh_master"] is True
    assert kwargs["sleep_seconds"] == 0.15


def test_maintenance_task_center_updates_before_io_bound_work(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    assert inspect.iscoroutinefunction(maintenance._run_task)

    events: list[str] = []
    io_bound_entered = False

    class FakeButton:
        def disable(self):
            events.append("disable")

        def enable(self):
            events.append("enable")

        def update(self):
            events.append("button_update")

    class FakeContainer:
        def clear(self):
            events.append("center_clear")

        def update(self):
            events.append("center_update")

        def __enter__(self):
            events.append("enter_center")
            return self

        def __exit__(self, *args):
            events.append("exit_center")
            return None

    class FakeElement:
        def __enter__(self):
            events.append("enter_element")
            return self

        def __exit__(self, *args):
            events.append("exit_element")
            return None

        def classes(self, value):
            return self

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def icon(self, name):
            events.append(f"icon:{name}")
            return FakeElement()

        def badge(self, text):
            events.append(f"badge:{text}")
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

        def table(self, columns, rows, pagination=None):
            events.append("table")
            return FakeElement()

        def notify(self, message, type=None):
            events.append(f"notify:{type}:{message}")

    async def fake_io_bound(callback):
        nonlocal io_bound_entered
        events.append("io_bound")
        io_bound_entered = True
        return callback()

    def action():
        assert io_bound_entered
        events.append("action")
        return [{"index_code": "000300"}]

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance.run, "io_bound", fake_io_bound)
    monkeypatch.setattr(maintenance, "invalidate_snapshot_cache", lambda: events.append("invalidate"))

    task_status = maintenance.MaintenanceTaskStatus()
    asyncio.run(
        maintenance._run_task(
            FakeButton(),
            FakeContainer(),
            task_status,
            "补齐全部指数历史",
            action,
            lambda result: f"已检查 {len(result)} 个指数",
        )
    )

    io_bound_position = events.index("io_bound")
    assert events.index("disable") < io_bound_position
    assert events.index("badge:运行中") < io_bound_position
    assert events.index("label:补齐全部指数历史") < io_bound_position
    assert events.index("label:补齐全部指数历史正在执行，请稍候...") < io_bound_position
    assert events.index("notify:info:补齐全部指数历史正在执行，请稍候...") < io_bound_position
    assert events.index("button_update") < io_bound_position
    assert events.index("center_update") < io_bound_position
    assert "notify:positive:已检查 1 个指数" in events
    assert "badge:成功" in events
    assert "table" in events
    assert task_status.state == "success"
    assert task_status.result == [{"index_code": "000300"}]
    assert events[-1] == "enable"


def test_maintenance_task_center_shows_failure(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []

    class FakeButton:
        def disable(self):
            events.append("disable")

        def enable(self):
            events.append("enable")

        def update(self):
            events.append("button_update")

    class FakeContainer:
        def clear(self):
            events.append("center_clear")

        def update(self):
            events.append("center_update")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeElement:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def classes(self, value):
            return self

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def icon(self, name):
            return FakeElement()

        def badge(self, text):
            events.append(f"badge:{text}")
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

        def notify(self, message, type=None):
            events.append(f"notify:{type}:{message}")

    async def fake_io_bound(callback):
        return callback()

    def action():
        raise RuntimeError("provider timeout")

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance.run, "io_bound", fake_io_bound)

    task_status = maintenance.MaintenanceTaskStatus()
    asyncio.run(
        maintenance._run_task(
            FakeButton(),
            FakeContainer(),
            task_status,
            "拉取指数历史",
            action,
            lambda result: "不会执行",
        )
    )

    assert "badge:失败" in events
    assert "label:拉取指数历史失败：provider timeout" in events
    assert "notify:negative:拉取指数历史失败：provider timeout" in events
    assert task_status.state == "failed"
    assert task_status.error == "provider timeout"
    assert events[-1] == "enable"


def test_maintenance_task_center_shows_cancelled_when_result_is_none(monkeypatch):
    from etf_trading.nicegui_app.pages import maintenance

    events: list[str] = []

    class FakeButton:
        def disable(self):
            events.append("disable")

        def enable(self):
            events.append("enable")

        def update(self):
            events.append("button_update")

    class FakeContainer:
        def clear(self):
            events.append("center_clear")

        def update(self):
            events.append("center_update")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class FakeElement:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def classes(self, value):
            return self

    class FakeUi:
        def row(self):
            return FakeElement()

        def column(self):
            return FakeElement()

        def icon(self, name):
            return FakeElement()

        def badge(self, text):
            events.append(f"badge:{text}")
            return FakeElement()

        def label(self, text):
            events.append(f"label:{text}")
            return FakeElement()

        def notify(self, message, type=None):
            events.append(f"notify:{type}:{message}")

    async def fake_io_bound(callback):
        return callback()

    monkeypatch.setattr(maintenance, "ui", FakeUi())
    monkeypatch.setattr(maintenance.run, "io_bound", fake_io_bound)

    task_status = maintenance.MaintenanceTaskStatus()
    asyncio.run(
        maintenance._run_task(
            FakeButton(),
            FakeContainer(),
            task_status,
            "补齐全部指数历史",
            lambda: None,
            lambda result: "不会执行",
        )
    )

    assert "badge:取消" in events
    assert "label:补齐全部指数历史已取消或服务正在关闭" in events
    assert "notify:warning:补齐全部指数历史已取消或服务正在关闭" in events
    assert task_status.state == "cancelled"
    assert events[-1] == "enable"
