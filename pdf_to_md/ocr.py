"""Scanned-page detection and OCR via Tesseract + PyMuPDF."""
from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pymupdf as fitz  # noqa: F401


class OcrUnavailable(RuntimeError):
    """Raised when OCR is needed but Tesseract is not installed."""


def _tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def page_needs_ocr(page: "fitz.Page") -> bool:
    """True when the page has almost no extractable text but carries image content."""
    text = page.get_text("text").strip()
    if len(text) >= 20:
        return False
    # Check for a large image or significant drawing paths
    images = page.get_image_info()
    if images:
        page_area = page.rect.width * page.rect.height
        for img in images:
            bbox = img.get("bbox")
            if bbox:
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                if w * h > page_area * 0.1:
                    return True
    drawings = page.get_drawings()
    return len(drawings) > 5


def get_ocr_textpage(
    page: "fitz.Page",
    language: str = "eng",
    dpi: int = 300,
) -> "fitz.TextPage":
    """
    Return a Tesseract-based textpage for this page.

    Raises OcrUnavailable with remediation instructions if Tesseract is missing.
    """
    if not _tesseract_available():
        raise OcrUnavailable(
            "Tesseract is not installed or not on PATH.\n"
            "To fix:\n"
            "  1. Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  2. Set TESSDATA_PREFIX to your tessdata directory if needed.\n"
            "  3. Re-run this command.\n"
            "Alternatively, pre-process the PDF with:\n"
            "  ocrmypdf in.pdf out.pdf\n"
            "then run pdf-to-md on the OCR'd PDF.\n"
            "To skip OCR and allow empty output: use --allow-empty"
        )
    return page.get_textpage_ocr(language=language, dpi=dpi, full=True)
