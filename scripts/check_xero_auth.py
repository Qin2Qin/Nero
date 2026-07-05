#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from config import get_settings  # noqa: E402
from services.xero_auth import AUTH_URL, SCOPES, TOKEN_URL  # noqa: E402


COMMON_REDIRECTS = (
    "http://localhost:8000/auth/callback",
    "http://localhost:8000/auth/callback/",
    "http://127.0.0.1:8000/auth/callback",
    "http://localhost:5173/auth/callback",
    "http://localhost:3000/auth/callback",
    "http://localhost:8000/callback",
    "http://localhost:3000/callback",
    "http://localhost:5173/callback",
)


def page_text(markup: str) -> str:
    text = re.sub(r"<[^>]+>", " ", markup)
    return html.unescape(" ".join(text.split()))


def authorize_url(client_id: str, redirect_uri: str, state: str = "nero-auth-check") -> str:
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def redact_url(value: str) -> str:
    return re.sub(r"([?&]client_id=)[^&]+", r"\1[REDACTED]", value)


def check_redirect(client: httpx.Client, client_id: str, redirect_uri: str) -> tuple[bool, str]:
    response = client.get(authorize_url(client_id, redirect_uri))
    text = page_text(response.text)
    final_url = str(response.url)
    if "Invalid redirect_uri" in text or "invalid_request" in text or "/identity/error" in final_url:
        return False, f"rejected by Xero ({response.status_code})"
    if "Log in to Xero" in text or "/identity/user/login" in final_url:
        return True, f"accepted by Xero ({response.status_code})"
    return False, f"unexpected authorize response ({response.status_code}, {redact_url(final_url)})"


def check_client_credentials(
    client: httpx.Client,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> tuple[bool, str]:
    response = client.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": "nero-intentionally-invalid-code",
            "redirect_uri": redirect_uri,
        },
        auth=(client_id, client_secret),
    )
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error")
    description = body.get("error_description") or ""
    if error == "invalid_grant":
        return True, "accepted client credentials; rejected fake code as expected"
    if error == "invalid_client":
        return False, f"invalid client credentials ({description})"
    return False, f"unexpected token response {response.status_code}: {error or 'no error'} {description}".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Xero OAuth settings without printing secrets or tokens.")
    parser.add_argument(
        "--probe-common-redirects",
        action="store_true",
        help="Also test common localhost redirect URI variants against this client ID.",
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"client_id_configured={bool(settings.xero_client_id)}")
    print(f"client_secret_configured={bool(settings.xero_client_secret)}")
    print(f"redirect_uri={settings.xero_redirect_uri}")
    if not settings.xero_client_id or not settings.xero_client_secret:
        print("result=failed")
        print("reason=missing XERO_CLIENT_ID or XERO_CLIENT_SECRET")
        return 2

    with httpx.Client(timeout=30.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as client:
        redirect_ok, redirect_message = check_redirect(client, settings.xero_client_id, settings.xero_redirect_uri)
        print(f"authorize_redirect={redirect_message}")

        credentials_ok, credentials_message = check_client_credentials(
            client,
            settings.xero_client_id,
            settings.xero_client_secret,
            settings.xero_redirect_uri,
        )
        print(f"token_client_auth={credentials_message}")

        if args.probe_common_redirects:
            print("common_redirect_probe:")
            for redirect_uri in COMMON_REDIRECTS:
                ok, message = check_redirect(client, settings.xero_client_id, redirect_uri)
                marker = "ok" if ok else "fail"
                print(f"  {marker} {redirect_uri} - {message}")

    if redirect_ok and credentials_ok:
        print("result=passed")
        return 0
    print("result=failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
