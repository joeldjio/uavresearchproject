"""
tools.ui — skymeshx gcs (PySide6)

Public API
----------
from tools.ui import MainWindow, SwarmBackend, DroneBackend

Lazy imports: ``MainWindow`` pulls pyqtgraph (+ QtOpenGL) which is a heavy
dependency and breaks in headless / partial-Qt environments. Using PEP 562
module-level ``__getattr__`` defers the import until something actually
references the name, so unrelated submodules (service_locator, context.*,
backend) can be imported on systems where pyqtgraph cannot load.
"""

from typing import Any

__all__ = [
    "DroneBackend",
    "SwarmBackend",
    "MainWindow",
]


def __getattr__(name: str) -> Any:
    if name in ("DroneBackend", "SwarmBackend"):
        from tools.ui.backend import DroneBackend, SwarmBackend

        globals().update(DroneBackend=DroneBackend, SwarmBackend=SwarmBackend)
        return globals()[name]
    if name == "MainWindow":
        from tools.ui.legacy.main_window import MainWindow

        globals()["MainWindow"] = MainWindow
        return MainWindow
    raise AttributeError(f"module 'tools.ui' has no attribute {name!r}")
