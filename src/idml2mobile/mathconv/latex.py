"""Best-effort conversion of IDML text runs into KaTeX-compatible LaTeX.

This is deliberately conservative: it only emits LaTeX when it is confident the
result is safe. Anything ambiguous is left as text (or, upstream, kept as the
original math image), because a wrong equation is worse than a picture of one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from idml2mobile.parsers.base import RawRun

# Unicode math symbols -> LaTeX commands
_SYMBOL_MAP = {
    "×": r"\times", "÷": r"\div", "±": r"\pm", "∓": r"\mp",
    "≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "≈": r"\approx",
    "→": r"\rightarrow", "←": r"\leftarrow", "⇌": r"\rightleftharpoons",
    "⇋": r"\rightleftharpoons", "↔": r"\leftrightarrow",
    "∞": r"\infty", "√": r"\sqrt{}", "∑": r"\sum", "∏": r"\prod",
    "∫": r"\int", "∂": r"\partial", "∆": r"\Delta", "∇": r"\nabla",
    "°": r"^{\circ}", "·": r"\cdot", "∈": r"\in", "∉": r"\notin",
    "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta",
    "ε": r"\epsilon", "θ": r"\theta", "λ": r"\lambda", "μ": r"\mu",
    "π": r"\pi", "ρ": r"\rho", "σ": r"\sigma", "τ": r"\tau",
    "φ": r"\phi", "ω": r"\omega", "Ω": r"\Omega", "Σ": r"\Sigma",
}

_MATH_HINT_RE = re.compile(
    r"[=<>≤≥≠≈+×÷±√∑∫∞→⇌]|\b\d+\s*/\s*\d+\b|\^|_\{|\\frac"
)


@dataclass
class MathConversion:
    latex: str
    display: bool
    confident: bool


def looks_like_math(text: str) -> bool:
    """Heuristic: does this string plausibly contain an equation?"""
    if not text or not text.strip():
        return False
    if _MATH_HINT_RE.search(text):
        # avoid flagging prose that merely contains a hyphen or plain number
        symbols = sum(1 for c in text if c in "=<>≤≥≠≈×÷±√∑∫→⇌^")
        return symbols >= 1
    return False


def fix_scripts(runs: List[RawRun]) -> str:
    """Rebuild sub/superscripts from run metadata into LaTeX ^{} / _{}."""
    out: List[str] = []
    for run in runs:
        token = _escape_symbols(run.text)
        if run.superscript:
            out.append("^{%s}" % token.strip())
        elif run.subscript:
            out.append("_{%s}" % token.strip())
        else:
            out.append(token)
    return "".join(out)


def _escape_symbols(text: str) -> str:
    for uni, cmd in _SYMBOL_MAP.items():
        text = text.replace(uni, cmd + " " if cmd[0] == "\\" else cmd)
    return text


def to_katex_latex(runs: List[RawRun], display: bool = True) -> Optional[MathConversion]:
    """Convert a run sequence to LaTeX if we are confident it is safe."""
    raw_text = "".join(r.text for r in runs)
    has_scripts = any(r.superscript or r.subscript for r in runs)
    if not (looks_like_math(raw_text) or has_scripts):
        return None

    latex = fix_scripts(runs)
    # simple a/b fractions -> \frac{a}{b} when both sides are short tokens
    latex = re.sub(r"(?<![\d)])\b(\d+)\s*/\s*(\d+)\b", r"\\frac{\1}{\2}", latex)
    latex = _collapse_spaces(latex)

    # Confidence gate: reject if unbalanced braces or leftover odd unicode.
    confident = latex.count("{") == latex.count("}") and not re.search(
        r"[^\x00-\x7f]", latex.replace("\\", "")
    )
    return MathConversion(latex=latex.strip(), display=display, confident=confident)


def _collapse_spaces(s: str) -> str:
    return re.sub(r"[ ]{2,}", " ", s).strip()
