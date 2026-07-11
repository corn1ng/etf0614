import inspect

from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app import layout
from etf_trading.nicegui_app.theme import WORKBENCH_CSS, tone_class


def test_theme_contains_dense_professional_workbench_rules():
    assert ".workbench-shell" in WORKBENCH_CSS
    assert ".workbench-sidebar" in WORKBENCH_CSS
    assert ".workbench-topbar" in WORKBENCH_CSS
    assert ".workbench-page-header" in WORKBENCH_CSS
    assert ".workbench-section-tabs" in WORKBENCH_CSS
    assert ".workbench-data-table" in WORKBENCH_CSS
    assert "height: 34px" in WORKBENCH_CSS
    assert "overflow-x: auto" in WORKBENCH_CSS


def test_theme_keeps_mobile_sidebar_navigation_labels_readable():
    assert "@media (max-width: 720px)" in WORKBENCH_CSS
    assert ".workbench-sidebar { width: 58px; flex-shrink: 0; }" in WORKBENCH_CSS
    assert ".workbench-nav-item::before" in WORKBENCH_CSS
    assert "content: attr(data-short);" in WORKBENCH_CSS
    assert "data-short" in inspect.getsource(layout._render_sidebar)
    assert "#0f172a" in WORKBENCH_CSS


def test_tone_class_maps_unknown_to_neutral():
    assert tone_class("success") == "tone-success"
    assert tone_class("warning") == "tone-warning"
    assert tone_class("unknown") == "tone-neutral"


def test_table_columns_derive_stable_field_names():
    columns = table_columns([{"ETF代码": "510300", "状态": "完整"}])

    assert columns == [
        {"name": "ETF代码", "label": "ETF代码", "field": "ETF代码", "align": "left"},
        {"name": "状态", "label": "状态", "field": "状态", "align": "left"},
    ]


def test_theme_contains_atomic_detail_layout_hooks():
    assert ".workbench-detail-grid" in WORKBENCH_CSS
    assert ".workbench-detail-group-title" in WORKBENCH_CSS
    assert ".atomic-workbench-grid" in WORKBENCH_CSS
    assert ".atomic-inspector" in WORKBENCH_CSS
    assert ".atomic-detail-row" in WORKBENCH_CSS


def test_task_center_theme_classes_exist():
    for css_class in [
        ".workbench-task-center",
        ".workbench-task-center-header",
        ".workbench-task-center-status",
        ".workbench-task-center-meta",
        ".workbench-task-center-result",
    ]:
        assert css_class in WORKBENCH_CSS


def test_theme_contains_atomic_data_health_layout_hooks():
    for css_class in [
        ".atomic-data-health",
        ".atomic-data-health-header",
        ".atomic-data-health-status",
        ".atomic-data-health-note",
        ".atomic-data-health-items",
        ".atomic-data-health-item",
        ".atomic-data-health-detail",
    ]:
        assert css_class in WORKBENCH_CSS
