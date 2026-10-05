"""Per-file conversion diagnostics and Markdown validation."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConversionReport:
    pdf_path: str = ""
    pages_total: int = 0
    pages_no_text: int = 0
    pages_ocr: int = 0
    tables_found: int = 0
    tables_approximated: int = 0
    figures_extracted: int = 0
    display_equations: int = 0
    inline_math_runs: int = 0
    math_fallback_blocks: int = 0
    unmapped_chars: dict[str, int] = field(default_factory=dict)
    validation_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_markdown(md: str) -> list[str]:
    """
    Check for common math formatting errors.

    Returns a list of error strings (empty means clean).
    """
    errors: list[str] = []

    # Parity checks: count $ and $$ delimiters
    # First extract $$ blocks, then count remaining $
    no_display = re.sub(r"\$\$[^$]*?\$\$", "", md, flags=re.DOTALL)
    dollar_count = no_display.count("$")
    if dollar_count % 2 != 0:
        errors.append(f"Unbalanced inline math: {dollar_count} $ delimiters (odd count)")

    # Brace balance within each math span
    for m in re.finditer(r"\$\$(.+?)\$\$", md, re.DOTALL):
        snippet = m.group(1)
        depth = 0
        for ch in snippet:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    errors.append(f"Unbalanced braces in display math near: {snippet[:40]!r}")
                    break
        if depth != 0:
            errors.append(f"Unbalanced braces in display math near: {snippet[:40]!r}")

    for m in re.finditer(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", md):
        snippet = m.group(1)
        depth = 0
        for ch in snippet:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth < 0:
                    errors.append(f"Unbalanced braces in inline math near: {snippet[:40]!r}")
                    break
        if depth != 0:
            errors.append(f"Unbalanced braces in inline math near: {snippet[:40]!r}")

    # Empty \frac{}{}
    if re.search(r"\\frac\{\s*\}\{\s*\}", md):
        errors.append("Empty \\frac{}{} found")

    # Stray control characters (except tab/newline/CR)
    stray = re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", md)
    if stray:
        named = ", ".join(sorted({f"U+{ord(c):04X}" for c in stray}))
        errors.append(f"Stray control characters in output: {named}")

    return errors


def write_report(report: ConversionReport, out_path: Path) -> None:
    data = {
        "pdf": report.pdf_path,
        "pages": {
            "total": report.pages_total,
            "no_text_layer": report.pages_no_text,
            "ocr": report.pages_ocr,
        },
        "tables": {
            "found": report.tables_found,
            "approximated": report.tables_approximated,
        },
        "figures": report.figures_extracted,
        "math": {
            "display_equations": report.display_equations,
            "inline_runs": report.inline_math_runs,
            "fallback_blocks": report.math_fallback_blocks,
        },
        "unmapped_chars": report.unmapped_chars,
        "validation_errors": report.validation_errors,
        "warnings": report.warnings,
    }
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def print_summary(report: ConversionReport) -> None:
    lines = [
        f"  Pages: {report.pages_total}"
        + (f" ({report.pages_ocr} OCR'd)" if report.pages_ocr else ""),
        f"  Tables: {report.tables_found}"
        + (f" ({report.tables_approximated} approximated)" if report.tables_approximated else ""),
        f"  Figures: {report.figures_extracted}",
        f"  Math: {report.display_equations} display, {report.inline_math_runs} inline"
        + (f", {report.math_fallback_blocks} fallback" if report.math_fallback_blocks else ""),
    ]
    if report.unmapped_chars:
        top = sorted(report.unmapped_chars.items(), key=lambda x: -x[1])[:5]
        lines.append("  Unmapped chars: " + ", ".join(f"{c!r}×{n}" for c, n in top))
    if report.validation_errors:
        lines.append(f"  Validation errors: {len(report.validation_errors)}")
        for e in report.validation_errors[:3]:
            lines.append(f"    - {e}")
    print("\n".join(lines))
