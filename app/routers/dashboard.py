from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import login_required
from app.models import User
from app.services.reports import dashboard_data
from app.web import render

router = APIRouter()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    as_of = date.today()
    data = dashboard_data(db, as_of)
    return render(request, db, "dashboard.html", user, nav="dashboard", **data)
