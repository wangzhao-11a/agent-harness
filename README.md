# agent-harness

[![tests](https://github.com/wangzhao-11a/agent-harness/actions/workflows/tests.yml/badge.svg)](https://github.com/wangzhao-11a/agent-harness/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Generic harness runtime for LLM agents. Four orthogonal subsystems (use what
you need; each works alone):

- **observability** — `.session_state.json` + `.transitions.jsonl` writers
- **events** — typed `FrameworkEvent` + legacy callback shim
- **state_machine** — generic state-machine engine; bring your own `Enum`
- **recovery** — recipe registry + `apply_recipe` + JSONL ledger

Zero runtime dependencies. Pure stdlib. Python 3.10+.

---

## Why

Every production LLM-agent project ends up writing the same four things:

1. A status file external monitors can `tail -f`
2. A typed event format so downstream consumers can match instead of grepping
3. An explicit state machine to prevent illegal "finish before start" bugs
4. A recipe + ledger system for auto-recovery from transient failures

`agent-harness` packages these four primitives so you stop reinventing them
per project. The state set, event vocabulary, and recipes stay project-
specific — the **engine** does not.

---

## Install

```bash
pip install agent-harness
# or, locally:
git clone https://github.com/wangzhao-11a/agent-harness && cd agent-harness && pip install -e .
```

---

## Quick start

```python
from enum import Enum
from agent_harness import (
    FrameworkEvent, emit, checkpoint,
    StateMachine, IllegalTransition,
    register_recipe, apply_recipe,
)

# 1) Define your project's state vocabulary
class JobState(Enum):
    INIT = "init"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

sm = StateMachine(
    state_enum=JobState,
    transitions={
        (JobState.INIT, "start"):    JobState.RUNNING,
        (JobState.RUNNING, "finish"): JobState.DONE,
        (JobState.INIT, "abort"):    JobState.FAILED,
        (JobState.RUNNING, "abort"): JobState.FAILED,
    },
    invariants={
        JobState.DONE: lambda j: j.get("result") is not None,
    },
)

# 2) Drive the lifecycle
job = {"id": "J-001", "state": JobState.INIT.value}
sm.transition(job, "start")            # job["state"] == "running"
checkpoint(job, "data/jobs/J-001",     # observability snapshot
           event_kind="started",
           fields=("id", "state"))

# 3) Recover from known failures
def fix_stale_token(target):
    # ... refresh token ...
    return True   # changed

register_recipe("auth_token_stale", fix_stale_token)
result = apply_recipe("auth_token_stale", token_path,
                      wf_dir="data/jobs/J-001",
                      op_name="J-001")
if result.should_retry:
    retry_request()
```

---

## API surface

```python
# events
FrameworkEvent(kind, payload, severity, ts)
emit(callback, *args, **kwargs)        # legacy + typed shim
coerce_event(*args, **kwargs)

# observability
checkpoint(session, wf_dir, event_kind, detail="", fields=None, **extra)
write_state(session, wf_dir, fields=None, extra=None)
append_log(wf_dir, record: dict)
set_default_fields(fields), get_default_fields()

# state_machine
StateMachine(state_enum, transitions, terminal_states=..., invariants=..., state_attr="state")
StateMachine.transition(session, event, on_transition=None) -> Enum
StateMachine.safe_transition(session, event) -> Enum | None
StateMachine.assert_invariants(session)
StateMachine.is_terminal(state=None, session=None) -> bool
StateMachine.legal_events(state) -> tuple[str, ...]
derive_state_from_flags(session, rules, default) -> Enum
IllegalTransition  # exception

# recovery
register_recipe(kind, handler, description="") -> Recipe
get_recipe(kind) -> Recipe | None
list_recipes() -> list[Recipe]
clear_registry()
apply_recipe(error_kind, target, wf_dir=None, op_name="", role_tag="") -> RecoveryResult
read_ledger(wf_dir) -> list[dict]
append_entry(wf_dir, entry: LedgerEntry)
```

---

## Design principles

1. **Never raise from observability** — a logger crash must not crash your
   pipeline. Every public function in `observability` and `recovery` swallows
   exceptions silently.
2. **Bring your own enum** — state sets are project-specific. The engine is
   generic; the vocabulary is yours.
3. **Backward compatible** — `emit` accepts both modern `FrameworkEvent` and
   legacy `(channel, message)` callbacks so migration can be incremental.
4. **Explicit over magic** — transitions and invariants are dictionaries you
   can grep. No metaclass tricks.
5. **JSON-first persistence** — every state file and log line is parseable
   with `jq`. No pickle, no custom format.

---

## What this is NOT

- A workflow engine (no DAG / scheduling). Use LangGraph or your own.
- A tool framework (no tool definitions). Use the Anthropic SDK or your own.
- A prompt library. Use whatever you like.
- An eval framework. See `agent-evals`, Hamel's blog, etc.

`agent-harness` is the **infrastructure layer beneath** all of those — the
boring plumbing every agent eventually needs.

---

## Related

- [infer-rsi](https://github.com/wangzhao-11a/infer-rsi) — experiment ledger and statistical gate for inference tuning.
- [kernel-agent](https://github.com/wangzhao-11a/kernel-agent) — kernel optimization loop with scoped strategy memory.

## License

MIT — see `LICENSE`.
