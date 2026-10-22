"""Append-only ledger of recipe applications.

Each recipe call writes one JSONL line to ``<wf_dir>/.recovery_ledger.jsonl``.
External monitors / post-mortem scripts read this file to answer:

  - Which recipes are most-used? (promote them to prevention)
  - Which error_kinds have no recipe yet? (high-ROI fix targets)
  - Did this run involve any auto-recovery? (verdict trustworthiness)
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class LedgerEntry:
    """One row in the recovery ledger.

    Schema is intentionally flat — each field is searchable with ``jq``.
    """
    error_kind: str            # what we tried to fix
    recipe_id: str             # which recipe (typically == error_kind)
    success: bool              # did the handler change anything
    target: str                # path / identifier the recipe acted on
    duration_ms: float = 0.0   # how long the handler took
    detail: str = ""           # free-form note (e.g. files modified count)
    op_name: str = ""          # caller's task / op identifier
    role_tag: str = ""         # caller-supplied tag (e.g. "optimizer:baseline")
    ts: float = field(default_factory=time.time)

    def to_jsonline(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def append_entry(wf_dir: Path | str, entry: LedgerEntry) -> None:
    """Append one entry to ``<wf_dir>/.recovery_ledger.jsonl``. Never raises."""
    try:
        wf = Path(wf_dir)
        if not wf.exists():
            return
        log = wf / ".recovery_ledger.jsonl"
        with log.open("a", encoding="utf-8") as f:
            f.write(entry.to_jsonline() + "\n")
    except Exception:
        pass


def read_ledger(wf_dir: Path | str) -> list[dict]:
    """Read all entries (parsed JSON dicts). Empty if file is absent."""
    try:
        wf = Path(wf_dir)
        log = wf / ".recovery_ledger.jsonl"
        if not log.exists():
            return []
        out: list[dict] = []
        for line in log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []
