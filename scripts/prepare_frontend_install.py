#!/usr/bin/env python3
"""Remove the legacy frontend dependency link before running pnpm."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE_MODULES = ROOT / "frontend" / "node_modules"
LEGACY_NODE_MODULES = ROOT / ".venv" / "frontend" / "node_modules"


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def remove_legacy_link(node_modules: Path, legacy_node_modules: Path) -> bool:
    """Remove only a link that resolves to the known legacy dependency directory."""
    is_junction = getattr(os.path, "isjunction", lambda _path: False)(node_modules)
    is_symlink = node_modules.is_symlink()
    if not (is_junction or is_symlink):
        return False

    if not _same_path(node_modules, legacy_node_modules):
        raise SystemExit(
            f"Refusing to remove unexpected frontend dependency link: {node_modules}"
        )

    if is_junction:
        os.rmdir(node_modules)
    else:
        node_modules.unlink()
    return True


def main() -> int:
    if remove_legacy_link(NODE_MODULES, LEGACY_NODE_MODULES):
        print("Migrated legacy frontend dependency directory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
