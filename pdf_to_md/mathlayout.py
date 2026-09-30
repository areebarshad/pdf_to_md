"""2-D recursive math layout parser: fractions, radicals, scripts, big ops."""
from __future__ import annotations

import statistics
from typing import TYPE_CHECKING

from .glyphs import Bar, Glyph
from .mathtext import is_math_font, has_math_chars, to_latex
from .symbols import FUNCS

if TYPE_CHECKING:
    pass


def _overlaps_x(x0: float, x1: float, bar: Bar, tol: float = 2.0) -> bool:
    return x0 < bar.x1 + tol and x1 > bar.x0 - tol


def _dominant_baseline(glyphs: list[Glyph]) -> float:
    """Return the most-common origin_y (size-weighted mode)."""
    if not glyphs:
        return 0.0
    # Use weighted median as a robust baseline
    ys = [g.origin_y for g in glyphs]
    return statistics.median(ys)


def _body_size(glyphs: list[Glyph]) -> float:
    if not glyphs:
        return 11.0
    sizes = sorted(g.size for g in glyphs)
    return sizes[len(sizes) // 2]


def _glyph_latex(g: Glyph) -> str:
    return to_latex(g.text)


def _is_big_op(g: Glyph) -> str | None:
    """Return the LaTeX command if this glyph is a big operator, else None."""
    BIG_OPS = {
        "∑": r"\sum", "∏": r"\prod",
        "∫": r"\int", "∮": r"\oint",
        "⋃": r"\bigcup", "⋂": r"\bigcap",
    }
    return BIG_OPS.get(g.text)


def _is_radical(g: Glyph) -> bool:
    return g.text == "√" or "cmex" in g.font.lower()


def parse_math_region(
    glyphs: list[Glyph],
    bars: list[Bar],
    depth: int = 0,
) -> str:
    """
    Recursively parse a list of Glyph objects + available bars into LaTeX.

    Precedence: fraction → radical → big op → scripts → plain.
    Falls back to simple linear join on any exception.
    """
    if not glyphs:
        return ""
    if depth > 8:
        # Bail out to avoid infinite recursion on pathological input
        return "".join(to_latex(g.text) for g in glyphs)

    try:
        return _parse(glyphs, bars, depth)
    except Exception:
        return "".join(to_latex(g.text) for g in glyphs)


def _parse(glyphs: list[Glyph], bars: list[Bar], depth: int) -> str:
    if not glyphs:
        return ""

    gx0 = min(g.bbox[0] for g in glyphs)
    gx1 = max(g.bbox[2] for g in glyphs)

    # ── 1. Fraction ──────────────────────────────────────────────────────────
    # Find the widest bar that has glyphs both above and below it
    region_bars = [b for b in bars if _overlaps_x(gx0, gx1, b)]
    best_frac_bar: Bar | None = None
    best_width = 0.0
    for b in region_bars:
        above = [g for g in glyphs if g.bbox[3] <= b.mid_y + 1]
        below = [g for g in glyphs if g.bbox[1] >= b.mid_y - 1]
        if above and below and b.width > best_width:
            best_frac_bar = b
            best_width = b.width

    if best_frac_bar is not None:
        b = best_frac_bar
        above = [g for g in glyphs if g.bbox[3] <= b.mid_y + 1]
        below = [g for g in glyphs if g.bbox[1] >= b.mid_y - 1]
        remaining_bars = [rb for rb in bars if rb is not b]
        num = parse_math_region(above, remaining_bars, depth + 1)
        den = parse_math_region(below, remaining_bars, depth + 1)
        return rf"\frac{{{num}}}{{{den}}}"

    # ── 2. Radical ────────────────────────────────────────────────────────────
    rad_glyphs = [g for g in glyphs if g.text == "√"]
    if rad_glyphs:
        rad = rad_glyphs[0]
        # Find an overbar at the top-right of the radical
        overbar = None
        for b in region_bars:
            if b.x0 >= rad.bbox[2] - 2 and abs(b.y0 - rad.bbox[1]) <= 4:
                overbar = b
                break
        if overbar is not None:
            arg_glyphs = [
                g for g in glyphs
                if g is not rad and g.bbox[0] >= overbar.x0 - 2 and g.bbox[2] <= overbar.x1 + 2
            ]
            rest = [g for g in glyphs if g is not rad and g not in arg_glyphs]
            inner = parse_math_region(arg_glyphs, bars, depth + 1)
            suffix = parse_math_region(rest, bars, depth + 1)
            return rf"\sqrt{{{inner}}}" + suffix
        else:
            # Bare √ with following glyphs as argument (heuristic)
            others = [g for g in glyphs if g is not rad]
            if others:
                inner = parse_math_region(others, bars, depth + 1)
                return rf"\sqrt{{{inner}}}"
            return r"\sqrt"

    # ── 3. Big operators ──────────────────────────────────────────────────────
    for i, g in enumerate(glyphs):
        op_cmd = _is_big_op(g)
        if op_cmd is None:
            continue
        op_cx = (g.bbox[0] + g.bbox[2]) / 2
        op_y0 = g.bbox[1]
        op_y1 = g.bbox[3]
        lower_glyphs = [
            og for j, og in enumerate(glyphs)
            if j != i and og.bbox[1] >= op_y1 - 2
            and og.bbox[0] >= g.bbox[0] - 4 and og.bbox[2] <= g.bbox[2] + 4
        ]
        upper_glyphs = [
            og for j, og in enumerate(glyphs)
            if j != i and og.bbox[3] <= op_y0 + 2
            and og.bbox[0] >= g.bbox[0] - 4 and og.bbox[2] <= g.bbox[2] + 4
        ]
        body_glyphs = [
            og for j, og in enumerate(glyphs)
            if j != i and og not in lower_glyphs and og not in upper_glyphs
        ]
        lower_str = parse_math_region(lower_glyphs, bars, depth + 1) if lower_glyphs else ""
        upper_str = parse_math_region(upper_glyphs, bars, depth + 1) if upper_glyphs else ""
        body_str = parse_math_region(body_glyphs, bars, depth + 1)
        result = op_cmd
        if lower_str:
            result += f"_{{{lower_str}}}"
        if upper_str:
            result += f"^{{{upper_str}}}"
        if body_str:
            result += " " + body_str
        return result

    # ── 4. Scripts ────────────────────────────────────────────────────────────
    baseline = _dominant_baseline(glyphs)
    body_sz = _body_size(glyphs)
    threshold = body_sz * 0.25
    size_threshold = body_sz * 0.85

    base_glyphs: list[Glyph] = []
    sup_glyphs: list[Glyph] = []
    sub_glyphs: list[Glyph] = []

    for g in glyphs:
        off = baseline - g.origin_y
        if g.size <= size_threshold and off > threshold:
            sup_glyphs.append(g)
        elif g.size <= size_threshold and off < -threshold:
            sub_glyphs.append(g)
        else:
            base_glyphs.append(g)

    if sup_glyphs or sub_glyphs:
        base_str = _parse_linear(base_glyphs, bars, depth)
        result = base_str
        if sub_glyphs:
            sub_str = parse_math_region(sub_glyphs, bars, depth + 1)
            result += f"_{{{sub_str}}}"
        if sup_glyphs:
            sup_str = parse_math_region(sup_glyphs, bars, depth + 1)
            result += f"^{{{sup_str}}}"
        return result

    # ── 5. Plain linear ───────────────────────────────────────────────────────
    return _parse_linear(glyphs, bars, depth)


def _parse_linear(glyphs: list[Glyph], bars: list[Bar], depth: int) -> str:
    """Convert glyphs left-to-right, recognising upright function names."""
    if not glyphs:
        return ""
    sorted_g = sorted(glyphs, key=lambda g: g.bbox[0])
    parts: list[str] = []
    i = 0
    while i < len(sorted_g):
        g = sorted_g[i]
        # Check for upright multi-letter run → function name
        if g.text.isalpha() and not (is_math_font(g.font) or has_math_chars(g.text)):
            j = i + 1
            word = g.text
            while j < len(sorted_g) and sorted_g[j].text.isalpha():
                word += sorted_g[j].text
                j += 1
            if word in FUNCS:
                parts.append(f"\\{word}")
                i = j
                continue
        parts.append(to_latex(g.text))
        i += 1
    return "".join(parts)


def block_to_latex(
    glyphs: list[Glyph],
    bars: list[Bar],
) -> tuple[str, bool]:
    """
    Convert a block's glyphs to LaTeX.

    Returns (latex_string, used_geometry) where used_geometry=True means
    the 2-D parse was exercised (fractions/radicals/scripts found).
    """
    if not glyphs:
        return "", False

    linear = _parse_linear(glyphs, bars, 0)
    try:
        geometric = _parse(glyphs, bars, 0)
    except Exception:
        return linear, False

    used_geometry = geometric != linear
    return geometric, used_geometry
