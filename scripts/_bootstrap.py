"""Shared bootstrap for the scripts in this directory.

Importing this puts ``services/api`` on the import path so a script can use the
``app`` package without the repository being installed, and forces UTF-8 on
stdout because these scripts are read on Windows consoles that default to
cp1252. Import it first; everything after it is an ordinary import.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_API_ROOT = str(REPO_ROOT / "services" / "api")
if _API_ROOT not in sys.path:
    sys.path.insert(0, _API_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
