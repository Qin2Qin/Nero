from __future__ import annotations

from urllib.parse import urlsplit


LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def request_origin(request) -> str:
    forwarded_host = request.headers.get("x-forwarded-host")
    host = (forwarded_host or request.headers.get("host") or request.url.netloc).split(",", 1)[0].strip()
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",", 1)[0].strip()
    if request.headers.get("x-forwarded-ssl") == "on":
        proto = "https"
    return f"{proto}://{host}".rstrip("/")


def is_local_origin(origin: str) -> bool:
    try:
        hostname = urlsplit(origin).hostname
    except ValueError:
        return False
    return hostname in LOCAL_HOSTS


def xero_redirect_uri_for_request(request, configured_redirect_uri: str) -> str:
    origin = request_origin(request)
    if is_local_origin(origin) and configured_redirect_uri:
        return configured_redirect_uri
    return f"{origin}/auth/callback"


def frontend_origin_for_request(request, configured_origins: tuple[str, ...]) -> str:
    origin = request_origin(request)
    if is_local_origin(origin) and configured_origins:
        return configured_origins[0].rstrip("/")
    return origin
