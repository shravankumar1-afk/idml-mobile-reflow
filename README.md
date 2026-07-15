# idml2mobile

Convert a **double-column IDML / InDesign package** into a **single-column,
mobile-friendly PDF** that opens on any phone with **no horizontal scrolling**.

The tool unpacks the IDML, reconstructs the reading order across threaded and
double-column frames, reflows everything into one narrow column, converts
unsupported link assets (EPS/WMF/TIF/CDR) to web-safe PNG, preserves math
(as readable text with real sub/superscripts, or the original equation image ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â never raw LaTeX), and renders a
fixed **360 px-wide** mobile PDF with Playwright Chromium ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â then runs QA.

```
convert  ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢  index.html + css/ + images/ + fonts/ + mobile.pdf + qa-report.json
```

---

## Mobile PDF contract

| Property | Value |
|---|---|
| Page width | **360 CSS px** (~3.75 in @ 96 dpi) |
| Page height | 780 px fixed, or auto-paginated (default) |
| Margin | 16 px |
| Safe content width | **328 px** |
| Body font | 15ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“16 px (min 13 px) |
| Line height | 1.45ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“1.6 |
| Columns | **single column only** |
| Images | `max-width: 100%`, never cropped |
| Overflow | none horizontally |
| Math | Editable local KaTeX with `data-latex`, or an original equation fallback image |

---

## Quick start for users

### Windows desktop app

1. Install Python 3.9 or newer.
2. Download the repository from **Code Ã¢â€ â€™ Download ZIP**, or clone it:

```powershell
git clone https://github.com/shravankumar1-afk/idml-mobile-reflow.git
cd idml-mobile-reflow
python -m pip install -e ".[dev]"
playwright install chromium
```

3. Launch the GUI:

```powershell
idml2mobile-gui
```

Choose the IDML package folder (or `.idml` file), select a separate output folder, keep **reflow (editable)** selected, and click **Convert**. The output package contains `index.html`, `mobile.pdf`, `css/`, `js/`, `images/`, `fonts/`, `katex/`, `qa-report.json`, and `stats.json`.

### Command line

```powershell
idml2mobile convert "C:\path\to\book-folder" --out "C:\path\to\mobile-output" --mode reflow
```

Use `--no-pdf` when only HTML/QA output is needed. Use `--mode facsimile` for page-faithful image output when text editability is not required.

### Preview the HTML locally

```powershell
cd C:\path\to\mobile-output
python -m http.server 8000
```

Open `http://localhost:8000` in a browser.
## Install

```bash
pip install idml2mobile
playwright install chromium      # one-time, for PDF rendering
```

From source:

```bash
git clone https://github.com/shravankumar1-afk/idml-mobile-reflow
cd idml2mobile
pip install -e ".[dev]"
playwright install chromium
```

**Optional external converters** (only needed for EPS / CDR / AI):
- **Ghostscript** ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â lets Pillow rasterize EPS.
- **ImageMagick** (`magick`) or **Inkscape** ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â fallback for vector formats.

WMF/EMF equations convert natively via Pillow on Windows; elsewhere they use
ImageMagick/Inkscape. Anything that cannot be converted is reported in
`qa-report.json` and rendered with a visible placeholder (never silently dropped).

---

## Desktop app (Windows)

Prefer a double-click? After installing, create a Desktop shortcut with an icon:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1
```

This adds **ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œIDML to Mobile PDFÃƒÂ¢Ã¢â€šÂ¬Ã‚Â** to your Desktop. Double-click it to open a
small window: pick the input `.idml`/package folder and an output folder, choose
options (reading order, render PDF, embed fonts), and click **Convert**. Progress
streams into the log and the output folder opens when it finishes.

You can also launch the GUI directly:

```bash
idml2mobile-gui
```

## CLI

```bash
# Convert one package (a folder or a bare .idml)
idml2mobile convert "01_Solution Folder" --out output/

# Two output styles:
#   --mode reflow     (default) single-column, selectable, mobile-readable text
#   --mode facsimile  each source page rendered 1:1 to mobile width ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â a 100%
#                     visual match to the source (all images/fonts/boxes), but
#                     the text is an image (not selectable) and smaller.
idml2mobile convert "01_Solution Folder" --out facsimile/ --mode facsimile

# Inspect structure without converting (add --json for machine output)
idml2mobile inspect "01_Solution Folder"

# Run QA against an existing output folder
idml2mobile validate output/

# Convert every IDML package found under a root
idml2mobile batch input-root/ --out output-root/
```

Useful `convert` flags:

| Flag | Purpose |
|---|---|
| `--strategy {auto,threaded,geometric,story_order}` | reading-order reconstruction |
| `--no-pdf` | skip Playwright (HTML + QA only) |
| `--no-fonts` | do not embed `Document fonts/` |
| `--fixed-height` | fixed 780 px pages instead of auto-pagination |
| `--body-font 16 --margin 16 --page-width 360` | override the profile |
| `--keep-temp -v` | keep the unpacked IDML and log verbosely |

Exit codes: `0` success Ãƒâ€šÃ‚Â· `2` completed but QA flagged errors Ãƒâ€šÃ‚Â· `1` failure.

---

## Output

```
output/
ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ index.html          # mobile-first, single column
ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ css/styles.css       # generated from the mobile profile
ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ images/              # web-safe PNGs (converted from EPS/WMF/TIF/...)
ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ fonts/               # embedded Document fonts (if licensed)
ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ mobile.pdf           # 360 px-wide mobile PDF
ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ qa-report.json       # pass/fail per check
ÃƒÂ¢Ã¢â‚¬ÂÃ¢â‚¬ÂÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ stats.json           # time + tokens/words/pages/images processed
```

You can point the tool at **any folder** ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â if the `.idml` package sits in a
subfolder, it is found automatically. Each run reports elapsed **time** and an
estimate of the **tokens** (text volume) processed. The conversion is fully
offline, so "tokens" is an estimate of processed text (~4 chars/token), not LLM
usage.

---

## Architecture

A single **Facade** (`ConversionPipeline`) orchestrates small, swappable
components. Content and rendering sit on opposite sides of a **Bridge**, so the
same content model can target HTML, PDF, or a future format.

```
CLI (Command)                 observers/ (Observer: progress + logging)
   ÃƒÂ¢Ã¢â‚¬ÂÃ¢â‚¬Å¡
   ÃƒÂ¢Ã¢â‚¬â€œÃ‚Â¼
ConversionPipeline (Facade)
   ÃƒÂ¢Ã¢â‚¬ÂÃ¢â‚¬Å¡
   ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ InputValidator ............ detect .idml / Links / fonts / missing refs
   ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ IDMLPackage ............... unzip, expose designmap / Stories / Spreads
   ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ ParserFactory ............. StoryParser Ãƒâ€šÃ‚Â· SpreadParser Ãƒâ€šÃ‚Â· ResourceParser
   ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ IDMLAdapter (Adapter) ..... raw IDML records ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ semantic blocks
   ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ ReadingOrderStrategy ...... threaded | geometric | story_order | auto
   ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ CleanupChain (CoR) ........ normalize Ãƒâ€šÃ‚Â· merge Ãƒâ€šÃ‚Â· drop-empty Ãƒâ€šÃ‚Â· dedup
   ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ DocumentBuilder (Builder) . blocks ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ Document > Section > Block (Composite)
   ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ AssetRepository (Repository) locate + convert links, cache, track origin
   ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ RendererFactory ........... HTMLRenderer / PDFRenderer (Template Method)
   ÃƒÂ¢Ã¢â‚¬ÂÃ¢â‚¬Å¡     ÃƒÂ¢Ã¢â‚¬ÂÃ¢â‚¬ÂÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ StyleBuilder (Builder) mobile CSS from MobileProfile
   ÃƒÂ¢Ã¢â‚¬ÂÃ¢â‚¬ÂÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ QAValidator ............... static + rendered-DOM checks ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ qa-report.json
```

### Design-pattern map

| Pattern | Where |
|---|---|
| **Facade** | `ConversionPipeline` |
| **Adapter** | `IDMLAdapter` (IDML XML ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ internal model) |
| **Composite** | `Document > Section > Block` (`model/blocks.py`) |
| **Repository** | `AssetRepository` |
| **Bridge** | content model (`model/`) decoupled from renderers (`render/`) |
| **Factory** | `ParserFactory`, `RendererFactory` |
| **Builder** | `DocumentBuilder`, `StyleBuilder` |
| **Strategy** | reading-order strategies (`reading_order/`) |
| **Chain of Responsibility** | cleanup passes (`cleanup/`) |
| **Command** | CLI verbs (`commands/`) |
| **Observer** | progress/logging (`observers/`) |
| **Template Method** | base renderer flow (`render/base.py`) |

---

## How it handles real InDesign quirks

- **Threaded + double-column frames** are resolved by absolute frame geometry
  (`ItemTransform` applied to `GeometricBounds`), ordered page ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ left column ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢
  right column ÃƒÂ¢Ã¢â‚¬Â Ã¢â‚¬â„¢ top-to-bottom, with each story emitted once even when it spans
  many frames.
- **Anchored equations** (MathType exports as inline WMF/EPS inside the story)
  are kept **inline, in place** ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â converted to PNG and constrained to the safe
  width so they never clip. Image-only equation paragraphs become centered
  display blocks.
- **Broken paragraphs** split across frames are re-joined by the cleanup chain.
- **Missing links / fonts** are surfaced by `inspect` and `qa-report.json`
  rather than failing silently.

---

## Repository layout

```
idml2mobile/
ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ pyproject.toml
ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ README.md Ãƒâ€šÃ‚Â· LICENSE Ãƒâ€šÃ‚Â· .gitignore
ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ .github/workflows/ci.yml
ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ src/idml2mobile/
ÃƒÂ¢Ã¢â‚¬ÂÃ¢â‚¬Å¡  ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ cli.py Ãƒâ€šÃ‚Â· config.py Ãƒâ€šÃ‚Â· pipeline.py
ÃƒÂ¢Ã¢â‚¬ÂÃ¢â‚¬Å¡  ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ observers/ Ãƒâ€šÃ‚Â· commands/ Ãƒâ€šÃ‚Â· idml/ Ãƒâ€šÃ‚Â· parsers/ Ãƒâ€šÃ‚Â· model/
ÃƒÂ¢Ã¢â‚¬ÂÃ¢â‚¬Å¡  ÃƒÂ¢Ã¢â‚¬ÂÃ…â€œÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ reading_order/ Ãƒâ€šÃ‚Â· cleanup/ Ãƒâ€šÃ‚Â· mathconv/ Ãƒâ€šÃ‚Â· assets/ Ãƒâ€šÃ‚Â· render/ Ãƒâ€šÃ‚Â· qa/
ÃƒÂ¢Ã¢â‚¬ÂÃ¢â‚¬ÂÃƒÂ¢Ã¢â‚¬ÂÃ¢â€šÂ¬ tests/
```

---

## Development

```bash
pip install -e ".[dev]"
pytest            # unit + end-to-end (synthetic IDML fixture, no PDF)
ruff check .
```

The test suite builds a tiny synthetic IDML in-memory, so it runs fast and does
not require the multi-MB sample or Chromium.

## License

MIT ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â see [LICENSE](LICENSE). Embedding fonts from `Document fonts/` is gated by
`--no-fonts`; you are responsible for honoring each font's license.


