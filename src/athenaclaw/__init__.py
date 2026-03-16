"""AthenaClaw public package surface."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from athenaclaw.kernel import Kernel, MEMORY_MAX_CHARS, Permission, Session
    from athenaclaw.runtime import AgentConfig, KernelBundle, build_kernel_bundle

__all__ = [
    "AgentConfig",
    "Kernel",
    "KernelBundle",
    "MEMORY_MAX_CHARS",
    "Permission",
    "Session",
    "build_kernel_bundle",
]

_EXPORTS = {
    "AgentConfig": ("athenaclaw.runtime", "AgentConfig"),
    "Kernel": ("athenaclaw.kernel", "Kernel"),
    "KernelBundle": ("athenaclaw.runtime", "KernelBundle"),
    "MEMORY_MAX_CHARS": ("athenaclaw.kernel", "MEMORY_MAX_CHARS"),
    "Permission": ("athenaclaw.kernel", "Permission"),
    "Session": ("athenaclaw.kernel", "Session"),
    "build_kernel_bundle": ("athenaclaw.runtime", "build_kernel_bundle"),
}


def __getattr__(name: str):
    try:
        module_name, attr_name = _EXPORTS[name]
    except KeyError as exc:  # pragma: no cover - standard module protocol
        raise AttributeError(name) from exc
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
