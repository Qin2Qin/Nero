from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import routers.data as data_router
from main import create_app
from services.statements import build_statement, render_statement_html


def statement_state() -> dict:
    return {
        "contacts": [
            {
                "id": "contact-1",
                "name": "City Limousines",
                "revenue_12m": 1000,
                "grade": "C",
                "avg_days_late": 3,
                "stdev_days_late": 1,
                "trend_slope": 0,
                "invoice_count": 4,
            }
        ],
        "invoices": [
            {
                "id": "invoice-1",
                "contact_id": "contact-1",
                "contact_name": "City Limousines",
                "invoice_number": "INV-001",
                "amount_due": 250,
                "issue_date": "2026-06-01",
                "due_date": "2026-06-30",
                "status": "AUTHORISED",
                "predicted_paid_date": "2026-07-10",
            },
            {
                "id": "invoice-2",
                "contact_id": "contact-1",
                "contact_name": "City Limousines",
                "invoice_number": "INV-002",
                "amount_due": 500,
                "issue_date": "2026-07-01",
                "due_date": "2026-07-20",
                "status": "AUTHORISED",
                "predicted_paid_date": "2026-07-25",
            },
            {
                "id": "invoice-other",
                "contact_id": "contact-2",
                "contact_name": "Other Customer",
                "invoice_number": "INV-003",
                "amount_due": 999,
                "issue_date": "2026-07-01",
                "due_date": "2026-07-10",
                "status": "AUTHORISED",
                "predicted_paid_date": "2026-07-12",
            },
        ],
        "proposals": [],
        "data_source": {"mode": "fixture", "label": "Demo Company"},
    }


def test_build_statement_filters_customer_open_invoices() -> None:
    statement = build_statement(statement_state(), "contact-1")

    assert statement["contact_name"] == "City Limousines"
    assert statement["business_name"] == "Demo Company"
    assert statement["invoice_count"] == 2
    assert statement["total_due"] == 750
    assert [invoice["invoice_number"] for invoice in statement["invoices"]] == ["INV-001", "INV-002"]
    assert statement["invoices"][0]["timing"] == "4 days overdue"


def test_statement_html_is_printable_and_escaped() -> None:
    state = statement_state()
    state["contacts"][0]["name"] = "City <Limousines>"

    html = render_statement_html(build_statement(state, "contact-1"))

    assert "Print or save as PDF" in html
    assert "City &lt;Limousines&gt;" in html
    assert "£750" in html
    assert "GBP" not in html
    assert "Other Customer" not in html


def test_statement_endpoint_returns_html(monkeypatch) -> None:
    monkeypatch.setattr(data_router, "get_state", statement_state)
    client = TestClient(create_app())

    response = client.get("/api/statements/contact-1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Customer statement" in response.text
    assert "INV-001" in response.text


def test_statement_endpoint_404s_unknown_customer(monkeypatch) -> None:
    monkeypatch.setattr(data_router, "get_state", statement_state)
    client = TestClient(create_app())

    response = client.get("/api/statements/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "customer not found"
