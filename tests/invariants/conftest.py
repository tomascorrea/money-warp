"""Make the strategies module importable by adding this directory to sys.path."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
