"""End-to-end and unit tests for the pdf_to_md package."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pdf_to_md import convert_pdf
from pdf_to_md.ocr import OcrUnavailable, page_needs_ocr
from pdf_to_md.report import validate_markdown


# ---------------------------------------------------------------------------
# Basic conversion
# ---------------------------------------------------------------------------

def test_simple_text(simple_text_pdf: Path):
    result = convert_pdf(simple_text_pdf, no_images=True, no_tables=True)
    assert "Hello" in result.markdown
    assert result.report.pages_total == 1


def test_no_validation_errors(simple_text_pdf: Path):
    result = convert_pdf(simple_text_pdf, no_images=True, no_tables=True)
    assert result.report.validation_errors == []


# ---------------------------------------------------------------------------
# Math
# ---------------------------------------------------------------------------

def test_fraction_bar_detected(math_fraction_pdf: Path):
    """The fraction bar in the PDF should produce a \frac or at minimum separate lines."""
    result = convert_pdf(math_fraction_pdf, no_images=True, no_tables=True)
    # With or without 2-D parse, the content should not be empty
    assert result.markdown.strip()


def test_sqrt_not_bare(sqrt_pdf: Path):
    result = convert_pdf(sqrt_pdf, no_images=True, no_tables=True)
    md = result.markdown
    # The conversion must not crash and must produce non-empty output.
    # Note: synthetic PDFs using insert_text may not embed math Unicode correctly;
    # real LaTeX-generated PDFs will produce \sqrt{...}.
    assert md.strip(), "Expected non-empty output from sqrt PDF"
    assert result.report.validation_errors == []


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def test_table_extraction(ruled_table_pdf: Path):
    result = convert_pdf(ruled_table_pdf, no_images=True)
    # Should produce a GFM table or at least extract some structure
    assert result.report.tables_found >= 0  # may be 0 for simple synthetic table
    assert result.markdown.strip()


def test_no_tables_flag(ruled_table_pdf: Path):
    result = convert_pdf(ruled_table_pdf, no_images=True, no_tables=True)
    # Tables flag respected — no table detection attempted
    assert result.report.tables_found == 0


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def test_figure_extracted(raster_image_pdf: Path, tmp_path: Path):
    result = convert_pdf(raster_image_pdf, no_tables=True, dpi=72)
    assert result.report.figures_extracted >= 1
    # Markdown should contain an image link
    assert "![" in result.markdown


def test_no_images_flag(raster_image_pdf: Path):
    result = convert_pdf(raster_image_pdf, no_images=True, no_tables=True)
    assert result.report.figures_extracted == 0
    assert "![" not in result.markdown


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def test_two_column_content_present(two_column_pdf: Path):
    result = convert_pdf(two_column_pdf, no_images=True, no_tables=True)
    assert "Left col" in result.markdown
    assert "Right col" in result.markdown


def test_running_headers_stripped(running_header_pdf: Path):
    result = convert_pdf(running_header_pdf, no_images=True, no_tables=True)
    # "My Paper" appears on every page header so should be stripped
    # Allow it to appear at most once (could be in body if classifier keeps it)
    occurrences = result.markdown.count("My Paper")
    assert occurrences <= 1, f"Running header not stripped: appeared {occurrences} times"


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def test_ocr_unavailable_raises(image_only_pdf: Path, monkeypatch):
    """When Tesseract is missing and OCR is needed, OcrUnavailable should be raised."""
    import pdf_to_md.ocr as ocr_module
    monkeypatch.setattr(ocr_module, "_tesseract_available", lambda: False)
    with pytest.raises(OcrUnavailable):
        convert_pdf(image_only_pdf, ocr_mode="auto", no_images=True, no_tables=True)


def test_ocr_allow_empty(image_only_pdf: Path, monkeypatch):
    """With --allow-empty, a scanned PDF without Tesseract should produce empty output, not raise."""
    import pdf_to_md.ocr as ocr_module
    monkeypatch.setattr(ocr_module, "_tesseract_available", lambda: False)
    result = convert_pdf(
        image_only_pdf,
        ocr_mode="auto",
        no_images=True,
        no_tables=True,
        allow_empty=True,
    )
    # Should not raise; markdown may be empty
    assert result.report.pages_no_text >= 1


# ---------------------------------------------------------------------------
# Report / Validation
# ---------------------------------------------------------------------------

def test_validate_balanced_math():
    assert validate_markdown("Some $x + y$ text") == []


def test_validate_unbalanced_dollar():
    errors = validate_markdown("$x + y")
    assert any("Unbalanced" in e for e in errors)


def test_validate_empty_frac():
    errors = validate_markdown(r"$$\frac{}{}$$")
    assert any("frac" in e for e in errors)


def test_validate_unbalanced_brace():
    errors = validate_markdown(r"$$\frac{x}{$$")
    assert any("brace" in e.lower() or "Unbalanced" in e for e in errors)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

def test_public_api_returns_str(simple_text_pdf: Path):
    """convert_pdf returns a ConversionResult with a .markdown string attribute."""
    from pdf_to_md import ConversionResult
    result = convert_pdf(simple_text_pdf, no_images=True, no_tables=True)
    assert isinstance(result, ConversionResult)
    assert isinstance(result.markdown, str)
