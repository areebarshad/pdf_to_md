"""Synthetic PDF fixtures built with PyMuPDF — no binary assets required."""
from __future__ import annotations

import io
from pathlib import Path

import pymupdf as fitz
import pytest


def _make_pdf(callback) -> bytes:
    """Create an in-memory PDF, call callback(doc), return bytes."""
    doc = fitz.open()
    callback(doc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_text_pdf(tmp_path: Path) -> Path:
    """One page of plain text."""
    def build(doc):
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), "Hello, world!", fontsize=12)

    p = tmp_path / "simple.pdf"
    p.write_bytes(_make_pdf(build))
    return p


@pytest.fixture
def math_fraction_pdf(tmp_path: Path) -> Path:
    """
    Page with a fraction-like layout: numerator above a horizontal bar, denominator below.
    Uses vector drawing for the bar.
    """
    def build(doc):
        page = doc.new_page(width=612, height=792)
        # Numerator
        page.insert_text((200, 200), "a + b", fontsize=12)
        # Fraction bar
        shape = page.new_shape()
        shape.draw_line(fitz.Point(190, 215), fitz.Point(270, 215))
        shape.finish(color=(0, 0, 0), width=1)
        shape.commit()
        # Denominator
        page.insert_text((200, 235), "c", fontsize=12)

    p = tmp_path / "fraction.pdf"
    p.write_bytes(_make_pdf(build))
    return p


@pytest.fixture
def sqrt_pdf(tmp_path: Path) -> Path:
    """Page with a square root symbol followed by an argument."""
    def build(doc):
        page = doc.new_page(width=612, height=792)
        page.insert_text((200, 300), "√", fontsize=14)
        page.insert_text((220, 300), "x + 1", fontsize=12)
        # Overbar above the argument
        shape = page.new_shape()
        shape.draw_line(fitz.Point(220, 288), fitz.Point(270, 288))
        shape.finish(color=(0, 0, 0), width=1)
        shape.commit()

    p = tmp_path / "sqrt.pdf"
    p.write_bytes(_make_pdf(build))
    return p


@pytest.fixture
def ruled_table_pdf(tmp_path: Path) -> Path:
    """Page with a simple 2×3 ruled table."""
    def build(doc):
        page = doc.new_page(width=612, height=792)
        # Draw table borders
        shape = page.new_shape()
        # Outer rect
        shape.draw_rect(fitz.Rect(72, 100, 400, 200))
        # Column divider
        shape.draw_line(fitz.Point(236, 100), fitz.Point(236, 200))
        # Row divider
        shape.draw_line(fitz.Point(72, 150), fitz.Point(400, 150))
        shape.finish(color=(0, 0, 0), width=0.5)
        shape.commit()
        # Cell text
        page.insert_text((80, 130), "Name", fontsize=11)
        page.insert_text((244, 130), "Value", fontsize=11)
        page.insert_text((80, 175), "Alpha", fontsize=11)
        page.insert_text((244, 175), "1.0", fontsize=11)

    p = tmp_path / "table.pdf"
    p.write_bytes(_make_pdf(build))
    return p


@pytest.fixture
def raster_image_pdf(tmp_path: Path) -> Path:
    """Page with a small embedded PNG image."""
    def build(doc):
        page = doc.new_page(width=612, height=792)
        # Create a tiny 50×50 red PNG in memory
        img_doc = fitz.open()
        img_page = img_doc.new_page(width=50, height=50)
        img_page.draw_rect(fitz.Rect(0, 0, 50, 50), color=(1, 0, 0), fill=(1, 0, 0))
        pix = img_page.get_pixmap()
        png_bytes = pix.tobytes("png")
        img_doc.close()
        rect = fitz.Rect(100, 100, 300, 300)
        page.insert_image(rect, stream=png_bytes)
        page.insert_text((100, 320), "Figure 1: A red square", fontsize=11)

    p = tmp_path / "image.pdf"
    p.write_bytes(_make_pdf(build))
    return p


@pytest.fixture
def two_column_pdf(tmp_path: Path) -> Path:
    """Page with two columns of text."""
    def build(doc):
        page = doc.new_page(width=612, height=792)
        # Left column
        for i, line in enumerate(["Left col line 1", "Left col line 2", "Left col line 3"]):
            page.insert_text((72, 100 + i * 20), line, fontsize=11)
        # Right column
        for i, line in enumerate(["Right col line 1", "Right col line 2", "Right col line 3"]):
            page.insert_text((320, 100 + i * 20), line, fontsize=11)

    p = tmp_path / "twocol.pdf"
    p.write_bytes(_make_pdf(build))
    return p


@pytest.fixture
def running_header_pdf(tmp_path: Path) -> Path:
    """Three pages each with the same header and footer."""
    def build(doc):
        for i in range(3):
            page = doc.new_page(width=612, height=792)
            # Header (top 8% = y < 63)
            page.insert_text((72, 40), "My Paper", fontsize=10)
            # Footer (bottom 8% = y > 729)
            page.insert_text((72, 750), f"Page {i + 1}", fontsize=10)
            # Body
            page.insert_text((72, 300), f"Body text on page {i + 1}", fontsize=12)

    p = tmp_path / "headers.pdf"
    p.write_bytes(_make_pdf(build))
    return p


@pytest.fixture
def image_only_pdf(tmp_path: Path) -> Path:
    """Page with only an image and no text — should trigger OCR path."""
    def build(doc):
        page = doc.new_page(width=612, height=792)
        img_doc = fitz.open()
        img_page = img_doc.new_page(width=612, height=792)
        img_page.draw_rect(fitz.Rect(0, 0, 612, 792), color=(0.9, 0.9, 0.9), fill=(0.9, 0.9, 0.9))
        pix = img_page.get_pixmap()
        png_bytes = pix.tobytes("png")
        img_doc.close()
        page.insert_image(fitz.Rect(0, 0, 612, 792), stream=png_bytes)

    p = tmp_path / "scanned.pdf"
    p.write_bytes(_make_pdf(build))
    return p
