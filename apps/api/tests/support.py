from __future__ import annotations

import sys
from pathlib import Path


def ensure_api_path() -> None:
    api_root = Path(__file__).resolve().parents[1]
    api_root_str = str(api_root)
    if api_root_str not in sys.path:
        sys.path.insert(0, api_root_str)
