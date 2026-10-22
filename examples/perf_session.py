"""Example: performance-tuning REPL session.

A performance-tuning REPL pipeline. Shows how
to use ``agent-harness`` for an LLM-driven optimization loop with
experiment groups (combo edits) and recovery recipes.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from agent_harness import (
    StateMachine,
    apply_recipe,
    checkpoint,
    register_recipe,
    set_default_fields,
)


# ── 1) Define your project's state vocabulary ─────────────────────────


class PerfState(Enum):
    INIT = "init"
    OPTIMIZING = "optimizing"   # baseline ready, can fix/verify
    IN_GROUP = "in_group"       # combo edit (experiment group) in progress
    TERMINAL = "terminal"       # finished successfully
    FAILED = "failed"           # framework error / abort / interrupt


def _optimizing_invariant(session):
    assert session.get("baseline_ready"), "OPTIMIZING requires baseline"
    assert (session.get("baseline_us") or 0) > 0


def _in_group_invariant(session):
    assert session.get("experiment_group_id"), "IN_GROUP requires group_id"


def _terminal_invariant(session):
    assert session.get("finished")
    assert session.get("final_verdict") or session.get("finish_reason")


sm = StateMachine(
    state_enum=PerfState,
    transitions={
        (PerfState.INIT, "baseline_done"):    PerfState.OPTIMIZING,
        (PerfState.INIT, "finish"):           PerfState.TERMINAL,
        (PerfState.OPTIMIZING, "group_start"): PerfState.IN_GROUP,
        (PerfState.IN_GROUP, "group_end"):     PerfState.OPTIMIZING,
        (PerfState.OPTIMIZING, "finish"):     PerfState.TERMINAL,
        (PerfState.IN_GROUP, "finish"):       PerfState.TERMINAL,
        (PerfState.INIT, "abort"):            PerfState.FAILED,
        (PerfState.OPTIMIZING, "abort"):      PerfState.FAILED,
        (PerfState.IN_GROUP, "abort"):        PerfState.FAILED,
    },
    invariants={
        PerfState.OPTIMIZING: _optimizing_invariant,
        PerfState.IN_GROUP:   _in_group_invariant,
        PerfState.TERMINAL:   _terminal_invariant,
    },
)


# ── 2) Configure observability fields once ─────────────────────────────


set_default_fields([
    "id", "op_name", "state",
    "baseline_us", "best_us", "current_us",
    "verify_count", "fix_count",
    "experiment_group_id",
    "finished", "final_verdict", "failure_cause",
])


# ── 3) Register recovery recipes ───────────────────────────────────────


def _refresh_vendor_path(target_dir: Path) -> bool:
    """Stale CANN vendored headers — re-symlink."""
    # ... actual fix logic ...
    return True   # changed something


register_recipe("vendor_path_outdated", _refresh_vendor_path,
                description="Refresh stale vendored CANN headers")


# ── 4) Run a session ───────────────────────────────────────────────────


def main():
    wf = Path("data/perf/wf_42")
    wf.mkdir(parents=True, exist_ok=True)

    session = {
        "id": "wf_42",
        "op_name": "RmsNormCustom",
        "state": PerfState.INIT.value,
        "baseline_ready": False,
        "verify_count": 0,
        "fix_count": 0,
        "finished": False,
    }
    checkpoint(session, wf, "session_init")

    # Pretend we ran the baseline measurement
    session["baseline_ready"] = True
    session["baseline_us"] = 18.6
    session["best_us"] = 18.6
    sm.transition(session, "baseline_done")
    checkpoint(session, wf, "baseline_done")

    # Try a combo edit
    session["experiment_group_id"] = "combo_p07_p14"
    sm.transition(session, "group_start")
    checkpoint(session, wf, "group_start")

    # ... run the combo, measure, decide ...
    session["best_us"] = 13.2
    session["experiment_group_id"] = None
    sm.transition(session, "group_end")
    checkpoint(session, wf, "group_end")

    # Finish
    session["finished"] = True
    session["final_verdict"] = "perf_improved"
    session["finish_reason"] = "success: 1.41x speedup"
    sm.transition(session, "finish")
    checkpoint(session, wf, "session_end",
                detail=f"speedup={18.6 / 13.2:.2f}x")

    print(f"Final state file: {wf}/.session_state.json")
    print(f"Transition log:   {wf}/.transitions.jsonl")


if __name__ == "__main__":
    main()
