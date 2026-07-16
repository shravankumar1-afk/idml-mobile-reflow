"""Tiny desktop GUI launcher for idml2mobile.

Double-click target for the desktop shortcut: pick an input package (folder or
.idml) and an output folder, choose options, and Convert. The pipeline runs on
a worker thread; progress is streamed into the log via a thread-safe queue.
Pure standard library (Tkinter) so it needs no extra dependencies.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import (
    BooleanVar,
    StringVar,
    Tk,
    filedialog,
    messagebox,
)
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from idml2mobile.config import ConversionConfig, MobileProfile
from idml2mobile.observers.base import Event, Level
from idml2mobile.pipeline import ConversionPipeline

APP_TITLE = "IDML -> Mobile PDF"
STRATEGIES = ["auto", "threaded", "geometric", "story_order"]


class _QueueObserver:
    """Observer that forwards pipeline events onto a queue for the UI thread."""

    def __init__(self, q: "queue.Queue[Event]") -> None:
        self._q = q

    def notify(self, event: Event) -> None:
        self._q.put(event)


class App:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.events: "queue.Queue[Event]" = queue.Queue()
        self.worker: threading.Thread | None = None

        self.input_var = StringVar()
        self.input_type_var = StringVar(value="Auto detect")
        self.output_var = StringVar()
        # Source-faithful is the production default: it preserves every font,
        # box, diagram, equation, table and word from the print PDF. Semantic
        # reflow remains available when editable text is preferred.
        self.mode_var = StringVar(value="reflow (editable)")
        self.strategy_var = StringVar(value="auto")
        self.pdf_var = BooleanVar(value=True)
        self.fonts_var = BooleanVar(value=True)
        self.visuals_var = BooleanVar(value=True)
        self.open_var = BooleanVar(value=True)

        root.title(APP_TITLE)
        root.geometry("720x600")
        root.minsize(640, 480)
        self._build()
        self.root.after(120, self._drain)

    # -- layout ------------------------------------------------------------
    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Input type").grid(row=0, column=0, sticky="w", **pad)
        ttk.Combobox(frm, textvariable=self.input_type_var, values=["Auto detect", "IDML", "PDF"], state="readonly", width=12).grid(row=0, column=1, sticky="w", **pad)
        ttk.Label(frm, text="Input (.idml, PDF, or package folder)").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.input_var).grid(row=1, column=1, sticky="ew", **pad)
        btns = ttk.Frame(frm)
        btns.grid(row=1, column=2, sticky="e", **pad)
        ttk.Button(btns, text="Folder...", command=self._pick_input_folder).pack(side="left")
        ttk.Button(btns, text=".idml...", command=self._pick_input_file).pack(side="left", padx=(4, 0))
        ttk.Button(btns, text="PDF...", command=self._pick_input_pdf).pack(side="left", padx=(4, 0))

        ttk.Label(frm, text="Output folder").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.output_var).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse...", command=self._pick_output).grid(row=2, column=2, sticky="e", **pad)


        opts = ttk.LabelFrame(frm, text="Options", padding=8)
        opts.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)
        ttk.Label(opts, text="Mode").pack(side="left")
        ttk.Combobox(
            opts, textvariable=self.mode_var,
            values=["reflow (editable)", "source-faithful (reference)"],
            width=22, state="readonly",
        ).pack(side="left", padx=(4, 12))
        ttk.Label(opts, text="Reading order").pack(side="left")
        ttk.Combobox(
            opts, textvariable=self.strategy_var, values=STRATEGIES,
            width=11, state="readonly",
        ).pack(side="left", padx=(4, 12))
        ttk.Checkbutton(opts, text="Render PDF", variable=self.pdf_var).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="Embed fonts", variable=self.fonts_var).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="Recover graphics", variable=self.visuals_var).pack(side="left", padx=4)
        ttk.Checkbutton(opts, text="Open output when done", variable=self.open_var).pack(side="left", padx=4)

        actions = ttk.Frame(frm)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)
        self.convert_btn = ttk.Button(actions, text="Convert", command=self._start)
        self.convert_btn.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=220)
        self.progress.pack(side="left", padx=12)
        self.status = ttk.Label(actions, text="Ready")
        self.status.pack(side="left")

        ttk.Label(frm, text="Log").grid(row=5, column=0, sticky="w", **pad)
        self.log = ScrolledText(frm, height=16, wrap="word", state="disabled",
                                font=("Consolas", 9))
        self.log.grid(row=6, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(6, weight=1)

    # -- pickers -----------------------------------------------------------
    def _pick_input_folder(self) -> None:
        d = filedialog.askdirectory(title="Select the IDML package folder")
        if d:
            self.input_var.set(d)
            if not self.output_var.get():
                self.output_var.set(self._default_output(Path(d)))

    def _pick_input_pdf(self) -> None:
        f = filedialog.askopenfilename(title="Select a PDF", filetypes=[("PDF", "*.pdf"), ("All files", "*.*")])
        if f:
            self.input_var.set(f)
            self.input_type_var.set("PDF")
            if not self.output_var.get():
                self.output_var.set(self._default_output(Path(f)))

    def _pick_input_file(self) -> None:
        f = filedialog.askopenfilename(title="Select an .idml file",
                                       filetypes=[("IDML", "*.idml"), ("All files", "*.*")])
        if f:
            self.input_var.set(f)
            if not self.output_var.get():
                self.output_var.set(self._default_output(Path(f).parent))

    @staticmethod
    def _default_output(chosen: Path) -> str:
        # A sibling folder OUTSIDE the source, so output never mingles with the
        # .idml / Links / fonts.
        parent = chosen.parent if chosen.parent != chosen else chosen
        return str(parent / f"{chosen.name} - mobile output")

    def _pick_output(self) -> None:
        d = filedialog.askdirectory(title="Select the output folder")
        if d:
            self.output_var.set(d)

    # -- run ---------------------------------------------------------------
    def _start(self) -> None:
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        if not inp or not Path(inp).exists():
            messagebox.showerror(APP_TITLE, "Please choose a valid IDML, PDF, or package folder.")
            return
        if not out:
            messagebox.showerror(APP_TITLE, "Please choose an output folder.")
            return
        if self.worker and self.worker.is_alive():
            return

        self._clear_log()
        self.convert_btn.config(state="disabled")
        self.progress.start(12)
        self.status.config(text="Converting...")        # Immediate feedback while a large PDF is parsed.
        self._append(f"[start] Input type: {self.input_type_var.get()} | Input: {inp}")

        config = ConversionConfig(
            input_path=Path(inp),
            output_dir=Path(out),
            profile=MobileProfile(),
            mode=("reflow" if self.mode_var.get().startswith("reflow")
                  else "facsimile"),
            input_type={"PDF": "pdf", "IDML": "idml"}.get(self.input_type_var.get(), "auto"),
            reading_order_strategy=self.strategy_var.get(),
            embed_fonts=self.fonts_var.get(),
            recover_visuals=self.visuals_var.get(),
            render_pdf=self.pdf_var.get(),
        )
        self.worker = threading.Thread(target=self._run, args=(config,), daemon=True)
        self.worker.start()

    def _run(self, config: ConversionConfig) -> None:
        pipeline = ConversionPipeline(config)
        pipeline.attach(_QueueObserver(self.events))
        try:
            result = pipeline.convert()
            ok = result.qa is None or result.qa.passed
            self.events.put(Event(
                stage="__done__",
                message=str(config.output_dir),
                level=Level.INFO if ok else Level.WARNING,
                data={"output": str(config.output_dir), "stats": result.stats},
            ))
        except Exception as exc:  # surface any failure in the log
            self.events.put(Event(stage="__error__", message=str(exc), level=Level.ERROR))

    # -- UI pump -----------------------------------------------------------
    def _drain(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle(event)
        except queue.Empty:
            pass
        self.root.after(120, self._drain)

    def _handle(self, event: Event) -> None:
        if event.stage == "__done__":
            stats = event.data.get("stats") or {}
            self._finish(success=event.level != Level.ERROR, output=event.message, stats=stats)
            self._append(f"[done] Output ready: {event.message}", event.level)
            if stats:
                self._append(
                    f"  Tokens (est.)  : {stats.get('text_tokens_est', 0):,}  "
                    + "-" * 48
                )
            return
        if event.stage == "__error__":
            self._finish(success=False, output="")
            self._append(f"[error] {event.message}", Level.ERROR)
            return
        pct = f" {event.progress * 100:5.1f}%" if event.progress is not None else ""
        self._append(f"[{event.stage}]{pct} {event.message}", event.level)

    def _finish(self, success: bool, output: str, stats: dict | None = None) -> None:
        self.progress.stop()
        self.convert_btn.config(state="normal")
        base = "Done" if success else "Finished with issues"
        if stats:
            base += (f"   |   {stats.get('elapsed_human', '?')}   |   "
                     f"~{stats.get('text_tokens_est', 0):,} tokens")
        self.status.config(text=base)
        if success and output and self.open_var.get():
            self._open_folder(Path(output))

    # -- helpers -----------------------------------------------------------
    def _append(self, text: str, level: Level = Level.INFO) -> None:
        self.log.config(state="normal")        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear_log(self) -> None:
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    @staticmethod
    def _open_folder(path: Path) -> None:
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception:
            pass


def _find_icon() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parent / "resources" / "idml2mobile.ico",   # packaged / installed
        here.parents[2] / "assets" / "idml2mobile.ico",  # editable repo checkout
    ]
    return next((c for c in candidates if c.exists()), None)


def main() -> None:
    root = Tk()
    try:
        ico = _find_icon()
        if ico is not None:
            root.iconbitmap(str(ico))
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()



