"""AkShare data provider.

AkShare is intentionally isolated behind this adapter. The rest of the system
uses normalized English column names and can switch to Tushare or another
provider without changing strategy code.
"""

from __future__ import annotations

from datetime import date
import time
from collections.abc import Callable
from typing import TypeVar

import pandas as pd

from etf_trading.data.provider import DataProvider
from etf_trading.data.indexes import get_index_definition, normalize_index_daily
from etf_trading.universe.classification import classify_etf


class AkShareProvider(DataProvider):
    def __init__(self) -> None:
        import akshare as ak

        self.ak = ak

    def fetch_etf_list(self) -> pd.DataFrame:
        return self.fetch_exchange_traded_etf_spot()

    def fetch_exchange_traded_etf_spot(self) -> pd.DataFrame:
        raw = _call_with_retries(self.ak.fund_etf_spot_em, "AkShare ETF实时列表")
        frame = _normalize_etf_spot(raw)
        frame["etf_code"] = frame["etf_code"].astype(str).str.zfill(6)
        frame["exchange"] = frame["etf_code"].map(_infer_exchange)
        frame["category"] = frame.apply(lambda r: classify_etf(r["etf_code"], r.get("name", ""), r.get("tracking_index", "")), axis=1)
        frame["is_active"] = 1
        frame["tradability_status"] = "exchange_traded"
        frame["data_source"] = "fund_etf_spot_em"
        return frame.sort_values("etf_code").drop_duplicates(subset=["etf_code"], keep="first").reset_index(drop=True)

    def fetch_etf_daily(self, code: str, start_date: date | str, end_date: date | str, adjust: str = "qfq") -> pd.DataFrame:
        normalized_code = str(code).zfill(6)
        try:
            raw = _call_with_retries(
                self.ak.fund_etf_hist_em,
                f"AkShare ETF历史行情 {normalized_code}",
                symbol=normalized_code,
                period="daily",
                start_date=_fmt_date(start_date),
                end_date=_fmt_date(end_date),
                adjust=adjust,
            )
            frame = _normalize_eastmoney_daily(raw, normalized_code)
        except Exception as eastmoney_error:
            try:
                raw = _call_with_retries(
                    self.ak.fund_etf_hist_sina,
                    f"AkShare 新浪ETF历史行情 {normalized_code}",
                    attempts=2,
                    symbol=_sina_symbol(normalized_code),
                )
                frame = _normalize_sina_daily(raw, normalized_code, start_date, end_date)
                frame["data_source"] = "sina"
                frame["adjust"] = "none"
            except Exception as sina_error:
                raise RuntimeError(
                    f"AkShare ETF历史行情 {normalized_code} 获取失败；"
                    f"东财错误：{eastmoney_error}；新浪错误：{sina_error}"
                ) from sina_error
        return frame

    def fetch_etf_nav(self, code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        # AkShare NAV coverage varies by fund. Return a normalized empty frame
        # when no stable endpoint is available for a code.
        return pd.DataFrame(columns=["etf_code", "trade_date", "unit_nav", "accumulated_nav", "iopv", "premium_rate"])

    def fetch_index_daily(self, code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        definition = get_index_definition(str(code))
        if definition.market == "港股":
            frame = pd.DataFrame()
            try:
                raw = _call_with_retries(self.ak.stock_hk_index_daily_em, f"AkShare 港股指数行情 {code}", symbol=definition.provider_symbol)
                frame = normalize_index_daily(raw, definition.index_code, "akshare_hk_em")
            except Exception:
                frame = pd.DataFrame()
            if frame.empty:
                raw = _call_with_retries(
                    self.ak.stock_hk_index_daily_sina,
                    f"AkShare 新浪港股指数行情 {code}",
                    attempts=2,
                    symbol=definition.provider_symbol,
                )
                frame = normalize_index_daily(raw, definition.index_code, "akshare_hk_sina")
        else:
            candidates: list[pd.DataFrame] = []
            try:
                raw = _call_with_retries(self.ak.stock_zh_index_daily_em, f"AkShare A股指数行情 {code}", symbol=definition.provider_symbol)
                candidates.append(normalize_index_daily(raw, definition.index_code, "akshare_zh_em"))
            except Exception:
                pass
            try:
                raw = _call_with_retries(
                    self.ak.stock_zh_index_daily,
                    f"AkShare A股指数新浪行情 {code}",
                    symbol=_sina_index_symbol(definition.provider_symbol),
                )
                candidates.append(normalize_index_daily(raw, definition.index_code, "akshare_zh_sina"))
            except Exception:
                pass
            try:
                raw = _call_with_retries(
                    self.ak.stock_zh_index_hist_csindex,
                    f"AkShare 中证官网指数行情 {code}",
                    symbol=definition.provider_symbol,
                    start_date=_fmt_date(start_date),
                    end_date=_fmt_date(end_date),
                )
                candidates.append(normalize_index_daily(raw, definition.index_code, "akshare_csindex"))
            except Exception:
                pass
            frame = _choose_latest_index_frame(candidates)
        if frame.empty:
            return pd.DataFrame(columns=["index_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "data_source"])
        if "trade_date" not in frame.columns:
            return pd.DataFrame(columns=["index_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "data_source"])
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        return frame[(frame["trade_date"] >= start) & (frame["trade_date"] <= end)].reset_index(drop=True)

    def fetch_trade_calendar(self, market: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        # MVP fallback: derive A-share business days. The provider boundary lets
        # this be replaced by an official exchange/Tushare calendar later.
        dates = pd.date_range(start_date, end_date, freq="B")
        return pd.DataFrame({"market": market, "trade_date": dates, "is_open": 1})


def _fmt_date(value: date | str) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def _infer_exchange(code: str) -> str:
    if code.startswith(("51", "52", "53", "56", "58")):
        return "SSE"
    if code.startswith(("15", "16")):
        return "SZSE"
    return "UNKNOWN"


def _normalize_etf_spot(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    rename_map = {
        "代码": "etf_code",
        "名称": "name",
        "最新价": "latest_price",
        "IOPV实时估值": "iopv",
        "基金折价率": "premium_rate",
        "成交额": "amount",
        "成交量": "volume",
        "最新份额": "latest_share",
        "流通市值": "float_market_value",
        "总市值": "total_market_value",
        "涨跌幅": "pct_change",
    }
    frame = frame.rename(columns={k: v for k, v in rename_map.items() if k in frame.columns})
    if "etf_code" not in frame.columns:
        raise ValueError("AkShare fund_etf_spot_em response missing ETF code column")
    if "name" not in frame.columns:
        frame["name"] = ""
    frame["etf_code"] = frame["etf_code"].astype(str).str.zfill(6)
    frame["is_active"] = 1
    return frame


def _normalize_fund_name_etfs(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    frame = raw.rename(
        columns={
            "基金代码": "etf_code",
            "基金简称": "name",
            "基金类型": "fund_type",
        }
    ).copy()
    if "etf_code" not in frame.columns or "name" not in frame.columns:
        return pd.DataFrame()
    frame["etf_code"] = frame["etf_code"].astype(str).str.zfill(6)
    frame["name"] = frame["name"].fillna("").astype(str)
    is_exchange_code = frame["etf_code"].str.startswith(("15", "16", "51", "52", "53", "56", "58"))
    is_etf_name = frame["name"].str.contains("ETF", case=False, na=False)
    frame = frame[is_exchange_code & is_etf_name].copy()
    if frame.empty:
        return pd.DataFrame()
    frame["latest_price"] = None
    frame["amount"] = None
    frame["volume"] = None
    frame["is_active"] = 1
    return frame[["etf_code", "name", "latest_price", "amount", "volume", "is_active"]]


def _choose_latest_index_frame(frames: list[pd.DataFrame]) -> pd.DataFrame:
    available = [frame for frame in frames if not frame.empty and "trade_date" in frame.columns]
    if not available:
        return pd.DataFrame()
    return max(available, key=lambda frame: (pd.Timestamp(frame["trade_date"].max()), len(frame)))


def _normalize_eastmoney_daily(raw: pd.DataFrame, code: str) -> pd.DataFrame:
    frame = raw.rename(
        columns={
            "日期": "trade_date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
            "换手率": "turnover_rate",
        }
    )
    return _finalize_daily_frame(frame, code)


def _normalize_sina_daily(raw: pd.DataFrame, code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
    frame = raw.rename(
        columns={
            "date": "trade_date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "amount": "amount",
        }
    )
    frame = _finalize_daily_frame(frame, code)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    return frame[(frame["trade_date"] >= start) & (frame["trade_date"] <= end)].reset_index(drop=True)


def _finalize_daily_frame(frame: pd.DataFrame, code: str) -> pd.DataFrame:
    result = frame.copy()
    result["etf_code"] = code
    result["trade_date"] = pd.to_datetime(result["trade_date"])
    for col in ["open", "high", "low", "close", "volume", "amount", "pct_change", "turnover_rate"]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")
    columns = ["etf_code", "trade_date", "open", "high", "low", "close", "volume", "amount"]
    optional = [col for col in ["pct_change", "change", "turnover_rate", "data_source", "adjust"] if col in result.columns]
    return result[columns + optional].sort_values("trade_date").reset_index(drop=True)


def _sina_symbol(code: str) -> str:
    return f"{'sh' if _infer_exchange(code) == 'SSE' else 'sz'}{code}"


def _sina_index_symbol(code: str) -> str:
    return f"{'sz' if code.startswith('399') else 'sh'}{code}"


T = TypeVar("T")


def _call_with_retries(func: Callable[..., T], label: str, attempts: int = 3, sleep_seconds: float = 1.0, **kwargs) -> T:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func(**kwargs)
        except Exception as exc:  # noqa: BLE001 - provider boundary normalizes third-party failures
            last_error = exc
            if attempt < attempts:
                time.sleep(sleep_seconds * attempt)
    raise RuntimeError(f"{label} 获取失败，已重试 {attempts} 次：{last_error}") from last_error
