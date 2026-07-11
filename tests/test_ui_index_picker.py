from contextlib import nullcontext
import json

from etf_trading.data.indexes import IndexDefinition
from etf_trading.ui import app


def test_recent_index_codes_are_persisted_unique_and_limited(tmp_path):
    prefs_path = tmp_path / "ui_preferences.json"

    for code in ["000300", "000905", "000852", "932000", "000510", "930050", "399006", "000300"]:
        app._remember_recent_index_code(code, path=prefs_path)

    assert app._load_recent_index_codes(path=prefs_path) == [
        "000300",
        "399006",
        "930050",
        "000510",
        "932000",
        "000852",
    ]
    assert json.loads(prefs_path.read_text(encoding="utf-8"))["recent_index_codes"] == [
        "000300",
        "399006",
        "930050",
        "000510",
        "932000",
        "000852",
    ]


def test_recent_index_codes_tolerate_missing_broken_and_unknown_config(tmp_path):
    prefs_path = tmp_path / "ui_preferences.json"

    assert app._load_recent_index_codes(path=prefs_path) == []

    prefs_path.write_text("{broken", encoding="utf-8")
    assert app._load_recent_index_codes(path=prefs_path) == []

    prefs_path.write_text(
        json.dumps({"recent_index_codes": ["NOPE", "000905", 123, "399006"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert app._load_recent_index_codes(path=prefs_path) == ["000905", "399006"]


def test_common_index_shortcuts_include_more_dense_benchmarks():
    assert app.INDEX_WATCH_COMMON_CODES == (
        "000300",
        "000905",
        "000852",
        "932000",
        "000510",
        "000016",
        "399006",
        "000688",
    )


def test_common_index_codes_can_be_customized_and_reset(tmp_path):
    prefs_path = tmp_path / "ui_preferences.json"

    updated = app._replace_common_index_code(0, "930997", path=prefs_path)

    assert updated == [
        "930997",
        "000905",
        "000852",
        "932000",
        "000510",
        "000016",
        "399006",
        "000688",
    ]
    assert app._load_common_index_codes(path=prefs_path) == updated
    assert json.loads(prefs_path.read_text(encoding="utf-8"))["common_index_codes"] == updated

    app._remember_recent_index_code("399006", path=prefs_path)
    reset = app._reset_common_index_codes(path=prefs_path)

    preferences = json.loads(prefs_path.read_text(encoding="utf-8"))
    assert reset == list(app.INDEX_WATCH_COMMON_CODES)
    assert "common_index_codes" not in preferences
    assert preferences["recent_index_codes"] == ["399006"]


def test_common_index_codes_ignore_broken_duplicates_and_unknown_config(tmp_path):
    prefs_path = tmp_path / "ui_preferences.json"

    assert app._load_common_index_codes(path=prefs_path) == list(app.INDEX_WATCH_COMMON_CODES)

    prefs_path.write_text("{broken", encoding="utf-8")
    assert app._load_common_index_codes(path=prefs_path) == list(app.INDEX_WATCH_COMMON_CODES)

    prefs_path.write_text(
        json.dumps({"common_index_codes": ["NOPE", "000905", "000905", 123, "399006"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert app._load_common_index_codes(path=prefs_path) == [
        "000905",
        "399006",
        "000300",
        "000852",
        "932000",
        "000510",
        "000016",
        "000688",
    ]


def test_quick_index_buttons_use_compact_grid(monkeypatch):
    calls = {}
    columns = []

    class FakeColumn:
        def button(self, label, **kwargs):
            return False

    def capture_columns(spec, **kwargs):
        calls["spec"] = spec
        calls["kwargs"] = kwargs
        columns[:] = [FakeColumn() for _ in range(spec)]
        return columns

    monkeypatch.setattr(app.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "columns", capture_columns)
    definitions = [
        IndexDefinition(f"{idx:06d}", f"Index {idx}", "market", "category", f"{idx:06d}")
        for idx in range(10)
    ]

    assert app._render_index_quick_buttons("Common", definitions, "quick") is None
    assert calls["spec"] == 8
    assert calls["kwargs"] == {"gap": "small"}


def test_select_index_for_watch_uses_saved_common_shortcuts(monkeypatch):
    rendered = {}

    class FakeColumn:
        def selectbox(self, label, options, index=0, **kwargs):
            return options[index]

        def text_input(self, *args, **kwargs):
            return ""

    monkeypatch.setattr(app.st, "session_state", {})
    monkeypatch.setattr(app.st, "columns", lambda *args, **kwargs: [FakeColumn(), FakeColumn(), FakeColumn()])
    monkeypatch.setattr(app.st, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app,
        "_load_common_index_codes",
        lambda: ["930997", "000905", "000852", "932000", "000510", "000016", "399006", "000688"],
    )
    monkeypatch.setattr(app, "_load_recent_index_codes", lambda: [])
    monkeypatch.setattr(app, "_remember_recent_index_code", lambda code: [])
    monkeypatch.setattr(app, "_render_common_index_customizer", lambda common_codes: None, raising=False)

    def capture_quick_buttons(title, definitions, key_prefix):
        rendered[key_prefix] = [definition.index_code for definition in definitions]
        return None

    monkeypatch.setattr(app, "_render_index_quick_buttons", capture_quick_buttons)

    assert app._select_index_for_watch() == "000300"
    assert rendered["index_watch_common"] == [
        "930997",
        "000905",
        "000852",
        "932000",
        "000510",
        "000016",
        "399006",
        "000688",
    ]


def test_common_index_customizer_saves_selected_replacement(monkeypatch):
    calls = {"replace": None, "rerun": 0}
    selectbox_calls = {"count": 0}

    class FakeColumn:
        def __init__(self, *, button_value=False):
            self.button_value = button_value

        def selectbox(self, label, options, index=0, **kwargs):
            selectbox_calls["count"] += 1
            if selectbox_calls["count"] == 1:
                return options[1]
            return next(option for option in options if option.startswith("930997 "))

        def button(self, *args, **kwargs):
            return self.button_value

    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(
        app.st,
        "columns",
        lambda *args, **kwargs: [FakeColumn(), FakeColumn(), FakeColumn(button_value=True), FakeColumn()],
    )
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "rerun", lambda: calls.__setitem__("rerun", calls["rerun"] + 1))

    def capture_replace(slot_index, replacement_code):
        calls["replace"] = (slot_index, replacement_code)
        return list(app.INDEX_WATCH_COMMON_CODES)

    monkeypatch.setattr(app, "_replace_common_index_code", capture_replace)

    app._render_common_index_customizer(list(app.INDEX_WATCH_COMMON_CODES))

    assert calls["replace"] == (1, "930997")
    assert calls["rerun"] == 1


def test_common_index_customizer_can_reset_to_defaults(monkeypatch):
    calls = {"reset": 0, "rerun": 0}
    selectbox_calls = {"count": 0}

    class FakeColumn:
        def __init__(self, *, button_value=False):
            self.button_value = button_value

        def selectbox(self, label, options, index=0, **kwargs):
            selectbox_calls["count"] += 1
            if selectbox_calls["count"] == 1:
                return options[0]
            return options[0]

        def button(self, *args, **kwargs):
            return self.button_value

    monkeypatch.setattr(app.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(
        app.st,
        "columns",
        lambda *args, **kwargs: [FakeColumn(), FakeColumn(), FakeColumn(), FakeColumn(button_value=True)],
    )
    monkeypatch.setattr(app.st, "success", lambda *args, **kwargs: None)
    monkeypatch.setattr(app.st, "rerun", lambda: calls.__setitem__("rerun", calls["rerun"] + 1))
    monkeypatch.setattr(app, "_reset_common_index_codes", lambda: calls.__setitem__("reset", calls["reset"] + 1))

    app._render_common_index_customizer(list(app.INDEX_WATCH_COMMON_CODES))

    assert calls["reset"] == 1
    assert calls["rerun"] == 1


def test_filter_index_definitions_matches_category_code_and_name():
    by_code = [item.index_code for item in app._filter_index_definitions(category_filter="A股行业", query="银行")]
    assert by_code == ["399986"]

    by_name = [item.index_code for item in app._filter_index_definitions(category_filter="全部分类", query="红利")]
    assert {"000922", "000015", "H30269", "930955", "931446"}.issubset(set(by_name))

    by_code_query = [item.index_code for item in app._filter_index_definitions(category_filter="全部分类", query="930997")]
    assert by_code_query == ["930997"]
