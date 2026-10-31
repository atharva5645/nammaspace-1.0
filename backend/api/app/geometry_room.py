"""Import adapter exposing the spatial-engine dimensioned draft builder."""

import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[3] / "spatial-engine"
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from geometry.room_draft import build_dimensioned_room_draft

__all__ = ["build_dimensioned_room_draft"]
