from __future__ import annotations

import sys
from pathlib import Path


# Keep the repository root importable so tests can load the Vercel entrypoint.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
