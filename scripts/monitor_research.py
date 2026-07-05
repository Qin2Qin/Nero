#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.services.research_monitor import scan_and_write


def print_summary(index: dict) -> None:
    changed = [item for item in index["files"] if item["status"] == "new_or_changed"]
    total_records = sum(source["records"] for source in index["sources"].values())
    print(
        f"{index['generated_at']} | {len(index['files'])} files | "
        f"{total_records} records | {len(changed)} new/changed"
    )
    for item in changed[:10]:
        print(f"  - {item['path']} ({item['record_count'] if item['record_count'] is not None else '?'} records)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor raw Xero opportunity research files.")
    parser.add_argument("--watch", action="store_true", help="Poll continuously.")
    parser.add_argument("--interval", type=int, default=30, help="Polling interval in seconds.")
    args = parser.parse_args()

    while True:
        print_summary(scan_and_write())
        if not args.watch:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
