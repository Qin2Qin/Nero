from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from services.xero_auth import bootstrap_tokens_from_env  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Xero OAuth tokens from environment into the local Nero DB.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing saved token set.")
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Do not refresh XERO_REFRESH_TOKEN when XERO_ACCESS_TOKEN is absent.",
    )
    parser.add_argument(
        "--no-resolve-tenant",
        action="store_true",
        help="Do not call Xero connections to infer XERO_TENANT_ID.",
    )
    args = parser.parse_args()

    try:
        result = bootstrap_tokens_from_env(
            overwrite=args.overwrite,
            allow_refresh=not args.no_refresh,
            resolve_tenant=not args.no_resolve_tenant,
        )
    except RuntimeError as exc:
        print(f"Xero token import failed: {exc}", file=sys.stderr)
        return 2
    except httpx.HTTPError as exc:
        print(f"Xero token import failed during Xero API call: {exc}", file=sys.stderr)
        return 2

    status = result["status"]
    print(f"imported={result['imported']}")
    if result.get("reason"):
        print(f"reason={result['reason']}")
    if result.get("source"):
        print(f"source={result['source']}")
    print(f"connected={status['connected']}")
    print(f"tenant_id={status.get('tenant_id') or ''}")
    print(f"expires_at={status.get('expires_at') or ''}")
    print(f"needs_tenant={status.get('needs_tenant')}")
    return 0 if status["connected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
