import inspect

from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app import layout
from etf_trading.nicegui_app.theme import WORKBENCH_CSS, tone_class


def test_theme_scopes_profile_width_grid_and_mobile_rules():
    css = WORKBENCH_CSS

    assert ".index-profile-dialog" in css
    assert "width: min(1180px, 92vw)" in css
    assert "max-width: min(1180px, 92vw) !important" in css
    assert ".index-profile-summary-grid" in css
    assert ".index-profile-trend-row" in css
    assert "@media (max-width: 720px)" in css
    mobile = css.split("@media (max-width: 720px)", 1)[1]
    assert ".index-profile-dialog" in mobile
    assert "width: calc(100vw - 48px)" in mobile
    assert "max-width: calc(100vw - 48px) !important" in mobile
    assert "96vw" not in mobile
    assert "grid-template-columns: minmax(0, 1fr)" in mobile


def test_theme_keeps_index_profile_mobile_controls_visible_and_panels_scrollable():
    css = WORKBENCH_CSS
    dialog_rule = css.split(".index-profile-dialog {", 1)[1].split("}", 1)[0]
    tabs_rule = css.split(".index-profile-tabs {", 1)[1].split("}", 1)[0]
    panels_rule = css.split(".index-profile-panels {", 1)[1].split("}", 1)[0]
    title_rule = css.split(".index-profile-title {", 1)[1].split("}", 1)[0]
    mobile = css.split("@media (max-width: 720px)", 1)[1]
    mobile_title_selector = ".index-profile-title,\n  .index-profile-as-of {"

    assert "\n  display: flex;" in dialog_rule
    assert "\n  flex-direction: column;" in dialog_rule
    assert "\n  overflow: hidden;" in dialog_rule
    assert ".index-profile-header { min-width: 0; flex: 0 0 auto; }" in css
    assert ".index-profile-header-copy { min-width: 0; flex: 1 1 auto; }" in css
    assert "\n  overflow-wrap: anywhere;" in title_rule
    assert ".index-profile-close { flex: 0 0 auto; }" in css
    assert "\n  flex: 0 0 auto;" in tabs_rule
    assert "\n  min-height: 48px;" in tabs_rule
    assert "\n  flex: 1 1 0;" in panels_rule
    assert "\n  min-height: 0;" in panels_rule
    assert "\n  overflow-y: auto;" in panels_rule
    assert ".index-profile-tabs { overflow-x: auto; overflow-y: hidden; flex-wrap: nowrap; }" in mobile
    assert ".index-profile-header-copy { max-width: calc(100% - 64px); }" in mobile
    assert mobile_title_selector in mobile
    mobile_title_rule = mobile.split(mobile_title_selector, 1)[1].split("}", 1)[0]
    assert "\n    max-width: 100%;" in mobile_title_rule
    assert "\n    white-space: normal;" in mobile_title_rule
    assert "\n    word-break: break-word;" in mobile_title_rule


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
