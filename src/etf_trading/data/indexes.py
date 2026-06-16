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
    IndexDefinition("000016", "上证50", "A股", "A股宽基", "000016"),
    IndexDefinition("000001", "上证指数", "A股", "A股综合", "000001"),
    IndexDefinition("399001", "深证成指", "A股", "A股综合", "399001"),
    IndexDefinition("399006", "创业板指", "A股", "A股成长", "399006"),
    IndexDefinition("000688", "科创50", "A股", "A股成长", "000688"),
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
            "open": "open",
            "开盘": "open",
            "high": "high",
            "最高": "high",
            "low": "low",
            "最低": "low",
            "close": "close",
            "收盘": "close",
            "volume": "volume",
            "成交量": "volume",
            "amount": "amount",
            "成交额": "amount",
        }
    ).copy()
    frame["index_code"] = index_code
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        if col not in frame.columns:
            frame[col] = 0
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["data_source"] = source
    return frame[columns].sort_values("trade_date").reset_index(drop=True)
