from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import PAGE_SIZE
from app.exceptions import ValidationError
from app.i18n import t as translate
from app.money import money


def lang(request: Request) -> str:
    return request.cookies.get("lang") or request.session.get("lang") or "en"


def t(request: Request, key: str) -> str:
    return translate(lang(request), key)


def flash(request: Request, message: str, category: str = "success") -> None:
    request.session.setdefault("flash", []).append({"message": message, "category": category})


def pop_flash(request: Request) -> list[dict[str, str]]:
    items = request.session.pop("flash", [])
    return items


def parse_date(value: str | None, field: str = "Date") -> date | None:
    """Parse a user date as DD/MM/YYYY (Bangladeshi). Never MM/DD/YYYY."""
    if not value:
        return None
    value = value.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt).date()
            if fmt == "%d/%m/%Y" or fmt == "%d-%m-%Y":
                day_s, month_s, _year_s = value.replace("-", "/").split("/")
                if int(day_s) != parsed.day or int(month_s) != parsed.month:
                    raise ValueError("day/month mismatch")
            return parsed
        except ValueError:
            continue
    raise ValidationError(f"{field} is invalid. Use DD/MM/YYYY.")


def require_date(value: str | None, field: str = "Date") -> date:
    parsed = parse_date(value, field)
    if not parsed:
        raise ValidationError(f"{field} is required.")
    return parsed


def parse_money(value: str | None, field: str = "Amount"):
    if value is None or str(value).strip() == "":
        raise ValidationError(f"{field} is required.")
    try:
        amount = money(value)
    except Exception as exc:
        raise ValidationError(f"{field} is not a valid amount.") from exc
    return amount


def optional_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(value)


def format_date(value: date | datetime | None) -> str:
    """User-facing Bangladeshi date: DD/MM/YYYY with leading zeros."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    return value.strftime("%d/%m/%Y")


def dmy(value: date | datetime | None) -> str:
    return format_date(value)


def paginate(db: Session, stmt, page: int, per_page: int = PAGE_SIZE):
    page = max(1, page)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.execute(count_stmt).scalar() or 0
    pages = max(1, math.ceil(total / per_page)) if total else 1
    rows = db.execute(stmt.offset((page - 1) * per_page).limit(per_page)).scalars().all()
    return {"rows": rows, "page": page, "pages": pages, "total": total, "per_page": per_page}


def query_with(request: Request, **updates: Any) -> str:
    data = dict(request.query_params)
    for key, value in updates.items():
        if value is None or value == "":
            data.pop(key, None)
        else:
            data[key] = value
    return urlencode(data)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""
