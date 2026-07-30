"""Tushare-backed implementation of the normalized market-data contract."""

from __future__ import annotations

from datetime import date
import time

import pandas as pd

from etf_trading.data.index_valuations import (
    OFFICIAL_INDEX_VALUATION_TS_CODES,
    finalize_index_valuation_frame,
)
from etf_trading.data.provider import DataProvider
from etf_trading.data.provider_runtime import (
    ProviderCallError,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderSettings,
    RequestRateLimiter,
)
from etf_trading.universe.classification import classify_etf


class TushareProvider(DataProvider):
    def __init__(self, settings: ProviderSettings, *, pro_client=None, limiter=None, sleeper=time.sleep) -> None:
        self.settings = settings
        self._pro_client = pro_client
        self.limiter = limiter or RequestRateLimiter(settings.requests_per_minute)
        self.sleeper = sleeper

    @property
    def pro(self):
        if self._pro_client is not None:
            return self._pro_client
        if not self.settings.token:
            raise ProviderConfigurationError("TUSHARE_TOKEN is not configured")
        import tushare as ts

        ts.set_token(self.settings.token)
        client = ts.pro_api(self.settings.token)
        client._DataApi__http_url = self.settings.api_url
        self._pro_client = client
        return client

    def _query(self, api_name: str, *, fields: str, **params) -> pd.DataFrame:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.attempts + 1):
            self.limiter.wait()
            try:
                result = self.pro.query(api_name, fields=fields, **params)
                if not isinstance(result, pd.DataFrame):
                    raise ProviderCallError(f"{api_name} returned a non-table response", category="schema")
                return result
            except (ProviderCallError, ProviderConfigurationError):
                raise
            except Exception as exc:  # noqa: BLE001
                category = _error_category(exc)
                if category in {"authentication", "permission", "parameter"}:
                    raise ProviderCallError(str(exc), category=category) from exc
                last_error = exc
                if attempt < self.settings.attempts:
                    self.sleeper(min(2 ** (attempt - 1), 4))
        raise ProviderCallError(str(last_error), category=_error_category(last_error)) from last_error

    def fetch_etf_list(self) -> pd.DataFrame:
        raw = self._query(
            "fund_basic",
            fields="ts_code,name,management,fund_type,type,list_date,status,market",
            market="E",
            status="L",
        )
        if raw.empty:
            raise ProviderCallError("fund_basic returned no listed ETFs", category="schema")
        kind = raw.get("type", pd.Series("", index=raw.index)).fillna("").astype(str)
        names = raw.get("name", pd.Series("", index=raw.index)).fillna("").astype(str)
        frame = raw[(kind.str.upper() == "ETF") | names.str.contains("ETF", case=False, na=False)].copy()
        frame = frame[~frame["type"].fillna("").astype(str).str.upper().eq("LOF")]
        if frame.empty:
            raise ProviderCallError("fund_basic returned no listed ETFs", category="schema")
        frame["etf_code"] = frame["ts_code"].astype(str).str.split(".").str[0].str.zfill(6)
        frame["name"] = frame["name"].fillna("").astype(str)
        frame["exchange"] = frame["ts_code"].astype(str).str.split(".").str[-1].map({"SH": "SSE", "SZ": "SZSE"})
        frame["fund_company"] = frame.get("management")
        frame["listing_date"] = pd.to_datetime(frame.get("list_date"), errors="coerce").dt.strftime("%Y-%m-%d")
        frame["category"] = frame.apply(lambda row: classify_etf(row["etf_code"], row["name"], ""), axis=1)
        frame["is_active"] = 1
        frame["tradability_status"] = "exchange_traded"
        frame["data_source"] = "tushare_fund_basic"
        for column in ("amount", "volume", "latest_price", "tracking_index"):
            frame[column] = None
        return frame.sort_values("etf_code").drop_duplicates("etf_code").reset_index(drop=True)

    def fetch_exchange_traded_etf_spot(self) -> pd.DataFrame:
        raise ProviderCapabilityError("realtime ETF spot is not supported by the Tushare adapter")

    def fetch_etf_daily(self, code: str, start_date: date | str, end_date: date | str, adjust: str = "qfq") -> pd.DataFrame:
        ts_code = _etf_ts_code(code)
        raw = self._query(
            "fund_daily",
            fields="ts_code,trade_date,open,high,low,close,vol,amount,pct_chg",
            ts_code=ts_code,
            start_date=_fmt_date(start_date),
            end_date=_fmt_date(end_date),
        )
        frame = _normalize_daily(raw, str(code).zfill(6))
        if adjust == "none":
            frame["adjust"] = "none"
            return frame
        if adjust != "qfq":
            raise ProviderCallError(f"unsupported ETF adjustment: {adjust}", category="parameter")
        factors = self._query("fund_adj", fields="ts_code,trade_date,adj_factor", ts_code=ts_code)
        factors = factors.copy()
        factors["trade_date"] = pd.to_datetime(factors.get("trade_date"), errors="coerce")
        factors["adj_factor"] = pd.to_numeric(factors.get("adj_factor"), errors="coerce")
        merged = frame.merge(factors[["trade_date", "adj_factor"]], on="trade_date", how="left", validate="one_to_one")
        if merged.empty and not frame.empty or merged["adj_factor"].isna().any():
            raise ProviderCallError("fund_adj returned incomplete adjustment factors", category="schema")
        if not merged.empty:
            latest_factor = float(merged.sort_values("trade_date").iloc[-1]["adj_factor"])
            for column in ("open", "high", "low", "close"):
                merged[column] = merged[column] * merged["adj_factor"] / latest_factor
        merged["adjust"] = "qfq"
        return merged.drop(columns="adj_factor")

    def fetch_etf_nav(self, code: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        raw = self._query("fund_nav", fields="ts_code,nav_date,unit_nav,accum_nav", ts_code=_etf_ts_code(code))
        frame = pd.DataFrame({
            "etf_code": str(code).zfill(6),
            "trade_date": pd.to_datetime(raw.get("nav_date"), errors="coerce"),
            "unit_nav": pd.to_numeric(raw.get("unit_nav"), errors="coerce"),
            "accumulated_nav": pd.to_numeric(raw.get("accum_nav"), errors="coerce"),
            "iopv": None,
            "premium_rate": None,
        })
        start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
        return frame[(frame["trade_date"] >= start) & (frame["trade_date"] <= end)].reset_index(drop=True)

    def fetch_index_daily(self, code, start_date, end_date) -> pd.DataFrame:
        index_code = str(getattr(code, "index_code", code))
        symbol = str(getattr(code, "provider_symbol", "")).strip()
        if not symbol:
            suffix = "SZ" if index_code.startswith("399") else "SH"
            symbol = f"{index_code}.{suffix}"
        elif "." not in symbol:
            suffix = "CSI" if symbol[:1].isalpha() else ("SZ" if index_code.startswith("399") else "SH")
            symbol = f"{symbol}.{suffix}"
        raw = self._query("index_daily", fields="ts_code,trade_date,open,high,low,close,vol,amount", ts_code=symbol, start_date=_fmt_date(start_date), end_date=_fmt_date(end_date))
        frame = raw.copy()
        if frame.empty:
            return pd.DataFrame(columns=["index_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "data_source"])
        frame["index_code"] = index_code
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
        for column in ("open", "high", "low", "close", "vol", "amount"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["volume"] = frame["vol"]
        frame["amount"] = frame["amount"] * 1000
        frame["data_source"] = "tushare_index_daily"
        return frame[["index_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "data_source"]].sort_values("trade_date").reset_index(drop=True)

    def fetch_index_official_valuations(self, index_code, start_date, end_date) -> pd.DataFrame:
        code = str(index_code).zfill(6)
        ts_code = OFFICIAL_INDEX_VALUATION_TS_CODES.get(code)
        if ts_code is None:
            raise ProviderCapabilityError(f"official index valuation is unsupported: {code}")
        raw = self._query(
            "index_dailybasic",
            fields=(
                "ts_code,trade_date,total_mv,float_mv,total_share,float_share,free_share,"
                "turnover_rate,turnover_rate_f,pe,pe_ttm,pb"
            ),
            ts_code=ts_code,
            start_date=_fmt_date(start_date),
            end_date=_fmt_date(end_date),
        )
        return finalize_index_valuation_frame(
            raw.rename(columns={"pe": "pe_static"}),
            code,
            "tushare_index_dailybasic",
            "official",
        )

    def fetch_trade_calendar(self, market: str, start_date: date | str, end_date: date | str) -> pd.DataFrame:
        raw = self._query(
            "trade_cal",
            fields="exchange,cal_date,is_open,pretrade_date",
            exchange=market,
            start_date=_fmt_date(start_date),
            end_date=_fmt_date(end_date),
        )
        frame = raw.rename(columns={"cal_date": "trade_date"}).copy()
        if "exchange" not in frame:
            frame["exchange"] = market
        frame["market"] = frame["exchange"]
        frame["trade_date"] = pd.to_datetime(frame.get("trade_date"), errors="coerce")
        frame["is_open"] = pd.to_numeric(frame.get("is_open"), errors="coerce").fillna(0).astype(int)
        return frame[["market", "trade_date", "is_open"]].dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)


def _etf_ts_code(code: str) -> str:
    value = str(code).zfill(6)
    if value.startswith(("51", "52", "53", "56", "58")):
        return f"{value}.SH"
    if value.startswith(("15", "16")):
        return f"{value}.SZ"
    raise ProviderCallError(f"unsupported ETF code: {code}", category="parameter")


def _fmt_date(value: date | str) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def _normalize_daily(raw: pd.DataFrame, code: str) -> pd.DataFrame:
    frame = raw.copy()
    if frame.empty:
        return pd.DataFrame(columns=["etf_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "data_source"])
    frame["etf_code"] = code
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    for column in ("open", "high", "low", "close", "vol", "amount", "pct_chg"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["volume"] = frame.get("vol")
    frame["amount"] = frame.get("amount") * 1000
    frame["data_source"] = "tushare_fund_daily"
    columns = ["etf_code", "trade_date", "open", "high", "low", "close", "volume", "amount", "data_source"]
    if "pct_chg" in frame:
        frame["pct_change"] = frame["pct_chg"]
        columns.append("pct_change")
    return frame[columns].sort_values("trade_date").drop_duplicates(["etf_code", "trade_date"]).reset_index(drop=True)


def _error_category(error: Exception | None) -> str:
    message = str(error or "").lower()
    if "权限" in str(error) or "permission" in message:
        return "permission"
    if "token" in message or "auth" in message:
        return "authentication"
    if "parameter" in message or "参数" in str(error):
        return "parameter"
    if "timeout" in message or "connection" in message:
        return "network"
    return "provider"
