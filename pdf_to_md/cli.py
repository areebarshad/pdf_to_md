"""Command-line interface for pdf-to-md."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .convert import convert_pdf
from .ocr import OcrUnavailable


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdf-to-md",
        description="Convert PDF files to Markdown with LaTeX math, tables, and figures.",
    )
    p.add_argument(
        "inputs", nargs="*", metavar="FILE_OR_DIR",
        help="PDF file(s) or directories (default: all *.pdf in current directory)",
    )
    p.add_argument("--out-dir", metavar="DIR", help="Write output .md files here")
    p.add_argument("--assets-dir", metavar="DIR", help="Override asset directory name")
    p.add_argument("--no-images", action="store_true", help="Skip figure extraction")
    p.add_argument("--no-tables", action="store_true", help="Skip table extraction")
    p.add_argument(
        "--no-math-layout", action="store_true",
        help="Disable 2-D math parse (faster, less accurate)",
    )
    p.add_argument(
        "--tables", choices=["lines", "aggressive"], default="lines",
        metavar="{lines,aggressive}",
        help="Table detection strategy (default: lines)",
    )
    p.add_argument(
        "--ocr", choices=["auto", "force", "never"], default="auto",
        metavar="{auto,force,never}",
        help="OCR mode (default: auto — only scanned pages)",
    )
    p.add_argument("--ocr-lang", default="eng", metavar="LANG", help="Tesseract language (default: eng)")
    p.add_argument("--dpi", type=int, default=200, help="DPI for figure rasterization (default: 200)")
    p.add_argument("--report", action="store_true", help="Write <stem>.report.json alongside output")
    p.add_argument("--strict", action="store_true", help="Exit non-zero on any validation failure")
    p.add_argument("--allow-empty", action="store_true", help="Allow writing empty .md for scanned PDFs when Tesseract is unavailable")
    p.add_argument("--no-page-markers", action="store_true", help="Omit <!-- page N --> comments")
    p.add_argument("-q", "--quiet", action="store_true", help="Suppress progress output")
    p.add_argument("-v", "--verbose", action="store_true", help="Show per-file diagnostics")
    return p


def main() -> None:
    p = _build_parser()
    args = p.parse_args()

    targets: list[Path] = []
    if args.inputs:
        for arg in args.inputs:
            path = Path(arg)
            if not path.exists():
                print(f"Not found: {arg}", file=sys.stderr)
            elif path.is_dir():
                targets.extend(sorted(path.glob("*.pdf")))
            else:
                targets.append(path)
    else:
        targets = sorted(Path(".").glob("*.pdf"))

    if not targets:
        print("No PDF files found.", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir) if args.out_dir else None
    any_failed = False
    any_strict_fail = False

    for pdf in targets:
        if not args.quiet:
            print(f"Converting: {pdf.name} ...", end=" ", flush=True)
        try:
            result = convert_pdf(
                pdf,
                no_images=args.no_images,
                no_tables=args.no_tables,
                no_math_layout=args.no_math_layout,
                ocr_mode=args.ocr,
                ocr_lang=args.ocr_lang,
                dpi=args.dpi,
                page_markers=not args.no_page_markers,
                allow_empty=args.allow_empty,
                assets_dir_name=args.assets_dir,
            )
            dest = (out_dir / pdf.stem).with_suffix(".md") if out_dir else pdf.with_suffix(".md")
            if out_dir:
                out_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text(result.markdown, encoding="utf-8")

            if args.report:
                report_path = dest.with_suffix(".report.json")
                from .report import write_report
                write_report(result.report, report_path)

            if result.report.validation_errors:
                any_strict_fail = True

            if not args.quiet:
                print(f"done → {dest.name}  ({len(result.markdown):,} chars)")

            if args.verbose or (args.report and not args.quiet):
                from .report import print_summary
                print_summary(result.report)

        except OcrUnavailable as exc:
            print(f"\nERROR (OCR unavailable): {exc}", file=sys.stderr)
            any_failed = True
        except Exception as exc:
            print(f"\nERROR: {exc}", file=sys.stderr)
            any_failed = True

    if any_failed or (args.strict and any_strict_fail):
        sys.exit(1)
