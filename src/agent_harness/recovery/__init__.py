"""Auto-recovery recipes + application ledger.

A ``Recipe`` is a named callable that fixes a specific class of error
in-place. Recipes are registered once at startup and looked up by
``apply_recipe(error_kind, target)`` which also writes to the ledger.

::

    from agent_harness.recovery import register_recipe, apply_recipe

    def fix_stale_vendor(local_dir):
        # ... in-place fix ...
        return True  # changed

    register_recipe("vendor_path_outdated", fix_stale_vendor,
                    description="Refresh stale vendored CANN headers")

    result = apply_recipe("vendor_path_outdated", target_dir,
                          wf_dir=wf, op_name="MyOp")
    if result.should_retry:
        retry_failed_operation()
"""

from .apply import RecoveryResult, apply_recipe
from .ledger import LedgerEntry, append_entry, read_ledger
from .recipes import (
    Recipe,
    RecipeHandler,
    clear_registry,
    get_recipe,
    list_recipes,
    register_recipe,
)

__all__ = [
    "Recipe",
    "RecipeHandler",
    "RecoveryResult",
    "LedgerEntry",
    "register_recipe",
    "get_recipe",
    "list_recipes",
    "clear_registry",
    "apply_recipe",
    "append_entry",
    "read_ledger",
]
