"""PDF → Markdown converter with LaTeX math support.

Uses PyMuPDF's structured dict extraction to detect math fonts / Unicode math
chars, convert them to LaTeX, and reconstruct headings, theorems, definitions,
and display equations.

Usage:
    python pdf_to_md.py                  # converts all *.pdf in current folder
    python pdf_to_md.py file.pdf         # converts a single file
    python pdf_to_md.py a.pdf b.pdf      # converts multiple files

Dependencies:
    pip install --upgrade pymupdf
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        sys.exit(
            "PyMuPDF is required.  Install with:\n"
            "    pip install --upgrade pymupdf"
        )

if not hasattr(fitz, "open"):
    sys.exit(
        "The imported 'fitz' module does not expose fitz.open — a different "
        "package is shadowing PyMuPDF.  Fix with:\n"
        "    pip uninstall fitz && pip install --upgrade pymupdf"
    )

# ---------------------------------------------------------------------------
# Unicode → LaTeX symbol table
# ---------------------------------------------------------------------------

U2L: dict[str, str] = {
    # Greek lowercase
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\varepsilon", "ϵ": r"\epsilon", "ζ": r"\zeta", "η": r"\eta",
    "θ": r"\theta", "ϑ": r"\vartheta", "ι": r"\iota", "κ": r"\kappa",
    "λ": r"\lambda", "μ": r"\mu", "ν": r"\nu", "ξ": r"\xi",
    "π": r"\pi", "ϖ": r"\varpi", "ρ": r"\rho", "ϱ": r"\varrho",
    "σ": r"\sigma", "ς": r"\varsigma", "τ": r"\tau", "υ": r"\upsilon",
    "φ": r"\varphi", "ϕ": r"\phi", "χ": r"\chi", "ψ": r"\psi",
    "ω": r"\omega",
    # Greek uppercase
    "Γ": r"\Gamma", "Δ": r"\Delta", "Θ": r"\Theta", "Λ": r"\Lambda",
    "Ξ": r"\Xi", "Π": r"\Pi", "Σ": r"\Sigma", "Υ": r"\Upsilon",
    "Φ": r"\Phi", "Ψ": r"\Psi", "Ω": r"\Omega",
    # Operators
    "±": r"\pm", "∓": r"\mp", "×": r"\times", "÷": r"\div",
    "·": r"\cdot", "∙": r"\bullet", "∗": r"\ast", "⋆": r"\star",
    "∘": r"\circ", "∝": r"\propto",
    "∑": r"\sum", "∏": r"\prod", "∫": r"\int", "∮": r"\oint",
    "∂": r"\partial", "∇": r"\nabla", "∞": r"\infty", "√": r"\sqrt",
    # Relations
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx",
    "≡": r"\equiv", "≅": r"\cong", "≃": r"\simeq", "∼": r"\sim",
    "≪": r"\ll", "≫": r"\gg", "≺": r"\prec", "≻": r"\succ",
    "⊂": r"\subset", "⊃": r"\supset", "⊆": r"\subseteq", "⊇": r"\supseteq",
    "∈": r"\in", "∉": r"\notin", "∋": r"\ni", "⊥": r"\perp",
    "∥": r"\parallel", "∦": r"\nparallel",
    # Logic / sets
    "∀": r"\forall", "∃": r"\exists", "¬": r"\neg",
    "∧": r"\wedge", "∨": r"\vee",
    "⊕": r"\oplus", "⊗": r"\otimes", "⊙": r"\odot",
    "∅": r"\emptyset", "∪": r"\cup", "∩": r"\cap",
    # Arrows
    "→": r"\rightarrow", "←": r"\leftarrow", "↔": r"\leftrightarrow",
    "↑": r"\uparrow", "↓": r"\downarrow",
    "⇒": r"\Rightarrow", "⇐": r"\Leftarrow", "⇔": r"\Leftrightarrow",
    "⟹": r"\implies", "⟺": r"\iff",
    "↦": r"\mapsto", "↪": r"\hookrightarrow", "↠": r"\twoheadrightarrow",
    "⟨": r"\langle", "⟩": r"\rangle",
    "⌈": r"\lceil", "⌉": r"\rceil", "⌊": r"\lfloor", "⌋": r"\rfloor",
    # Blackboard bold
    "ℝ": r"\mathbb{R}", "ℤ": r"\mathbb{Z}", "ℕ": r"\mathbb{N}",
    "ℚ": r"\mathbb{Q}", "ℂ": r"\mathbb{C}", "ℙ": r"\mathbb{P}",
    # Dots / misc
    "…": r"\ldots", "⋯": r"\cdots", "⋮": r"\vdots", "⋱": r"\ddots",
    "‖": r"\|", "†": r"\dagger", "‡": r"\ddagger",
    "′": r"'", "″": r"''", "‴": r"'''",
    # Superscript / subscript digits
    "⁰": "^{0}", "¹": "^{1}", "²": "^{2}", "³": "^{3}",
    "⁴": "^{4}", "⁵": "^{5}", "⁶": "^{6}", "⁷": "^{7}",
    "⁸": "^{8}", "⁹": "^{9}",
    "₀": "_{0}", "₁": "_{1}", "₂": "_{2}", "₃": "_{3}",
    "₄": "_{4}", "₅": "_{5}", "₆": "_{6}", "₇": "_{7}",
    "₈": "_{8}", "₉": "_{9}",
}

MATH_FONT_KWDS = (
    "cmmi", "cmsy", "cmex", "cmr", "cmbx", "cmtt", "cmsl",
    "msam", "msbm",
    "stix", "xits", "libertinusmath",
    "mathit", "mathbf", "mathrm", "mathcal", "mathbb",
    "symbol", "zapfding", "mt extra",
)

MATH_RANGES = (
    (0x0391, 0x03C9),
    (0x2100, 0x214F),
    (0x2190, 0x21FF),
    (0x2200, 0x22FF),
    (0x27C0, 0x27EF),
    (0x2900, 0x29FF),
    (0x2A00, 0x2AFF),
    (0x1D400, 0x1D7FF),
)

_THEOREM_PAT = re.compile(
    r"^\s*(theorem|lemma|corollary|proposition|conjecture|claim|fact)"
    r"(\s+\d+[\d.]*)?[.:)]",
    re.IGNORECASE,
)
_DEFN_PAT = re.compile(
    r"^\s*(definition|notation|remark|note|example|exercise|problem|claim)"
    r"(\s+\d+[\d.]*)?[.:)]",
    re.IGNORECASE,
)
_PROOF_PAT = re.compile(r"^\s*proof\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_math_font(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in MATH_FONT_KWDS)


def _has_math_chars(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in MATH_RANGES):
            return True
    return False


def _to_latex(text: str) -> str:
    return "".join(U2L.get(ch, ch) for ch in text)


def _median(vals: list[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n else 11.0


def _is_bold(flags: int, font: str) -> bool:
    return bool(flags & 16) or any(k in font.lower() for k in ("bold", "bx", "bf"))


def _classify(text: str) -> str:
    if _PROOF_PAT.match(text):
        return "proof"
    if _THEOREM_PAT.match(text):
        return "theorem"
    if _DEFN_PAT.match(text):
        return "definition"
    return "text"


# ---------------------------------------------------------------------------
# Per-page extraction
# ---------------------------------------------------------------------------

def _page_to_md(page: "fitz.Page", page_width: float) -> str:
    data = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

    all_sizes: list[float] = []
    for blk in data.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for ln in blk.get("lines", []):
            for sp in ln.get("spans", []):
                if sp.get("text", "").strip():
                    all_sizes.append(sp["size"])

    body_size = _median(all_sizes)
    h1_min = body_size * 1.5
    h2_min = body_size * 1.2

    out: list[str] = []

    for blk in data.get("blocks", []):
        if blk.get("type") != 0:
            continue

        x0, _, x1, _ = blk["bbox"]
        blk_center = (x0 + x1) / 2
        blk_width = x1 - x0
        is_centered = abs(blk_center - page_width / 2) < page_width * 0.12

        lines_text: list[str] = []
        blk_has_math = False
        blk_max_size: float = 0.0
        blk_bold = False
        line_sizes: list[float] = []

        for ln in blk.get("lines", []):
            spans_out: list[str] = []
            prev_origin_y: float | None = None

            for sp in ln.get("spans", []):
                raw: str = sp.get("text", "")
                if not raw:
                    continue
                font: str = sp.get("font", "")
                size: float = sp.get("size", body_size)
                flags: int = sp.get("flags", 0)
                origin_y: float = sp.get("origin", (0, 0))[1]

                line_sizes.append(size)
                if _is_bold(flags, font):
                    blk_bold = True

                is_math = _is_math_font(font) or _has_math_chars(raw)

                if is_math:
                    blk_has_math = True
                    converted = _to_latex(raw)
                    if prev_origin_y is not None:
                        delta = prev_origin_y - origin_y
                        threshold = size * 0.3
                        if delta > threshold:
                            converted = f"^{{{converted.strip()}}}"
                        elif delta < -threshold:
                            converted = f"_{{{converted.strip()}}}"
                    spans_out.append(converted)
                else:
                    spans_out.append(raw)

                prev_origin_y = origin_y

            line_text = "".join(spans_out).strip()
            if line_text:
                lines_text.append(line_text)

        full = " ".join(lines_text).strip()
        if not full:
            continue

        if line_sizes:
            blk_max_size = max(line_sizes)

        if not blk_has_math and blk_max_size >= h1_min:
            out.append(f"\n# {full}\n")
            continue
        if not blk_has_math and blk_max_size >= h2_min:
            out.append(f"\n## {full}\n")
            continue
        if not blk_has_math and re.match(r"^\d+(\.\d+)*\s+\w", full) and blk_bold:
            out.append(f"\n## {full}\n")
            continue

        if blk_has_math and is_centered and blk_width < page_width * 0.65:
            eq_num_match = re.search(r"\((\d+[\d.]*)\)\s*$", full)
            if eq_num_match:
                eq_body = full[: eq_num_match.start()].strip()
                eq_num = eq_num_match.group(1)
                out.append(f"\n$$\n{eq_body} \\tag{{{eq_num}}}\n$$\n")
            else:
                out.append(f"\n$$\n{full}\n$$\n")
            continue

        kind = _classify(full)
        if kind == "theorem":
            out.append(f"\n> **{full}**\n")
            continue
        if kind == "definition":
            out.append(f"\n> *{full}*\n")
            continue
        if kind == "proof":
            out.append(f"\n*{full}*\n")
            continue

        if blk_has_math:
            out.append(f"${full}$")
            continue

        if blk_bold and len(full.split()) <= 8:
            out.append(f"\n**{full}**\n")
            continue

        out.append(full)

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Document-level conversion
# ---------------------------------------------------------------------------

def convert_pdf(pdf_path: Path) -> str:
    parts: list[str] = []
    with fitz.open(pdf_path) as doc:
        pw = doc[0].rect.width if len(doc) else 612.0
        for i, page in enumerate(doc, 1):
            md = _page_to_md(page, pw)
            if md.strip():
                parts.append(f"<!-- page {i} -->\n{md}")
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    targets: list[Path] = []

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            p = Path(arg)
            if not p.exists():
                print(f"Not found: {arg}")
            elif p.is_dir():
                targets.extend(sorted(p.glob("*.pdf")))
            else:
                targets.append(p)
    else:
        targets = sorted(Path(".").glob("*.pdf"))

    if not targets:
        print("No PDF files found.")
        return

    for pdf in targets:
        print(f"Converting: {pdf.name} ...", end=" ", flush=True)
        try:
            md = convert_pdf(pdf)
            out = pdf.with_suffix(".md")
            out.write_text(md, encoding="utf-8")
            print(f"done → {out.name}  ({len(md):,} chars)")
        except Exception as exc:
            print(f"ERROR: {exc}")


if __name__ == "__main__":
    main()
