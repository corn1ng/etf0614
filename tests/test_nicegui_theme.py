from etf_trading.nicegui_app.components.tables import table_columns
from etf_trading.nicegui_app.theme import WORKBENCH_CSS, tone_class


def test_theme_contains_dense_professional_workbench_rules():
    assert ".workbench-shell" in WORKBENCH_CSS
    assert ".workbench-sidebar" in WORKBENCH_CSS
    assert ".workbench-topbar" in WORKBENCH_CSS
    assert ".workbench-data-table" in WORKBENCH_CSS
    assert "height: 34px" in WORKBENCH_CSS
    assert "overflow-x: auto" in WORKBENCH_CSS
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
