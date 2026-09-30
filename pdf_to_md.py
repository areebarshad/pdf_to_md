"""Thin shim — keeps `python pdf_to_md.py` working after the refactor."""
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf_to_md.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
