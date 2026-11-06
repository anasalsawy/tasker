"""Tray presence via pystray (installed in .venv; win32 backend verified).
States color a tiny icon: idle/listening/working/done/error. pyncallbacks from
main wire menu (Quit). If pystray cannot display (locked session), .ok=False and
the shell keeps running headless - API/wake/persona unaffected.
"""
from __future__ import annotations

import logging

log = logging.getLogger("hands.tray")

_COLORS = {"idle": (70, 70, 70), "listening": (0, 190, 90),
           "working": (60, 130, 255), "done": (255, 170, 0),
           "error": (220, 40, 40)}


def _make_image(color):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2, 2, 30, 30), fill=tuple(color) + (255,))
    d.text((12, 9), "H", fill=(255, 255, 255, 255))
    return img


class TrayPresence:
    """Tiny stateful tray icon. run() blocks (pystray loop) -> call from thread.

    Menu: status text updates with state; Quit -> on_quit() then icon.stop().
    set_state(name) is thread-safe (pystray handles cross-thread icon calls on
    Windows; set_image reflects ring -> redraw).
    """

    def __init__(self, on_quit=None, title: str = "Hands shell"):
        self.on_quit = on_quit
        self.title = title
        self.state = "idle"
        self.ok = False
        self.error = ""
        self._icon = None
        self._images: dict = {}

    def _image(self):
        col = _COLORS.get(self.state, (90, 90, 90))
        if col not in self._images:
            self._images[col] = _make_image(col)
        return self._images[col]

    def set_state(self, name: str) -> None:
        if name not in _COLORS:
            return
        self.state = name
        if self._icon is not None:
            try:
                self._icon.icon = self._image()
                self._icon.title = f"{self.title} - {name}"
            except Exception as exc:
                log.debug("tray set_state(%s) failed: %s", name, exc)

    def notify(self, title: str, msg: str, timeout: float = 4.0) -> None:
        if self._icon is None:
            return
        try:
            import pystray
            self._icon.notify(msg, title)
        except Exception as exc:
            log.debug("tray notify failed: %s", exc)

    def run(self) -> None:
        """Blocking pystray loop (call in daemon thread)."""
        try:
            import pystray
            def _quit():
                if self.on_quit:
                    self.on_quit()
                self.stop()
            menu = pystray.Menu(
                pystray.MenuItem(lambda item: "state: " + self.state,
                                 lambda item: None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", _quit, default=True))
            self._icon = pystray.Icon("hands_shell", self._image(),
                                      f"{self.title} - idle", menu=menu)
            self.ok = True
            self._icon.run()
        except Exception as exc:
            self.error = str(exc)[:200]
            log.warning("DEGRADED: tray unavailable (%s) - shell still runs "
                        "headless", self.error)
            self.ok = False
        finally:
            self._icon = None

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass


__all__ = ["TrayPresence"]

