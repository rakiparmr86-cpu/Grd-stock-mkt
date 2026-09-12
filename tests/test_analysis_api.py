from __future__ import annotations

import io

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.main import app
from app.models.user import User

PW = "pw12345678"


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    User.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        c.post("/api/v1/auth/register", json={"email": "t@t.com", "password": PW})
        token = c.post(
            "/api/v1/auth/login", data={"username": "t@t.com", "password": PW}
        ).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
    app.dependency_overrides.clear()


def test_requires_auth():
    with TestClient(app) as c:
        payload = {"index": ["2022"], "series": {"sales": [1.0]}}
        r = c.post("/api/v1/analysis/statistics", json=payload)
        assert r.status_code == 401


def test_statistics_full_report(client):
    payload = {
        "index": ["2019", "2020", "2021", "2022", "2023"],
        "series": {
            "sales": [100.0, 110.0, 121.0, 133.0, 146.0],
            "net_profit": [10.0, 12.0, 15.0, 17.0, 20.0],
        },
        "target": "net_profit",
        "features": ["sales"],
        "forecast_periods": 1,
    }
    r = client.post("/api/v1/analysis/statistics", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert set(body["metrics"]) == {"sales", "net_profit"}
    assert body["metrics"]["sales"]["descriptive_stats"]["count"] == 5
    assert body["metrics"]["net_profit"]["growth_trend"]["cagr_pct"] > 0
    assert "correlation" in body
    assert body["regression"]["target"] == "net_profit"
    assert body["regression"]["r_squared"] > 0.9


def test_statistics_rejects_mismatched_lengths(client):
    payload = {"index": ["2022", "2023"], "series": {"sales": [1.0]}}
    r = client.post("/api/v1/analysis/statistics", json=payload)
    assert r.status_code == 422


def test_statistics_rejects_unknown_target(client):
    payload = {
        "index": ["2022", "2023"],
        "series": {"sales": [1.0, 2.0]},
        "target": "nonexistent",
    }
    r = client.post("/api/v1/analysis/statistics", json=payload)
    assert r.status_code == 422


_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _screener_style_xlsx(sheet_name: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.append(["SOME COMPANY LTD"])
    ws.append([
        "Narration", "2019", "2020", "2021", "2022", "2023",
        "Trailing", "Best Case", "Worst Case",
    ])
    ws.append(["Sales", 100, 110, 121, 133, 146, 150, 160, 140])
    ws.append(["Net profit", 10, 12, 15, 17, 20, 21, 23, 18])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_analyze_excel_end_to_end(client):
    xlsx_bytes = _screener_style_xlsx("Profit & Loss")
    r = client.post(
        "/api/v1/analysis/excel",
        files={"file": ("statement.xlsx", xlsx_bytes, _XLSX_MIME)},
        data={
            "sheet": "Profit & Loss",
            "target": "Net profit",
            "features": "Sales",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body["metrics"]) == {"Sales", "Net profit"}
    assert body["regression"]["target"] == "Net profit"
    assert body["metrics"]["Sales"]["descriptive_stats"]["count"] == 5


def test_analyze_excel_bad_sheet_name(client):
    xlsx_bytes = _screener_style_xlsx("Profit & Loss")
    r = client.post(
        "/api/v1/analysis/excel",
        files={"file": ("statement.xlsx", xlsx_bytes, _XLSX_MIME)},
        data={"sheet": "Does Not Exist"},
    )
    assert r.status_code == 422
