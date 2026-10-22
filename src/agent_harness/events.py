"""Typed framework events.

Replaces ad-hoc string-keyed log calls (``on_event(channel, message)``)
with a single ``FrameworkEvent`` dataclass that downstream consumers can
type-check.

Backward compatible: ``emit`` accepts both legacy callbacks
(``callable(channel: str, message: str)``) and modern callbacks
(``callable(event: FrameworkEvent)``). Migration is incremental.

Unlike ``observability``, this module is intentionally schema-light —
``kind`` is a str (not Literal) so projects can define their own event
vocabulary without subclassing or extending an enum. The discipline
of "use a closed set of kinds" is a project convention, not enforced here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class FrameworkEvent:
    """A single typed event emitted by an agent harness.

    Attributes
    ----------
    kind : str
        Short event tag — projects should pick from a closed vocabulary
        (e.g. "deploy", "verify", "audit_done", "state_transition").
    payload : dict
        Event-specific data. Stay JSON-serializable.
    severity : str
        One of ``"info"``, ``"warn"``, ``"error"``. Free-form-tolerant.
    ts : float
        Unix timestamp; defaults to ``time.time()`` at construction.
    """
    kind: str
    payload: dict = field(default_factory=dict)
    severity: str = "info"
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "ts": self.ts,
            "payload": dict(self.payload),  # copy
        }


# Caller-supplied callback type. Accepts either form for backward compat.
EventCallback = Callable[..., None]


def coerce_event(*args: Any, **kwargs: Any) -> FrameworkEvent:
    """Normalize legacy and modern signatures to a ``FrameworkEvent``.

    Accepts:
      * ``coerce_event(FrameworkEvent(...))``                  — modern
      * ``coerce_event("deploy", "perf_files deploy #2")``     — legacy 2-arg
      * ``coerce_event("deploy")``                             — legacy 1-arg
      * ``coerce_event(kind="deploy", payload={...})``         — kwargs
    """
    if args and isinstance(args[0], FrameworkEvent):
        return args[0]
    kind = kwargs.pop("kind", None) or (args[0] if args else "info")
    message = kwargs.pop("message", None)
    if message is None and len(args) >= 2:
        message = args[1]
    payload = kwargs.pop("payload", None) or {}
    if message is not None and "message" not in payload:
        payload["message"] = message
    severity = kwargs.pop("severity", "info")
    return FrameworkEvent(kind=kind, payload=payload, severity=severity)


def emit(callback: EventCallback | None, *args: Any, **kwargs: Any) -> None:
    """Invoke ``callback`` with both legacy and typed signatures.

    The callback may be:
      * ``None`` — no-op
      * an old ``(str, str) -> None`` consumer — receives ``kind, message``
      * a new ``(FrameworkEvent) -> None`` consumer — receives the event

    Any exception in user callback is swallowed — observability must not
    crash the pipeline.
    """
    if callback is None:
        return
    event = coerce_event(*args, **kwargs)
    try:
        callback(event)
        return
    except TypeError:
        msg = event.payload.get("message", "")
        try:
            callback(event.kind, msg)
        except Exception:
            pass
    except Exception:
        pass
