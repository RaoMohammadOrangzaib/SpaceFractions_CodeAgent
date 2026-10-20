"""Tkinter GUI: API key, input files, output directory, progress, file tree, log and run summary."""
from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Any

from .agent import DEFAULT_TASK, run_agent
from .config import load_settings, save_settings
from .llm import MODEL, DeepSeekClient, LLMError

TREE_REFRESH_MS = 1000


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def format_summary(result: dict[str, Any], out: Path, elapsed: float) -> str:
    """Build the post-run summary text (pure function, unit-testable)."""
    files = [out / f for f in result.get("files", [])]
    total = sum(f.stat().st_size for f in files if f.is_file())
    status = {"finished": "Finished successfully", "cancelled": "Cancelled",
              "max_steps_reached": "Stopped: step limit reached before the agent called finish",
              "error": "Failed"}.get(result.get("status", ""), result.get("status", "unknown"))
    mins, secs = divmod(int(elapsed), 60)
    lines = [f"Status: {status}",
             f"Steps: {result.get('steps', 0)}   Files: {len(files)} ({human_size(total)})   "
             f"Time: {mins}m {secs:02d}s",
             f"Output: {out}"]
    if result.get("error"):
        lines.append(f"Error: {result['error']}")
    if result.get("summary"):
        lines += ["", "Agent summary:", result["summary"]]
    return "\n".join(lines)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Code Agent - DeepSeek")
        self.geometry("980x760")
        self.minsize(760, 560)
        self.q: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self.running = False
        self.started_at = 0.0
        self.run_out: Path | None = None
        self.tree_nodes: dict[str, str] = {}  # relative path -> tree iid
        s = load_settings()

        self.api_key = tk.StringVar(value=s.get("api_key", ""))
        self.remember = tk.BooleanVar(value=bool(s.get("api_key")))
        self.doc = tk.StringVar(value=s.get("doc", ""))
        self.views = tk.StringVar(value=s.get("views", ""))
        self.out = tk.StringVar(value=s.get("out", ""))
        self.model = tk.StringVar(value=s.get("model", MODEL))
        self.status = tk.StringVar(value="Idle")

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="x")
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="DeepSeek API key").grid(row=0, column=0, sticky="w", pady=3)
        self.key_entry = ttk.Entry(frm, textvariable=self.api_key, show="*")
        self.key_entry.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Checkbutton(frm, text="Show", command=self._toggle_key).grid(row=0, column=2)
        ttk.Checkbutton(frm, text="Remember key on this PC", variable=self.remember).grid(
            row=1, column=1, sticky="w", padx=6)

        ttk.Label(frm, text="Model").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=self.model).grid(row=2, column=1, sticky="ew", padx=6)

        self._file_row(frm, 3, "Architecture documentation (.md)", self.doc, self._pick_doc)
        self._file_row(frm, 4, "Architecture views (.md)", self.views, self._pick_views)
        self._file_row(frm, 5, "Output directory", self.out, self._pick_out)

        ttk.Label(frm, text="Task").grid(row=6, column=0, sticky="nw", pady=3)
        self.task = tk.Text(frm, height=3, wrap="word")
        self.task.insert("1.0", DEFAULT_TASK)
        self.task.grid(row=6, column=1, columnspan=2, sticky="ew", padx=6)

        bar = ttk.Frame(self, padding=(10, 0))
        bar.pack(fill="x")
        self.run_btn = ttk.Button(bar, text="Run agent", command=self.start)
        self.run_btn.pack(side="left")
        self.cancel_btn = ttk.Button(bar, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=6)
        ttk.Button(bar, text="Open output folder", command=self._open_out).pack(side="left")

        prog = ttk.Frame(self, padding=(10, 8, 10, 0))
        prog.pack(fill="x")
        self.progress = ttk.Progressbar(prog, mode="determinate", maximum=1, value=0)
        self.progress.pack(fill="x")
        ttk.Label(prog, textvariable=self.status).pack(anchor="w", pady=(2, 0))

        # Summary is packed at the bottom first so the paned area gets the remaining space.
        self.summary_frame = ttk.LabelFrame(self, text="Run summary", padding=6)
        self.summary = tk.Text(self.summary_frame, height=7, wrap="word", state="disabled")
        self.summary.pack(fill="both", expand=True)

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(side="top", fill="both", expand=True, padx=10, pady=10)
        self.pane = pane

        left = ttk.LabelFrame(pane, text="Generated files (double-click to open)", padding=4)
        self.tree = ttk.Treeview(left, columns=("size",), selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("size", text="Size")
        self.tree.column("#0", width=240, stretch=True)
        self.tree.column("size", width=70, anchor="e", stretch=False)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._open_selected)
        pane.add(left, weight=1)

        right = ttk.LabelFrame(pane, text="Agent log", padding=4)
        self.log = scrolledtext.ScrolledText(right, state="disabled", wrap="word", height=14)
        self.log.pack(fill="both", expand=True)
        pane.add(right, weight=2)

        self.after(100, self._drain)
        self.after(TREE_REFRESH_MS, self._tick_tree)

    # --- helpers ---
    def _file_row(self, frm: ttk.Frame, row: int, label: str, var: tk.StringVar, cmd) -> None:
        ttk.Label(frm, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(frm, textvariable=var).grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(frm, text="Browse...", command=cmd).grid(row=row, column=2)

    def _toggle_key(self) -> None:
        self.key_entry.config(show="" if self.key_entry.cget("show") else "*")

    def _pick_doc(self) -> None:
        p = filedialog.askopenfilename(title="Architecture documentation",
                                       filetypes=[("Markdown", "*.md"), ("All files", "*.*")])
        if p:
            self.doc.set(p)
            guess = Path(p).with_name("Architecture_View.md")
            if not self.views.get() and guess.exists():
                self.views.set(str(guess))

    def _pick_views(self) -> None:
        p = filedialog.askopenfilename(title="Architecture views",
                                       filetypes=[("Markdown", "*.md"), ("All files", "*.*")])
        if p:
            self.views.set(p)

    def _pick_out(self) -> None:
        p = filedialog.askdirectory(title="Output directory")
        if p:
            self.out.set(p)

    def _open_out(self) -> None:
        if self.out.get() and Path(self.out.get()).is_dir():
            os.startfile(self.out.get())  # Windows only

    def _cancel(self) -> None:
        self.cancel.set()
        self.status.set("Cancelling after the current step...")
        self.cancel_btn.config(state="disabled")

    def _append(self, text: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # --- file tree ---
    def _clear_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree_nodes.clear()

    def refresh_tree(self) -> None:
        """Incrementally add new files/folders under the output dir (keeps expansion state)."""
        root = self.run_out
        if root is None or not root.is_dir():
            return
        for path in sorted(root.rglob("*"), key=lambda p: (len(p.relative_to(root).parts), str(p).lower())):
            rel = path.relative_to(root).as_posix()
            size = "" if path.is_dir() else human_size(path.stat().st_size)
            if rel in self.tree_nodes:
                if not path.is_dir():
                    self.tree.set(self.tree_nodes[rel], "size", size)
                continue
            parent_rel = path.parent.relative_to(root).as_posix()
            parent = self.tree_nodes.get(parent_rel, "") if parent_rel != "." else ""
            self.tree_nodes[rel] = self.tree.insert(parent, "end", text=path.name, values=(size,), open=True)

    def _tick_tree(self) -> None:
        if self.running:
            try:
                self.refresh_tree()
            except OSError:
                pass  # a file vanished mid-scan; next tick will catch up
        self.after(TREE_REFRESH_MS, self._tick_tree)

    def _open_selected(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel or self.run_out is None:
            return
        rel = next((r for r, iid in self.tree_nodes.items() if iid == sel[0]), None)
        if rel and (self.run_out / rel).is_file():
            os.startfile(self.run_out / rel)

    # --- queue pump ---
    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._append(payload)
                elif kind == "progress":
                    step, total = payload
                    self.progress.config(maximum=total, value=step)
                    self.status.set(f"Working... step {step + 1} of at most {total}")
                elif kind == "done":
                    self._finish(payload)
        except queue.Empty:
            pass
        self.after(100, self._drain)

    # --- run ---
    def start(self) -> None:
        key, doc, views, out = self.api_key.get().strip(), self.doc.get(), self.views.get(), self.out.get()
        missing = [n for n, v in (("API key", key), ("documentation file", doc),
                                  ("views file", views), ("output directory", out)) if not v]
        if missing:
            messagebox.showerror("Missing input", "Please provide: " + ", ".join(missing))
            return
        for p in (doc, views):
            if not Path(p).is_file():
                messagebox.showerror("File not found", p)
                return
        save_settings({"api_key": key if self.remember.get() else "", "doc": doc, "views": views,
                       "out": out, "model": self.model.get()})
        self.cancel.clear()
        self.running = True
        self.started_at = time.monotonic()
        self.run_out = Path(out)
        self._clear_tree()
        self.summary_frame.pack_forget()
        self.progress.config(maximum=1, value=0)
        self.status.set("Starting...")
        self.run_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        task = self.task.get("1.0", "end").strip() or DEFAULT_TASK
        self.worker = threading.Thread(
            target=self._work, args=(key, Path(doc), Path(views), Path(out), task, self.model.get().strip()),
            daemon=True)
        self.worker.start()

    def _work(self, key: str, doc: Path, views: Path, out: Path, task: str, model: str) -> None:
        put = self.q.put
        result: dict[str, Any]
        try:
            client = DeepSeekClient(key, model=model or MODEL)
            result = run_agent(client, doc, views, out, task=task, cancel=self.cancel,
                               log=lambda m: put(("log", m)),
                               progress=lambda s, t: put(("progress", (s, t))))
        except LLMError as e:
            put(("log", f"LLM error: {e}"))
            result = {"status": "error", "error": f"LLM error: {e}", "steps": 0, "files": self._existing(out)}
        except Exception as e:  # keep the GUI alive on any failure
            put(("log", f"Unexpected error: {type(e).__name__}: {e}"))
            result = {"status": "error", "error": f"{type(e).__name__}: {e}", "steps": 0,
                      "files": self._existing(out)}
        put(("done", result))

    @staticmethod
    def _existing(out: Path) -> list[str]:
        try:
            return sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
        except OSError:
            return []

    def _finish(self, result: dict[str, Any]) -> None:
        self.running = False
        self.run_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        if result.get("status") == "finished":
            self.progress.config(value=self.progress["maximum"])
        self.status.set({"finished": "Done", "cancelled": "Cancelled", "error": "Failed"}.get(
            result.get("status", ""), "Stopped"))
        self.refresh_tree()
        text = format_summary(result, self.run_out or Path("."), time.monotonic() - self.started_at)
        self.summary.config(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", text)
        self.summary.config(state="disabled")
        self.summary_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10), before=self.pane)


def main() -> None:
    App().mainloop()
