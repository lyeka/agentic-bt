from __future__ import annotations

from importlib import import_module

__all__ = ["bash", "compute", "edit", "market", "read", "shell", "web", "write"]

_EXPORTS = {
    "bash": ("athenaclaw.tools.shell.tool", None),
    "compute": ("athenaclaw.tools.compute.tool", None),
    "edit": ("athenaclaw.tools.filesystem.edit", None),
    "market": ("athenaclaw.tools.market.tool", None),
    "read": ("athenaclaw.tools.filesystem.read", None),
    "shell": ("athenaclaw.tools.shell.tool", None),
    "web": ("athenaclaw.tools.web.tool", None),
    "write": ("athenaclaw.tools.filesystem.write", None),
}


def __getattr__(name: str):
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:  # pragma: no cover - standard module protocol
        raise AttributeError(name) from exc
    module = import_module(module_name)
    value = module if attr_name is None else getattr(module, attr_name)
    globals()[name] = value
    return value
