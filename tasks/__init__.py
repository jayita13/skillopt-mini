"""Task plug-ins for skillopt_mini.

A task is any module in this folder that defines the names in REQUIRED (see _template.py).
Drop a new file here and it becomes available as `python skillopt_mini.py --task <file name>`.
Files that start with "_" and the offline `mock` helper are not listed as tasks.
"""
from __future__ import annotations

import importlib
import pkgutil

REQUIRED = ("TASK_NAME", "SEED_SKILL", "TASK_BRIEF",
            "make_splits", "user_message", "check", "show_expected")


def available() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__)
                  if not m.name.startswith("_") and m.name != "mock")


def load(name: str):
    module = importlib.import_module(f"tasks.{name}")
    missing = [n for n in REQUIRED if not hasattr(module, n)]
    if missing:
        raise SystemExit(f"tasks/{name}.py is missing {', '.join(missing)}. See tasks/_template.py")
    return module
