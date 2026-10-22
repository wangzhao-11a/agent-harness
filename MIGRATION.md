# Migrating an existing project to `agent-harness`

If your project already has its own `observability.py`, `events.py`,
`state_machine.py` and `recovery/` modules, you do **not** need a rewrite.
The migration is purely additive and reversible at every stage.

This guide describes the three-stage path I used on two production agent
projects (an operator-tuning REPL and a bid-generation pipeline).

---

## Strategy

1. **Coexist (half a day).** Add `agent-harness` as a dependency. Turn the old
   modules into shims that re-export from the package. Existing imports keep
   working; new code imports from `agent_harness`.
2. **Switch (about a day).** Move internal imports to the package, keep the
   shims, run the full test suite and require zero regressions.
3. **Delete (optional, after a week).** Remove the shims. Keep project-specific
   state enums and transition tables — those are local assets, not library code.

Each stage is independently shippable, and rolling back is a one-line revert.

---

## Stage 1: make the old modules shims

```python
"""Shim — the real implementation lives in agent_harness.

Kept so existing imports continue to work during migration.
"""
from agent_harness.observability import *  # noqa: F401,F403
```

Do the same for `events.py` and the recovery package:

```python
# core/events.py
from agent_harness.events import *  # noqa: F401,F403

# core/recovery/__init__.py
from agent_harness.recovery import *  # noqa: F401,F403
```

`emit` accepts both the legacy `(channel, message)` callback and the typed
`FrameworkEvent` callback, so no call site has to change on day one.

---

## Stage 2: wrap the project-specific state machine

The state set and transition table stay in your project. Only the engine comes
from the package.

```python
from enum import Enum
from agent_harness import StateMachine, IllegalTransition


class SessionState(Enum):
    INIT = "init"
    OPTIMIZING = "optimizing"
    IN_GROUP = "in_group"
    TERMINAL = "terminal"
    FAILED = "failed"


_sm = StateMachine(
    state_enum=SessionState,
    transitions={
        (SessionState.INIT, "baseline_done"): SessionState.OPTIMIZING,
        (SessionState.OPTIMIZING, "group_start"): SessionState.IN_GROUP,
        # ... the rest of your table ...
    },
    invariants={
        # state -> predicate receiving the session
    },
)


# Keep the old function-style API so callers do not change.
def transition(session, event, on_transition=None):
    return _sm.transition(session, event, on_transition=on_transition)


def safe_transition(session, event):
    return _sm.safe_transition(session, event)


def assert_invariants(session):
    return _sm.assert_invariants(session)
```

If your persisted sessions predate the state machine, use
`derive_state_from_flags()` to compute the current state from existing boolean
flags instead of migrating the data.

---

## Stage 3: verify behavior equivalence

Run the project's test suite at every stage. On the two projects I migrated,
the suites were 31/31 and 129/129 with zero changes to assertions.

A minimal smoke check:

```python
from agent_harness import checkpoint, StateMachine

# legacy imports still resolve through the shims
from core.observability import checkpoint as legacy_checkpoint
from core.recovery import register_recipe

print("both import paths work")
```

Then run one end-to-end workflow and confirm that `.session_state.json` and
`.transitions.jsonl` are still produced with the expected fields.

---

## What stays local

- The state `Enum` and the transition table.
- Invariant predicates (they encode your domain rules).
- Event `kind` vocabulary.
- Recovery recipes (they know how to fix your errors).
- The ledger directory layout.

The package only supplies the engine, the writers and the orchestration around
recipes. That boundary is what keeps it reusable.

---

## Cost

Roughly 1.5 days for two mid-size projects, including test runs. The payoff is
that a fix in one project benefits every other project, and the next project
starts with the plumbing already done.