"""Extract embedded MathType MathML from WMF and convert it to KaTeX LaTeX."""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Optional

from lxml import etree

_MATHML_RE = re.compile(br"(<math\b.*?</math>)", re.DOTALL)
_SPACE_RE = re.compile(r"\s+")
_OPERATORS = {
    "\u2212": "-", "\u2013": "-", "\u00d7": r"\times ", "\u00f7": r"\div ",
    "\u00b1": r"\pm ", "\u2213": r"\mp ", "\u2264": r"\leq ", "\u2265": r"\geq ",
    "\u2260": r"\neq ", "\u2248": r"\approx ", "\u2192": r"\rightarrow ",
    "\u2190": r"\leftarrow ", "\u2194": r"\leftrightarrow ", "\u21cc": r"\rightleftharpoons ",
    "\u21d2": r"\Rightarrow ", "\u221d": r"\propto ", "\u221e": r"\infty ",
    "\u2211": r"\sum ", "\u220f": r"\prod ", "\u222b": r"\int ", "\u2234": r"\therefore ",
    "\u2206": r"\Delta ", "\u0394": r"\Delta ", "\u03c0": r"\pi ", "\u03b1": r"\alpha ",
    "\u03b2": r"\beta ", "\u03b3": r"\gamma ", "\u03b8": r"\theta ", "\u03bb": r"\lambda ",
    "\u03bc": r"\mu ", "\u03c1": r"\rho ", "\u03c3": r"\sigma ", "\u03c9": r"\omega ",
    "\u00b0": r"^{\circ}", "\u00b7": r"\cdot ", "\u22c5": r"\cdot ",
    "\u2032": "'", "\u2033": "''",
}


def extract_mathtype_latex(path: Path) -> Optional[str]:
    """Return lossless LaTeX from a MathType WMF, or None if absent."""
    try:
        match = _MATHML_RE.search(Path(path).read_bytes())
        if not match:
            return None
        latex = _node(etree.fromstring(match.group(1)))
        return _SPACE_RE.sub(" ", latex).strip()
    except (OSError, etree.XMLSyntaxError, ValueError):
        return None


def _text(value: str) -> str:
    value = html.unescape(value or "").replace("\u2009", " ").replace("\u00a0", " ")
    out = []
    for char in value:
        if char in _OPERATORS:
            out.append(_OPERATORS[char])
        elif char in "#%&_{}$":
            out.append("\\" + char)
        else:
            out.append(char)
    return "".join(out)


def _node(node) -> str:
    tag = etree.QName(node).localname
    kids = list(node)
    content = "".join(_node(child) for child in kids)
    own = _text(node.text or "")
    if tag in {"math", "mrow", "mstyle", "mprescripts"}:
        return own + content
    if tag in {"mi", "mn", "mo"}:
        return own + content
    if tag == "mtext":
        raw = html.unescape(node.text or "")
        if raw and not raw.strip():
            # Ordinary whitespace is ignored in TeX math mode. MathType uses
            # U+2009 mtext nodes as semantic word separators, so preserve each
            # one as an explicit thin space instead of emitting a plain space.
            return "".join(r"\," if ch == "\u2009" else r"\ " for ch in raw)
        value = own + content
        return r"\text{" + value.strip() + "}" if value.strip() else ""
    if tag == "mfrac" and len(kids) >= 2:
        return r"\frac{" + _node(kids[0]) + "}{" + _node(kids[1]) + "}"
    if tag == "msqrt":
        return r"\sqrt{" + content + "}"
    if tag == "msub" and len(kids) >= 2:
        return "{" + _node(kids[0]) + "}_{" + _node(kids[1]) + "}"
    if tag == "msup" and len(kids) >= 2:
        return "{" + _node(kids[0]) + "}^{" + _node(kids[1]) + "}"
    if tag == "msubsup" and len(kids) >= 3:
        return "{" + _node(kids[0]) + "}_{" + _node(kids[1]) + "}^{" + _node(kids[2]) + "}"
    if tag == "mover" and len(kids) >= 2:
        accent = _node(kids[1]).strip()
        if accent in {"-", "¯"}:
            return r"\bar{" + _node(kids[0]) + "}"
        return r"\overset{" + accent + "}{" + _node(kids[0]) + "}"
    if tag == "munder" and len(kids) >= 2:
        return r"\underset{" + _node(kids[1]) + "}{" + _node(kids[0]) + "}"
    if tag == "munderover" and len(kids) >= 3:
        return r"\mathop{" + _node(kids[0]) + "}_{" + _node(kids[1]) + "}^{" + _node(kids[2]) + "}"
    if tag == "mfenced":
        left, right = node.get("open", "("), node.get("close", ")")
        left = r"\{" if left == "{" else r"\}" if left == "}" else left or "."
        right = r"\{" if right == "{" else r"\}" if right == "}" else right or "."
        return r"\left" + left + content + r"\right" + right
    if tag == "mtable":
        rows = [r for r in kids if etree.QName(r).localname == "mtr"]
        return r"\begin{aligned}" + r"\\".join(_node(r) for r in rows) + r"\end{aligned}"
    if tag == "mtr":
        return " & ".join(_node(c) for c in kids)
    if tag == "mtd":
        return content
    if tag == "menclose":
        return r"\boxed{" + content + "}" if "box" in node.get("notation", "") else content
    if tag == "mmultiscripts" and kids:
        base = _node(kids[0])
        rest = [k for k in kids[1:] if etree.QName(k).localname != "mprescripts"]
        scripts = ""
        for i in range(0, len(rest), 2):
            sub = _node(rest[i]) if i < len(rest) else ""
            sup = _node(rest[i + 1]) if i + 1 < len(rest) else ""
            if sub:
                scripts += "_{" + sub + "}"
            if sup:
                scripts += "^{" + sup + "}"
        return ("{" + base + "}" if base else "") + scripts
    return own + content

