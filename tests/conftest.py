"""Pytest config — make ``agent_harness`` importable from src/ without
requiring ``pip install -e .`` first.

This lets ``pytest`` work in the repo before the package is installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
