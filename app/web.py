from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import can_approve, can_config, can_reverse, can_write, csrf_token
from app.helpers import dmy, lang, pop_flash, t
from app.i18n import t as translate
from app.models import CompanySettings, Project
from app.money import amount_in_words_bn, amount_in_words_en, format_money

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["money"] = format_money
templates.env.filters["bdt"] = format_money
templates.env.filters["dmy"] = dmy
templates.env.filters["words"] = amount_in_words_en
templates.env.filters["words_bn"] = amount_in_words_bn


def company(db: Session) -> CompanySettings | None:
    return db.execute(select(CompanySettings)).scalar_one_or_none()


def render(request: Request, db: Session, name: str, user, **ctx):
    settings = company(db)
    projects = db.execute(select(Project).order_by(Project.code)).scalars().all()
    language = lang(request)
    context = {
        "request": request,
        "user": user,
        "settings": settings,
        "projects": projects,
        "lang": language,
        "csrf": csrf_token(request),
        "flash_messages": pop_flash(request),
        "t": lambda key: translate(language, key),
        "can_write": can_write(user) if user else False,
        "can_approve": can_approve(user) if user else False,
        "can_config": can_config(user) if user else False,
        "can_reverse": can_reverse(user) if user else False,
        "nav": ctx.pop("nav", ""),
        **ctx,
    }
    status_code = context.pop("status_code", 200)
    return templates.TemplateResponse(request, name, context, status_code=status_code)
