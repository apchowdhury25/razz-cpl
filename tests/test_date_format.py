"""Bangladeshi date display DD/MM/YYYY. Storage stays date objects."""

from datetime import date, datetime

from app.helpers import format_date, parse_date


DISPLAY = [
    (date(2026, 1, 1), "01/01/2026"),
    (date(2026, 1, 5), "05/01/2026"),
    (date(2026, 3, 9), "09/03/2026"),
    (date(2026, 8, 20), "20/08/2026"),
    (date(2026, 8, 31), "31/08/2026"),
    (date(2027, 1, 28), "28/01/2027"),
    (date(2027, 2, 16), "16/02/2027"),
    (date(2027, 8, 1), "01/08/2027"),
    (date(2027, 8, 20), "20/08/2027"),
]


def test_format_date_dd_mm_yyyy():
    for value, expected in DISPLAY:
        assert format_date(value) == expected


def test_parse_dd_mm_yyyy_not_us():
    assert parse_date("09/03/2026") == date(2026, 3, 9)
    assert parse_date("20/08/2027") == date(2027, 8, 20)
    assert parse_date("01/08/2026") == date(2026, 8, 1)
    assert parse_date("5/3/2026") == date(2026, 3, 5)


def test_parse_iso_still_works_for_legacy_query_strings():
    assert parse_date("2026-08-20") == date(2026, 8, 20)


def test_display_uses_slash_not_dash():
    assert "/" in format_date(date(2026, 8, 20))
    assert "-" not in format_date(date(2026, 8, 20))


def test_datetime_display():
    stamp = datetime(2026, 8, 20, 14, 30)
    assert format_date(stamp).startswith("20/08/2026")
