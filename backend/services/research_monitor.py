from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
RESEARCH_ROOT = ROOT / "xero-opportunity-research"
RAW_ROOT = RESEARCH_ROOT / "raw"
INDEX_PATH = RESEARCH_ROOT / "research_index.json"
SUPPORTED_SUFFIXES = {".json", ".jsonl", ".csv", ".txt", ".md"}


@dataclass(frozen=True)
class ResearchFile:
    path: Path
    source: str
    size_bytes: int
    sha256: str
    record_count: int | None
    modified_at: str


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _count_records(path: Path) -> int | None:
    try:
        if path.suffix == ".json":
            data = json.loads(path.read_text())
            return len(data) if isinstance(data, list) else 1
        if path.suffix == ".jsonl":
            return sum(1 for line in path.read_text().splitlines() if line.strip())
        if path.suffix == ".csv":
            with path.open(newline="") as handle:
                return max(sum(1 for _ in csv.DictReader(handle)), 0)
        if path.suffix in {".txt", ".md"}:
            return sum(1 for line in path.read_text().splitlines() if line.strip())
    except (UnicodeDecodeError, json.JSONDecodeError, OSError):
        return None
    return None


def scan_research_files(raw_root: Path = RAW_ROOT) -> list[ResearchFile]:
    if not raw_root.exists():
        return []
    files: list[ResearchFile] = []
    for path in sorted(raw_root.rglob("*")):
        if not path.is_file() or path.name == ".gitkeep" or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        stat = path.stat()
        try:
            source = path.relative_to(raw_root).parts[0]
        except IndexError:
            source = "unknown"
        files.append(
            ResearchFile(
                path=path,
                source=source,
                size_bytes=stat.st_size,
                sha256=_hash_file(path),
                record_count=_count_records(path),
                modified_at=datetime.fromtimestamp(stat.st_mtime, timezone.utc).replace(microsecond=0).isoformat(),
            )
        )
    return files


def read_previous_index(index_path: Path = INDEX_PATH) -> dict[str, dict]:
    if not index_path.exists():
        return {}
    try:
        data = json.loads(index_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return {item["path"]: item for item in data.get("files", [])}


def build_index(files: Iterable[ResearchFile], previous: dict[str, dict] | None = None) -> dict:
    previous = previous or {}
    indexed_files = []
    by_source: dict[str, dict[str, int]] = {}

    for item in files:
        try:
            rel_path = str(item.path.relative_to(RESEARCH_ROOT))
        except ValueError:
            rel_path = str(Path("raw") / item.source / item.path.name)
        previous_item = previous.get(rel_path)
        status = "unchanged" if previous_item and previous_item.get("sha256") == item.sha256 else "new_or_changed"
        row = {
            "path": rel_path,
            "source": item.source,
            "size_bytes": item.size_bytes,
            "sha256": item.sha256,
            "record_count": item.record_count,
            "modified_at": item.modified_at,
            "status": status,
        }
        indexed_files.append(row)
        source_summary = by_source.setdefault(item.source, {"files": 0, "records": 0, "changed_files": 0})
        source_summary["files"] += 1
        source_summary["records"] += item.record_count or 0
        if status == "new_or_changed":
            source_summary["changed_files"] += 1

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "root": str(RESEARCH_ROOT),
        "sources": by_source,
        "files": indexed_files,
    }


def write_index(index: dict, index_path: Path = INDEX_PATH) -> None:
    index_path.write_text(json.dumps(index, indent=2) + "\n")


def scan_and_write() -> dict:
    previous = read_previous_index()
    index = build_index(scan_research_files(), previous)
    write_index(index)
    return index
