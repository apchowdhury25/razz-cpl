from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def _dump(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except TypeError:
        return str(value)


def write_audit(
    db: Session,
    *,
    user: User | None,
    action: str,
    module: str,
    record_type: str = "",
    record_id: int | None = None,
    document_no: str = "",
    old_values: Any = None,
    new_values: Any = None,
    ip_address: str = "",
    description: str = "",
) -> AuditLog:
    log = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else "",
        action=action,
        module=module,
        record_type=record_type,
        record_id=record_id,
        document_no=document_no,
        old_values=_dump(old_values),
        new_values=_dump(new_values),
        ip_address=ip_address or "",
        description=description,
    )
    db.add(log)
    db.flush()
    return log
