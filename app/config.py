from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RAZZ_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("RAZZ_DATABASE_URL", f"sqlite:///{DATA_DIR / 'razz_accounts.db'}")
SECRET_KEY = os.environ.get("RAZZ_SECRET_KEY", "razz-cnpl-dev-secret-change-in-production")
SESSION_COOKIE = "razz_session"
APP_NAME = "Razz CNPL Accounts"
COMPANY_NAME = "Razz CNPL"
DEFAULT_FY_CODE = "FY 2026-27"
PAGE_SIZE = 25
BACKUP_DIR = Path(os.environ.get("RAZZ_BACKUP_DIR", BASE_DIR / "backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
