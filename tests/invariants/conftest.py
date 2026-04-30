"""Shared Hypothesis strategies and helpers for invariant tests.

conftest.py adds this directory to sys.path so test files can import
the strategies module directly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
