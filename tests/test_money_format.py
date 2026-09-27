"""Bangladeshi/Indian grouping for BDT display. Values stay Decimal underneath."""

from decimal import Decimal

from app.money import format_bdt_number, format_money, money


CASES = [
    ("1000", "1,000.00"),
    ("10000", "10,000.00"),
    ("99999.99", "99,999.99"),
    ("100000", "1,00,000.00"),
    ("1000000", "10,00,000.00"),
    ("10000000", "1,00,00,000.00"),
    ("12345678.90", "1,23,45,678.90"),
    ("123456789", "12,34,56,789.00"),
    ("1000000000", "1,00,00,00,000.00"),
    ("0", "0.00"),
    ("0.00", "0.00"),
    ("-100000", "-1,00,000.00"),
    ("-1234567.89", "-12,34,567.89"),
    ("61095000", "6,10,95,000.00"),
    ("18205000", "1,82,05,000.00"),
    ("4387300", "43,87,300.00"),
]


def test_bdt_grouping_acceptance():
    for raw, expected in CASES:
        assert format_bdt_number(raw) == expected, f"{raw} -> {expected}"
        assert format_money(raw, symbol=False) == expected
        assert format_money(raw, symbol=True) == f"৳ {expected}"


def test_western_grouping_is_not_used_for_bdt():
    assert format_money("100000", symbol=False) != "100,000.00"
    assert format_money("1000000", symbol=False) != "1,000,000.00"
    assert "100,000.00" not in format_money("100000")


def test_formatter_does_not_change_numeric_value():
    assert money("1,00,000.00") == Decimal("100000.00")
    assert money("৳ 10,00,000.00") == Decimal("1000000.00")
    assert money("-12,34,567.89") == Decimal("-1234567.89")


def test_other_currency_does_not_use_bdt_grouping():
    assert format_money("100000", symbol=False, currency="USD") == "100,000.00"
