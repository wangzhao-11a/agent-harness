"""Recovery orchestrator — single entry point for callers.

Replaces the historical pattern of looking up a handler in a dict and
manually wrapping it in try/except + counters::

    handler = _ENV_AUTOFIX_HANDLERS.get(env_err["kind"])
    if handler is not None:
        try:
            changed = handler(local_source)
            if changed:
                session.env_autofix_attempts += 1
                ...
        except Exception:
            ...

with::

    result = apply_recipe(env_err["kind"], local_source, wf_dir,
                          op_name=op_name, role_tag=role_tag)
    if result.recipe_applied and result.changed:
        session.env_autofix_attempts += 1
        ...

The orchestrator handles ledger writes automatically so callers stop
losing audit trail.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_harness.recovery.ledger import LedgerEntry, append_entry
from agent_harness.recovery.recipes import get_recipe


@dataclass
class RecoveryResult:
    """Outcome of an ``apply_recipe`` call.

    Attributes
    ----------
    error_kind : str
        The error_kind we were asked to recover from.
    recipe_applied : bool
        Did we find a recipe? (False = no recipe registered)
    changed : bool
        Did the recipe actually modify anything? (only meaningful if
        recipe_applied is True)
    duration_ms : float
        Wall time spent in the recipe handler.
    detail : str
        Free-form explanation (e.g. "matched 0 files" or "modified 3 files").
    """
    error_kind: str
    recipe_applied: bool = False
    changed: bool = False
    duration_ms: float = 0.0
    detail: str = ""

    @property
    def should_retry(self) -> bool:
        """True iff caller should re-attempt the failed operation."""
        return self.recipe_applied and self.changed


def apply_recipe(error_kind: str,
                 target: Any,
                 wf_dir: Path | str | None = None,
                 op_name: str = "",
                 role_tag: str = "") -> RecoveryResult:
    """Resolve and run a recipe for ``error_kind``.

    Returns a ``RecoveryResult`` indicating whether a recipe matched and
    whether it changed anything. Always logs to the ledger (if ``wf_dir``
    is provided) so post-mortem analysis is possible.

    Parameters
    ----------
    error_kind : str
        The kind tag from your error detector (e.g. "vendor_path_outdated").
    target : Any
        Local target the recipe should act on (typically a Path).
    wf_dir : Path | str | None
        Workflow root for ledger persistence. ``None`` = no ledger write.
    op_name, role_tag : str
        Caller context for ledger searchability.
    """
    recipe = get_recipe(error_kind)

    if recipe is None:
        result = RecoveryResult(
            error_kind=error_kind,
            recipe_applied=False,
            changed=False,
            detail="no recipe registered for this error_kind",
        )
    else:
        t0 = time.time()
        changed = recipe(target)  # Recipe.__call__ swallows exceptions
        dt_ms = (time.time() - t0) * 1000.0
        result = RecoveryResult(
            error_kind=error_kind,
            recipe_applied=True,
            changed=changed,
            duration_ms=round(dt_ms, 2),
            detail=("modified files" if changed else "matched 0 files (no-op)"),
        )

    if wf_dir is not None:
        append_entry(wf_dir, LedgerEntry(
            error_kind=error_kind,
            recipe_id=recipe.kind if recipe else "<none>",
            success=result.changed,
            target=str(target),
            duration_ms=result.duration_ms,
            detail=result.detail,
            op_name=op_name,
            role_tag=role_tag,
        ))

    return result
