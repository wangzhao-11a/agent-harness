"""Tests for agent_harness.observability."""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from types import SimpleNamespace

from agent_harness import (
    append_log,
    checkpoint,
    get_default_fields,
    set_default_fields,
    write_state,
)
from agent_harness.observability import _to_observable_dict


class _DemoState(Enum):
    INIT = "init"
    DONE = "done"


def test_dict_session_minimal(tmp_path):
    sess = {"id": "T-1", "state": "init", "turn": 0}
    write_state(sess, tmp_path)
    state = json.loads((tmp_path / ".session_state.json").read_text(encoding="utf-8"))
    assert state["id"] == "T-1"
    assert state["state"] == "init"


def test_namespace_session(tmp_path):
    sess = SimpleNamespace(id="N-1", state=_DemoState.DONE, turn=5, finished=True)
    write_state(sess, tmp_path, fields=("id", "state", "turn", "finished"))
    state = json.loads((tmp_path / ".session_state.json").read_text(encoding="utf-8"))
    assert state["state"] == "done"   # enum -> .value
    assert state["finished"] is True


def test_missing_dir_silent(tmp_path):
    write_state({"id": "x"}, tmp_path / "ghost")
    append_log(tmp_path / "ghost", {"kind": "x"})


def test_unicode_preserved(tmp_path):
    sess = {"id": "T-7", "name": "测试任务🚀", "company": "北京某某"}
    write_state(sess, tmp_path, fields=("id", "name", "company"))
    state = json.loads((tmp_path / ".session_state.json").read_text(encoding="utf-8"))
    assert state["name"] == "测试任务🚀"


def test_path_field_serializes(tmp_path):
    sess = SimpleNamespace(wf_dir=tmp_path / "x")
    snap = _to_observable_dict(sess, ("wf_dir",))
    # Just verify Path -> str (OS-specific separator is fine)
    assert isinstance(snap["wf_dir"], str)
    assert "x" in snap["wf_dir"]


def test_atomic_write_no_partial_file(tmp_path):
    sess = {"id": "X", "turn": 0}
    for i in range(20):
        sess["turn"] = i
        write_state(sess, tmp_path, fields=("id", "turn"))
    state = json.loads((tmp_path / ".session_state.json").read_text(encoding="utf-8"))
    assert state["turn"] == 19
    assert not (tmp_path / ".session_state.json.tmp").exists()


def test_jsonl_appends(tmp_path):
    for k in range(5):
        append_log(tmp_path, {"kind": f"e_{k}"})
    lines = (tmp_path / ".transitions.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert [json.loads(l)["kind"] for l in lines] == [f"e_{k}" for k in range(5)]


def test_checkpoint_writes_both(tmp_path):
    sess = {"id": "T-9", "state": "init", "turn": 1}
    checkpoint(sess, tmp_path, "started", detail="kickoff",
               fields=("id", "state", "turn"))
    assert (tmp_path / ".session_state.json").exists()
    log = (tmp_path / ".transitions.jsonl").read_text(encoding="utf-8").strip()
    assert json.loads(log)["kind"] == "started"


def test_set_default_fields_roundtrip():
    original = get_default_fields()
    try:
        set_default_fields(["id", "custom_field"])
        assert get_default_fields() == ("id", "custom_field")
    finally:
        set_default_fields(original)


def test_callback_exception_in_session_attr_swallowed(tmp_path):
    """If getattr or session.elapsed() raises, no crash."""
    class Bad:
        @property
        def state(self):
            raise RuntimeError("boom")
        id = "B-1"
    write_state(Bad(), tmp_path, fields=("id", "state"))


def test_extra_payload_merged(tmp_path):
    write_state({"id": "X"}, tmp_path, fields=("id",), extra={"meta": "v1"})
    state = json.loads((tmp_path / ".session_state.json").read_text(encoding="utf-8"))
    assert state["extra"]["meta"] == "v1"
