from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import login_required
from app.helpers import optional_int, parse_date
from app.models import Project, User
from app.money import money
from app.services.excel import excel_response
from app.services.reports import daily_transactions, monthly_transactions, project_accounting, project_summaries
from app.web import company, render

router = APIRouter(prefix="/reports")


@router.get("")
def index(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    return render(request, db, "reports/index.html", user, nav="reports")


@router.get("/project-pnl")
def project_pnl(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    summaries = project_summaries(db)
    if request.query_params.get("export") == "1":
        return excel_response(
            title="Project P&L",
            headers=["Project", "Revenue", "Cost", "Gross result", "Receivable", "Payable", "Cash collected", "Cash paid", "Budget"],
            rows=[[s["project"].code, s["revenue"], s["cost"], s["gross_result"], s["receivable"], s["payable"], s["cash_collected"], s["cash_paid"], s["budget"]] for s in summaries],
            filename="Project P&L.xlsx",
            company=company(db).name if company(db) else "Razz CNPL",
        )
    return render(request, db, "reports/project_pnl.html", user, nav="project_pnl", summaries=summaries)


@router.get("/project-cost")
def project_cost(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    summaries = project_summaries(db)
    return render(request, db, "reports/project_cost.html", user, nav="reports", summaries=summaries)


@router.get("/project-cashflow")
def project_cashflow(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    summaries = project_summaries(db)
    return render(request, db, "reports/project_cashflow.html", user, nav="reports", summaries=summaries)


@router.get("/daily")
def daily(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    txn_date = parse_date(request.query_params.get("date")) or date.today()
    project_id = optional_int(request.query_params.get("project_id"))
    data = daily_transactions(db, txn_date, project_id)
    return render(request, db, "reports/daily.html", user, nav="reports", txn_date=txn_date, data=data, project_id=project_id)


@router.get("/monthly")
def monthly(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    year = int(request.query_params.get("year") or date.today().year)
    month = int(request.query_params.get("month") or date.today().month)
    project_id = optional_int(request.query_params.get("project_id"))
    data = monthly_transactions(db, year, month, project_id)
    return render(request, db, "reports/monthly.html", user, nav="reports", year=year, month=month, data=data, project_id=project_id)


@router.get("/project/{project_id}")
def project_report(project_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    project = db.get(Project, project_id)
    if not project:
        from app.exceptions import ValidationError
        raise ValidationError("Project not found.")
    summary = project_accounting(db, project)
    return render(request, db, "reports/project_detail.html", user, nav="projects", summary=summary)
