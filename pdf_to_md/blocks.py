"""Block classification and Markdown emission — the core per-page pipeline."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .glyphs import Bar, Glyph, extract_bars, extract_glyphs
from .layout import (
    dehyphenate_and_join,
    detect_footnotes,
    detect_list_item,
    normalize_blocks,
    two_column_order,
)
from .mathlayout import block_to_latex, parse_math_region
from .mathtext import escape_markdown, has_math_chars, is_math_font, to_latex
from .report import ConversionReport

if TYPE_CHECKING:
    import pymupdf as fitz  # noqa: F401

_THEOREM_PAT = re.compile(
    r"^\s*(theorem|lemma|corollary|proposition|conjecture|claim|fact)"
    r"(\s+\d+[\d.]*)?[.:)]",
    re.IGNORECASE,
)
_DEFN_PAT = re.compile(
    r"^\s*(definition|notation|remark|note|example|exercise|problem)"
    r"(\s+\d+[\d.]*)?[.:)]",
    re.IGNORECASE,
)
_PROOF_PAT = re.compile(r"^\s*proof\b", re.IGNORECASE)
_HYPHEN_LINE_END = re.compile(r"\w-$")


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n else 11.0


def _is_bold(flags: int, font: str) -> bool:
    return bool(flags & 16) or any(k in font.lower() for k in ("bold", "bx", "bf"))


def _classify(text: str) -> str:
    if _PROOF_PAT.match(text):
        return "proof"
    if _THEOREM_PAT.match(text):
        return "theorem"
    if _DEFN_PAT.match(text):
        return "definition"
    return "text"


def _overlap_ratio(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Return the fraction of bbox *a* that is covered by bbox *b* (0.0–1.0)."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    area_a = (ax1 - ax0) * (ay1 - ay0)
    return intersection / area_a if area_a > 0 else 0.0


def _bbox_in_suppressed(
    bbox: tuple[float, float, float, float],
    suppressed: list[tuple[float, float, float, float]],
) -> bool:
    """Suppress a block only when >60% of its area overlaps a suppressed region."""
    return any(_overlap_ratio(bbox, s) > 0.60 for s in suppressed)


def _block_glyphs_and_bars(
    blk: dict,
    all_glyphs: list[Glyph],
    bars: list[Bar],
) -> tuple[list[Glyph], list[Bar]]:
    """Return glyphs and bars that fall within this block's bbox."""
    x0, y0, x1, y1 = blk["bbox"]
    # Expand slightly for floating-point tolerance
    blk_glyphs = [
        g for g in all_glyphs
        if g.bbox[0] >= x0 - 2 and g.bbox[2] <= x1 + 2
        and g.bbox[1] >= y0 - 2 and g.bbox[3] <= y1 + 2
    ]
    blk_bars = [
        b for b in bars
        if b.x0 >= x0 - 2 and b.x1 <= x1 + 2
        and b.y0 >= y0 - 2 and b.y1 <= y1 + 2
    ]
    return blk_glyphs, blk_bars


def _join_lines(lines_text: list[str]) -> str:
    """Join lines with de-hyphenation and collapse runs of spaces."""
    parts: list[str] = []
    for line in lines_text:
        if parts and _HYPHEN_LINE_END.search(parts[-1]):
            if line and line[0].islower():
                # Remove hyphen and join without space
                parts[-1] = parts[-1][:-1] + line
                continue
        parts.append(line)
    joined = " ".join(parts).strip()
    # Collapse multiple spaces (justified-text artifact)
    return re.sub(r" {2,}", " ", joined)


def page_to_chunks(
    page: "fitz.Page",
    page_width: float,
    page_height: float,
    suppressed_bboxes: list[tuple[float, float, float, float]],
    report: ConversionReport,
    no_math_layout: bool = False,
    unmapped: dict[str, int] | None = None,
    low_confidence: bool = False,
    precomputed_blocks: list[dict] | None = None,
) -> list[tuple[float, str]]:
    """
    Convert one page to a list of (y0, markdown_chunk) pairs.

    Each tuple carries the top y-coordinate of its source block so callers can
    interleave tables and figures at their natural reading positions.
    """
    if precomputed_blocks is not None:
        blocks = precomputed_blocks
    else:
        data = page.get_text("dict", flags=0)
        blocks = data.get("blocks", [])

    # Normalise text (ligatures, TeX control chars, smart quotes, etc.)
    normalize_blocks(blocks)

    # Reading order
    blocks = two_column_order(blocks, page_width)

    # De-hyphenation
    blocks = dehyphenate_and_join(blocks)

    # Size statistics
    all_sizes: list[float] = []
    for blk in blocks:
        if blk.get("type") != 0:
            continue
        for ln in blk.get("lines", []):
            for sp in ln.get("spans", []):
                if sp.get("text", "").strip():
                    all_sizes.append(sp["size"])

    body_size = _median(all_sizes)
    h1_min = body_size * 1.5 if not low_confidence else body_size * 1.3
    h2_min = body_size * 1.2 if not low_confidence else body_size * 1.1

    # Footnote detection
    blocks, footnote_lines = detect_footnotes(blocks, page_height, body_size)

    # Glyph and bar extraction for 2-D math parse
    all_glyphs: list[Glyph] = []
    all_bars: list[Bar] = []
    if not no_math_layout:
        try:
            all_glyphs = extract_glyphs(page)
            all_bars = extract_bars(page, page_width, suppressed_bboxes)
        except Exception:
            pass

    # Minimum x0 among non-suppressed body blocks, for list indentation
    body_x0 = min(
        (blk["bbox"][0] for blk in blocks
         if blk.get("type") == 0
         and not _bbox_in_suppressed(blk["bbox"], suppressed_bboxes)),
        default=72.0,
    )
    indent_unit = 12.0  # typical per-level indent in points

    chunks: list[tuple[float, str]] = []

    for blk in blocks:
        if blk.get("type") != 0:
            continue

        bbox = blk["bbox"]
        if _bbox_in_suppressed(bbox, suppressed_bboxes):
            continue

        x0, _, x1, _ = bbox
        blk_y0: float = bbox[1]
        blk_center = (x0 + x1) / 2
        blk_width = x1 - x0
        is_centered = abs(blk_center - page_width / 2) < page_width * 0.12

        # Try 2-D math parse for this block
        blk_glyphs, blk_bars = _block_glyphs_and_bars(blk, all_glyphs, all_bars)
        has_bars = bool(blk_bars)
        block_math_text: str | None = None
        used_geometry = False

        if blk_glyphs and blk_bars and not no_math_layout:
            block_is_math = any(
                is_math_font(g.font) or has_math_chars(g.text)
                for g in blk_glyphs
            )
            if block_is_math:
                try:
                    block_math_text, used_geometry = block_to_latex(blk_glyphs, blk_bars)
                    if used_geometry:
                        report.math_fallback_blocks = max(0, report.math_fallback_blocks)
                except Exception:
                    block_math_text = None
                    report.math_fallback_blocks += 1

        # Fallback: span-based extraction
        lines_text: list[str] = []
        blk_has_math = False
        blk_max_size: float = 0.0
        blk_bold = False
        line_sizes: list[float] = []

        for ln in blk.get("lines", []):
            spans_out: list[str] = []
            prev_origin_y: float | None = None

            for sp in ln.get("spans", []):
                raw: str = sp.get("text", "")
                if not raw:
                    continue
                font: str = sp.get("font", "")
                size: float = sp.get("size", body_size)
                flags: int = sp.get("flags", 0)
                origin_y: float = sp.get("origin", (0, 0))[1]

                line_sizes.append(size)
                if _is_bold(flags, font):
                    blk_bold = True

                is_math = is_math_font(font) or has_math_chars(raw)

                if is_math:
                    blk_has_math = True
                    converted = to_latex(raw, unmapped)
                    if prev_origin_y is not None:
                        delta = prev_origin_y - origin_y
                        threshold = size * 0.3
                        if delta > threshold:
                            converted = f"^{{{converted.strip()}}}"
                        elif delta < -threshold:
                            converted = f"_{{{converted.strip()}}}"
                    spans_out.append(converted)
                else:
                    spans_out.append(escape_markdown(raw))

                prev_origin_y = origin_y

            line_text = "".join(spans_out).strip()
            if line_text:
                lines_text.append(line_text)

        full = _join_lines(lines_text)
        if not full:
            continue

        if line_sizes:
            blk_max_size = max(line_sizes)

        # Use 2-D math text if we got one
        if block_math_text is not None and blk_has_math:
            full = block_math_text

        # ── List detection (before heading/math classification) ──────────────
        if not blk_has_math:
            list_items: list[tuple[str, str]] = []  # (marker, content)
            continuation_buf: list[str] = []

            for line in lines_text:
                item = detect_list_item(line)
                if item is not None:
                    if continuation_buf and list_items:
                        marker, content = list_items[-1]
                        list_items[-1] = (marker, content + " " + " ".join(continuation_buf))
                        continuation_buf = []
                    elif continuation_buf:
                        continuation_buf = []
                    list_items.append(item)
                else:
                    continuation_buf.append(line)

            if list_items:
                # Flush any trailing continuation onto the last item
                if continuation_buf:
                    marker, content = list_items[-1]
                    list_items[-1] = (marker, content + " " + " ".join(continuation_buf))

                level = min(3, round((x0 - body_x0) / indent_unit))
                level = max(0, level)
                prefix = "  " * level
                item_lines = [f"{prefix}{marker} {content}" for marker, content in list_items]
                chunks.append((blk_y0, "\n".join(item_lines)))
                continue

        # ── Classification ───────────────────────────────────────────────────
        if not blk_has_math and blk_max_size >= h1_min:
            chunks.append((blk_y0, f"\n# {full}\n"))
            continue
        if not blk_has_math and blk_max_size >= h2_min:
            chunks.append((blk_y0, f"\n## {full}\n"))
            continue
        if not blk_has_math and re.match(r"^\d+(\.\d+)*\s+\w", full) and blk_bold:
            chunks.append((blk_y0, f"\n## {full}\n"))
            continue

        if blk_has_math and is_centered and blk_width < page_width * 0.65:
            eq_num_match = re.search(r"\((\d+[\d.]*)\)\s*$", full)
            if eq_num_match:
                eq_body = full[: eq_num_match.start()].strip()
                eq_num = eq_num_match.group(1)
                chunks.append((blk_y0, f"\n$$\n{eq_body} \\tag{{{eq_num}}}\n$$\n"))
            else:
                chunks.append((blk_y0, f"\n$$\n{full}\n$$\n"))
            report.display_equations += 1
            continue

        kind = _classify(full)
        if kind == "theorem":
            chunks.append((blk_y0, f"\n> **{full}**\n"))
            continue
        if kind == "definition":
            chunks.append((blk_y0, f"\n> *{full}*\n"))
            continue
        if kind == "proof":
            chunks.append((blk_y0, f"\n*{full}*\n"))
            continue

        if blk_has_math:
            chunks.append((blk_y0, f"${full}$"))
            report.inline_math_runs += 1
            continue

        if blk_bold and len(full.split()) <= 8:
            chunks.append((blk_y0, f"\n**{full}**\n"))
            continue

        chunks.append((blk_y0, full))

    # Append footnotes at the bottom of the page
    if footnote_lines:
        footnote_text = "\n".join(f"[^{i}]: {fn}" for i, fn in enumerate(footnote_lines, 1))
        chunks.append((page_height, "\n" + footnote_text))

    return chunks


def page_to_md(
    page: "fitz.Page",
    page_width: float,
    page_height: float,
    suppressed_bboxes: list[tuple[float, float, float, float]],
    report: ConversionReport,
    no_math_layout: bool = False,
    unmapped: dict[str, int] | None = None,
    low_confidence: bool = False,
    precomputed_blocks: list[dict] | None = None,
) -> str:
    """
    Convert one page to Markdown.

    Thin wrapper around page_to_chunks for backward compatibility.
    """
    chunks = page_to_chunks(
        page,
        page_width=page_width,
        page_height=page_height,
        suppressed_bboxes=suppressed_bboxes,
        report=report,
        no_math_layout=no_math_layout,
        unmapped=unmapped,
        low_confidence=low_confidence,
        precomputed_blocks=precomputed_blocks,
    )
    return "\n".join(chunk for _, chunk in chunks)
