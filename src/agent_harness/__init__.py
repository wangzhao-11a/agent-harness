"""agent-harness — generic harness runtime for LLM agents.

Four orthogonal subsystems (use what you need; each works alone):

  observability    .session_state.json + .transitions.jsonl writers
  events           Typed FrameworkEvent + legacy callback shim
  state_machine    Generic state-machine engine — bring your own Enum
  recovery         Recipe registry + apply_recipe + JSONL ledger

Quick start
-----------
::

    from agent_harness import (
        FrameworkEvent, emit, checkpoint,
        StateMachine, IllegalTransition,
        register_recipe, apply_recipe,
    )

See ``examples/`` for full project sketches.
"""

from agent_harness.events import (
    EventCallback,
    FrameworkEvent,
    coerce_event,
    emit,
)
from agent_harness.observability import (
    DEFAULT_OBSERVABLE_FIELDS,
    append_log,
    checkpoint,
    get_default_fields,
    set_default_fields,
    write_state,
)
from agent_harness.recovery import (
    LedgerEntry,
    Recipe,
    RecipeHandler,
    RecoveryResult,
    apply_recipe,
    append_entry,
    clear_registry,
    get_recipe,
    list_recipes,
    read_ledger,
    register_recipe,
)
from agent_harness.state_machine import (
    IllegalTransition,
    InvariantFn,
    StateMachine,
    TransitionHook,
    derive_state_from_flags,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # events
    "FrameworkEvent", "EventCallback",
    "coerce_event", "emit",
    # observability
    "DEFAULT_OBSERVABLE_FIELDS",
    "checkpoint", "write_state", "append_log",
    "set_default_fields", "get_default_fields",
    # state machine
    "StateMachine", "IllegalTransition",
    "InvariantFn", "TransitionHook",
    "derive_state_from_flags",
    # recovery
    "Recipe", "RecipeHandler", "RecoveryResult", "LedgerEntry",
    "register_recipe", "get_recipe", "list_recipes", "clear_registry",
    "apply_recipe", "append_entry", "read_ledger",
]
