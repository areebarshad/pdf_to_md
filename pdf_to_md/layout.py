"""Reading-order, running head/foot removal, de-hyphenation, and text normalisation."""
from __future__ import annotations

import re
import statistics
from collections import Counter

from .symbols import LIGATURES

_TERMINAL_PUNCT = re.compile(r"[.!?:;]$")
_HYPHEN_END = re.compile(r"(\w)-$")
_LIST_BULLET = re.compile(r"^[•–—\-\*]\s+")
_LIST_ALPHA = re.compile(r"^\(([a-zA-Z]|[ivxlcdm]+)\)\s+")
_LIST_NUMERIC = re.compile(r"^\d+[.)]\s+")
_FOOTNOTE_RE = re.compile(r"^\s*(\d+|[*†‡])\s+\S")
_SECTION_NUM = re.compile(r"^\d")


def _normalize_text(text: str) -> str:
    for src, dst in LIGATURES.items():
        text = text.replace(src, dst)
    return text


def _block_text(blk: dict) -> str:
    return " ".join(
        sp.get("text", "")
        for ln in blk.get("lines", [])
        for sp in ln.get("spans", [])
    ).strip()


def _block_min_size(blk: dict) -> float:
    sizes = [
        sp.get("size", 11.0)
        for ln in blk.get("lines", [])
        for sp in ln.get("spans", [])
        if sp.get("text", "").strip()
    ]
    return min(sizes) if sizes else 11.0


def strip_running_heads(
    all_page_blocks: list[list[dict]],
    page_heights: list[float],
) -> list[list[dict]]:
    """
    Remove headers and footers that repeat on ≥40% of pages.

    Normalises numbers to '#' before comparing so '1', '2', … all match.
    """
    n_pages = len(all_page_blocks)
    if n_pages < 3:
        return all_page_blocks

    def _norm(t: str) -> str:
        return re.sub(r"\d+", "#", t.strip())

    top_candidates: Counter[str] = Counter()
    bot_candidates: Counter[str] = Counter()

    for blocks, h in zip(all_page_blocks, page_heights):
        top_margin = h * 0.08
        bot_margin = h * 0.92
        for blk in blocks:
            if blk.get("type") != 0:
                continue
            y0, y1 = blk["bbox"][1], blk["bbox"][3]
            t = _norm(_block_text(blk))
            if not t:
                continue
            if y1 <= top_margin:
                top_candidates[t] += 1
            elif y0 >= bot_margin:
                bot_candidates[t] += 1

    threshold = n_pages * 0.40
    running = {t for t, c in top_candidates.items() if c >= threshold}
    running |= {t for t, c in bot_candidates.items() if c >= threshold}

    result: list[list[dict]] = []
    for blocks, h in zip(all_page_blocks, page_heights):
        top_margin = h * 0.08
        bot_margin = h * 0.92
        cleaned: list[dict] = []
        for blk in blocks:
            if blk.get("type") != 0:
                cleaned.append(blk)
                continue
            y0, y1 = blk["bbox"][1], blk["bbox"][3]
            t = _norm(_block_text(blk))
            if not t:
                cleaned.append(blk)
                continue
            if (y1 <= top_margin or y0 >= bot_margin) and t in running:
                continue
            cleaned.append(blk)
        result.append(cleaned)
    return result


def two_column_order(
    blocks: list[dict],
    page_width: float,
) -> list[dict]:
    """
    Re-sort blocks into reading order for two-column layouts.

    Detects a vertical gutter by clustering block x-centers. If a clean
    two-column split is found, sorts blocks by (column, y); otherwise
    returns blocks in original order.
    """
    text_blocks = [b for b in blocks if b.get("type") == 0]
    if len(text_blocks) < 4:
        return blocks

    centers = [(b["bbox"][0] + b["bbox"][2]) / 2 for b in text_blocks]
    left_centers = [c for c in centers if c < page_width / 2]
    right_centers = [c for c in centers if c >= page_width / 2]

    if not left_centers or not right_centers:
        return blocks

    # Heuristic: if a clean split exists, medians should be well-separated
    try:
        lm = statistics.median(left_centers)
        rm = statistics.median(right_centers)
    except statistics.StatisticsError:
        return blocks

    # Require centres to be at least 20% of page width apart
    if rm - lm < page_width * 0.20:
        return blocks

    def _col(b: dict) -> int:
        cx = (b["bbox"][0] + b["bbox"][2]) / 2
        return 0 if cx < page_width / 2 else 1

    return sorted(blocks, key=lambda b: (_col(b), b["bbox"][1]))


def dehyphenate_and_join(blocks: list[dict]) -> list[dict]:
    """
    Merge consecutive text blocks where the previous ends with a soft hyphen
    or where the continuation is a lowercase non-sentence-start word.

    Modifies blocks in-place (appending text to the first block).
    Returns a new list with merged blocks removed.
    """
    if not blocks:
        return blocks

    result: list[dict] = []
    skip = set()
    for i, blk in enumerate(blocks):
        if i in skip or blk.get("type") != 0:
            result.append(blk)
            continue
        text = _block_text(blk)
        # De-hyphenation: "word-" + lowercase next block
        m = _HYPHEN_END.search(text)
        if m and i + 1 < len(blocks) and blocks[i + 1].get("type") == 0:
            next_text = _block_text(blocks[i + 1])
            if next_text and next_text[0].islower():
                merged_text = text[: m.start()] + m.group(1) + next_text
                blk = dict(blk)
                _set_block_text(blk, merged_text)
                skip.add(i + 1)
                result.append(blk)
                continue
        result.append(blk)
    return result


def _set_block_text(blk: dict, text: str) -> None:
    """Replace all span text in a block with a single flat string (best-effort)."""
    lines = blk.get("lines", [])
    if not lines:
        return
    first_line = lines[0]
    spans = first_line.get("spans", [])
    if spans:
        spans[0]["text"] = text
        for sp in spans[1:]:
            sp["text"] = ""
    for ln in lines[1:]:
        for sp in ln.get("spans", []):
            sp["text"] = ""


def detect_footnotes(
    blocks: list[dict],
    page_height: float,
    body_size: float,
) -> tuple[list[dict], list[str]]:
    """
    Separate footnote blocks from body blocks.

    Returns (body_blocks, footnote_lines).
    Small-font blocks in the bottom 20% of the page starting with a digit/symbol.
    """
    cutoff_y = page_height * 0.80
    body: list[dict] = []
    footnotes: list[str] = []

    for blk in blocks:
        if blk.get("type") != 0:
            body.append(blk)
            continue
        y0 = blk["bbox"][1]
        min_sz = _block_min_size(blk)
        text = _block_text(blk)
        if y0 >= cutoff_y and min_sz <= body_size * 0.85 and _FOOTNOTE_RE.match(text):
            footnotes.append(text)
        else:
            body.append(blk)
    return body, footnotes


def normalize_blocks(blocks: list[dict]) -> list[dict]:
    """Apply ligature/quote normalization to all span text."""
    for blk in blocks:
        if blk.get("type") != 0:
            continue
        for ln in blk.get("lines", []):
            for sp in ln.get("spans", []):
                raw = sp.get("text", "")
                if raw:
                    sp["text"] = _normalize_text(raw)
    return blocks
