from datetime import date

from etf_trading.data.update_state import DataUpdateState


def test_missing_trade_dates_are_computed_from_last_success_date():
    state = DataUpdateState(last_success_trade_date=date(2024, 1, 2))
    calendar = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    ]

    assert state.missing_trade_dates(calendar, through=date(2024, 1, 5)) == [
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
    ]


def test_rolling_refetch_window_includes_recent_successful_dates():
    state = DataUpdateState(last_success_trade_date=date(2024, 1, 10))
    calendar = [
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
        date(2024, 1, 9),
        date(2024, 1, 10),
    ]

    assert state.rolling_refetch_dates(calendar, window=5) == [
        date(2024, 1, 4),
        date(2024, 1, 5),
        date(2024, 1, 8),
        date(2024, 1, 9),
        date(2024, 1, 10),
    ]
