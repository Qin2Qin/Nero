#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.xero_auth import get_valid_access  # noqa: E402


XERO_REMOTE_MCP_URL = "https://builders.xero.com/beta/mcp"


def main() -> int:
    npx = shutil.which("npx") or "/opt/homebrew/bin/npx"
    if not Path(npx).exists():
        print("npx is required to run mcp-remote but was not found.", file=sys.stderr)
        return 127

    try:
        tokens = get_valid_access()
    except Exception as exc:  # pragma: no cover - defensive entrypoint
        print(f"Failed to load or refresh Xero OAuth tokens: {exc}", file=sys.stderr)
        return 1

    access_token = tokens.get("access_token")
    if not access_token:
        print("No Xero access token is saved. Run the Xero OAuth flow first.", file=sys.stderr)
        return 1

    env = os.environ.copy()

    os.execve(
        npx,
        [
            npx,
            "-y",
            "mcp-remote@latest",
            XERO_REMOTE_MCP_URL,
            "--transport",
            "http-only",
            "--header",
            f"Authorization: Bearer {access_token}",
            "--silent",
        ],
        env,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
