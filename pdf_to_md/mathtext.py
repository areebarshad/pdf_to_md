"""Math font/character detection and Unicode → LaTeX conversion."""
from __future__ import annotations

import re
from .symbols import FUNCS, MATH_FONT_KWDS, MATH_RANGES, U2L

# Characters that need escaping in Markdown body text (not inside math)
_MD_ESCAPE = re.compile(r"([*_#\[\]\\`|])")


def is_math_font(name: str) -> bool:
    n = name.lower()
    return any(k in n for k in MATH_FONT_KWDS)


def has_math_chars(text: str) -> bool:
    for ch in text:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in MATH_RANGES):
            return True
    return False


def to_latex(text: str, unmapped: dict[str, int] | None = None) -> str:
    """Convert text to LaTeX, optionally recording unmapped code points."""
    parts: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in U2L:
            parts.append(U2L[ch])
        else:
            # Check if this is an upright multi-letter run that's a known function
            if ch.isalpha():
                j = i + 1
                while j < len(text) and text[j].isalpha():
                    j += 1
                word = text[i:j]
                if word in FUNCS:
                    parts.append(f"\\{word}")
                    i = j
                    continue
                else:
                    parts.append(ch)
            else:
                if unmapped is not None and ord(ch) > 127:
                    unmapped[ch] = unmapped.get(ch, 0) + 1
                parts.append(ch)
        i += 1
    return "".join(parts)


def escape_markdown(text: str) -> str:
    """Escape Markdown special characters in plain body text."""
    return _MD_ESCAPE.sub(r"\\\1", text)
