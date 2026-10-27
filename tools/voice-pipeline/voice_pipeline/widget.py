"""A small always-on-top window that says what DeskBuddy is doing.

Deliberately plain: a colored dot, a word, and a bar for the microphone. The
point is to answer "is it hearing me?" at a glance, not to be a face.

Tkinter because it ships with Python (no install) and the whole window is
under a page. The window never touches audio — it polls the `StateFeed` that
the conversation loop publishes into.
"""

from __future__ import annotations

import tkinter as tk

from . import state as ui

WIDTH = 300
HEIGHT = 150
REFRESH_MS = 50

BG = "#16181d"
FG = "#e6e8ee"
DIM = "#7d8595"


def _hex(rgb) -> str:  # noqa: ANN001
    return "#%02x%02x%02x" % tuple(int(max(0.0, min(1.0, c)) * 255) for c in rgb)


class Widget:
    """Colored dot + state word + mic bar, following a `StateFeed`."""

    def __init__(self, feed, *, on_close=None) -> None:  # noqa: ANN001
        self.feed = feed
        self.on_close = on_close
        self.shown_level = 0.0

        self.root = tk.Tk()
        self.root.title("DeskBuddy")
        x = max(0, self.root.winfo_screenwidth() - WIDTH - 40)
        self.root.geometry(f"{WIDTH}x{HEIGHT}+{x}+40")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT,
                                bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self._drag = (0, 0)
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag_to)
        self.root.bind("<Escape>", lambda _e: self.close())

        self._tick()

    # -- window ---------------------------------------------------------------
    def _start_drag(self, event) -> None:  # noqa: ANN001
        self._drag = (event.x, event.y)

    def _drag_to(self, event) -> None:  # noqa: ANN001
        x = self.root.winfo_x() + event.x - self._drag[0]
        y = self.root.winfo_y() + event.y - self._drag[1]
        self.root.geometry(f"+{x}+{y}")

    def close(self) -> None:
        if self.on_close is not None:
            self.on_close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # -- drawing --------------------------------------------------------------
    def _tick(self) -> None:
        snapshot = self.feed.read() if hasattr(self.feed, "read") else ui.State()
        self.shown_level += (snapshot.level - self.shown_level) * 0.35
        self._draw(snapshot)
        self.root.after(REFRESH_MS, self._tick)

    def _draw(self, snapshot: ui.State) -> None:
        c = self.canvas
        c.delete("all")
        accent = ui.COLORS.get(snapshot.state, ui.COLORS[ui.SLEEPING])

        # Dot
        c.create_oval(22, 30, 44, 52, fill=_hex(accent), outline="")
        # State word
        c.create_text(56, 41, text=ui.LABELS.get(snapshot.state, ""), anchor="w",
                      fill=FG, font=("DejaVu Sans", 15, "bold"))
        # Bigger description line
        line = snapshot.detail if snapshot.state == ui.ERROR else (snapshot.text or "")
        if not line:
            line = {"sleeping": 'say "choom"', "listening": "go ahead",
                    "thinking": "working on it", "speaking": ""}.get(snapshot.state, "")
        if line:
            c.create_text(56, 68, text=_trim(line, 34), anchor="w", fill=DIM,
                          font=("DejaVu Sans", 10))

        # Mic bar
        left, right, top, height = 22, WIDTH - 22, 100, 10
        c.create_rectangle(left, top, right, top + height, fill="#23262e", outline="")
        filled = left + (right - left) * self.shown_level
        if filled > left + 1:
            c.create_rectangle(left, top, filled, top + height, fill=_hex(accent), outline="")

        c.create_text(WIDTH - 14, HEIGHT - 12, text="esc", fill=DIM,
                      font=("DejaVu Sans", 8), anchor="se")


def _trim(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def show(feed, *, on_close=None) -> None:  # noqa: ANN001
    """Run the window until closed. Blocking; call from the main thread."""
    Widget(feed, on_close=on_close).root.mainloop()
