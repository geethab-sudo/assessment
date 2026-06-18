"""Pytest bootstrap — shared by all tests under this folder.

Adds the repository root to ``sys.path`` so imports like ``from services...``
work when pytest discovers tests. Unittest files may duplicate this when run
via ``python -m unittest``; see TEST_GUIDE.md for how to run the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
