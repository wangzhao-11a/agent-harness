"""Recipe registry — named auto-recovery strategies.

A recipe is a callable that, given a target (typically a Path to the artifact
being acted on), attempts to fix a specific class of environment error
in-place. It returns ``True`` iff it actually modified things; ``False`` for
"matched zero items" or "nothing to do".

Recipes never raise. They never touch session state directly. They never
emit events. All of that is the orchestrator's job (``apply_recipe``).

Genericized from an operator-tuning project's recovery module.
The legacy bootstrap that auto-imported project-specific handlers has been
removed; projects now register their own recipes at startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# A handler takes the target (typically a Path) and returns whether it
# changed anything. Generic Any since some projects might pass non-Path targets.
RecipeHandler = Callable[[Any], bool]


@dataclass(frozen=True)
class Recipe:
    """One named recovery strategy.

    ``kind`` is a free-form string matching the error category your
    orchestrator detects. By convention, use snake_case identifiers like
    ``"vendor_path_outdated"`` or ``"missing_dependency"``.
    """
    kind: str
    handler: RecipeHandler
    description: str = ""

    def __call__(self, target: Any) -> bool:
        """Defensive wrapper: a recipe handler bug must not crash the pipeline.

        Async handlers are explicitly rejected: ``bool(coroutine_obj)`` is
        always True, so without a guard we would falsely report changed=True
        AND leak an un-awaited coroutine. Recipes must be sync.
        """
        try:
            result = self.handler(target)
        except Exception:
            return False
        import inspect
        if inspect.iscoroutine(result):
            try:
                result.close()
            except Exception:
                pass
            return False
        if inspect.isawaitable(result):
            return False
        return bool(result)


_REGISTRY: dict[str, Recipe] = {}


def register_recipe(kind: str, handler: RecipeHandler,
                    description: str = "") -> Recipe:
    """Register a recipe under ``kind``. Idempotent: re-registering with the
    same handler is a no-op; re-registering with a different handler raises."""
    existing = _REGISTRY.get(kind)
    if existing is not None and existing.handler is not handler:
        raise ValueError(
            f"Recipe for {kind!r} already registered with a different "
            f"handler ({existing.handler!r}). Use a new kind or remove first."
        )
    recipe = existing or Recipe(kind=kind, handler=handler, description=description)
    _REGISTRY[kind] = recipe
    return recipe


def get_recipe(kind: str) -> Recipe | None:
    """Look up a recipe by error kind. Returns None if no recipe exists."""
    return _REGISTRY.get(kind)


def list_recipes() -> list[Recipe]:
    """Snapshot of all registered recipes (for diagnostic reporting)."""
    return list(_REGISTRY.values())


def clear_registry() -> None:
    """Wipe the registry. Useful in tests or when reconfiguring at runtime."""
    _REGISTRY.clear()


# Backward-compat alias for projects that adopted the perf_repl naming.
_clear_registry_for_tests = clear_registry
