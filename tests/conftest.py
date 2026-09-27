from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_DB = ROOT / "data" / "pytest_razz.db"
TEST_DB.parent.mkdir(parents=True, exist_ok=True)
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["RAZZ_DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["RAZZ_SECRET_KEY"] = "pytest-secret-key"
os.environ["RAZZ_DATA_DIR"] = str(ROOT / "data")

import pytest
from starlette.testclient import TestClient

from app.database import SessionLocal, init_db
from app.seed import seed_all


CSRF_RE = re.compile(r'name="csrf"\s+value="([^"]+)"')


@pytest.fixture(scope="session")
def seeded_db():
    init_db()
    seed_all()
    yield


@pytest.fixture
def client(seeded_db):
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(seeded_db):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def extract_csrf(html: str) -> str:
    match = CSRF_RE.search(html)
    return match.group(1) if match else ""


def login(client: TestClient, username: str, password: str):
    page = client.get("/login")
    token = extract_csrf(page.text)
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf": token},
        follow_redirects=False,
    )



