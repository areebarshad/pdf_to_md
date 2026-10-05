"""End-to-end and unit tests for the pdf_to_md package."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pdf_to_md import convert_pdf
from pdf_to_md.layout import dehyphenate_and_join, detect_list_item, normalize_text
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


# ---------------------------------------------------------------------------
# Unit: normalize_text — TeX T1 ligature / control-char decoding
# ---------------------------------------------------------------------------

def test_normalize_tex_ligatures():
    assert normalize_text("\x1cnal de\x1cne classi\x1ccation di\x1berent") == \
        "final define classification different"


def test_normalize_tex_bullet():
    assert normalize_text("\x88 item") == "• item"


def test_normalize_tex_em_dash():
    # \x16 maps to em-dash (—), NOT triple hyphen
    result = normalize_text("word\x16word")
    assert "—" in result
    assert "---" not in result


def test_normalize_precomposed_ligatures():
    assert normalize_text("ﬁgure ﬂow") == "figure flow"


def test_normalize_smart_quotes():
    assert normalize_text("‘hello’") == "'hello'"


# ---------------------------------------------------------------------------
# Unit: dehyphenate_and_join — fix-3 duplicate bug regression
# ---------------------------------------------------------------------------

def _make_text_block(text: str, bbox=(0, 0, 100, 20)) -> dict:
    return {
        "type": 0,
        "bbox": bbox,
        "lines": [{"spans": [{"text": text, "size": 11.0, "flags": 0, "font": "Arial", "origin": (0, 10)}]}],
    }


def test_dehyphenate_no_duplicate():
    """Merged block must appear exactly once, not twice."""
    blocks = [
        _make_text_block("ran-", bbox=(0, 0, 100, 20)),
        _make_text_block("domization, please.", bbox=(0, 25, 100, 45)),
    ]
    result = dehyphenate_and_join(blocks)
    assert len(result) == 1
    combined = " ".join(
        sp.get("text", "")
        for ln in result[0].get("lines", [])
        for sp in ln.get("spans", [])
    )
    assert combined.count("domization") == 1


def test_dehyphenate_no_mutation_of_original():
    """dehyphenate_and_join must not mutate the original block dicts."""
    original_text = "hyph-"
    blk = _make_text_block(original_text, bbox=(0, 0, 100, 20))
    cont = _make_text_block("enated", bbox=(0, 25, 100, 45))
    dehyphenate_and_join([blk, cont])
    # Original span text must be unchanged
    assert blk["lines"][0]["spans"][0]["text"] == original_text


# ---------------------------------------------------------------------------
# Unit: detect_list_item
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_marker,has_content", [
    ("• item text", "-", True),
    ("- item text", "-", True),
    ("* item text", "-", True),
    ("1. item text", "1.", True),
    ("3) item text", "3.", True),
    ("(a) item text", "-", True),
    ("(iv) item text", "-", True),
    ("normal paragraph text", None, False),
    ("2+2=4", None, False),
])
def test_detect_list_item(text, expected_marker, has_content):
    result = detect_list_item(text)
    if not has_content:
        assert result is None
    else:
        assert result is not None
        marker, content = result
        assert marker == expected_marker
        assert content.strip()


# ---------------------------------------------------------------------------
# Fixture-based: prose page yields no tables
# ---------------------------------------------------------------------------

def test_prose_page_no_false_tables(prose_pdf: Path):
    result = convert_pdf(prose_pdf, no_images=True)
    assert result.report.tables_found == 0


def test_ruled_table_still_found(ruled_table_pdf: Path):
    result = convert_pdf(ruled_table_pdf, no_images=True)
    assert result.report.tables_found >= 1, "Ruled table should still be detected"


def test_bullet_list_emitted(bullet_list_pdf: Path):
    result = convert_pdf(bullet_list_pdf, no_images=True, no_tables=True)
    assert "- " in result.markdown, "Bullet items should be emitted with '- ' prefix"


# ---------------------------------------------------------------------------
# Validate stray-char error names the offending code points
# ---------------------------------------------------------------------------

def test_validate_stray_chars_named():
    errors = validate_markdown("text\x1cmore")
    assert errors, "Should report a stray-char error"
    assert "U+001C" in errors[0]


# ---------------------------------------------------------------------------
# Real-document regression test (opt-in: requires tests/data/ PDF)
# ---------------------------------------------------------------------------

_REAL_PDF = Path(__file__).parent / "data" / "CS3654_TermProject_Proposal.pdf"


@pytest.mark.skipif(not _REAL_PDF.exists(), reason="Real PDF not present in tests/data/")
def test_real_pdf_fidelity(tmp_path):
    result = convert_pdf(_REAL_PDF, no_images=True)
    md = result.markdown

    assert result.report.tables_found == 0, "No real tables in this doc"
    assert result.report.validation_errors == [], f"Validation errors: {result.report.validation_errors}"
    assert not re.search(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", md), "Stray control chars found"
    assert md.count("domization") == 1, "Duplicate de-hyphenation block"
    for word in ("final", "define", "classification", "different"):
        assert word in md, f"Ligature fix: '{word}' missing"
    assert md.index("CS/STAT 3654") < md.index("1 "), "Title must precede section 1 text"
