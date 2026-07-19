"""Shared configuration and runtime helpers for market-data providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from time import monotonic, sleep
from typing import Callable, Generic, Mapping, Sequence, TypeVar
import os
import re

import yaml


DEFAULT_DATA_SOURCE_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "data_sources.yaml"
T = TypeVar("T")


@dataclass(frozen=True)
class ProviderSettings:
    """Non-secret provider settings; token is intentionally hidden from repr."""

    primary_provider: str = "tushare"
    fallback_provider: str = "akshare"
    api_url: str = "https://ts.gyzcloud.top/api"
    requests_per_minute: int = 120
    attempts: int = 3
    token: str = field(default="", repr=False)


class ProviderError(RuntimeError):
    """Base class for failures normalized at the provider boundary."""

    category = "provider"


class ProviderConfigurationError(ProviderError):
    category = "configuration"


class ProviderCapabilityError(ProviderError):
    category = "unsupported"


class ProviderCallError(ProviderError):
    def __init__(self, message: str, *, category: str = "provider") -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class ProviderNotice:
    operation: str
    asset_code: str
    category: str
    reason: str
    fallback_provider: str
    known_gap: bool = False


@dataclass(frozen=True)
class ProviderOperationResult(Generic[T]):
    value: T
    notices: tuple[ProviderNotice, ...] = ()


def load_provider_settings(
    path: str | Path = DEFAULT_DATA_SOURCE_CONFIG,
    environ: Mapping[str, str] | None = None,
) -> ProviderSettings:
    """Read non-secret YAML configuration and credentials from the environment."""

    values = os.environ if environ is None else environ
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    tushare = raw.get("tushare", {}) or {}
    return ProviderSettings(
        primary_provider=str(raw.get("primary_provider") or "tushare"),
        fallback_provider=str(raw.get("fallback_provider") or "akshare"),
        api_url=str(values.get("TUSHARE_API_URL") or tushare.get("api_url") or "https://ts.gyzcloud.top/api"),
        requests_per_minute=int(tushare.get("requests_per_minute", 120)),
        attempts=int(tushare.get("attempts", 3)),
        token=str(values.get("TUSHARE_TOKEN") or "").strip(),
    )


def redact_provider_text(text: object, *, secrets: Sequence[str] = ()) -> str:
    """Remove credentials before failures reach a UI, log, or task record."""

    result = str(text)
    for secret in sorted({value for value in secrets if value}, key=len, reverse=True):
        result = result.replace(secret, "[REDACTED]")
    result = re.sub(r"(?i)(token\s*[=:]\s*)[^\s&]+", r"\1[REDACTED]", result)
    result = re.sub(r"(?i)(authorization\s*[=:]\s*)[^\s,]+", r"\1[REDACTED]", result)
    return result


def summarize_provider_notices(notices: Sequence[ProviderNotice], *, example_limit: int = 5) -> str:
    """Describe a batch fallback once rather than producing one alert per asset."""

    if not notices:
        return ""
    examples = list(dict.fromkeys(item.asset_code for item in notices if item.asset_code))[:example_limit]
    categories = list(dict.fromkeys(item.category for item in notices))
    return (
        f"Tushare 异常后已使用 AkShare：{len(notices)} 次；"
        f"示例：{'、'.join(examples) or '全局配置'}；原因：{'、'.join(categories)}"
    )


class RequestRateLimiter:
    """Serializes calls so all Tushare endpoints share one safe request rate."""

    def __init__(
        self,
        requests_per_minute: int,
        *,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], None] = sleep,
    ) -> None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        self.interval = 60.0 / requests_per_minute
        self.clock = clock
        self.sleep = sleep
        self._lock = Lock()
        self._last_call: float | None = None

    def wait(self) -> None:
        with self._lock:
            now = self.clock()
            if self._last_call is not None:
                delay = self.interval - (now - self._last_call)
                if delay > 0:
                    self.sleep(delay)
                    now += delay
            self._last_call = now
