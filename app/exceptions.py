from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "error"

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class ValidationError(AppError):
    code = "validation"


class DuplicateDocumentError(AppError):
    code = "duplicate"
    status_code = 409


class LockedPeriodError(AppError):
    code = "locked_period"
    status_code = 409


class UnbalancedJournalError(AppError):
    code = "unbalanced_journal"
    status_code = 400


class AllocationError(AppError):
    code = "allocation"
    status_code = 400


class UnauthorizedError(AppError):
    code = "unauthorized"
    status_code = 403


class NotFoundError(AppError):
    code = "not_found"
    status_code = 404


class PostedDocumentError(AppError):
    code = "posted_locked"
    status_code = 409
