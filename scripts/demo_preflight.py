#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_FRONTEND_URL = "http://127.0.0.1:5173"
ROOT = Path(__file__).resolve().parents[1]
SUBMISSION_IMAGE = ROOT / "frontend" / "public" / "visuals" / "nero-live-dashboard-submission.png"
SUBMISSION_IMAGE_SIZE = (1120, 720)
ACTION_COPY_FIELDS = ("reasoning_text", "draft_subject", "draft_body", "recommendation_detail")
ACTION_COPY_BANNED_PATTERNS = {
    "payment-link placeholder": re.compile(r"\{payment_link\}", re.IGNORECASE),
    "fixture sender": re.compile(r"Harbour & Co", re.IGNORECASE),
    "singular-days grammar": re.compile(r"\b1 days\b", re.IGNORECASE),
    "raw GBP code": re.compile(r"\bGBP\s+", re.IGNORECASE),
    "technical variance": re.compile(r"\bvariance\b", re.IGNORECASE),
    "undefined placeholder": re.compile(r"\bundefined\b", re.IGNORECASE),
    "internal proposal count": re.compile(r"proposal\(s\)", re.IGNORECASE),
    "internal profile count": re.compile(r"profile\(s\)", re.IGNORECASE),
    "technical materialised copy": re.compile(r"\bmaterialised\b", re.IGNORECASE),
}
RAW_XERO_ID_LABEL = re.compile(r"(?<!invoice )\b[0-9a-f]{8}\b", re.IGNORECASE)
AI_DISABLED_DETAIL = "AI draft polishing is disabled."


def request_json(base_url: str, path: str, method: str = "GET", timeout: float = 10.0) -> dict[str, Any] | list[Any]:
    url = urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))
    body = b"" if method != "GET" else None
    request = Request(url, data=body, method=method, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as error:
        detail = ""
        try:
            error_payload = error.read().decode("utf-8", errors="replace")
            parsed_error = json.loads(error_payload)
            detail = str(parsed_error.get("detail") or "")
        except (OSError, json.JSONDecodeError, AttributeError):
            detail = ""
        retry_after = error.headers.get("Retry-After") if error.headers else None
        message = f"{method} {path} returned HTTP {error.code}"
        if detail:
            message = f"{message}: {detail}"
        if retry_after:
            message = f"{message} (Retry-After: {retry_after}s)"
        raise RuntimeError(message) from error
    except URLError as error:
        raise RuntimeError(f"{method} {path} failed: {error.reason}") from error
    try:
        return json.loads(payload)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{method} {path} did not return JSON") from error


def request_text(url: str, timeout: float = 10.0) -> str:
    request = Request(url, headers={"Accept": "text/html"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        raise RuntimeError(f"GET {url} returned HTTP {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"GET {url} failed: {error.reason}") from error


def check_frontend(frontend_url: str, timeout: float = 10.0) -> dict[str, Any]:
    text = request_text(frontend_url, timeout=timeout)
    return {
        "url": frontend_url,
        "has_root": '<div id="root"' in text,
        "has_title": "<title>Nero</title>" in text,
    }


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("not a PNG")
    return struct.unpack(">II", data[16:24])


def check_submission_image(path: Path = SUBMISSION_IMAGE) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path.relative_to(ROOT)), "exists": path.exists()}
    if not path.exists():
        return result
    try:
        width, height = png_dimensions(path)
    except (OSError, ValueError):
        result.update({"is_png": False})
        return result
    result.update({"is_png": True, "width": width, "height": height})
    return result


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def pounds(value: Any) -> str:
    return f"£{round(float(value or 0)):,}"


def action_copy_issues(proposals: list[Any]) -> list[str]:
    issues: list[str] = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        contact = str(proposal.get("contact_name") or proposal.get("id") or "unknown action")
        text = "\n".join(str(proposal.get(field) or "") for field in ACTION_COPY_FIELDS)
        if not text.strip():
            continue
        scrubbed = re.sub(r"https?://\S+", "", text)
        for label, pattern in ACTION_COPY_BANNED_PATTERNS.items():
            if pattern.search(scrubbed):
                issues.append(f"{contact}: {label}")
        if RAW_XERO_ID_LABEL.search(scrubbed):
            issues.append(f"{contact}: raw Xero ID label")
    return issues


def ai_boundary_issue(ai_status: dict[str, Any]) -> str | None:
    enabled = ai_status.get("enabled") is True
    detail = str(ai_status.get("detail") or "")
    if enabled:
        provider = ai_status.get("provider")
        mode = ai_status.get("mode")
        model = str(ai_status.get("model") or "")
        if provider == "openrouter" and mode == "free" and model.endswith(":free"):
            return None
        return "AI polishing must use OpenRouter free-model app-runtime inference only"
    if detail == AI_DISABLED_DETAIL:
        return None
    return detail or "AI polishing is misconfigured"


def fail(failures: list[str], lines: list[str], label: str, detail: str) -> None:
    failures.append(f"{label}: {detail}")
    lines.append(f"FAIL {label}: {detail}")


def pass_line(lines: list[str], label: str, detail: str) -> None:
    lines.append(f"PASS {label}: {detail}")


def evaluate_preflight(
    payloads: dict[str, Any],
    *,
    max_age_minutes: int = 120,
    strict_app_store: bool = False,
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

    frontend = payloads.get("frontend")
    if frontend is not None:
        if frontend.get("has_root") and frontend.get("has_title"):
            pass_line(lines, "frontend", f"{frontend.get('url')} is serving Nero")
        else:
            fail(failures, lines, "frontend", f"{frontend.get('url', 'frontend')} did not look like the Nero app")

    submission_image = payloads.get("submission_image")
    if submission_image is not None:
        size = (submission_image.get("width"), submission_image.get("height"))
        if submission_image.get("exists") and submission_image.get("is_png") and size == SUBMISSION_IMAGE_SIZE:
            pass_line(lines, "submission image", f"{submission_image.get('path')} is a 1120x720 PNG")
        else:
            fail(
                failures,
                lines,
                "submission image",
                f"{submission_image.get('path', 'project image')} is missing or not a 1120x720 PNG",
            )

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
    sync_error = payloads.get("sync_error")
    if sync_error:
        lines.append(f"INFO sync: requested refresh was not completed: {sync_error}")
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

    copy_issues = action_copy_issues(proposals)
    if copy_issues:
        fail(failures, lines, "action copy", "; ".join(copy_issues[:8]))
    else:
        pass_line(lines, "action copy", "drafts are owner-readable and free of known demo placeholders")

    ai_status = payloads.get("/api/ai/status") or {}
    ai_issue = ai_boundary_issue(ai_status)
    if ai_issue:
        fail(failures, lines, "ai boundary", ai_issue)
    elif ai_status.get("enabled") is True:
        pass_line(lines, "ai boundary", f"optional draft polishing uses {ai_status.get('provider')} free model")
    else:
        pass_line(lines, "ai boundary", "optional app-runtime polishing is disabled; deterministic agent remains default")

    readiness = payloads.get("/api/app_store/readiness") or {}
    ready_count = int(readiness.get("ready_count") or 0)
    total_count = int(readiness.get("total_count") or 0)
    lines.append(f"INFO app store readiness: {ready_count}/{total_count} checks ready")
    incomplete_readiness = [
        item
        for item in readiness.get("items", [])
        if item.get("status") not in {"ready", "demo"}
    ]
    if incomplete_readiness:
        labels = ", ".join(f"{item.get('label', item.get('id', 'unknown'))}={item.get('status')}" for item in incomplete_readiness)
        lines.append(f"INFO app store incomplete: {labels}")
        if strict_app_store:
            fail(failures, lines, "app store", "complete production webhook/subscription setup before certification")

    if failures:
        lines.append("result=failed")
        return 1, lines
    lines.append("result=passed")
    return 0, lines


def collect_payloads(
    base_url: str,
    *,
    sync: bool,
    timeout: float,
    frontend_url: str | None = DEFAULT_FRONTEND_URL,
) -> dict[str, Any]:
    payloads: dict[str, Any] = {
        "/health": request_json(base_url, "/health", timeout=timeout),
        "/api/xero/status": request_json(base_url, "/api/xero/status", timeout=timeout),
    }
    if frontend_url:
        payloads["frontend"] = check_frontend(frontend_url, timeout=timeout)
    payloads["submission_image"] = check_submission_image()
    if sync:
        try:
            payloads["/api/sync"] = request_json(base_url, "/api/sync", method="POST", timeout=max(timeout, 30.0))
        except RuntimeError as error:
            payloads["sync_error"] = str(error)
    payloads.update(
        {
            "/api/data_source": request_json(base_url, "/api/data_source", timeout=timeout),
            "/api/metrics": request_json(base_url, "/api/metrics", timeout=timeout),
            "/api/proposals": request_json(base_url, "/api/proposals", timeout=timeout),
            "/api/ai/status": request_json(base_url, "/api/ai/status", timeout=timeout),
            "/api/app_store/readiness": request_json(base_url, "/api/app_store/readiness", timeout=timeout),
        }
    )
    return payloads


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the local Nero live-Xero demo without printing secrets.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Backend base URL. Default: {DEFAULT_BASE_URL}")
    parser.add_argument(
        "--frontend-url",
        default=DEFAULT_FRONTEND_URL,
        help=f"Frontend URL to check. Default: {DEFAULT_FRONTEND_URL}",
    )
    parser.add_argument("--skip-frontend", action="store_true", help="Only check backend/Xero readiness.")
    parser.add_argument("--sync", action="store_true", help="Run POST /api/sync before evaluating demo readiness.")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds.")
    parser.add_argument("--max-age-minutes", type=int, default=120, help="Maximum acceptable Xero snapshot age.")
    parser.add_argument("--strict-app-store", action="store_true", help="Fail if any App Store readiness item is not ready.")
    args = parser.parse_args(argv)

    try:
        frontend_url = None if args.skip_frontend else args.frontend_url
        payloads = collect_payloads(args.base_url, sync=args.sync, timeout=args.timeout, frontend_url=frontend_url)
        exit_code, lines = evaluate_preflight(
            payloads,
            max_age_minutes=args.max_age_minutes,
            strict_app_store=args.strict_app_store,
        )
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
