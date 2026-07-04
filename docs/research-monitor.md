# Research Monitor

Nero watches the lightweight research scratchpad at:

```text
xero-opportunity-research/raw/
  forums/
  appstore/
  community/
```

Supported files: `.json`, `.jsonl`, `.csv`, `.txt`, `.md`.

Run one scan:

```bash
python3 scripts/monitor_research.py
```

Run continuous polling:

```bash
python3 scripts/monitor_research.py --watch --interval 30
```

The monitor writes `xero-opportunity-research/research_index.json` with file
hashes, record counts where possible, source summaries, and changed-file flags.
The backend also exposes:

```text
GET  /api/research/status
POST /api/research/scan
```
