from etf_trading.nicegui_app.components import tables
from etf_trading.nicegui_app.components.tables import render_table, table_columns, table_rows
from etf_trading.nicegui_app.pages.etf_data import _atomic_filter_options, _atomic_filter_value


def test_table_columns_translate_internal_index_headers_to_chinese():
    rows = [
        {
            "index_code": "000300",
            "index_name": "沪深300",
            "market": "A股",
            "category": "A股宽基",
            "large_trend": "UP",
            "medium_trend": "RANGE",
            "small_trend": "BROKEN",
            "allows_new_position": False,
            "latest_date": "2026-07-03",
            "history_rows": 5941,
        }
    ]

    labels = [column["label"] for column in table_columns(rows)]

    assert labels == [
        "指数代码",
        "指数名称",
        "市场",
        "分类",
        "大趋势",
        "中趋势",
        "小趋势",
        "允许新开仓",
        "最新日期",
        "历史行数",
    ]
    assert "index_code" not in labels
    assert "allows_new_position" not in labels


def test_table_columns_translate_price_history_headers_to_chinese():
    rows = [
        {
            "etf_code": "159001",
            "trade_date": "2021-07-08",
            "open": 100,
            "high": 100.001,
            "low": 99.999,
            "close": 100,
            "volume": 55071,
            "amount": 550710592,
            "pct_change": 0,
            "change": 0,
            "turnover_rate": 26.1,
            "ma20": "",
            "ma51": "",
            "ma60": "",
            "ma120": "",
        }
    ]

    labels = [column["label"] for column in table_columns(rows)]

    assert labels == [
        "ETF代码",
        "交易日",
        "开盘",
        "最高",
        "最低",
        "收盘",
        "成交量",
        "成交额",
        "涨跌幅",
        "涨跌额",
        "换手率",
        "20日均线",
        "51日均线",
        "60日均线",
        "120日均线",
    ]
    assert not {"trade_date", "open", "high", "low", "close", "volume", "pct_change", "turnover_rate"} & set(labels)


def test_table_columns_translate_maintenance_log_headers_to_chinese():
    rows = [
        {
            "dataset": "index_daily_price",
            "asset_code": "000300",
            "last_success_trade_date": "2026-07-06",
            "severity": "warning",
            "message": "ok",
            "log_id": 1,
        }
    ]

    labels = [column["label"] for column in table_columns(rows)]

    assert labels == ["数据集", "标的代码", "最近成功交易日", "级别", "消息", "日志编号"]
    assert not {"dataset", "asset_code", "last_success_trade_date", "severity", "log_id"} & set(labels)


def test_table_columns_name_maintenance_detail_as_status_explanation():
    labels = [
        column["label"]
        for column in table_columns([{"error_message": "已更新至 2026-07-09，缺少 2026-07-10 行情。"}])
    ]

    assert labels == ["状态说明"]


def test_table_rows_do_not_use_baseline_pending_verification_as_the_primary_conclusion():
    display = table_rows(
        [
            {
                "completeness_status": "BASELINE_UNVERIFIED",
                "completeness_message": (
                    "已有 1999-12-30 至 2026-07-09 的行情，但缺少官方基日；"
                    "暂时无法判断是否从指数起点完整，不作为交易依据。"
                ),
            }
        ]
    )

    assert display[0]["completeness_status"] == "历史起点无法确认"
    assert "基日待核验" not in " ".join(str(value) for value in display[0].values())


def test_render_table_localizes_pagination_labels(monkeypatch):
    captured = {}

    class FakeTable:
        def __init__(self):
            self.props = {}

    class FakeUi:
        def table(self, **kwargs):
            captured.update(kwargs)
            return FakeTable()

    monkeypatch.setattr(tables, "ui", FakeUi())

    table = render_table(
        [{"etf_code": "159001", "trade_date": "2021-07-08", "open": 100}],
        pagination=10,
    )

    assert captured["pagination"] == 10
    assert captured["columns"] == [
        {"name": "etf_code", "label": "ETF代码", "field": "etf_code", "align": "left"},
        {"name": "trade_date", "label": "交易日", "field": "trade_date", "align": "left"},
        {"name": "open", "label": "开盘", "field": "open", "align": "left"},
    ]
    assert table.props["rows-per-page-label"] == "每页行数"
    assert table.props[":pagination-label"] == "(first, end, total) => `${first}-${end} / ${total}`"
    assert table.props["no-data-label"] == "暂无数据"
    assert table.props["no-results-label"] == "没有匹配结果"
    assert table.props["loading-label"] == "加载中..."


def test_table_rows_translate_internal_status_codes_and_booleans_to_chinese():
    rows = [
        {
            "large_trend": "UP",
            "medium_trend": "RANGE",
            "small_trend": "RIGHT_SIDE_START",
            "allows_new_position": True,
            "history_status": "stale",
            "feature_status": "missing_features",
            "missing_feature_names": "read_failed",
            "valuation_overview_label": "missing",
            "valuation_health_status": "missing_valuation",
            "action": "BUY",
            "status": "FAILED",
            "note": "short_history",
        }
    ]

    display = table_rows(rows)

    assert display == [
        {
            "large_trend": "上升",
            "medium_trend": "震荡",
            "small_trend": "右侧开始",
            "allows_new_position": "是",
            "history_status": "行情滞后",
            "feature_status": "特征缺失",
            "missing_feature_names": "读取失败",
            "valuation_overview_label": "估值缺失",
            "valuation_health_status": "估值缺失",
            "action": "买入",
            "status": "失败",
            "note": "历史不足",
        }
    ]
    rendered_text = " ".join(str(value) for value in display[0].values())
    for raw_code in ["UP", "RANGE", "RIGHT_SIDE_START", "true", "stale", "missing_features", "read_failed", "short_history", "missing", "missing_valuation", "BUY", "FAILED"]:
        assert raw_code not in rendered_text
    assert "正在刷新" not in rendered_text


def test_table_rows_do_not_apply_history_lag_label_to_generic_stale_status():
    display = table_rows([{"status": "stale", "history_status": "stale"}])

    assert display[0]["history_status"] == "行情滞后"
    assert display[0]["status"] == "待刷新"
    assert display[0]["status"] != "行情滞后"
    assert "正在刷新" not in " ".join(str(value) for value in display[0].values())


def test_table_rows_translate_uppercase_stale_maintenance_status_to_chinese():
    display = table_rows([{"index_code": "930633", "status": "STALE"}])

    assert display == [{"index_code": "930633", "status": "行情仍滞后"}]


def test_table_rows_translate_maintenance_dataset_and_job_codes_to_chinese():
    rows = [
        {
            "dataset": "index_daily_price",
            "job_type": "history",
            "severity": "warning",
            "status": "EMPTY",
        }
    ]

    display = table_rows(rows)

    assert display == [
        {
            "dataset": "指数日行情",
            "job_type": "历史行情",
            "severity": "警告",
            "status": "无数据",
        }
    ]
    rendered_text = " ".join(str(value) for value in display[0].values())
    for raw_code in ["index_daily_price", "history", "warning", "EMPTY"]:
        assert raw_code not in rendered_text


def test_compact_table_columns_add_width_hints_for_index_summary():
    rows = [
        {
            "index_code": "000300",
            "index_name": "沪深300",
            "market": "A股",
            "category": "A股宽基",
            "large_trend": "UP",
            "medium_trend": "RANGE",
            "small_trend": "BROKEN",
            "allows_new_position": False,
            "latest_date": "2026-07-03",
            "history_rows": 5941,
        }
    ]

    columns = table_columns(rows, compact=True)
    by_name = {column["name"]: column for column in columns}

    assert by_name["index_code"]["style"] == "width: 88px; min-width: 88px; max-width: 88px;"
    assert by_name["index_name"]["style"] == "width: 116px; min-width: 116px; max-width: 116px;"
    assert by_name["index_code"]["classes"] == "text-no-wrap"
    assert by_name["index_code"]["headerClasses"] == "text-no-wrap"


def test_atomic_status_filter_options_show_chinese_labels_but_keep_internal_values():
    frame = {
        "history_status": ["complete", "missing_history", "short_history", "stale"],
    }

    options = _atomic_filter_options(frame, "history_status", "全部历史状态")

    assert list(options) == ["全部历史状态", "数据可用", "历史缺失", "历史不足", "行情滞后"]
    assert _atomic_filter_value(options, "全部历史状态") == "全部历史状态"
    assert _atomic_filter_value(options, "数据可用") == "complete"
    assert _atomic_filter_value(options, "历史缺失") == "missing_history"
    assert _atomic_filter_value(options, "历史不足") == "short_history"
    assert _atomic_filter_value(options, "行情滞后") == "stale"


def test_atomic_indicator_new_detail_labels_are_human_readable():
    rows = [{"ma60_slope_20": 0.015, "history_rows": 520}]

    labels = [column["label"] for column in table_columns(rows)]

    assert labels == ["60日线20日斜率", "历史行数"]
