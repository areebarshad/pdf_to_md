# pdf_to_md

A PDF → Markdown converter with LaTeX math, tables, figures, and OCR support.

Drop in a PDF, get clean Markdown out — headings, equations, pipe tables, extracted figures, and all.  
The only Python dependency is **[PyMuPDF](https://pymupdf.readthedocs.io/)** — no ML model, no internet connection, no GPU.

---

## What it produces

| PDF element | Markdown output |
|---|---|
| Large-font title / heading | `# Heading` or `## Heading` |
| Numbered section (`1.2 Title`) | `## 1.2 Title` |
| Short bold label | `**Label**` |
| Inline math | `$...$` |
| Centred display equation | `$$\n...\n$$` |
| Numbered display equation `(3)` | `$$\n... \tag{3}\n$$` |
| Theorem / Lemma / Corollary … | `> **Theorem 1. ...**` |
| Definition / Remark / Example … | `> *Definition 2. ...*` |
| Proof | `*Proof. ...*` |
| Ruled or booktabs table | GFM pipe table |
| Raster image / vector figure | `![caption](stem_assets/pageN-figM.png)` |
| Page boundary | `<!-- page N -->` + `---` |

Math is rendered by any viewer that supports KaTeX or MathJax (GitHub, Obsidian, Typora, Jupyter, VS Code, …).

---

## Requirements

```
Python ≥ 3.9
PyMuPDF ≥ 1.24
```

OCR for scanned PDFs additionally requires [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) on your PATH (optional — the converter tells you exactly what to install if it's needed).

---

## Installation

```bash
git clone https://github.com/<your-username>/pdf_to_md.git
cd pdf_to_md/pdf_to_md
pip install -e .
```

This installs the `pdf-to-md` command. To run without installing:

```bash
pip install --upgrade pymupdf
python pdf_to_md.py --help
```

> If an old `fitz` package shadows PyMuPDF, fix it with:
> ```bash
> pip uninstall fitz && pip install --upgrade pymupdf
> ```

---

## Usage

```bash
# Convert every PDF in the current folder
pdf-to-md

# Or via the script shim (no install needed)
python pdf_to_md.py

# Single file
pdf-to-md paper.pdf

# Multiple files or directories
pdf-to-md chapter1.pdf chapter2.pdf ./appendices/
```

Each PDF produces a sibling `.md` file:

```
paper.pdf  →  paper.md
paper.pdf  →  paper_assets/   (figures, if any)
```

---

## CLI reference

```
pdf-to-md [FILE_OR_DIR ...] [options]
```

| Option | Default | Description |
|---|---|---|
| `--out-dir DIR` | (same as PDF) | Write `.md` files here |
| `--assets-dir DIR` | `<stem>_assets` | Override figure asset directory name |
| `--no-images` | off | Skip figure extraction |
| `--no-tables` | off | Skip table extraction |
| `--no-math-layout` | off | Use fast linear math parse instead of 2-D geometry |
| `--tables {lines,aggressive}` | `lines` | Table detection strategy |
| `--ocr {auto,force,never}` | `auto` | OCR mode: auto detects scanned pages automatically |
| `--ocr-lang LANG` | `eng` | Tesseract language code |
| `--dpi N` | `200` | Figure rasterization resolution |
| `--report` | off | Write `<stem>.report.json` with per-file diagnostics |
| `--strict` | off | Exit non-zero on any validation failure |
| `--allow-empty` | off | Write empty `.md` instead of failing when Tesseract is absent |
| `--no-page-markers` | off | Omit `<!-- page N -->` comments |
| `-q` / `-v` | — | Quiet / verbose output |

---

## Output example

```markdown
<!-- page 1 -->

# Introduction

This is body text on page 1.

---

<!-- page 2 -->

## 1.1 Background

Some inline math: $\alpha \leq \beta$

$$
\frac{1}{2\pi i} \oint_{\gamma} \frac{f(z)}{z - a} \, dz = f(a) \tag{1}
$$

> **Theorem 1.** *Every continuous function on a compact set attains its maximum.*

*Proof.* ...

| Method | Accuracy | Time (s) |
|---|---:|---:|
| Baseline | 91.2% | 1.4 |
| Proposed | **95.7%** | 2.1 |

![Figure 2: Architecture overview](paper_assets/page03-fig01.png)

*Figure 2: Architecture overview*
```

---

## How it works

### Text and math

`page.get_text("rawdict")` from PyMuPDF returns per-character bounding boxes along with font names and flags. A character is classified as math if its font name contains a known math-font keyword (`cmmi`, `cmsy`, `cmex`, `stix`, …) or if its code point falls in a Unicode math block (Greek, Mathematical Operators, Letterlike Symbols, Mathematical Alphanumerics, etc.).

Math characters are mapped to LaTeX through a ~150-entry lookup table. Beyond simple substitution, the converter parses each math block geometrically (2-D, not line-by-line):

- **Fractions** — a horizontal bar from `page.get_drawings()` with glyphs above and below becomes `\frac{numerator}{denominator}`. Nesting is handled recursively, so `\frac{\frac{a}{b}}{c}` works.
- **Radicals** — a √ glyph paired with an overbar drawing becomes `\sqrt{argument}` instead of a bare `\sqrt`.
- **Big operators** — ∑ ∏ ∫ ⋃ ⋂ with glyphs above/below within the operator's x-span become `\sum_{lower}^{upper}`.
- **Scripts** — glyphs offset from the dominant baseline by more than 25% of body size with a smaller font become `^{...}` or `_{...}`. Nesting (`x^{2^{n}}`) is supported.
- **Safety net** — if the geometry parse fails for any block, the converter falls back to the previous linear span join and records a `math-fallback` diagnostic in the report.

### Tables

`page.find_tables()` is run twice per page — once with `strategy="lines"` for fully ruled tables and once with `horizontal_strategy="lines", vertical_strategy="text"` for booktabs-style tables (horizontal rules only). Whichever run finds more plausible tables (≥ 2 rows × ≥ 2 columns) wins. Cell content is passed through the math converter so equations survive in table cells.

### Figures

Raster images are extracted via `page.get_image_info()` and `doc.extract_image()`. Vector figures (plots, diagrams) are detected by clustering `page.get_drawings()` path rects — clusters larger than ~1% of the page area that are not table borders are rasterized with `page.get_pixmap()`. Text blocks matching `Figure N` or `Table N` within 60 pt of a figure bbox are paired as captions.

Extracted assets are written to `<stem>_assets/pageN-figM.{png,…}` alongside the `.md` file.

### Scanned PDFs

Pages with fewer than 20 characters of extractable text and a large image are flagged as scanned. In `auto` mode (the default) those pages are run through Tesseract via `page.get_textpage_ocr()` — the rest of the pipeline then runs identically. If Tesseract is not installed, the converter raises a clear error with remediation instructions instead of silently writing an empty file.

### Layout quality

Before block classification, each page goes through a layout pass:

- **Two-column reading order** — block x-centers are clustered; if a clean vertical gutter is detected, blocks are re-sorted by `(column, y)` instead of PyMuPDF's default order.
- **Running heads and footers** — strings appearing on ≥ 40% of pages within the top or bottom 8% of the page are removed.
- **De-hyphenation** — words broken across a line ending in `-` are rejoined.
- **Ligatures and quotes** — ﬁﬂﬀ → fi fl ff, smart quotes and dashes are normalised, NBSP and soft-hyphen are cleaned.
- **Footnotes** — small-font blocks at the bottom of the page starting with a digit or symbol are separated from body text and emitted as `[^n]` references.
- **Markdown escaping** — `*`, `_`, `#`, `[`, `]`, `` ` ``, `|`, `\` in body text are escaped so they don't accidentally trigger Markdown formatting.

---

## Diagnostics and validation

Run with `--report` to write `<stem>.report.json`:

```json
{
  "pages": { "total": 12, "no_text_layer": 2, "ocr": 2 },
  "tables": { "found": 3, "approximated": 0 },
  "figures": 5,
  "math": { "display_equations": 18, "inline_runs": 47, "fallback_blocks": 1 },
  "unmapped_chars": { "⊞": 2 },
  "validation_errors": [],
  "warnings": []
}
```

`--strict` causes the process to exit non-zero if `validation_errors` is non-empty.  
`-v` prints the report summary to the terminal after each file.

Validation checks: `$`/`$$` delimiter parity, brace balance inside every math span, no empty `\frac{}{}`, no stray control characters.

---

## Supported symbols

| Category | Examples |
|---|---|
| Greek lowercase | α β γ δ ε ζ η θ ι κ λ μ ν ξ π ρ σ τ υ φ χ ψ ω |
| Greek uppercase | Γ Δ Θ Λ Ξ Π Σ Υ Φ Ψ Ω |
| Operators | ± × ÷ · ∑ ∏ ∫ ∮ ∂ ∇ ∞ √ |
| Relations | ≤ ≥ ≠ ≈ ≡ ≅ ≃ ∼ ≪ ≫ ⊂ ⊃ ∈ ∉ ⊥ ∥ |
| Logic / sets | ∀ ∃ ¬ ∧ ∨ ⊕ ⊗ ∅ ∪ ∩ |
| Arrows | → ← ↔ ⇒ ⇐ ⇔ ⟹ ⟺ ↦ |
| Blackboard bold | ℝ ℤ ℕ ℚ ℂ ℙ |
| Brackets | ⟨ ⟩ ⌈ ⌉ ⌊ ⌋ |
| Dots | … ⋯ ⋮ ⋱ |
| Super/subscript digits | ⁰ ¹ ² ³ … → `^{0}` `^{1}` `^{2}` … |

---

## Python API

```python
from pathlib import Path
from pdf_to_md import convert_pdf

result = convert_pdf(
    Path("paper.pdf"),
    no_images=False,
    no_tables=False,
    ocr_mode="auto",   # "auto" | "force" | "never"
    dpi=200,
    report=False,
)

print(result.markdown)          # the full Markdown string
print(result.report.pages_total)
print(result.report.validation_errors)
```

---

## License

See [LICENSE](LICENSE).
