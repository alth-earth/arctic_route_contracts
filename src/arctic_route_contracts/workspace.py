"""Workspace root resolution for the multi-repository Arctic Route workspace.

Resolve the workspace root (the common parent directory containing the
``arctic_route_contracts/``, ``work_package_a/`` ... repositories) using the
following priority:

1. ``ARCTIC_ROUTE_ROOT`` environment variable (if set and valid);
2. derivation from this module's location (``__file__``), i.e. the repository
   layout as delivered;
3. ``$HOME`` (only if it happens to contain ``arctic_route_contracts/``).

The resolved root is validated: it must contain ``arctic_route_contracts/``.
This mirrors the convention declared in
``arctic_route_governance/README.md`` (路径约定).
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_VAR = "ARCTIC_ROUTE_ROOT"
_MARKER_DIR = "arctic_route_contracts"

# Path to this file in the delivered layout:
#   <workspace>/arctic_route_contracts/src/arctic_route_contracts/workspace.py
_WORKSPACE_PARENTS = 3


def _is_workspace_root(candidate: Path) -> bool:
    return (candidate / _MARKER_DIR).is_dir()


def _resolve_from_env() -> Path | None:
    raw = os.environ.get(_ENV_VAR)
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if _is_workspace_root(candidate):
        return candidate
    raise ValueError(
        f"{_ENV_VAR}={raw!r} does not point to a workspace root "
        f"(missing {_MARKER_DIR}/ directory)"
    )


def _resolve_from_file() -> Path | None:
    candidate = Path(__file__).resolve().parents[_WORKSPACE_PARENTS]
    if _is_workspace_root(candidate):
        return candidate
    return None


def _resolve_from_home() -> Path | None:
    candidate = Path.home()
    if _is_workspace_root(candidate):
        return candidate
    return None


def workspace_root() -> Path:
    """Return the validated workspace root directory."""
    for resolver in (_resolve_from_env, _resolve_from_file, _resolve_from_home):
        resolved = resolver()
        if resolved is not None:
            return resolved
    raise RuntimeError(
        "unable to locate the Arctic Route workspace root: "
        f"set {_ENV_VAR} to the workspace directory containing "
        f"{_MARKER_DIR}/, or run from the delivered repository layout"
    )
