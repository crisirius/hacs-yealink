"""Load integration modules without importing the Home Assistant package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

COMPONENT_DIR = (
    Path(__file__).parents[1] / "custom_components" / "yealink_t54w"
)


def load_module(name: str) -> ModuleType:
    """Load ``custom_components/yealink_t54w/<name>.py`` in isolation.

    Importing the package normally would execute ``__init__.py`` and require
    Home Assistant.  The modules used by the tests are self-contained, so load
    them straight from disk instead.
    """
    module_name = f"yealink_t54w_test_{name}"
    spec = importlib.util.spec_from_file_location(
        module_name, COMPONENT_DIR / f"{name}.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
