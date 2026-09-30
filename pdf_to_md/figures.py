"""Figure extraction: rasters, vector clusters, caption pairing."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pymupdf as fitz  # noqa: F401

_CAPTION_RE = re.compile(
    r"^\s*(Figure|Fig\.?|FIGURE|Table|TABLE)\s*\d+",
    re.IGNORECASE,
)

_MIN_SIDE_PT = 24.0    # ignore tiny images (logos, bullets)
_MIN_AREA_FRAC = 0.01  # vector cluster must be ≥ 1% of page area
_CLUSTER_GAP = 12.0    # pt — max gap to merge drawing rects into one cluster
_CAPTION_DIST = 60.0   # pt — max distance above/below figure for caption


@dataclass
class ExtractedFigure:
    markdown: str
    bbox: tuple[float, float, float, float]
    caption: str = ""


def _rect_merge(rects: list[tuple[float, float, float, float]]) -> list[tuple[float, float, float, float]]:
    """Merge overlapping/nearby rects into clusters."""
    if not rects:
        return []
    merged = list(rects)
    changed = True
    while changed:
        changed = False
        result: list[tuple[float, float, float, float]] = []
        used = [False] * len(merged)
        for i, r in enumerate(merged):
            if used[i]:
                continue
            x0, y0, x1, y1 = r
            for j in range(i + 1, len(merged)):
                if used[j]:
                    continue
                ox0, oy0, ox1, oy1 = merged[j]
                # Merge if they overlap or are within CLUSTER_GAP
                if (ox0 - _CLUSTER_GAP <= x1 and ox1 + _CLUSTER_GAP >= x0 and
                        oy0 - _CLUSTER_GAP <= y1 and oy1 + _CLUSTER_GAP >= y0):
                    x0 = min(x0, ox0)
                    y0 = min(y0, oy0)
                    x1 = max(x1, ox1)
                    y1 = max(y1, oy1)
                    used[j] = True
                    changed = True
            result.append((x0, y0, x1, y1))
            used[i] = True
        merged = result
    return merged


def _is_thin_horizontal(bbox: tuple[float, float, float, float]) -> bool:
    """True for single-line rules that aren't real figures."""
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    return h < 3.0 or (w > 0 and h / w < 0.01)


def extract_figures(
    page: "fitz.Page",
    doc: "fitz.Document",
    page_num: int,
    assets_dir: Path,
    dpi: int,
    table_bboxes: list[tuple[float, float, float, float]],
    text_blocks: list[dict],
) -> tuple[list[ExtractedFigure], set[int]]:
    """
    Extract raster images and vector-cluster figures.

    Returns (figures, consumed_block_indices).
    """
    import pymupdf as fitz  # noqa: F811

    assets_dir.mkdir(parents=True, exist_ok=True)
    page_rect = page.rect
    page_area = page_rect.width * page_rect.height

    figures: list[ExtractedFigure] = []
    consumed_blocks: set[int] = set()
    fig_counter = [0]

    def _save_pixmap(clip: tuple[float, float, float, float], label: str) -> Path | None:
        try:
            clip_rect = fitz.Rect(*clip)
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, clip=clip_rect, alpha=False)
            fname = assets_dir / f"page{page_num:02d}-fig{fig_counter[0]:02d}.png"
            fig_counter[0] += 1
            pix.save(str(fname))
            return fname
        except Exception:
            return None

    def _find_caption(bbox: tuple[float, float, float, float]) -> tuple[str, int]:
        """Find a caption block near this bbox. Returns (caption_text, block_idx)."""
        x0, y0, x1, y1 = bbox
        for idx, blk in enumerate(text_blocks):
            if blk.get("type") != 0:
                continue
            bx0, by0, bx1, by1 = blk["bbox"]
            text = " ".join(
                sp.get("text", "")
                for ln in blk.get("lines", [])
                for sp in ln.get("spans", [])
            ).strip()
            if not _CAPTION_RE.match(text):
                continue
            # Check proximity: within CAPTION_DIST above or below
            above = y0 - by1
            below = by0 - y1
            if (0 <= above <= _CAPTION_DIST) or (0 <= below <= _CAPTION_DIST):
                return text, idx
        return "", -1

    def _in_table(bbox: tuple[float, float, float, float]) -> bool:
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        return any(
            tx0 <= cx <= tx1 and ty0 <= cy <= ty1
            for tx0, ty0, tx1, ty1 in table_bboxes
        )

    # ── Raster images ────────────────────────────────────────────────────────
    seen_xrefs: set[int] = set()
    for img_info in page.get_image_info(xrefs=True):
        xref = img_info.get("xref", 0)
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)

        bbox = img_info.get("bbox")
        if bbox is None:
            continue
        x0, y0, x1, y1 = bbox
        w, h = x1 - x0, y1 - y0
        if w < _MIN_SIDE_PT or h < _MIN_SIDE_PT:
            continue
        if _in_table((x0, y0, x1, y1)):
            continue

        try:
            img_data = doc.extract_image(xref)
            ext = img_data.get("ext", "png")
            fname = assets_dir / f"page{page_num:02d}-fig{fig_counter[0]:02d}.{ext}"
            fig_counter[0] += 1
            fname.write_bytes(img_data["image"])
        except Exception:
            fname_saved = _save_pixmap((x0, y0, x1, y1), "raster")
            if fname_saved is None:
                continue
            fname = fname_saved

        caption, cap_idx = _find_caption((x0, y0, x1, y1))
        if cap_idx >= 0:
            consumed_blocks.add(cap_idx)
        alt = caption or fname.stem
        rel = fname.name
        md = f"![{alt}]({assets_dir.name}/{rel})"
        if caption:
            md += f"\n\n*{caption}*"
        figures.append(ExtractedFigure(markdown=md, bbox=(x0, y0, x1, y1), caption=caption))

    # ── Vector figure clusters ────────────────────────────────────────────────
    drawing_rects: list[tuple[float, float, float, float]] = []
    for path in page.get_drawings():
        r = path.get("rect")
        if r is None:
            continue
        x0, y0, x1, y1 = r
        if (x1 - x0) < 4 or (y1 - y0) < 3:
            continue
        drawing_rects.append((x0, y0, x1, y1))

    clusters = _rect_merge(drawing_rects)
    for cluster in clusters:
        x0, y0, x1, y1 = cluster
        w, h = x1 - x0, y1 - y0
        area = w * h
        if area < page_area * _MIN_AREA_FRAC:
            continue
        if _is_thin_horizontal(cluster):
            continue
        if _in_table(cluster):
            continue

        fname = _save_pixmap(cluster, "vector")
        if fname is None:
            continue

        caption, cap_idx = _find_caption(cluster)
        if cap_idx >= 0:
            consumed_blocks.add(cap_idx)
        alt = caption or fname.stem
        rel = fname.name
        md = f"![{alt}]({assets_dir.name}/{rel})"
        if caption:
            md += f"\n\n*{caption}*"
        figures.append(ExtractedFigure(markdown=md, bbox=cluster, caption=caption))

    # Sort figures top-to-bottom for reading order
    figures.sort(key=lambda f: f.bbox[1])
    return figures, consumed_blocks
