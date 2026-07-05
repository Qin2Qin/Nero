from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.xero_client import XeroClient


def test_xero_client_surface_is_read_only_for_mvp() -> None:
    assert hasattr(XeroClient, "list_contacts")
    assert hasattr(XeroClient, "list_invoices")
    assert hasattr(XeroClient, "list_payments")
    assert not hasattr(XeroClient, "create_invoices")
    assert not hasattr(XeroClient, "create_payments")
    assert not hasattr(XeroClient, "add_invoice_history")
