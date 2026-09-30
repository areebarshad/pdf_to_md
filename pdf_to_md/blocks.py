"""Block classification and Markdown emission — the core per-page pipeline."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from .glyphs import Bar, Glyph, extract_bars, extract_glyphs
from .layout import (
    dehyphenate_and_join,
    detect_footnotes,
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


def _bbox_in_suppressed(
    bbox: tuple[float, float, float, float],
    suppressed: list[tuple[float, float, float, float]],
) -> bool:
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    return any(
        sx0 <= cx <= sx1 and sy0 <= cy <= sy1
        for sx0, sy0, sx1, sy1 in suppressed
    )


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

    suppressed_bboxes: regions already handled by tables/figures — skip body text there.
    precomputed_blocks: pre-fetched and pre-filtered blocks (e.g. with running heads removed).
    """
    if precomputed_blocks is not None:
        blocks = precomputed_blocks
    else:
        data = page.get_text("dict", flags=0)
        blocks = data.get("blocks", [])

    # Normalise text (ligatures, smart quotes, etc.)
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

    out: list[str] = []

    for blk_idx, blk in enumerate(blocks):
        if blk.get("type") != 0:
            continue

        bbox = blk["bbox"]
        if _bbox_in_suppressed(bbox, suppressed_bboxes):
            continue

        x0, _, x1, _ = bbox
        blk_center = (x0 + x1) / 2
        blk_width = x1 - x0
        is_centered = abs(blk_center - page_width / 2) < page_width * 0.12

        # Try 2-D math parse for this block
        blk_glyphs, blk_bars = _block_glyphs_and_bars(blk, all_glyphs, all_bars)
        has_bars = bool(blk_bars)
        block_math_text: str | None = None
        used_geometry = False

        if blk_glyphs and blk_bars and not no_math_layout:
            # Determine if this block is math (any math glyph)
            block_is_math = any(
                is_math_font(g.font) or has_math_chars(g.text)
                for g in blk_glyphs
            )
            if block_is_math:
                try:
                    block_math_text, used_geometry = block_to_latex(blk_glyphs, blk_bars)
                    if used_geometry:
                        report.math_fallback_blocks = max(0, report.math_fallback_blocks)  # no-op, stays
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

        full = " ".join(lines_text).strip()
        if not full:
            continue

        if line_sizes:
            blk_max_size = max(line_sizes)

        # Use 2-D math text if we got one
        if block_math_text is not None and blk_has_math:
            full = block_math_text

        # ── Classification ──────────────────────────────────────────────────
        if not blk_has_math and blk_max_size >= h1_min:
            out.append(f"\n# {full}\n")
            continue
        if not blk_has_math and blk_max_size >= h2_min:
            out.append(f"\n## {full}\n")
            continue
        if not blk_has_math and re.match(r"^\d+(\.\d+)*\s+\w", full) and blk_bold:
            out.append(f"\n## {full}\n")
            continue

        if blk_has_math and is_centered and blk_width < page_width * 0.65:
            eq_num_match = re.search(r"\((\d+[\d.]*)\)\s*$", full)
            if eq_num_match:
                eq_body = full[: eq_num_match.start()].strip()
                eq_num = eq_num_match.group(1)
                out.append(f"\n$$\n{eq_body} \\tag{{{eq_num}}}\n$$\n")
            else:
                out.append(f"\n$$\n{full}\n$$\n")
            report.display_equations += 1
            continue

        kind = _classify(full)
        if kind == "theorem":
            out.append(f"\n> **{full}**\n")
            continue
        if kind == "definition":
            out.append(f"\n> *{full}*\n")
            continue
        if kind == "proof":
            out.append(f"\n*{full}*\n")
            continue

        if blk_has_math:
            out.append(f"${full}$")
            report.inline_math_runs += 1
            continue

        if blk_bold and len(full.split()) <= 8:
            out.append(f"\n**{full}**\n")
            continue

        out.append(full)

    # Append footnotes
    if footnote_lines:
        out.append("")
        for i, fn in enumerate(footnote_lines, 1):
            out.append(f"[^{i}]: {fn}")

    return "\n".join(out)
