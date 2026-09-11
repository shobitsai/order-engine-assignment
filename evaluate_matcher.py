"""Runs the Part B eval harness: python evaluate_matcher.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from orderengine.matching.evaluate import main

if __name__ == "__main__":
    main()
