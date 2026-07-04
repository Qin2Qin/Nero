from __future__ import annotations

from fastapi import APIRouter

from services.research_monitor import build_index, read_previous_index, scan_and_write, scan_research_files


router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/status")
def status() -> dict:
    previous = read_previous_index()
    return build_index(scan_research_files(), previous)


@router.post("/scan")
def scan() -> dict:
    return scan_and_write()
