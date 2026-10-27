"""A small always-on-top window that says what DeskBuddy is doing.

Deliberately plain: a colored dot, a word, and a bar for the microphone. The
point is to answer "is it hearing me?" at a glance, not to be a face.

Tkinter because it ships with Python (no install) and the whole window is
under a page. The window never touches audio — it polls the `StateFeed` that
the conversation loop publishes into.

Two modes:

* **attached** — meant to sit on screen next to a running session. Closing it
  ends the session.
* **auto-hide** — the window is unmapped while asleep and pops up by itself
  when the wake word fires, then disappears again a few seconds after the
  conversation goes quiet. This is what the background service uses, so
  nothing is on screen until you say the word, and Escape means "go away"
  rather than "quit the service".
"""

from __future__ import annotations

import time
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

    def __init__(self, feed, *, on_close=None, on_dismiss=None,  # noqa: ANN001
                 auto_hide: bool = False, hide_after: float = 3.0) -> None:
        self.feed = feed
        self.on_close = on_close
        self.on_dismiss = on_dismiss
        self.shown_level = 0.0
        self.auto_hide = auto_hide
        self.hide_after = hide_after
        self._mapped = False
        self._asleep_since = None
        self._hold_hidden = False

        self.root = tk.Tk()
        self.root.title("DeskBuddy")
        # Under a tiling compositor a decorated window gets tiled into the
        # layout and its size request is ignored. This is a HUD, not a
        # document: map it unmanaged so it keeps the size and corner it asks
        # for and never steals a tile from real work.
        self.root.overrideredirect(True)
        x = max(0, self.root.winfo_screenwidth() - WIDTH - 40)
        self.root.geometry(f"{WIDTH}x{HEIGHT}+{x}+40")
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._dismiss if auto_hide else self.close)

        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT,
                                bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self._drag = (0, 0)
        self._pressed_at = (0, 0)
        self.canvas.bind("<ButtonPress-1>", self._start_drag)
        self.canvas.bind("<B1-Motion>", self._drag_to)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.root.bind("<Escape>", lambda _e: self._dismiss() if auto_hide else self.close())

        if auto_hide:
            # Start hidden: nothing on screen until the wake word is heard.
            self.root.withdraw()
        else:
            self._mapped = True

        self._tick()

    # -- window ---------------------------------------------------------------
    def _start_drag(self, event) -> None:  # noqa: ANN001
        self._drag = (event.x, event.y)
        self._pressed_at = (event.x_root, event.y_root)

    def _release(self, event) -> None:  # noqa: ANN001
        """A click that did not move the window means "go away".

        The window is unmanaged, so the compositor will not give it keyboard
        focus on its own — Escape alone would often not reach it. Clicking is
        the gesture that always works.
        """
        moved = abs(event.x_root - self._pressed_at[0]) + abs(event.y_root - self._pressed_at[1])
        if moved <= 3 and self.auto_hide:
            self._dismiss()

    def _drag_to(self, event) -> None:  # noqa: ANN001
        x = self.root.winfo_x() + event.x - self._drag[0]
        y = self.root.winfo_y() + event.y - self._drag[1]
        self.root.geometry(f"+{x}+{y}")

    def close(self) -> None:
        """Tear the window down. In auto-hide mode the window outlives the UI."""
        if self.on_close is not None:
            self.on_close()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _dismiss(self) -> None:
        """Hide now and end the open conversation; the service keeps running.

        `_hold_hidden` stops the very next repaint from popping the window
        straight back up before the loop has noticed the dismissal.
        """
        self.root.withdraw()
        self._mapped = False
        self._asleep_since = None
        self._hold_hidden = True
        if self.on_dismiss is not None:
            self.on_dismiss()

    def _sync_visibility(self, snapshot: ui.State) -> None:
        """Show on any active state, hide again a few seconds after sleeping."""
        if not self.auto_hide:
            return
        if self._hold_hidden:
            if snapshot.state == ui.SLEEPING:
                self._hold_hidden = False
            return

        if snapshot.state != ui.SLEEPING:
            self._asleep_since = None
            if not self._mapped:
                self.root.deiconify()
                self.root.attributes("-topmost", True)
                self._mapped = True
            return

        if not self._mapped:
            return
        if self._asleep_since is None:
            self._asleep_since = time.monotonic()
        elif time.monotonic() - self._asleep_since >= self.hide_after:
            self.root.withdraw()
            self._mapped = False
            self._asleep_since = None

    # -- drawing --------------------------------------------------------------
    def _tick(self) -> None:
        snapshot = self.feed.read() if hasattr(self.feed, "read") else ui.State()
        self.shown_level += (snapshot.level - self.shown_level) * 0.35
        self._sync_visibility(snapshot)
        if self._mapped:
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

        hint = "click or esc to close" if self.auto_hide else "esc"
        c.create_text(WIDTH - 14, HEIGHT - 12, text=hint, fill=DIM,
                      font=("DejaVu Sans", 8), anchor="se")


def _trim(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def show(feed, *, on_close=None, auto_hide: bool = False) -> None:  # noqa: ANN001
    """Run the window until closed. Blocking; call from the main thread."""
    Widget(feed, on_close=on_close, auto_hide=auto_hide).root.mainloop()
