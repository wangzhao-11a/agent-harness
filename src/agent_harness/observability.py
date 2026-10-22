"""Observability layer — session state file + append-only event log.

Writes a machine-readable snapshot to ``<wf_dir>/.session_state.json`` and
an append-only JSONL event log to ``<wf_dir>/.transitions.jsonl``. Both are
designed to be tail-able by external monitors without parsing process logs
or attaching a debugger.

Usage::

    from agent_harness import checkpoint
    checkpoint(session, wf_dir, "task_done", detail="score=78 fatal=0")

The function never raises — observability must never crash the pipeline.
This is the most-imitated piece of harness infrastructure in the wild;
keeping it boring + bulletproof is the whole point.

Configuration
-------------
``checkpoint`` and ``write_state`` accept a ``fields`` parameter to whitelist
which session attributes get serialized. If omitted, the default
``DEFAULT_OBSERVABLE_FIELDS`` set is used. Subclassing the project's session
to expose more attributes does not require any changes here — pass the
expanded list at the call site, or set a project-wide default via
``set_default_fields()``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable

# Default whitelist. Projects override with set_default_fields() OR by passing
# `fields=` to each call. Most projects only need to override once at startup.
DEFAULT_OBSERVABLE_FIELDS: tuple[str, ...] = (
    "id", "name",
    "state", "stage", "status",
    "turn", "fix_count", "verify_count", "deploy_count",
    "finished", "finish_reason", "failure_cause",
)

# Module-level mutable for project-wide override. Keep small; per-call
# `fields=` parameter is the more flexible option.
_default_fields: list[str] = list(DEFAULT_OBSERVABLE_FIELDS)


def set_default_fields(fields: Iterable[str]) -> None:
    """Override the project-wide default observable field list.

    Call once at startup (e.g. in your app's __init__). Per-call ``fields=``
    parameter overrides this.
    """
    global _default_fields
    _default_fields = list(fields)


def get_default_fields() -> tuple[str, ...]:
    """Return the current default field whitelist (for inspection / tests)."""
    return tuple(_default_fields)


# ── Serialization helpers ───────────────────────────────────────────────


def _serializable(value: Any) -> Any:
    """Coerce a value into something json.dumps can handle.

    Handles: primitives, Path, Enum (returns .value), list/tuple, dict.
    Falls back to repr() for unknown types — never raises.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    # Enum -> .value (handles any project's state enum)
    enum_value = getattr(value, "value", None)
    if (enum_value is not None
            and hasattr(value, "name")
            and hasattr(type(value), "__members__")):
        return enum_value
    if isinstance(value, (list, tuple)):
        return [_serializable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serializable(v) for k, v in value.items()}
    return repr(value)


def _to_observable_dict(session: Any, fields: Iterable[str]) -> dict:
    """Extract whitelisted fields from a dict OR namespace OR custom object."""
    snapshot: dict = {}
    if isinstance(session, dict):
        getter = lambda k: session.get(k)
    else:
        getter = lambda k: getattr(session, k, None)
    for name in fields:
        try:
            snapshot[name] = _serializable(getter(name))
        except Exception:
            snapshot[name] = None
    snapshot["ts"] = time.time()
    return snapshot


# ── Public API ──────────────────────────────────────────────────────────


def write_state(session: Any, wf_dir: Path | str,
                fields: Iterable[str] | None = None,
                extra: dict | None = None) -> None:
    """Write the current session snapshot to ``<wf_dir>/.session_state.json``.

    Atomic write via tmp file + rename. Never raises.

    Parameters
    ----------
    session : dict | namespace | object with attrs
        The session-like object to snapshot.
    wf_dir : Path | str
        Workflow directory. If it does not exist, the call is silently a no-op.
    fields : iterable of str, optional
        Whitelist of session attributes to serialize. Defaults to the
        project-wide setting from ``set_default_fields()``.
    extra : dict, optional
        Free-form payload merged into the snapshot under ``"extra"`` key.
    """
    try:
        wf = Path(wf_dir)
        if not wf.exists():
            return
        active_fields = list(fields) if fields is not None else _default_fields
        snapshot = _to_observable_dict(session, active_fields)
        if extra:
            snapshot["extra"] = _serializable(extra)
        tmp = wf / ".session_state.json.tmp"
        final = wf / ".session_state.json"
        tmp.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(final)
    except Exception:
        pass


def append_log(wf_dir: Path | str, record: dict) -> None:
    """Append one JSONL record to ``<wf_dir>/.transitions.jsonl``.

    Each line is a self-contained JSON object so ``tail -f`` works and
    consumers can parse line-by-line. Never raises.
    """
    try:
        wf = Path(wf_dir)
        if not wf.exists():
            return
        payload = {"ts": time.time(), **record}
        line = json.dumps(_serializable(payload), ensure_ascii=False)
        log_file = wf / ".transitions.jsonl"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def checkpoint(session: Any, wf_dir: Path | str, event_kind: str,
               detail: str = "",
               fields: Iterable[str] | None = None,
               **extra: Any) -> None:
    """Write the session snapshot AND append a transition log entry.

    Convenience wrapper for the common case where you want both observability
    files updated at the same sync point.

    Use at natural sync points: turn boundaries, after framework tools
    complete, when ``session.finished`` flips.
    """
    write_state(session, wf_dir, fields=fields, extra=extra or None)
    g = (lambda k: session.get(k)) if isinstance(session, dict) else (lambda k: getattr(session, k, None))
    append_log(wf_dir, {
        "kind": event_kind,
        "detail": detail,
        "session_id": g("id"),
        "state_brief": {
            "state": _serializable(g("state")),
            "stage": g("stage"),
            "finished": g("finished"),
        },
        **(_serializable(extra) if extra else {}),
    })
