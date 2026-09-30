"""Table extraction: page.find_tables() → GFM pipe tables."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .mathtext import to_latex

if TYPE_CHECKING:
    import pymupdf as fitz  # noqa: F401


_NUM_RE = re.compile(r"^\s*-?\d[\d,. ]*%?\s*$")


@dataclass
class ExtractedTable:
    markdown: str
    bbox: tuple[float, float, float, float]
    caption: str = ""
    approximated: bool = False


def _cell_to_md(cell: str | None) -> str:
    if cell is None:
        return ""
    text = " ".join(cell.split())  # collapse in-cell newlines
    text = text.replace("|", r"\|")
    return text


def _is_numeric_col(rows: list[list[str]], col_idx: int) -> bool:
    vals = [r[col_idx] for r in rows if col_idx < len(r) and r[col_idx].strip()]
    return bool(vals) and all(_NUM_RE.match(v) for v in vals)


def _render_gfm(header: list[str], rows: list[list[str]], numeric_cols: set[int]) -> str:
    n_cols = max(len(header), max((len(r) for r in rows), default=0))

    def pad(row: list[str]) -> list[str]:
        return row + [""] * (n_cols - len(row))

    lines: list[str] = []
    lines.append("| " + " | ".join(_cell_to_md(c) for c in pad(header)) + " |")
    sep = []
    for i in range(n_cols):
        sep.append("---:" if i in numeric_cols else "---")
    lines.append("| " + " | ".join(sep) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_cell_to_md(c) for c in pad(row)) + " |")
    return "\n".join(lines)


def _try_find_tables(page: "fitz.Page", strategy: dict) -> list:
    try:
        tabs = page.find_tables(**strategy)
        return tabs.tables if tabs else []
    except Exception:
        return []


def extract_tables(page: "fitz.Page") -> list[ExtractedTable]:
    """
    Extract tables from a page and return GFM Markdown + suppression bboxes.

    Tries ruled (strategy='lines') first, then booktabs-style. Keeps the
    result with more plausible tables (≥2 rows × ≥2 cols).
    """
    ruled = _try_find_tables(page, {"strategy": "lines"})
    booktabs = _try_find_tables(
        page,
        {"horizontal_strategy": "lines", "vertical_strategy": "text"},
    )

    def plausible(tabs: list) -> list:
        return [t for t in tabs if _table_is_plausible(t)]

    p_ruled = plausible(ruled)
    p_booktabs = plausible(booktabs)
    chosen = p_ruled if len(p_ruled) >= len(p_booktabs) else p_booktabs

    results: list[ExtractedTable] = []
    for tbl in chosen:
        md, approx, bbox = _render_table(tbl)
        if md:
            results.append(ExtractedTable(markdown=md, bbox=bbox, approximated=approx))
    return results


def _table_is_plausible(tbl) -> bool:
    try:
        rows = tbl.extract()
        return len(rows) >= 2 and all(len(r) >= 2 for r in rows[:3])
    except Exception:
        return False


def _render_table(tbl) -> tuple[str, bool, tuple[float, float, float, float]]:
    approximated = False
    try:
        rows = tbl.extract()
        if not rows:
            return "", False, (0, 0, 0, 0)

        # Header: use tbl.header if available, otherwise first row
        header_cells = []
        data_rows = rows
        try:
            if tbl.header and tbl.header.cells:
                header_cells = [c.text if c else "" for c in tbl.header.cells]
                # Check for multi-row header (approximation)
                if any(
                    isinstance(c, object) and hasattr(c, "rows") and c.rows > 1
                    for c in (tbl.header.cells or [])
                    if c
                ):
                    approximated = True
        except Exception:
            pass

        if not header_cells and rows:
            header_cells = [str(c) if c else "" for c in rows[0]]
            data_rows = rows[1:]

        n_cols = len(header_cells)
        data_rows_str = [[str(c) if c else "" for c in r] for r in data_rows]
        numeric_cols = {i for i in range(n_cols) if _is_numeric_col(data_rows_str, i)}

        md = _render_gfm(header_cells, data_rows_str, numeric_cols)
        bbox = tuple(tbl.bbox) if hasattr(tbl, "bbox") else (0, 0, 0, 0)
        return md, approximated, bbox  # type: ignore[return-value]
    except Exception:
        return "", True, (0, 0, 0, 0)
