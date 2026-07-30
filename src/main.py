"""Application entry point."""

from __future__ import annotations

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.gui import run_application


if __name__ == "__main__":
    run_application(smoke_test="--smoke-test" in sys.argv[1:])
