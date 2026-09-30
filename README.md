# 📄 pdf_to_md

> **A PDF → Markdown converter with first-class LaTeX math support.**
> Drop in a PDF, get clean Markdown out — headings, theorems, equations and all.

---

## ✨ What it does

Most PDF-to-text tools either strip all math or dump raw Unicode gibberish.  
`pdf_to_md` does neither. It reads the PDF's internal font and glyph data with **[PyMuPDF](https://pymupdf.readthedocs.io/)** and reconstructs the document structure intelligently:

| PDF element | Markdown output |
|---|---|
| Large-font title / heading | `# Heading` or `## Heading` |
| Numbered section (`1.2 Title`) | `## 1.2 Title` |
| Short bold label | `**Label**` |
| Inline math (math font or Unicode symbols) | `$...$` |
| Centred display equation | `$$\n...\n$$` |
| Numbered display equation `(3)` | `$$\n... \tag{3}\n$$` |
| Theorem / Lemma / Corollary … | `> **Theorem 1. ...**` |
| Definition / Remark / Example … | `> *Definition 2. ...*` |
| Proof | `*Proof. ...*` |
| Page boundary | `<!-- page N -->` + `---` |

### Math conversion

Greek letters, operators, relations, arrows, blackboard-bold letters — everything in the Unicode math planes — is mapped to proper LaTeX macros automatically.

*Example:* a PDF span that looks like `α ≤ β ∈ ℝ` becomes `\alpha \leq \beta \in \mathbb{R}` in the output.

Superscripts and subscripts are detected by tracking the vertical origin of each glyph, so `x²` becomes `x^{2}` and `H₂O` becomes `H_{2}O`.

---

## 📦 Requirements

```
Python ≥ 3.9
PyMuPDF ≥ 1.23
```

> **No other dependencies.** No ML model, no internet connection, no GPU.

---

## 🚀 Installation

**1. Clone the repo**

```bash
git clone https://github.com/<your-username>/pdf_to_md.git
cd pdf_to_md
```

**2. Install the one dependency**

```bash
pip install --upgrade pymupdf
```

> ⚠️ If you have an old package named `fitz` installed from a *different* project, it will shadow PyMuPDF and cause an import error. Fix it with:
> ```bash
> pip uninstall fitz && pip install --upgrade pymupdf
> ```

---

## 🖥️ Usage

### Convert every PDF in the current folder

```bash
python pdf_to_md.py
```

### Convert a single file

```bash
python pdf_to_md.py paper.pdf
```

### Convert multiple specific files

```bash
python pdf_to_md.py chapter1.pdf chapter2.pdf appendix.pdf
```

### Convert all PDFs inside a folder

```bash
python pdf_to_md.py ./my_papers/
```

Each PDF produces a sibling `.md` file with the same name:

```
paper.pdf  →  paper.md
```

The terminal prints a one-liner per file showing how many characters were written:

```
Converting: paper.pdf ... done → paper.md  (42,317 chars)
```

---

## 📂 Output format

Each converted file looks like this:

```markdown
<!-- page 1 -->

# Introduction

This is body text on page 1.

---

<!-- page 2 -->

## 1.1 Background

Some inline math: $\alpha \leq \beta$

$$
\int_{0}^{\infty} e^{-x^{2}} \, dx = \frac{\sqrt{\pi}}{2}
$$

> **Theorem 1.** *Every continuous function on a compact set attains its maximum.*

*Proof.* ...
```

- Pages are delimited by `<!-- page N -->` HTML comments and `---` horizontal rules, so you can split or process them programmatically if needed.
- Math is rendered by any Markdown viewer that supports KaTeX or MathJax (GitHub, Obsidian, Typora, VS Code with a math extension, Jupyter, etc.).

---

## ⚙️ How it works (technical)

1. **Structured text extraction** — `page.get_text("dict")` from PyMuPDF returns every text span with its font name, font size, flags (bold/italic), and the exact *y*-coordinate of each glyph's origin. Raw text-only extraction is never used.

2. **Math detection** — a span is classified as math if its font name contains a known math-font keyword (`cmmi`, `cmsy`, `stix`, `mathbb`, …) *or* if any character falls in a Unicode math block (Greek, Mathematical Operators, Letterlike Symbols, Mathematical Alphanumerics, etc.).

3. **LaTeX conversion** — math spans are passed through a ~150-entry lookup table (`U2L`) that maps Unicode code points to LaTeX macros. Vertical glyph displacement relative to the previous span is used to infer `^{...}` (superscript) and `_{...}` (subscript).

4. **Block classification** — after per-span processing, each text block is classified:
   - by *font size* relative to the page median → `#` / `##` headings
   - by *horizontal centering* + *block width* → display equation `$$...$$`
   - by *regex on the text* → theorems, definitions, proofs
   - by *bold flag* + *short word count* → bold label

5. **Page assembly** — blocks are joined and wrapped with page markers; pages are joined with `---`.

---

## 🗺️ Supported symbol categories

| Category | Examples |
|---|---|
| Greek lowercase | `α β γ δ ε ζ η θ ι κ λ μ ν ξ π ρ σ τ υ φ χ ψ ω` |
| Greek uppercase | `Γ Δ Θ Λ Ξ Π Σ Υ Φ Ψ Ω` |
| Operators | `± × ÷ · ∑ ∏ ∫ ∮ ∂ ∇ ∞ √` |
| Relations | `≤ ≥ ≠ ≈ ≡ ≅ ≃ ∼ ≪ ≫ ⊂ ⊃ ∈ ∉ ⊥ ∥` |
| Logic / sets | `∀ ∃ ¬ ∧ ∨ ⊕ ⊗ ∅ ∪ ∩` |
| Arrows | `→ ← ↔ ⇒ ⇐ ⇔ ⟹ ⟺ ↦` |
| Blackboard bold | `ℝ ℤ ℕ ℚ ℂ ℙ` |
| Brackets | `⟨ ⟩ ⌈ ⌉ ⌊ ⌋` |
| Dots | `… ⋯ ⋮ ⋱` |
| Super/subscript digits | `⁰¹²³…` → `^{0}^{1}^{2}^{3}…` |

---

## ⚠️ Known limitations

- **Images and figures** are not extracted (PyMuPDF can do this, but it is out of scope here).
- **Tables** are not reconstructed — table cells appear as sequential text blocks.
- **Complex nested fractions** (`\frac{a}{b}`) are not inferred; the numerator and denominator will appear as separate lines.
- **Scanned PDFs** (image-only, no text layer) will produce empty output. Run OCR first (e.g. `ocrmypdf`) to add a text layer before converting.
- Results vary by PDF quality. Professionally typeset papers (LaTeX-generated PDFs) convert very well; older or scanned-and-OCR'd PDFs may need manual cleanup.

---

## 📝 License

See [`LICENSE`](LICENSE).
