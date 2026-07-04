from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.research_monitor import build_index, scan_research_files


def test_research_monitor_counts_records(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    forums = raw / "forums"
    forums.mkdir(parents=True)
    (forums / "threads.jsonl").write_text('{"id": 1}\n{"id": 2}\n')

    files = scan_research_files(raw)
    index = build_index(files)

    assert index["sources"]["forums"]["files"] == 1
    assert index["sources"]["forums"]["records"] == 2
    assert index["files"][0]["status"] == "new_or_changed"
