"""Generic explicit state-machine framework.

Each project defines its own state ``Enum`` + transition table; this module
provides the engine: legality check, atomic transition, invariant assertion,
observable hooks, and a derive-from-flags bootstrap helper.

Why generic?
------------
Different agent projects have different states:
- A perf-tuning REPL has ``INIT / OPTIMIZING / IN_GROUP / TERMINAL / FAILED``
- A bid-generation pipeline has ``INIT / PARSING / PARSED / COMPOSING / ...``
- A research agent has ``IDLE / SEARCHING / SYNTHESIZING / DONE``

The state set is project-specific, but the **engine** is identical:
- Closed transition table (``(from_state, event) -> to_state``)
- ``transition(session, event)`` mutates session.state, calls invariants,
  fires observability hooks.
- ``IllegalTransition`` on missing edge.
- ``safe_transition`` swallows IllegalTransition for incremental migration.

Usage
-----
::

    from enum import Enum
    from agent_harness import StateMachine, IllegalTransition

    class MyState(Enum):
        INIT = "init"
        ACTIVE = "active"
        DONE = "done"
        FAILED = "failed"

    sm = StateMachine(
        state_enum=MyState,
        transitions={
            (MyState.INIT, "start"):  MyState.ACTIVE,
            (MyState.ACTIVE, "finish"): MyState.DONE,
            (MyState.INIT, "abort"):   MyState.FAILED,
            (MyState.ACTIVE, "abort"): MyState.FAILED,
        },
        terminal_states={MyState.DONE, MyState.FAILED},
        invariants={
            MyState.DONE: lambda s: bool(s.get("result")),
        },
    )

    task = {"state": MyState.INIT.value}
    sm.transition(task, "start")  # task["state"] == "active"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

E = TypeVar("E", bound=Enum)


class IllegalTransition(Exception):
    """Raised when ``transition()`` gets an edge not in the transition table."""


# A predicate that takes a session-like object and asserts state-specific
# invariants. Should raise AssertionError on violation. Default is no-op.
InvariantFn = Callable[[Any], None]

# Hook fired AFTER a successful transition. Gets (session, event, from, to).
TransitionHook = Callable[[Any, str, Any, Any], None]


@dataclass
class StateMachine(Generic[E]):
    """A reusable state-machine engine bound to a project-specific state Enum.

    Parameters
    ----------
    state_enum : type[Enum]
        The Enum class defining all legal states.
    transitions : dict[tuple[E, str], E]
        Closed table of (current_state, event_name) -> new_state. Anything
        not in this dict is an illegal transition.
    terminal_states : frozenset[E] | set[E], optional
        States with no outgoing transitions. Computed from `transitions`
        if not provided (any state that never appears as `from` is terminal).
    invariants : dict[E, InvariantFn], optional
        Per-state assertion functions called after every transition.
        Each function receives the session and should raise AssertionError on
        violation. States without an entry have no invariant check.
    state_attr : str, default "state"
        Attribute name on the session where current state is stored. Works
        both for dict-style (``session["state"]``) and namespace-style
        (``session.state``) sessions.
    """
    state_enum: type[E]
    transitions: dict[tuple[E, str], E]
    terminal_states: frozenset[E] = field(default=frozenset())
    invariants: dict[E, InvariantFn] = field(default_factory=dict)
    state_attr: str = "state"

    def __post_init__(self):
        # Auto-derive terminal states if not provided
        if not self.terminal_states:
            sources = {src for (src, _) in self.transitions}
            self.terminal_states = frozenset(
                s for s in self.state_enum if s not in sources
            )
        # Convert set to frozenset for safety
        if not isinstance(self.terminal_states, frozenset):
            self.terminal_states = frozenset(self.terminal_states)

    # ── State access (works for dict or attribute-style sessions) ────────

    def _get_state(self, session: Any) -> E:
        if session is None:
            raise TypeError("StateMachine operations require a session, got None")
        if isinstance(session, dict):
            raw = session.get(self.state_attr)
        else:
            raw = getattr(session, self.state_attr, None)
        if raw is None:
            # Default to the first declared state (typically the INIT analogue)
            return next(iter(self.state_enum))
        if isinstance(raw, self.state_enum):
            return raw
        if isinstance(raw, str):
            try:
                return self.state_enum(raw)
            except ValueError:
                # Unknown string — fall back to first state
                return next(iter(self.state_enum))
        return next(iter(self.state_enum))

    def _set_state(self, session: Any, state: E) -> None:
        if isinstance(session, dict):
            # Store as the enum's .value string for JSON persistence
            session[self.state_attr] = state.value
        else:
            setattr(session, self.state_attr, state)

    # ── Public API ───────────────────────────────────────────────────────

    def is_terminal(self, state: E | None = None, session: Any = None) -> bool:
        """Check if a state (or the session's current state) is terminal."""
        if state is None and session is not None:
            state = self._get_state(session)
        return state in self.terminal_states

    def legal_events(self, from_state: E) -> tuple[str, ...]:
        """Return the events that can fire from a given state."""
        return tuple(sorted(
            evt for (src, evt) in self.transitions if src == from_state
        ))

    def transition(self, session: Any, event: str,
                    on_transition: TransitionHook | None = None) -> E:
        """Move ``session.state`` along edge ``event``.

        Raises ``IllegalTransition`` if no edge exists for ``(current_state,
        event)``. Asserts invariants on the new state. Calls
        ``on_transition`` (best-effort) after a successful move.

        Returns the new state.
        """
        current = self._get_state(session)
        key = (current, event)
        if key not in self.transitions:
            raise IllegalTransition(
                f"No transition for ({current.name}, {event!r}). "
                f"Legal events from {current.name}: {list(self.legal_events(current))}"
            )
        new = self.transitions[key]
        self._set_state(session, new)
        self.assert_invariants(session)
        if on_transition is not None:
            try:
                on_transition(session, event, current, new)
            except Exception:
                pass
        return new

    def safe_transition(self, session: Any, event: str) -> E | None:
        """Wrap ``transition()`` to swallow ``IllegalTransition`` silently.

        Use during incremental migration of legacy code that might call
        transition() from a state that's not yet wired up correctly.
        Returns the new state on success, ``None`` on swallowed error.
        """
        try:
            return self.transition(session, event)
        except IllegalTransition:
            return None

    def assert_invariants(self, session: Any) -> None:
        """Run the invariant function for the session's current state.

        States without a registered invariant are no-ops. Invariant violation
        is a programming bug, not a recoverable condition — it raises
        AssertionError.
        """
        current = self._get_state(session)
        fn = self.invariants.get(current)
        if fn is not None:
            fn(session)


def derive_state_from_flags(
    session: Any,
    rules: list[tuple[Callable[[Any], bool], E]],
    default: E,
) -> E:
    """Bootstrap helper: compute the current state from legacy boolean flags.

    Useful for sessions persisted before the state machine was introduced.
    Rules are evaluated in order — the first predicate that returns True
    wins. Order matters: most-specific first.

    Usage::

        derive_state_from_flags(
            task,
            rules=[
                (lambda t: bool(t.get("audit_json")), MyState.AUDITED),
                (lambda t: bool(t.get("bid_docx")),   MyState.COMPOSED),
                (lambda t: bool(t.get("tender_spec")), MyState.PARSED),
            ],
            default=MyState.INIT,
        )
    """
    g = (lambda k: session.get(k)) if isinstance(session, dict) else (lambda k: getattr(session, k, None))
    for predicate, target_state in rules:
        try:
            if predicate(session):
                return target_state
        except Exception:
            continue
    return default
