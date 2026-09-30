"""Document-level PDF → Markdown conversion pipeline."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .blocks import page_to_md
from .figures import extract_figures
from .layout import strip_running_heads
from .ocr import OcrUnavailable, get_ocr_textpage, page_needs_ocr
from .report import ConversionReport, validate_markdown

if TYPE_CHECKING:
    pass


@dataclass
class ConversionResult:
    markdown: str
    report: ConversionReport


def convert_pdf(
    pdf_path: Path,
    *,
    no_images: bool = False,
    no_tables: bool = False,
    no_math_layout: bool = False,
    ocr_mode: str = "auto",
    ocr_lang: str = "eng",
    dpi: int = 200,
    page_markers: bool = True,
    allow_empty: bool = False,
    assets_dir_name: str | None = None,
) -> ConversionResult:
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # type: ignore[no-redef]

    pdf_path = Path(pdf_path)
    report = ConversionReport(pdf_path=str(pdf_path))
    assets_dir = pdf_path.parent / (assets_dir_name or f"{pdf_path.stem}_assets")

    with fitz.open(str(pdf_path)) as doc:
        report.pages_total = len(doc)

        # Collect all page blocks for running-head detection
        all_page_blocks: list[list[dict]] = []
        page_heights: list[float] = []
        for page in doc:
            data = page.get_text("dict", flags=0)
            all_page_blocks.append(data.get("blocks", []))
            page_heights.append(page.rect.height)

        # Strip running heads/footers across all pages
        all_page_blocks = strip_running_heads(all_page_blocks, page_heights)

        parts: list[str] = []
        unmapped: dict[str, int] = {}

        for page_num, (page, stripped_blocks) in enumerate(
            zip(doc, all_page_blocks), 1
        ):
            page_width = page.rect.width
            page_height = page.rect.height

            # OCR handling
            low_confidence = False
            textpage = None
            needs_ocr = False

            if ocr_mode == "force":
                needs_ocr = True
            elif ocr_mode == "auto":
                needs_ocr = page_needs_ocr(page)

            if needs_ocr:
                try:
                    textpage = get_ocr_textpage(page, language=ocr_lang, dpi=dpi)
                    report.pages_ocr += 1
                    low_confidence = True
                except OcrUnavailable:
                    if not allow_empty:
                        raise
                    report.pages_no_text += 1
                    report.warnings.append(
                        f"Page {page_num}: OCR unavailable, page skipped"
                    )
                    continue

            raw_text = page.get_text("text").strip()
            if len(raw_text) < 20 and not needs_ocr:
                report.pages_no_text += 1

            suppressed: list[tuple[float, float, float, float]] = []

            # Table extraction
            table_mds: list[str] = []
            if not no_tables:
                try:
                    from .tables import extract_tables
                    tables = extract_tables(page)
                    for tbl in tables:
                        suppressed.append(tbl.bbox)
                        table_mds.append(tbl.markdown)
                        report.tables_found += 1
                        if tbl.approximated:
                            report.tables_approximated += 1
                except Exception as exc:
                    report.warnings.append(f"Page {page_num}: table extraction failed: {exc}")

            # Figure extraction
            figure_mds: list[str] = []
            consumed_blocks: set[int] = set()
            if not no_images:
                try:
                    figs, consumed_blocks = extract_figures(
                        page, doc, page_num, assets_dir, dpi,
                        suppressed, stripped_blocks,
                    )
                    for fig in figs:
                        suppressed.append(fig.bbox)
                        figure_mds.append(fig.markdown)
                        report.figures_extracted += 1
                except Exception as exc:
                    report.warnings.append(f"Page {page_num}: figure extraction failed: {exc}")

            # Body text
            md = page_to_md(
                page,
                page_width=page_width,
                page_height=page_height,
                suppressed_bboxes=suppressed,
                report=report,
                no_math_layout=no_math_layout,
                unmapped=unmapped,
                low_confidence=low_confidence,
                precomputed_blocks=stripped_blocks,
            )

            # Assemble page: figures/tables interleaved by y-position is complex;
            # simpler approach: tables first (they have suppression rects so body skips them),
            # then body text, then figures at their natural positions would require
            # full reading-order merge. For now, emit tables before body, figures after.
            page_parts: list[str] = []
            if table_mds:
                page_parts.extend(table_mds)
            if md.strip():
                page_parts.append(md)
            if figure_mds:
                page_parts.extend(figure_mds)

            page_md = "\n\n".join(p for p in page_parts if p.strip())
            if page_md.strip():
                if page_markers:
                    parts.append(f"<!-- page {page_num} -->\n{page_md}")
                else:
                    parts.append(page_md)

        full_md = "\n\n---\n\n".join(parts)

        # Record unmapped chars
        report.unmapped_chars = unmapped

        # Validate
        report.validation_errors = validate_markdown(full_md)

        return ConversionResult(markdown=full_md, report=report)
