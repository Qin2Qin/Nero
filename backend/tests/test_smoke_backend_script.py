from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "smoke_backend.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("smoke_backend", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_backend_defaults_to_demo_mode_and_temp_db(monkeypatch) -> None:
    module = load_script_module()
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("NERO_DB_PATH", raising=False)
    monkeypatch.setattr(module.os, "getpid", lambda: 12345)

    module.prepare_environment()

    assert module.os.environ["DEMO_MODE"] == "true"
    assert module.os.environ["NERO_DB_PATH"].endswith("nero-smoke-backend-12345.db")


def test_smoke_backend_respects_explicit_environment(monkeypatch, tmp_path) -> None:
    module = load_script_module()
    db_path = tmp_path / "custom.db"
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NERO_DB_PATH", str(db_path))

    module.prepare_environment()

    assert module.os.environ["DEMO_MODE"] == "false"
    assert module.os.environ["NERO_DB_PATH"] == str(db_path)
