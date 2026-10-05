"""Table extraction: page.find_tables() → GFM pipe tables."""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .layout import normalize_text
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
    text = normalize_text(" ".join(cell.split()))  # collapse in-cell newlines + normalize
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


def _has_ruling_lines(tbl, page: "fitz.Page") -> bool:
    """Return True if there are ≥2 horizontal drawing segments spanning ≥60% of the table width."""
    try:
        bx0, _, bx1, _ = tbl.bbox
        table_width = bx1 - bx0
        if table_width <= 0:
            return False
        min_span = table_width * 0.60
        count = 0
        for path in page.get_drawings():
            r = path.get("rect")
            if r is None:
                continue
            rx0, ry0, rx1, ry1 = r
            # Thin horizontal segment (height < 4 pt)
            if (ry1 - ry0) < 4 and (rx1 - rx0) >= min_span:
                count += 1
                if count >= 2:
                    return True
    except Exception:
        pass
    return False


def _table_is_plausible(tbl, page: "fitz.Page | None" = None, aggressive: bool = False) -> bool:
    """
    Return True only if the table looks like real tabular data.

    Applies several prose-rejection heuristics to avoid treating justified
    text columns as tables.
    """
    try:
        rows = tbl.extract()
        if not (len(rows) >= 2 and all(len(r) >= 2 for r in rows[:3])):
            return False

        # Flatten all cells for aggregate checks
        all_cells = [c for row in rows for c in row]
        non_empty = [c for c in all_cells if c and c.strip()]

        if not non_empty:
            return False

        # 1. Mid-word column split: any cell ends with a letter while the
        #    next cell in its row starts with a lowercase letter.
        for row in rows:
            for ci in range(len(row) - 1):
                a = (row[ci] or "").strip()
                b = (row[ci + 1] or "").strip()
                if a and b and a[-1].isalpha() and b[0].islower():
                    return False

        # 2. Cell brevity: median word count > 6 implies prose paragraph, not data.
        word_counts = [len(c.split()) for c in non_empty]
        if statistics.median(word_counts) > 6:
            return False

        # 3. Wrapped cells: majority of cells contain embedded newlines.
        cells_with_newlines = sum(1 for c in non_empty if "\n" in c)
        if cells_with_newlines > len(non_empty) / 2:
            return False

        # 4. Sparsity: more than 30% of cells are None.
        none_count = sum(1 for c in all_cells if c is None)
        if none_count > len(all_cells) * 0.30:
            return False

        # 5. Area cap: reject a table covering >70% of the page that has no ruling.
        if page is not None:
            try:
                bx0, by0, bx1, by1 = tbl.bbox
                page_area = page.rect.width * page.rect.height
                tbl_area = (bx1 - bx0) * (by1 - by0)
                if tbl_area > page_area * 0.70 and not _has_ruling_lines(tbl, page):
                    return False
            except Exception:
                pass

        # 6. Aggressive-pass ruling evidence: require actual line drawings.
        if aggressive and page is not None and not _has_ruling_lines(tbl, page):
            return False

        return True
    except Exception:
        return False


def extract_tables(page: "fitz.Page", strategy: str = "lines") -> list[ExtractedTable]:
    """
    Extract tables from a page and return GFM Markdown + suppression bboxes.

    strategy='lines'      — ruled tables only (default; safe for prose documents).
    strategy='aggressive' — also try vertical_strategy='text'; only kept when it
                            passes ruling-evidence checks.
    """
    ruled = _try_find_tables(page, {"strategy": "lines"})
    p_ruled = [t for t in ruled if _table_is_plausible(t, page)]

    # Prefer the ruled result; only fall back to aggressive when ruled found nothing.
    if p_ruled or strategy != "aggressive":
        chosen = p_ruled
    else:
        booktabs = _try_find_tables(
            page,
            {"horizontal_strategy": "lines", "vertical_strategy": "text"},
        )
        p_booktabs = [t for t in booktabs if _table_is_plausible(t, page, aggressive=True)]
        chosen = p_booktabs

    results: list[ExtractedTable] = []
    for tbl in chosen:
        md, approx, bbox = _render_table(tbl)
        if md:
            results.append(ExtractedTable(markdown=md, bbox=bbox, approximated=approx))
    return results


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
