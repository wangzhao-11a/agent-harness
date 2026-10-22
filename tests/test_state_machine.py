"""Tests for agent_harness.state_machine — generic engine."""
from __future__ import annotations

import json
from enum import Enum

import pytest

from agent_harness import (
    IllegalTransition,
    StateMachine,
    derive_state_from_flags,
)


class TaskState(Enum):
    INIT = "init"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"


def _done_invariant(s):
    """DONE state requires `result` field to be set (non-None)."""
    val = s.get("result") if isinstance(s, dict) else getattr(s, "result", None)
    assert val is not None, "DONE requires result"


def _build_simple_sm() -> StateMachine[TaskState]:
    return StateMachine(
        state_enum=TaskState,
        transitions={
            (TaskState.INIT, "start"):    TaskState.ACTIVE,
            (TaskState.ACTIVE, "finish"): TaskState.DONE,
            (TaskState.INIT, "abort"):    TaskState.FAILED,
            (TaskState.ACTIVE, "abort"):  TaskState.FAILED,
        },
        invariants={TaskState.DONE: _done_invariant},
    )


def test_terminal_states_auto_derived():
    sm = _build_simple_sm()
    assert TaskState.DONE in sm.terminal_states
    assert TaskState.FAILED in sm.terminal_states
    assert TaskState.INIT not in sm.terminal_states


def test_explicit_terminal_states_respected():
    sm = StateMachine(
        state_enum=TaskState,
        transitions={(TaskState.INIT, "x"): TaskState.ACTIVE},
        terminal_states={TaskState.ACTIVE, TaskState.DONE, TaskState.FAILED},
    )
    assert sm.terminal_states == frozenset({TaskState.ACTIVE, TaskState.DONE, TaskState.FAILED})


def test_legal_events():
    sm = _build_simple_sm()
    assert sm.legal_events(TaskState.INIT) == ("abort", "start")
    assert sm.legal_events(TaskState.DONE) == ()  # terminal


def test_dict_session_transition():
    sm = _build_simple_sm()
    task = {"state": "init"}
    new = sm.transition(task, "start")
    assert new is TaskState.ACTIVE
    assert task["state"] == "active"  # stored as .value


def test_namespace_session_transition():
    from types import SimpleNamespace
    sm = _build_simple_sm()
    task = SimpleNamespace(state=TaskState.INIT)
    sm.transition(task, "start")
    assert task.state is TaskState.ACTIVE


def test_finish_with_invariant():
    sm = _build_simple_sm()
    task = {"state": "active", "result": {"score": 9}}
    sm.transition(task, "finish")
    assert task["state"] == "done"


def test_invariant_violation_raises():
    sm = _build_simple_sm()
    task = {"state": "active"}  # no result -> DONE invariant fails
    with pytest.raises(AssertionError):
        sm.transition(task, "finish")


def test_illegal_transition_raises():
    sm = _build_simple_sm()
    task = {"state": "init"}
    with pytest.raises(IllegalTransition):
        sm.transition(task, "finish")  # cannot finish from INIT


def test_safe_transition_swallows_illegal():
    sm = _build_simple_sm()
    task = {"state": "init"}
    assert sm.safe_transition(task, "finish") is None
    assert task["state"] == "init"  # unchanged


def test_safe_transition_returns_new_state():
    sm = _build_simple_sm()
    task = {"state": "init"}
    assert sm.safe_transition(task, "start") is TaskState.ACTIVE


def test_no_outgoing_from_terminal():
    sm = _build_simple_sm()
    task = {"state": "done", "result": "x"}
    with pytest.raises(IllegalTransition):
        sm.transition(task, "finish")


def test_transition_with_none_session():
    sm = _build_simple_sm()
    with pytest.raises(TypeError, match="None"):
        sm.transition(None, "start")


def test_on_transition_hook_fires():
    sm = _build_simple_sm()
    task = {"state": "init"}
    captured = []
    sm.transition(task, "start",
                   on_transition=lambda s, e, src, dst: captured.append((e, src.value, dst.value)))
    assert captured == [("start", "init", "active")]


def test_on_transition_exception_swallowed():
    sm = _build_simple_sm()
    task = {"state": "init"}
    sm.transition(task, "start", on_transition=lambda *_: (_ for _ in ()).throw(RuntimeError()))
    assert task["state"] == "active"


def test_unknown_string_state_falls_back_to_first():
    sm = _build_simple_sm()
    task = {"state": "garbage_value"}
    # transition tries from INIT (default fallback)
    sm.transition(task, "start")
    assert task["state"] == "active"


def test_state_value_json_roundtrip():
    sm = _build_simple_sm()
    task = {"state": "init"}
    sm.transition(task, "start")
    encoded = json.dumps(task)
    decoded = json.loads(encoded)
    assert TaskState(decoded["state"]) is TaskState.ACTIVE


def test_is_terminal_helpers():
    sm = _build_simple_sm()
    assert sm.is_terminal(TaskState.DONE)
    assert not sm.is_terminal(TaskState.INIT)
    task = {"state": "done", "result": "x"}
    assert sm.is_terminal(session=task)


def test_custom_state_attr_name():
    sm = StateMachine(
        state_enum=TaskState,
        transitions={(TaskState.INIT, "go"): TaskState.ACTIVE},
        state_attr="phase",
    )
    task = {"phase": "init"}
    sm.transition(task, "go")
    assert task["phase"] == "active"
    assert "state" not in task


def test_derive_state_from_flags_first_match_wins():
    rules = [
        (lambda t: bool(t.get("done_at")),  TaskState.DONE),
        (lambda t: bool(t.get("started_at")), TaskState.ACTIVE),
    ]
    assert derive_state_from_flags({"done_at": 1, "started_at": 1},
                                    rules, default=TaskState.INIT) is TaskState.DONE
    assert derive_state_from_flags({"started_at": 1},
                                    rules, default=TaskState.INIT) is TaskState.ACTIVE
    assert derive_state_from_flags({}, rules, default=TaskState.INIT) is TaskState.INIT


def test_derive_state_swallows_predicate_exceptions():
    def bad(_): raise RuntimeError("bad pred")
    rules = [(bad, TaskState.DONE),
             (lambda t: True, TaskState.ACTIVE)]
    assert derive_state_from_flags({}, rules, default=TaskState.INIT) is TaskState.ACTIVE
