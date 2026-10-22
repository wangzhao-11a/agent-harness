"""Tests for agent_harness.recovery."""
from __future__ import annotations

import json

import pytest

from agent_harness import (
    LedgerEntry,
    Recipe,
    apply_recipe,
    append_entry,
    clear_registry,
    get_recipe,
    list_recipes,
    read_ledger,
    register_recipe,
)


@pytest.fixture(autouse=True)
def _isolate():
    clear_registry()
    yield
    clear_registry()


def test_register_and_lookup():
    register_recipe("k1", lambda d: True, "test")
    r = get_recipe("k1")
    assert r is not None and r.kind == "k1"


def test_register_idempotent():
    h = lambda d: True
    register_recipe("k", h)
    register_recipe("k", h)
    assert len(list_recipes()) == 1


def test_register_conflict():
    register_recipe("k", lambda d: True)
    with pytest.raises(ValueError, match="already registered"):
        register_recipe("k", lambda d: False)


def test_recipe_swallows_handler_exception(tmp_path):
    register_recipe("crashy", lambda d: (_ for _ in ()).throw(RuntimeError()))
    r = get_recipe("crashy")
    assert r(tmp_path) is False


def test_apply_recipe_no_recipe(tmp_path):
    result = apply_recipe("ghost", tmp_path, wf_dir=tmp_path)
    assert not result.recipe_applied
    assert not result.should_retry
    assert "no recipe" in result.detail


def test_apply_recipe_changed(tmp_path):
    register_recipe("k", lambda d: True)
    result = apply_recipe("k", tmp_path, wf_dir=tmp_path)
    assert result.recipe_applied and result.changed
    assert result.should_retry


def test_apply_recipe_no_change(tmp_path):
    register_recipe("k", lambda d: False)
    result = apply_recipe("k", tmp_path, wf_dir=tmp_path)
    assert result.recipe_applied
    assert not result.changed
    assert not result.should_retry


def test_apply_recipe_writes_ledger(tmp_path):
    register_recipe("k", lambda d: True)
    apply_recipe("k", tmp_path, wf_dir=tmp_path,
                  op_name="OpX", role_tag="role:y")
    entries = read_ledger(tmp_path)
    assert len(entries) == 1
    e = entries[0]
    assert e["error_kind"] == "k"
    assert e["op_name"] == "OpX"
    assert e["role_tag"] == "role:y"


def test_apply_recipe_no_wf_no_ledger(tmp_path):
    register_recipe("k", lambda d: True)
    apply_recipe("k", tmp_path, wf_dir=None)
    assert not (tmp_path / ".recovery_ledger.jsonl").exists()


def test_ledger_persists_across_calls(tmp_path):
    register_recipe("k", lambda d: True)
    for _ in range(3):
        apply_recipe("k", tmp_path, wf_dir=tmp_path)
    assert len(read_ledger(tmp_path)) == 3


def test_corrupt_ledger_line_skipped(tmp_path):
    log = tmp_path / ".recovery_ledger.jsonl"
    log.write_text('{"ok":1}\nBAD\n{"ok":2}\n', encoding="utf-8")
    assert len(read_ledger(tmp_path)) == 2


def test_async_handler_rejected(tmp_path):
    """Coroutines must be rejected — bool(coro) is True without this guard."""
    async def async_h(d):
        return True
    register_recipe("k", async_h)
    result = apply_recipe("k", tmp_path, wf_dir=tmp_path)
    assert not result.changed


def test_handler_returning_falsy_non_bool(tmp_path):
    register_recipe("k", lambda d: None)
    result = apply_recipe("k", tmp_path, wf_dir=tmp_path)
    assert not result.changed


def test_handler_returning_truthy_non_bool(tmp_path):
    register_recipe("k", lambda d: 7)
    result = apply_recipe("k", tmp_path, wf_dir=tmp_path)
    assert result.changed is True


def test_ledger_entry_serialization():
    e = LedgerEntry(error_kind="k", recipe_id="k", success=True,
                    target="/tmp/x")
    parsed = json.loads(e.to_jsonline())
    assert parsed["error_kind"] == "k"


def test_append_entry_silent_on_missing(tmp_path):
    append_entry(tmp_path / "nope", LedgerEntry(error_kind="x", recipe_id="x",
                                                  success=False, target=""))
    assert read_ledger(tmp_path / "nope") == []
