"""Unicode → LaTeX symbol tables and math font/range constants."""
from __future__ import annotations

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

MATH_FONT_KWDS: tuple[str, ...] = (
    "cmmi", "cmsy", "cmex", "cmr", "cmbx", "cmtt", "cmsl",
    "msam", "msbm",
    "stix", "xits", "libertinusmath",
    "mathit", "mathbf", "mathrm", "mathcal", "mathbb",
    "symbol", "zapfding", "mt extra",
)

MATH_RANGES: tuple[tuple[int, int], ...] = (
    (0x0391, 0x03C9),
    (0x2100, 0x214F),
    (0x2190, 0x21FF),
    (0x2200, 0x22FF),
    (0x27C0, 0x27EF),
    (0x2900, 0x29FF),
    (0x2A00, 0x2AFF),
    (0x1D400, 0x1D7FF),
)

# Known math function names → produce \name in LaTeX
FUNCS: frozenset[str] = frozenset({
    "sin", "cos", "tan", "cot", "sec", "csc",
    "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh",
    "log", "ln", "exp",
    "lim", "sup", "inf", "max", "min",
    "det", "dim", "ker", "rank", "tr", "sgn",
    "gcd", "lcm", "mod", "deg",
    "Re", "Im",
    "Pr", "prob",
})

# Ligature normalization map
LIGATURES: dict[str, str] = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    "­": "",   # soft hyphen
    " ": " ",  # NBSP
    "‘": "'", "’": "'",  # smart single quotes
    "“": '"', "”": '"',  # smart double quotes
    "–": "--", "—": "---",  # en/em dash
}


# TeX/LaTeX T1 (Cork) encoding control-character maps.
# \x1b-\x1f are the T1 ligature block; \x10/\x11 dotless letters;
# \x16 is T1 em-dash (advance ~1.079 em); \x88 is the T1 bullet glyph.
TEX_CTRL: dict[str, str] = {
    "\x1b": "ff", "\x1c": "fi", "\x1d": "fl", "\x1e": "ffi", "\x1f": "ffl",
    "\x10": "i", "\x11": "j",
    "\x16": "\u2014", "\x88": "\u2022",
}

# OT1 ligature block -- \x0b-\x0f collide with form-feed/CR so these must only
# be substituted when surrounded by letters (see normalize_text in layout.py).
TEX_CTRL_OT1: dict[str, str] = {
    "\x0b": "ff", "\x0c": "fi", "\x0d": "fl", "\x0e": "ffi", "\x0f": "ffl",
}
