"""Index definitions and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


INDEX_HISTORY_AUTO_START = date(1990, 1, 1)


@dataclass(frozen=True)
class IndexDefinition:
    index_code: str
    name: str
    market: str
    category: str
    provider_symbol: str


DEFAULT_INDEXES: tuple[IndexDefinition, ...] = (
    IndexDefinition("000300", "沪深300", "A股", "A股宽基", "000300"),
    IndexDefinition("000905", "中证500", "A股", "A股宽基", "000905"),
    IndexDefinition("000852", "中证1000", "A股", "A股宽基", "000852"),
    IndexDefinition("932000", "中证2000", "A股", "A股宽基", "932000"),
    IndexDefinition("000510", "中证A500", "A股", "A股宽基", "000510"),
    IndexDefinition("930050", "中证A50", "A股", "A股宽基", "930050"),
    IndexDefinition("000903", "中证A100", "A股", "A股宽基", "000903"),
    IndexDefinition("000906", "中证800", "A股", "A股宽基", "000906"),
    IndexDefinition("000016", "上证50", "A股", "A股宽基", "000016"),
    IndexDefinition("000001", "上证指数", "A股", "A股综合", "000001"),
    IndexDefinition("399001", "深证成指", "A股", "A股综合", "399001"),
    IndexDefinition("399006", "创业板指", "A股", "A股成长", "399006"),
    IndexDefinition("000688", "科创50", "A股", "A股成长", "000688"),
    IndexDefinition("931643", "科创创业50", "A股", "A股成长", "931643"),
    IndexDefinition("000922", "中证红利", "A股", "A股主题", "000922"),
    IndexDefinition("000015", "上证红利", "A股", "A股主题", "000015"),
    IndexDefinition("H30269", "红利低波", "A股", "A股主题", "H30269"),
    IndexDefinition("930955", "红利低波100", "A股", "A股主题", "930955"),
    IndexDefinition("931446", "东证红利低波", "A股", "A股主题", "931446"),
    IndexDefinition("000919", "沪深300价值", "A股", "A股主题", "000919"),
    IndexDefinition("000029", "上证180价值", "A股", "A股主题", "000029"),
    IndexDefinition("930782", "行业中性低波", "A股", "A股主题", "930782"),
    IndexDefinition("399986", "中证银行", "A股", "A股行业", "399986"),
    IndexDefinition("399975", "证券公司", "A股", "A股行业", "399975"),
    IndexDefinition("000933", "中证医药", "A股", "A股行业", "000933"),
    IndexDefinition("000932", "中证消费", "A股", "A股行业", "000932"),
    IndexDefinition("000934", "中证金融", "A股", "A股行业", "000934"),
    IndexDefinition("000935", "中证信息", "A股", "A股行业", "000935"),
    IndexDefinition("000928", "中证能源", "A股", "A股行业", "000928"),
    IndexDefinition("000819", "有色金属", "A股", "A股行业", "000819"),
    IndexDefinition("000827", "中证环保", "A股", "A股行业", "000827"),
    IndexDefinition("399812", "养老产业", "A股", "A股行业", "399812"),
    IndexDefinition("930997", "新能源车", "A股", "A股主题", "930997"),
    IndexDefinition("931152", "CS创新药", "A股", "A股行业", "931152"),
    IndexDefinition("930707", "中证畜牧", "A股", "A股行业", "930707"),
    IndexDefinition("930697", "家用电器", "A股", "A股行业", "930697"),
    IndexDefinition("931009", "建筑材料", "A股", "A股行业", "931009"),
    IndexDefinition("930901", "动漫游戏", "A股", "A股主题", "930901"),
    IndexDefinition("930743", "中证生科", "A股", "A股行业", "930743"),
    IndexDefinition("930633", "中证旅游", "A股", "A股行业", "930633"),
    IndexDefinition("931087", "科技龙头", "A股", "A股主题", "931087"),
    IndexDefinition("931865", "中证半导", "A股", "A股行业", "931865"),
    IndexDefinition("931775", "房地产", "A股", "A股行业", "931775"),
    IndexDefinition("H11052", "智能电车", "A股", "A股主题", "H11052"),
    IndexDefinition("H30015", "800汽车", "A股", "A股行业", "H30015"),
    IndexDefinition("H30533", "中国互联网50", "港股", "港股科技", "H30533"),
    IndexDefinition("HSI", "恒生指数", "港股", "港股宽基", "HSI"),
    IndexDefinition("HSCEI", "恒生中国企业指数", "港股", "港股宽基", "HSCEI"),
    IndexDefinition("HSTECH", "恒生科技指数", "港股", "港股科技", "HSTECH"),
)


def index_options() -> list[str]:
    return [f"{item.index_code} {item.name}" for item in DEFAULT_INDEXES]


def get_index_definition(index_code: str) -> IndexDefinition:
    for item in DEFAULT_INDEXES:
        if item.index_code == index_code:
            return item
    raise KeyError(f"Unknown index code: {index_code}")


def normalize_index_daily(raw: pd.DataFrame, index_code: str, source: str) -> pd.DataFrame:
    columns = ["index_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "data_source"]
    if raw.empty:
        return pd.DataFrame(columns=columns)

    frame = raw.rename(
        columns={
            "date": "trade_date",
            "日期": "trade_date",
            "交易日": "trade_date",
            "cal_date": "trade_date",
            "calendar_date": "trade_date",
            "open": "open",
            "开盘": "open",
            "開盤": "open",
            "high": "high",
            "最高": "high",
            "low": "low",
            "最低": "low",
            "close": "close",
            "收盘": "close",
            "收盤": "close",
            "volume": "volume",
            "成交量": "volume",
            "amount": "amount",
            "成交金额": "amount",
            "成交額": "amount",
            "成交额": "amount",
        }
    ).copy()

    date_column = _find_trade_date_column(frame)
    if date_column is None:
        return pd.DataFrame(columns=columns)
    if date_column != "trade_date":
        frame = frame.rename(columns={date_column: "trade_date"})

    frame["index_code"] = index_code
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        if col not in frame.columns:
            frame[col] = 0
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["data_source"] = source
    return frame[columns].sort_values("trade_date").reset_index(drop=True)


def _find_trade_date_column(frame: pd.DataFrame) -> str | None:
    if "trade_date" in frame.columns:
        return "trade_date"

    exact_candidates = ("date", "日期", "交易日", "cal_date", "calendar_date")
    for candidate in exact_candidates:
        if candidate in frame.columns:
            return candidate

    lower_map = {str(col).lower().strip(): col for col in frame.columns}
    for key in ("date", "time", "datetime", "trade"):
        if key in lower_map:
            return lower_map[key]
    for col_lower, original in lower_map.items():
        if "date" in col_lower or "time" in col_lower or "交易" in col_lower or "时间" in col_lower:
            return original

    for col in frame.columns:
        parsed = pd.to_datetime(frame[col], errors="coerce")
        if parsed.notna().mean() >= 0.95:
            return col
    return None
