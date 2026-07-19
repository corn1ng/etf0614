from pathlib import Path

from etf_trading.data.provider_runtime import (
    ProviderNotice,
    RequestRateLimiter,
    load_provider_settings,
    redact_provider_text,
    summarize_provider_notices,
)


def test_settings_read_token_only_from_environment(tmp_path: Path):
    config = tmp_path / "data_sources.yaml"
    config.write_text(
        "tushare:\n"
        "  api_url: https://proxy.example/api\n"
        "  requests_per_minute: 120\n"
        "  attempts: 3\n",
        encoding="utf-8",
    )

    settings = load_provider_settings(config, {"TUSHARE_TOKEN": "secret-value"})

    assert settings.token == "secret-value"
    assert settings.api_url == "https://proxy.example/api"
    assert "secret-value" not in repr(settings)


def test_environment_overrides_tushare_api_url(tmp_path: Path):
    config = tmp_path / "data_sources.yaml"
    config.write_text("tushare:\n  api_url: https://default.example/api\n", encoding="utf-8")

    settings = load_provider_settings(
        config,
        {"TUSHARE_TOKEN": "secret", "TUSHARE_API_URL": "https://override.example/api"},
    )

    assert settings.api_url == "https://override.example/api"


def test_redaction_removes_token_and_tokenized_url():
    text = "failed token=secret-value at https://proxy.example/mcp/token=secret-value"

    result = redact_provider_text(text, secrets=("secret-value",))

    assert "secret-value" not in result
    assert "[REDACTED]" in result


def test_notice_summary_aggregates_codes():
    notices = [
        ProviderNotice("fetch_etf_daily", "510300", "network", "timeout", "akshare"),
        ProviderNotice("fetch_etf_daily", "510500", "network", "timeout", "akshare"),
    ]

    assert summarize_provider_notices(notices, example_limit=1) == (
        "Tushare 异常后已使用 AkShare：2 次；示例：510300；原因：network"
    )


def test_rate_limiter_waits_for_configured_interval():
    times = iter([0.0, 0.1])
    waits: list[float] = []
    limiter = RequestRateLimiter(120, clock=lambda: next(times), sleep=waits.append)

    limiter.wait()
    limiter.wait()

    assert waits == [0.4]
