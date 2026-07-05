from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


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


def _local_origin_variant(origin: str) -> str | None:
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or parsed.path not in {"", "/"}:
        return None
    if parsed.hostname == "localhost":
        return urlunsplit((parsed.scheme, f"127.0.0.1:{port}" if port else "127.0.0.1", "", "", ""))
    if parsed.hostname == "127.0.0.1":
        return urlunsplit((parsed.scheme, f"localhost:{port}" if port else "localhost", "", "", ""))
    return None


def _frontend_origins(value: str) -> tuple[str, ...]:
    origins: list[str] = []
    seen: set[str] = set()

    def add(origin: str) -> None:
        if origin and origin not in seen:
            seen.add(origin)
            origins.append(origin)

    for raw_origin in value.split(","):
        origin = raw_origin.strip()
        add(origin)
        variant = _local_origin_variant(origin)
        if variant:
            add(variant)
    return tuple(origins)


@dataclass(frozen=True)
class Settings:
    demo_mode: bool
    xero_client_id: str
    xero_client_secret: str
    xero_tenant_id: str
    xero_redirect_uri: str
    xero_access_token: str
    xero_refresh_token: str
    xero_token_expires_at: str
    xero_token_expires_in: int
    xero_webhook_key: str
    xero_app_store_subscriptions_configured: bool
    ai_copy_enabled: bool
    openrouter_api_key: str
    openrouter_model: str
    openrouter_base_url: str
    cash_floor: int
    frontend_origins: tuple[str, ...]
    database_path: Path


def get_settings() -> Settings:
    _read_dotenv()
    origins = _frontend_origins(os.getenv("FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000"))
    return Settings(
        demo_mode=_as_bool(os.getenv("DEMO_MODE"), True),
        xero_client_id=os.getenv("XERO_CLIENT_ID", ""),
        xero_client_secret=os.getenv("XERO_CLIENT_SECRET", ""),
        xero_tenant_id=os.getenv("XERO_TENANT_ID", ""),
        xero_redirect_uri=os.getenv("XERO_REDIRECT_URI", "http://localhost:8000/auth/callback"),
        xero_access_token=os.getenv("XERO_ACCESS_TOKEN", ""),
        xero_refresh_token=os.getenv("XERO_REFRESH_TOKEN", ""),
        xero_token_expires_at=os.getenv("XERO_TOKEN_EXPIRES_AT", ""),
        xero_token_expires_in=int(os.getenv("XERO_TOKEN_EXPIRES_IN", "1800")),
        xero_webhook_key=os.getenv("XERO_WEBHOOK_KEY", ""),
        xero_app_store_subscriptions_configured=_as_bool(os.getenv("XERO_APP_STORE_SUBSCRIPTIONS_CONFIGURED"), False),
        ai_copy_enabled=_as_bool(os.getenv("NERO_AI_COPY_ENABLED"), False),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", ""),
        openrouter_model=os.getenv("OPENROUTER_MODEL", ""),
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"),
        cash_floor=int(os.getenv("CASH_FLOOR", "5000")),
        frontend_origins=origins,
        database_path=Path(os.getenv("NERO_DB_PATH", Path(__file__).with_name("nero.db"))),
    )
