from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import DuplicateDocumentError
from app.models import DocumentSequence

DEFAULT_PREFIXES = {
    "MR": "MR",
    "AR": "AR",
    "AP": "AP",
    "VP": "VP",
    "JV": "JV",
    "BK": "BK",
    "CN": "CN",
    "VN": "VN",
    "TR": "TR",
    "OR": "OR",
    "OP": "OP",
    "CU": "CU",
    "VE": "VE",
    "EM": "EM",
}


def ensure_sequence(db: Session, doc_type: str, year: int, prefix: str | None = None) -> DocumentSequence:
    seq = db.execute(
        select(DocumentSequence).where(DocumentSequence.doc_type == doc_type, DocumentSequence.year == year)
    ).scalar_one_or_none()
    if seq:
        return seq
    seq = DocumentSequence(
        doc_type=doc_type,
        prefix=prefix or DEFAULT_PREFIXES.get(doc_type, doc_type),
        year=year,
        next_number=1,
        padding=4,
    )
    db.add(seq)
    db.flush()
    return seq


def next_number(db: Session, doc_type: str, year: int, prefix: str | None = None) -> str:
    seq = ensure_sequence(db, doc_type, year, prefix)
    number = seq.next_number
    seq.next_number = number + 1
    db.flush()
    return f"{seq.prefix}-{year}-{number:0{seq.padding}d}"


def assert_unique(db: Session, model, field_name: str, value: str) -> None:
    existing = db.execute(select(model).where(getattr(model, field_name) == value)).scalar_one_or_none()
    if existing:
        raise DuplicateDocumentError(f"Document number {value} already exists.")
