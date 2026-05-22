#!/usr/bin/env python3
"""Mizan — point d'entrée CLI (wrapper de `src/cli/main.py`)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
