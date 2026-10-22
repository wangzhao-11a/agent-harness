"""Tests for agent_harness.events."""
from __future__ import annotations

from agent_harness import FrameworkEvent, coerce_event, emit


def test_dataclass_defaults():
    e = FrameworkEvent("deploy")
    assert e.kind == "deploy"
    assert e.severity == "info"
    assert e.payload == {}


def test_to_dict_isolates_payload():
    e = FrameworkEvent("verify", payload={"ok": True})
    d1 = e.to_dict()
    d1["payload"]["leaked"] = True
    d2 = e.to_dict()
    assert "leaked" not in d2["payload"]


def test_coerce_modern_passthrough():
    src = FrameworkEvent("fix")
    assert coerce_event(src) is src


def test_coerce_legacy_two_args():
    e = coerce_event("deploy", "msg")
    assert e.kind == "deploy" and e.payload["message"] == "msg"


def test_coerce_legacy_one_arg():
    e = coerce_event("preflight")
    assert e.kind == "preflight"


def test_coerce_kwargs_form():
    e = coerce_event(kind="advisor", payload={"x": 1}, severity="warn")
    assert e.kind == "advisor" and e.severity == "warn" and e.payload["x"] == 1


def test_emit_none_callback_noop():
    emit(None, "deploy", "msg")  # no exception


def test_emit_typed_callback():
    captured = []
    emit(lambda ev: captured.append(ev), "verify", payload={"r": 9})
    assert captured[0].kind == "verify" and captured[0].payload["r"] == 9


def test_emit_legacy_two_arg_callback():
    captured = []
    emit(lambda ch, m: captured.append((ch, m)), "deploy", "msg")
    assert captured == [("deploy", "msg")]


def test_emit_callback_exception_swallowed():
    def bad(_): raise RuntimeError("logger blew up")
    emit(bad, "info")  # no exception


def test_emit_legacy_kwargs_message():
    captured = []
    emit(lambda c, m: captured.append((c, m)), kind="audit", payload={"message": "ok"})
    assert captured == [("audit", "ok")]
