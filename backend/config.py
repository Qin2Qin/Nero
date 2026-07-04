from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = ROOT_DIR / "fixtures"
PROMPTS_DIR = ROOT_DIR / "prompts"


def _read_dotenv() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    demo_mode: bool
    xero_client_id: str
    xero_client_secret: str
    xero_tenant_id: str
    xero_redirect_uri: str
    anthropic_api_key: str
    cash_floor: int
    frontend_origins: tuple[str, ...]
    database_path: Path


def get_settings() -> Settings:
    _read_dotenv()
    origins = tuple(
        origin.strip()
        for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
        if origin.strip()
    )
    return Settings(
        demo_mode=_as_bool(os.getenv("DEMO_MODE"), True),
        xero_client_id=os.getenv("XERO_CLIENT_ID", ""),
        xero_client_secret=os.getenv("XERO_CLIENT_SECRET", ""),
        xero_tenant_id=os.getenv("XERO_TENANT_ID", ""),
        xero_redirect_uri=os.getenv("XERO_REDIRECT_URI", "http://localhost:8000/auth/callback"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        cash_floor=int(os.getenv("CASH_FLOOR", "5000")),
        frontend_origins=origins,
        database_path=Path(os.getenv("NERO_DB_PATH", Path(__file__).with_name("nero.db"))),
    )
