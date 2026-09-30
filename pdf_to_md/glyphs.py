"""Per-page glyph and drawing-bar extraction from PyMuPDF rawdict."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pymupdf as fitz  # noqa: F401


@dataclass(slots=True)
class Glyph:
    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    size: float
    font: str
    flags: int
    origin_y: float


@dataclass(slots=True)
class Bar:
    """Horizontal bar from get_drawings() — potential fraction bar or rule."""
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return abs(self.y1 - self.y0)

    @property
    def mid_y(self) -> float:
        return (self.y0 + self.y1) / 2


def extract_glyphs(page: "fitz.Page") -> list[Glyph]:
    """Return a flat list of Glyph objects from the page's rawdict."""
    glyphs: list[Glyph] = []
    data = page.get_text("rawdict", flags=0)
    for blk in data.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for ln in blk.get("lines", []):
            for sp in ln.get("spans", []):
                font = sp.get("font", "")
                size = float(sp.get("size", 11))
                flags = sp.get("flags", 0)
                chars = sp.get("chars", [])
                for ch_data in chars:
                    ch = ch_data.get("c", "")
                    if not ch or ch.isspace():
                        continue
                    bbox = ch_data.get("bbox", (0, 0, 0, 0))
                    origin = ch_data.get("origin", (0, 0))
                    glyphs.append(Glyph(
                        text=ch,
                        bbox=(bbox[0], bbox[1], bbox[2], bbox[3]),
                        size=size,
                        font=font,
                        flags=flags,
                        origin_y=float(origin[1]),
                    ))
    return glyphs


def extract_bars(
    page: "fitz.Page",
    page_width: float,
    table_bboxes: list[tuple[float, float, float, float]] | None = None,
) -> list[Bar]:
    """
    Harvest horizontal bars from vector drawings.

    Keeps:
    - Filled rects with height ≤ 1.5pt and width ≥ 4pt
    - Stroked lines where p1.y ≈ p2.y (within 1pt)

    Excludes:
    - Bars spanning > 70% of page width (page rules)
    - Bars whose x-range falls inside a known table bbox
    """
    bars: list[Bar] = []
    table_bboxes = table_bboxes or []

    for path in page.get_drawings():
        rect = path.get("rect")
        if rect is None:
            continue

        x0, y0, x1, y1 = rect
        w = x1 - x0
        h = abs(y1 - y0)

        # Skip page-width rules
        if w > page_width * 0.70:
            continue

        is_bar = False
        if path.get("fill") is not None and h <= 1.5 and w >= 4:
            is_bar = True
        elif path.get("fill") is None:
            # Stroked lines: check items for near-horizontal segments
            for item in path.get("items", []):
                if item[0] == "l":  # line segment
                    p1, p2 = item[1], item[2]
                    if abs(p1.y - p2.y) <= 1.0 and abs(p1.x - p2.x) >= 4:
                        is_bar = True
                        break

        if not is_bar:
            continue

        # Skip if inside a known table bbox
        mid_x = (x0 + x1) / 2
        mid_y = (y0 + y1) / 2
        in_table = any(
            tx0 <= mid_x <= tx1 and ty0 <= mid_y <= ty1
            for tx0, ty0, tx1, ty1 in table_bboxes
        )
        if in_table:
            continue

        bars.append(Bar(x0=x0, y0=y0, x1=x1, y1=y1))

    return bars
