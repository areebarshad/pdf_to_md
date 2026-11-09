"""PyMuPDF layout-engine integration: activation, capability detection, silence."""
from __future__ import annotations

import functools
import os

_SILENCED = False


class LayoutUnavailable(RuntimeError):
    """Raised when --layout on is requested but pymupdf.layout is not importable."""


def silence_recommendation() -> None:
    """Suppress PyMuPDF's 'consider pymupdf_layout' print. Idempotent."""
    global _SILENCED
    if _SILENCED:
        return
    _SILENCED = True
    try:
        import pymupdf
        if callable(getattr(pymupdf, "no_recommend_layout", None)):
            pymupdf.no_recommend_layout()
            return
        if hasattr(pymupdf, "_recommend_layout"):
            pymupdf._recommend_layout = False
            return
    except Exception:
        pass
    os.environ.setdefault("PYMUPDF_SUGGEST_LAYOUT_ANALYZER", "0")


def activate(mode: str = "auto") -> tuple[bool, str]:
    """
    Probe layout availability.

    Returns (available: bool, detail: str).
    mode "off"  — never attempt import, return (False, "disabled").
    mode "auto" — return (True, ...) if importable, else (False, ...) silently.
    mode "on"   — raise LayoutUnavailable with pip remediation if not importable.
    """
    if mode == "off":
        return False, "disabled"

    try:
        import importlib.util
        spec = importlib.util.find_spec("pymupdf.layout")
        if spec is None:
            raise ImportError("pymupdf.layout not found")
        import importlib
        ml = importlib.import_module("pymupdf.layout")
        if callable(getattr(ml, "activate", None)):
            ml.activate()
        return True, f"pymupdf.layout loaded from {spec.origin or 'unknown'}"
    except Exception as exc:
        if mode == "on":
            raise LayoutUnavailable(
                f"pymupdf.layout is not available ({exc}).\n"
                "To fix: pip install 'pymupdf>=2.1,<3'\n"
                "PyMuPDF 2.x bundles the layout analyzer in the core wheel."
            ) from exc
        return False, str(exc)


@functools.lru_cache(maxsize=1)
def table_kwargs_supported() -> frozenset[str]:
    """Return the set of kwarg names accepted by pymupdf.table.find_tables."""
    try:
        import inspect
        import pymupdf.table as tbl_mod
        sig = inspect.signature(tbl_mod.find_tables)
        return frozenset(sig.parameters.keys())
    except Exception:
        return frozenset()
