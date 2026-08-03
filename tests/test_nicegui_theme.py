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


def test_theme_allows_mobile_workbench_topbar_to_wrap_without_overlapping_page_header():
    mobile_css = WORKBENCH_CSS.split("@media (max-width: 720px) {", 1)[1]
    topbar_rule = mobile_css.split(".workbench-topbar {", 1)[1].split("}", 1)[0]

    assert "height: auto;" in topbar_rule
    assert "min-height:" in topbar_rule
    assert "flex-wrap: wrap;" in topbar_rule
    assert "padding:" in topbar_rule
    assert "gap:" in topbar_rule


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


def test_theme_contains_index_atomic_workbench_layout_hooks():
    for css_class in [
        ".index-atomic-alert",
        ".index-atomic-dialog",
        ".index-atomic-detail-grid",
    ]:
        assert css_class in WORKBENCH_CSS
    assert ".index-atomic-detail-grid {" in WORKBENCH_CSS
    assert "grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));" in WORKBENCH_CSS


def test_theme_contains_readable_index_atomic_overview_rules():
    for css_class in [
        ".index-atomic-overview-grid", ".index-atomic-overview-card", ".index-atomic-ma-ladder",
        ".index-atomic-range-track", ".index-atomic-event-timeline", ".index-atomic-expand-group",
        ".index-atomic-evidence-groups", ".index-atomic-full-groups",
    ]:
        assert css_class in WORKBENCH_CSS
    assert "grid-template-columns: repeat(4, minmax(0, 1fr));" in WORKBENCH_CSS
    assert "@media (max-width: 960px)" in WORKBENCH_CSS
    assert ".index-atomic-overview-grid { grid-template-columns: 1fr; }" in WORKBENCH_CSS
    assert "overflow-x: clip;" in WORKBENCH_CSS


def test_theme_contains_positioned_index_atomic_ma_ladder_markers():
    for css_class in [
        ".index-atomic-ma-ladder", ".index-atomic-ma-marker", ".index-atomic-ma-marker-label",
        ".index-atomic-ma-marker-value", ".index-atomic-range-labels",
    ]:
        assert css_class in WORKBENCH_CSS
    assert "bottom: 0;" in WORKBENCH_CSS
    ladder_rule = WORKBENCH_CSS.split(".index-atomic-ma-ladder {", 1)[1].split("}", 1)[0]
    assert "\n  height: 124px;" in ladder_rule
    marker_rule = WORKBENCH_CSS.split(".index-atomic-ma-marker {", 1)[1].split("}", 1)[0]
    assert "\n  height: 14px;" in marker_rule
    assert "transform:" not in marker_rule
    assert ".index-atomic-ma-marker-label { position: relative; z-index: 1; }" in WORKBENCH_CSS


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
