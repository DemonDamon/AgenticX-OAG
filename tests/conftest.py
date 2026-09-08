"""Test-suite bootstrap: make tests/fixtures importable as ``fixtures.*``."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
