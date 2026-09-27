from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import can_write, login_required, verify_csrf
from app.exceptions import ValidationError
from app.helpers import flash, optional_int, paginate, parse_money, require_date
from app.models import Booking, Customer, Unit, User
from app.services.ar import create_booking
from app.web import render

router = APIRouter(prefix="/bookings")


@router.get("")
def list_bookings(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    stmt = (
        select(Booking)
        .options(selectinload(Booking.customer), selectinload(Booking.project), selectinload(Booking.unit))
        .order_by(Booking.id.desc())
    )
    project_id = optional_int(request.query_params.get("project_id"))
    q = request.query_params.get("q", "").strip()
    if project_id:
        stmt = stmt.where(Booking.project_id == project_id)
    if q:
        stmt = stmt.where(Booking.booking_no.ilike(f"%{q}%"))
    page = paginate(db, stmt, int(request.query_params.get("page", 1)))
    return render(request, db, "bookings/list.html", user, nav="bookings", page=page, q=q, project_id=project_id)


@router.get("/new")
def new_form(request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    customers = db.execute(select(Customer).where(Customer.is_active.is_(True)).order_by(Customer.name)).scalars().all()
    units = db.execute(select(Unit).options(selectinload(Unit.project)).where(Unit.status.in_(["UNSOLD", "RESERVED"]))).scalars().all()
    return render(request, db, "bookings/form.html", user, nav="bookings", customers=customers, units=units)


@router.post("/new")
def create(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(login_required),
    csrf: str = Form(""),
    booking_date: str = Form(...),
    customer_id: int = Form(...),
    unit_id: int = Form(...),
    agreed_price: str = Form(...),
    notes: str = Form(""),
):
    verify_csrf(request, csrf)
    if not can_write(user):
        raise ValidationError("You cannot create bookings.")
    unit = db.get(Unit, unit_id)
    if not unit:
        raise ValidationError("Unit not found.")
    booking = create_booking(
        db,
        booking_date=require_date(booking_date, "Booking date"),
        customer_id=customer_id,
        project_id=unit.project_id,
        unit_id=unit.id,
        agreed_price=parse_money(agreed_price, "Agreed price"),
        user=user,
        notes=notes,
        generate_demands=True,
    )
    db.commit()
    flash(request, f"Booking {booking.booking_no} created and demands posted.")
    return RedirectResponse(f"/bookings/{booking.id}", status_code=303)


@router.get("/{item_id}")
def detail(item_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(login_required)):
    item = db.execute(
        select(Booking)
        .options(
            selectinload(Booking.customer),
            selectinload(Booking.project),
            selectinload(Booking.unit),
            selectinload(Booking.schedules),
        )
        .where(Booking.id == item_id)
    ).scalar_one_or_none()
    if not item:
        raise ValidationError("Booking not found.")
    return render(request, db, "bookings/detail.html", user, nav="bookings", item=item)
