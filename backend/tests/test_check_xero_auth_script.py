from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_xero_auth.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("check_xero_auth", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_redact_url_hides_xero_client_id() -> None:
    module = load_script_module()
    redacted = module.redact_url(
        "https://login.xero.com/identity/connect/authorize?response_type=code&client_id=abc123&state=nero"
    )

    assert "abc123" not in redacted
    assert "client_id=[REDACTED]" in redacted
