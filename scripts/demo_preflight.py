#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def request_json(base_url: str, path: str, method: str = "GET", timeout: float = 10.0) -> dict[str, Any] | list[Any]:
    url = urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))
    body = b"" if method != "GET" else None
    request = Request(url, data=body, method=method, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as error:
        raise RuntimeError(f"{method} {path} returned HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"{method} {path} failed: {error.reason}") from error
    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{method} {path} did not return JSON") from error


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def pounds(value: Any) -> str:
    return f"£{round(float(value or 0)):,}"


def fail(failures: list[str], lines: list[str], label: str, detail: str) -> None:
    failures.append(f"{label}: {detail}")
    lines.append(f"FAIL {label}: {detail}")


def pass_line(lines: list[str], label: str, detail: str) -> None:
    lines.append(f"PASS {label}: {detail}")


def evaluate_preflight(
    payloads: dict[str, Any],
    *,
    max_age_minutes: int = 120,
    now: datetime | None = None,
) -> tuple[int, list[str]]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    lines = ["Nero live demo preflight"]
    failures: list[str] = []

    health = payloads.get("/health") or {}
    if health.get("ok") is True and health.get("demo_mode") is False:
        pass_line(lines, "backend", "running in live Xero mode")
    else:
        fail(failures, lines, "backend", "backend is not healthy or DEMO_MODE is still true")

    xero_status = payloads.get("/api/xero/status") or {}
    if (
        xero_status.get("connected") is True
        and xero_status.get("expired") is False
        and xero_status.get("needs_tenant") is False
        and xero_status.get("demo_mode") is False
    ):
        tenant = xero_status.get("tenant_id") or "selected tenant"
        pass_line(lines, "xero", f"connected, token current, tenant {tenant}")
    else:
        reason = xero_status.get("refresh_error") or "connect Xero, select a tenant, or refresh the OAuth token"
        fail(failures, lines, "xero", reason)

    sync_result = payloads.get("/api/sync")
    if sync_result is not None:
        fetched = sync_result.get("fetched") or {}
        materialized = sync_result.get("materialized") or {}
        if sync_result.get("status") == "synced" and not sync_result.get("empty") and sync_result.get("cash_data_ready"):
            pass_line(
                lines,
                "sync",
                (
                    f"{fetched.get('contacts', 0)} contacts, {fetched.get('invoices', 0)} invoices, "
                    f"{fetched.get('payments', 0)} payments; {materialized.get('proposals', 0)} actions ready"
                ),
            )
        else:
            fail(failures, lines, "sync", sync_result.get("detail") or "sync did not return usable cash data")

    data_source = payloads.get("/api/data_source") or {}
    generated_at = parse_datetime(data_source.get("generated_at"))
    if data_source.get("mode") == "xero" and generated_at:
        age_minutes = max(0, int((now - generated_at).total_seconds() // 60))
        detail = f"{data_source.get('label', 'Xero data')} updated {age_minutes} minutes ago"
        if age_minutes <= max_age_minutes:
            pass_line(lines, "data", detail)
        else:
            fail(failures, lines, "data", f"{detail}; run preflight with --sync or click Sync Xero")
    else:
        fail(failures, lines, "data", "dashboard is not using live Xero data")

    metrics = payloads.get("/api/metrics") or {}
    receivables = metrics.get("aged_receivables") or {}
    pending_count = int(metrics.get("pending_actions_count") or 0)
    pending_impact = float(metrics.get("pending_impact_dollars") or 0)
    open_total = float(receivables.get("open_total") or 0)
    overdue_total = float(receivables.get("overdue_total") or 0)
    if open_total > 0 and pending_count > 0:
        pass_line(
            lines,
            "cash story",
            f"{pounds(open_total)} owed, {pounds(overdue_total)} overdue, {pending_count} actions worth {pounds(pending_impact)}",
        )
    else:
        fail(failures, lines, "cash story", "needs open receivables and at least one pending action")

    proposals = payloads.get("/api/proposals") or []
    sendable = [
        proposal
        for proposal in proposals
        if proposal.get("status") == "pending" and proposal.get("draft_subject") and proposal.get("contact_email")
    ]
    if sendable:
        first = sendable[0]
        draft_label = "draft has" if len(sendable) == 1 else "drafts have"
        pass_line(
            lines,
            "actions",
            f"{len(sendable)} {draft_label} customer email; first is {first.get('contact_name')} for {pounds(first.get('expected_impact_dollars'))}",
        )
    else:
        fail(failures, lines, "actions", "no pending draft has a customer email")

    readiness = payloads.get("/api/app_store/readiness") or {}
    ready_count = int(readiness.get("ready_count") or 0)
    total_count = int(readiness.get("total_count") or 0)
    lines.append(f"INFO app store readiness: {ready_count}/{total_count} checks ready")

    if failures:
        lines.append("result=failed")
        return 1, lines
    lines.append("result=passed")
    return 0, lines


def collect_payloads(base_url: str, *, sync: bool, timeout: float) -> dict[str, Any]:
    payloads: dict[str, Any] = {
        "/health": request_json(base_url, "/health", timeout=timeout),
        "/api/xero/status": request_json(base_url, "/api/xero/status", timeout=timeout),
    }
    if sync:
        payloads["/api/sync"] = request_json(base_url, "/api/sync", method="POST", timeout=max(timeout, 30.0))
    payloads.update(
        {
            "/api/data_source": request_json(base_url, "/api/data_source", timeout=timeout),
            "/api/metrics": request_json(base_url, "/api/metrics", timeout=timeout),
            "/api/proposals": request_json(base_url, "/api/proposals", timeout=timeout),
            "/api/app_store/readiness": request_json(base_url, "/api/app_store/readiness", timeout=timeout),
        }
    )
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the local Nero live-Xero demo without printing secrets.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Backend base URL. Default: {DEFAULT_BASE_URL}")
    parser.add_argument("--sync", action="store_true", help="Run POST /api/sync before evaluating demo readiness.")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds.")
    parser.add_argument("--max-age-minutes", type=int, default=120, help="Maximum acceptable Xero snapshot age.")
    args = parser.parse_args(argv)

    try:
        payloads = collect_payloads(args.base_url, sync=args.sync, timeout=args.timeout)
        exit_code, lines = evaluate_preflight(payloads, max_age_minutes=args.max_age_minutes)
    except RuntimeError as error:
        print("Nero live demo preflight")
        print(f"FAIL request: {error}")
        print("result=failed")
        return 1

    for line in lines:
        print(line)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
