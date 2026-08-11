"""Pytest wiring for the Locksmith Loop deterministic-parity checks.

``test.sh`` invokes ``pytest /tests/test_outputs.py``, which collects only that
one file. This conftest is auto-loaded for that session and, via
``pytest_collection_modifyitems``, also pulls the witness-based parity tests
defined in ``test_locksmith_parity`` into the same run -- so the existing
verifier path now also exercises the deterministic oracle across many generated
inputs. No existing file (``test.sh``, ``test_outputs.py``) is modified.

The locksmith tests are ordinary ``test_*`` functions and can also be collected
directly (``pytest test_locksmith_parity.py``) or as part of a whole-directory
run; the hook here only guarantees they run under the fixed-argument invocation
that ``test.sh`` uses.
"""

import inspect

import pytest


def _sibling_test_items(mod, existing_names):
    """Yield ``(name, function)`` for test functions defined in ``mod``."""
    for name in sorted(dir(mod)):
        if not name.startswith("test_"):
            continue
        obj = getattr(mod, name)
        if not inspect.isfunction(obj):
            continue
        if getattr(obj, "__module__", None) != mod.__name__:
            continue
        if name in existing_names:
            continue
        yield name, obj


def pytest_collection_modifyitems(items):
    """Also collect witness-based parity tests alongside ``test_outputs``.

    Runs late enough that the test module's directory is already on
    ``sys.path`` (pytest puts it there for ``test_outputs.py``), so a plain
    ``import test_locksmith_parity`` resolves. If the sibling module cannot be
    imported for any reason, we leave the session's collection unchanged
    rather than failing the whole run.
    """
    if not items:
        return
    try:
        import test_locksmith_parity as locksmith
    except Exception:
        return

    existing_names = {item.name for item in items}
    parent = items[0].parent
    for name, func in _sibling_test_items(locksmith, existing_names):
        items.append(
            pytest.Function.from_parent(parent, name=name, callobj=func)
        )
