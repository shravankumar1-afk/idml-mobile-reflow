"""StyleBuilder — assembles the mobile-first stylesheet from the profile.

Builder pattern: chainable `.with_*` calls accumulate CSS fragments; `.build()`
emits the final stylesheet. Everything is derived from MobileProfile so the
360px page contract is enforced in exactly one place.
"""
from __future__ import annotations

from typing import List, Tuple

from idml2mobile.config import MobileProfile


class StyleBuilder:
    def __init__(self, profile: MobileProfile) -> None:
        self.profile = profile
        self._font_faces: List[str] = []
        self._extra: List[str] = []

    def with_font(self, family: str, rel_path: str, weight: str = "normal",
                  style: str = "normal") -> "StyleBuilder":
        self._font_faces.append(
            "@font-face{"
            f"font-family:'{family}';"
            f"src:url('{rel_path}');"
            f"font-weight:{weight};font-style:{style};font-display:swap;"
            "}"
        )
        return self

    def with_fonts(self, faces: List[Tuple[str, str, str, str]]) -> "StyleBuilder":
        for family, rel_path, weight, style in faces:
            self.with_font(family, rel_path, weight, style)
        return self

    def with_extra(self, css: str) -> "StyleBuilder":
        self._extra.append(css)
        return self

    def build(self) -> str:
        p = self.profile
        # Margin is handled by body padding so the page background reaches the
        # very edge (blue frame like the source), so @page margin is 0.
        page_rule = (
            f"@page{{size:{p.width_in:.4f}in {p.height_in:.4f}in;margin:0;}}"
            if not p.paginated
            else f"@page{{size:{p.width_in:.4f}in auto;margin:0;}}"
        )
        fonts = "\n".join(self._font_faces)
        extra = "\n".join(self._extra)
        return f"""{fonts}
:root{{
  --page-w:{p.page_width}px;
  --safe-w:{p.safe_content_width}px;
  --margin:{p.margin}px;
  --body:{p.body_font_px}px;
  --min:{p.min_font_px}px;
  --lh:{p.line_height};
  --ink:#1a1a1a;
  --brand:#1f6fb2;
  --brand-dark:#123a63;
  --accent-bg:#dcebf7;
  --rule:#b9d4ea;
}}
{page_rule}
*{{box-sizing:border-box;}}
html,body{{margin:0;padding:0;}}
body{{
  width:var(--page-w);
  max-width:100%;
  margin:0 auto;
  padding:var(--margin);
  background:#e6eef8;                 /* page background echoes the source */
  font-family:'BodySerif','Georgia','Times New Roman',serif;
  font-size:var(--body);
  line-height:var(--lh);
  color:var(--ink);
  -webkit-text-size-adjust:100%;
  overflow-x:hidden;
  word-wrap:break-word;
  overflow-wrap:anywhere;
}}
.doc{{
  width:100%;
  background:#ffffff;
  border:1px solid #cfe0f2;
  border-radius:8px;
  padding:12px 12px;
}}
.doc-title{{
  font-family:'HeadingSans','Helvetica Neue',Arial,sans-serif;
  font-size:24px;font-weight:800;letter-spacing:0.5px;text-transform:uppercase;
  color:var(--brand-dark);text-align:center;margin:0.1em 0 0.5em;
  padding-bottom:6px;border-bottom:3px solid var(--brand);
}}
h1,h2,h3{{line-height:1.25;margin:0.7em 0 0.4em;break-after:avoid;page-break-after:avoid;
  font-family:'HeadingSans','Helvetica Neue',Arial,sans-serif;}}
h1.chapter-title{{font-size:22px;font-weight:800;color:var(--brand-dark);
  border-bottom:2px solid var(--brand);padding-bottom:4px;}}
h2.heading{{font-size:17px;font-weight:700;color:var(--brand-dark);
  background:var(--accent-bg);border-left:4px solid var(--brand);
  padding:6px 10px;border-radius:4px;}}
/* Sub-heading: deliberately DIFFERENT size + colour from the main heading (per
   faculty note) — smaller, teal, lighter tinted bar, no heavy blue box. */
h3.subhead{{font-size:14.5px;font-weight:700;color:#0f7d86;
  background:#e7f6f7;border-left:3px solid #14a3ad;
  padding:4px 9px;border-radius:3px;margin:0.7em 0 0.3em;letter-spacing:0.2px;}}
/* Key-note / callout header + its bordered box (orange, like the source). */
.callout-head{{background:#f6a02a;color:#fff;
  font-family:'HeadingSans','Helvetica Neue',Arial,sans-serif;font-weight:700;font-size:14px;
  padding:5px 12px;border-radius:14px;display:inline-block;margin:0.8em 0 0;
  box-shadow:0 1px 2px rgba(0,0,0,0.2);}}
.callout-head.kn{{background:var(--brand-dark);border-radius:6px;}}   /* Key Note = navy */
/* Question-section header bar (dark blue, white text), like the source. */
.qsection-head{{background:var(--brand-dark);color:#fff;
  font-family:'HeadingSans','Helvetica Neue',Arial,sans-serif;font-weight:700;font-size:15px;
  letter-spacing:0.3px;padding:7px 12px;border-radius:4px;margin:0.9em 0 0;}}
/* Anchored callout/key-note boxes (recovered from anchored text frames). */
.box.anchored{{border:1.5px solid #eab35a;background:#fff8ec;border-radius:8px;
  padding:8px 11px;margin:0.5em 0;break-inside:avoid;}}
.box.anchored .callout-head{{margin-top:0;}}
/* Worked-example box (question + Ex-N ribbon + solution), like the source. */
.box.example{{border:1.5px solid #e0b070;background:#fff8ee;border-radius:8px;
  padding:8px 11px 9px;margin:0.7em 0;break-inside:avoid;position:relative;}}
.ex-ribbon{{display:inline-block;background:var(--brand-dark);color:#fff;
  font-family:'HeadingSans','Helvetica Neue',Arial,sans-serif;font-weight:700;font-size:12.5px;
  letter-spacing:0.3px;padding:3px 12px;border-radius:5px;margin:0 0 6px;
  box-shadow:0 1px 2px rgba(0,0,0,0.15);}}
.box.example paragraph{{margin:0.25em 0;}}
.box paragraph,.box .option,.box .question{{text-align:left;}}
paragraph{{display:block;margin:0 0 0.6em;font-size:var(--body);text-align:justify;hyphens:auto;-webkit-hyphens:auto;}}
paragraph.small,.option{{font-size:14px;}}
/* Bullet lists (source "Bullets"/"Key Bullet" styles). */
ul.bullets{{margin:0.35em 0 0.6em;padding-left:1.25em;list-style:none;}}
ul.bullets>li{{position:relative;margin:0.2em 0;text-align:left;padding-left:0.1em;}}
ul.bullets>li::before{{content:"\\25B8";color:var(--brand);position:absolute;
  left:-0.95em;font-size:0.95em;top:0.02em;}}
/* Indented sub-points under a bullet ("(a) ...", "(i) ..."). */
paragraph.subpoint{{margin:0.15em 0 0.15em 1.4em;text-align:left;}}
paragraph.caption{{font-size:12.5px;color:#555;text-align:center;font-style:italic;margin:0.3em 0 0.6em;}}
.chapter-title-plain{{text-align:left;}}
.question{{font-weight:600;margin:0.9em 0 0.2em;text-align:left;}}
.qcont{{margin:0.05em 0 0.35em;text-align:left;}}   /* verse/answer continuation line */
.question .qnum{{color:var(--brand);font-weight:700;}}
.sublabel{{color:#e8912a;font-weight:800;font-size:15px;margin:0.3em 0 0.2em;
  font-family:'HeadingSans','Helvetica Neue',Arial,sans-serif;}}
.option{{margin:0.1em 0 0.1em 1.3em;text-align:left;}}
.speaker{{color:var(--brand);font-weight:700;}}
.example{{background:#eef4fb;border-left:3px solid var(--brand);padding:8px 10px;margin:0.6em 0;border-radius:6px;}}
.solution{{border-left:3px solid #2e9e5b;padding:6px 10px;margin:0.5em 0;background:#eef9f1;border-radius:6px;}}
/* Key-note / callout boxes use the source's orange highlight styling. */
.note{{background:#fff4e0;border:1px solid #f0c479;border-left:4px solid #e8912a;
  padding:8px 10px;border-radius:6px;margin:0.6em 0;font-size:14px;color:#5b3b12;}}
sup,sub{{font-size:75%;line-height:0;}}
/* Equation images (MathType WMF) are sized by physical height via an inline
   max-height (see renderer); these are safety caps that preserve aspect ratio. */
img.inline-eqn{{max-width:100%;max-height:2.4em;width:auto;height:auto;vertical-align:middle;margin:0 2px;}}
img.block-eqn{{display:block;max-width:100%;width:auto;height:auto;margin:0.3em auto;}}
.missing-inline{{color:#b30000;font-size:12px;border:1px dotted #b30000;padding:0 2px;border-radius:3px;}}
figure{{margin:0.8em 0;text-align:center;break-inside:avoid;page-break-inside:avoid;}}
figure img{{max-width:100%;height:auto;display:block;margin:0 auto;
  border:1px solid #e3e8ee;border-radius:6px;}}
figure.opener img{{border:0;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,0.15);}}
figure.finisher img{{border:0;border-radius:0;box-shadow:none;}}
figure.math-display img{{border:0;}}
figcaption{{font-size:12px;color:#555;margin-top:3px;}}
.math-display{{overflow-x:auto;overflow-y:hidden;max-width:100%;margin:0.6em 0;text-align:center;break-inside:avoid;}}
/* Inline equations that are tall (fractions/stacked) read better on their own line. */
.math-inline-block{{display:block;text-align:center;margin:0.35em 0;overflow-x:auto;overflow-y:hidden;max-width:100%;}}
.math-cont{{text-align:center;margin:0.1em 0 0.35em;}}
.katex-display{{margin:0.2em 0 !important;max-width:100%;overflow-x:auto;overflow-y:hidden;}}
.katex-display>.katex{{white-space:normal;max-width:100%;}}
.katex{{font-size:1.02em;max-width:100%;}}
/* KaTeX's clipped accessibility MathML remains available to assistive
   technology but must never expand Chromium's printable canvas. */
.katex .katex-mathml{{max-width:1px!important;max-height:1px!important;}}
.katex-error{{color:#b30000;}}
.missing-asset{{border:1px dashed #c33;color:#c33;padding:6px;font-size:12px;border-radius:4px;}}
.table-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0.6em 0;
  border:1px solid var(--rule);border-radius:6px;}}
/* Let columns size to their content and scroll horizontally when the table is
   wider than the page, instead of squeezing headers into "Sol ven t". */
table.tbl{{width:auto;min-width:100%;border-collapse:collapse;font-size:12.5px;
  table-layout:auto;}}
table.tbl td,table.tbl th{{border:1px solid #e0b070;padding:4px 7px;text-align:left;
  vertical-align:top;overflow-wrap:normal;word-break:normal;hyphens:none;
  -webkit-hyphens:none;}}
/* Title row (navy) and header row (orange), echoing the source table style. */
table.tbl tr:first-child td,table.tbl tr:first-child th{{background:var(--brand-dark);
  color:#fff;font-weight:700;text-align:center;}}
table.tbl tr:nth-child(2) td{{background:#e8912a;color:#fff;font-weight:700;text-align:center;}}
table.tbl tr:nth-child(n+3) td:first-child{{text-align:center;}}
table.tbl tr:nth-child(n+3):nth-child(even) td{{background:#fff6ea;}}
table.tbl tr:nth-child(n+3):nth-child(odd) td{{background:#fffdf9;}}
img,svg,figure,.math-display,table{{break-inside:avoid;page-break-inside:avoid;}}
{extra}
"""
