import json

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


def test_filter_index_definitions_matches_category_code_and_name():
    by_code = [item.index_code for item in app._filter_index_definitions(category_filter="A股行业", query="银行")]
    assert by_code == ["399986"]

    by_name = [item.index_code for item in app._filter_index_definitions(category_filter="全部分类", query="红利")]
    assert {"000922", "000015", "H30269", "930955", "931446"}.issubset(set(by_name))

    by_code_query = [item.index_code for item in app._filter_index_definitions(category_filter="全部分类", query="930997")]
    assert by_code_query == ["930997"]
