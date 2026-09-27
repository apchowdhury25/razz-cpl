from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def money(value: Any) -> Decimal:
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, str):
        result = Decimal(value.replace(",", "").replace("৳", "").strip() or "0")
    elif isinstance(value, float):
        result = Decimal(str(value))
    else:
        result = Decimal(str(value))
    return result.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def pct_amount(base: Any, percent: Any) -> Decimal:
    return money(money(base) * money(percent) / HUNDRED)


def format_bdt_number(value: Any) -> str:
    """Group a BDT amount with Indian/Bangladeshi separators and exactly 2 decimals.

    Last three digits before the decimal form one group; every group to the
    left has two digits. Sign is preserved. Zero is 0.00.
    """
    amount = money(value)
    negative = amount < 0
    amount = abs(amount)
    text = f"{amount:.2f}"
    int_part, frac_part = text.split(".")
    if len(int_part) <= 3:
        grouped = int_part
    else:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        pairs: list[str] = []
        while rest:
            pairs.append(rest[-2:])
            rest = rest[:-2]
        grouped = ",".join(reversed(pairs)) + "," + last3
    sign = "-" if negative else ""
    return f"{sign}{grouped}.{frac_part}"


def format_money(value: Any, symbol: bool = True, currency: str = "BDT") -> str:
    """Display formatter for monetary amounts. BDT uses Bangladeshi grouping."""
    if (currency or "BDT").upper() != "BDT":
        amount = money(value)
        formatted = f"{amount:,.2f}"
        return formatted if not symbol else formatted
    formatted = format_bdt_number(value)
    return f"৳ {formatted}" if symbol else formatted


def parse_percent(value: Any) -> Decimal:
    if value is None or value == "":
        return ZERO
    return money(value)


ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

ONES_BN = [
    "", "এক", "দুই", "তিন", "চার", "পাঁচ", "ছয়", "সাত", "আট", "নয়", "দশ",
    "এগারো", "বারো", "তেরো", "চৌদ্দ", "পনেরো", "ষোল", "সতেরো", "আঠারো", "উনিশ",
    "বিশ", "একুশ", "বাইশ", "তেইশ", "চব্বিশ", "পঁচিশ", "ছাব্বিশ", "সাতাশ", "আঠাশ", "ঊনত্রিশ",
    "ত্রিশ", "একত্রিশ", "বত্রিশ", "তেত্রিশ", "চৌত্রিশ", "পঁয়ত্রিশ", "ছত্রিশ", "সাঁইত্রিশ", "আটত্রিশ", "ঊনচল্লিশ",
    "চল্লিশ", "একচল্লিশ", "বিয়াল্লিশ", "তেতাল্লিশ", "চুয়াল্লিশ", "পঁয়তাল্লিশ", "ছেচল্লিশ", "সাতচল্লিশ", "আটচল্লিশ", "ঊনপঞ্চাশ",
    "পঞ্চাশ", "একান্ন", "বায়ান্ন", "তিপ্পান্ন", "চুয়ান্ন", "পঞ্চান্ন", "ছাপ্পান্ন", "সাতান্ন", "আটান্ন", "ঊনষাট",
    "ষাট", "একষট্টি", "বাষট্টি", "তেষট্টি", "চৌষট্টি", "পঁয়ষট্টি", "ছেষট্টি", "সাতষট্টি", "আটষট্টি", "ঊনসত্তর",
    "সত্তর", "একাত্তর", "বাহাত্তর", "তিয়াত্তর", "চুয়াত্তর", "পঁচাত্তর", "ছিয়াত্তর", "সাতাত্তর", "আটাত্তর", "ঊনআশি",
    "আশি", "একাশি", "বিরাশি", "তিরাশি", "চুরাশি", "পঁচাশি", "ছিয়াশি", "সাতাশি", "আটাশি", "ঊননব্বই",
    "নব্বই", "একানব্বই", "বিরানব্বই", "তিরানব্বই", "চুরানব্বই", "পঁচানব্বই", "ছিয়ানব্বই", "সাতানব্বই", "আটানব্বই", "নিরানব্বই",
]


def _chunk_en(n: int) -> str:
    if n == 0:
        return ""
    if n < 20:
        return ONES[n]
    if n < 100:
        return (TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")).strip()
    return (ONES[n // 100] + " Hundred" + (" " + _chunk_en(n % 100) if n % 100 else "")).strip()


def amount_in_words_en(value: Any) -> str:
    amount = money(value)
    if amount < 0:
        return "Minus " + amount_in_words_en(-amount)
    taka = int(amount)
    poisha = int((amount - Decimal(taka)) * 100)
    if taka == 0:
        words = "Zero"
    else:
        crore = taka // 10000000
        lakh = (taka % 10000000) // 100000
        thousand = (taka % 100000) // 1000
        rest = taka % 1000
        parts = []
        if crore:
            parts.append(_chunk_en(crore) + " Crore")
        if lakh:
            parts.append(_chunk_en(lakh) + " Lakh")
        if thousand:
            parts.append(_chunk_en(thousand) + " Thousand")
        if rest:
            parts.append(_chunk_en(rest))
        words = " ".join(parts)
    result = f"{words} Taka"
    if poisha:
        result += f" and {_chunk_en(poisha)} Poisha"
    return result + " Only"


def _bn_below_thousand(n: int) -> str:
    if n == 0:
        return ""
    parts = []
    if n >= 100:
        parts.append(ONES_BN[n // 100] + " শত")
        n %= 100
    if n:
        parts.append(ONES_BN[n])
    return " ".join(parts)


def amount_in_words_bn(value: Any) -> str:
    amount = money(value)
    taka = int(amount)
    if taka == 0:
        return "শূন্য টাকা মাত্র"
    crore = taka // 10000000
    lakh = (taka % 10000000) // 100000
    thousand = (taka % 100000) // 1000
    rest = taka % 1000
    parts = []
    if crore:
        parts.append(_bn_below_thousand(crore) + " কোটি")
    if lakh:
        parts.append(_bn_below_thousand(lakh) + " লক্ষ")
    if thousand:
        parts.append(_bn_below_thousand(thousand) + " হাজার")
    if rest:
        parts.append(_bn_below_thousand(rest))
    return " ".join(parts) + " টাকা মাত্র"
