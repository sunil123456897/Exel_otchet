"""Periodic network-drive reachability probe for the sidebar indicator.

Extracted from ``core/ui/ui_sidebar.py`` (TD: god-widget decomposition).
The ``os.path.exists`` probes run on a daemon thread because on
slow/unreachable network drives each probe blocks for the SMB redirector
timeout (5-30 s) — running that on the GUI thread froze the whole window
every poll cycle. Only the final status callback is marshalled back to
the GUI thread via ``after(0, ...)``.
"""

from __future__ import annotations

import logging
import os
import threading
import tkinter as tk
from typing import Any, Callable, Optional


class NetworkDrivePoller:
    """Probe configured drive letters every ``POLL_INTERVAL_MS``.

    ``get_config`` returns the controller's config dict (probed lazily so
    config edits apply on the next poll); ``on_status(level, text)`` is
    called on the host widget's GUI thread.
    """

    INITIAL_DELAY_MS = 2_000
    POLL_INTERVAL_MS = 30_000
    DEFAULT_DRIVE_LETTERS = ["Q"]

    def __init__(
        self,
        host: tk.Misc,
        get_config: Callable[[], dict[str, Any]],
        on_status: Callable[[str, str], None],
    ) -> None:
        self._host = host
        self._get_config = get_config
        self._on_status = on_status
        self._after_id: Optional[str] = None

    def start(self) -> None:
        self.schedule(self.INITIAL_DELAY_MS)

    def stop(self) -> None:
        if self._after_id is not None:
            try:
                self._host.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def schedule(self, delay_ms: int) -> None:
        try:
            self._after_id = self._host.after(delay_ms, self.poll)
        except tk.TclError:
            self._after_id = None

    def poll(self) -> None:
        """Probe drives on a daemon thread, then schedule the next poll."""
        try:
            config = self._get_config() or {}
            network_cfg = config.get("network", {}) if isinstance(config, dict) else {}
            drive_letters = network_cfg.get("drive_letters", self.DEFAULT_DRIVE_LETTERS)
            if not isinstance(drive_letters, list):
                drive_letters = [drive_letters]

            def _probe() -> tuple[int, int]:
                reachable = 0
                total = 0
                for letter in drive_letters:
                    drive_path = f"{str(letter)}:\\"
                    total += 1
                    if os.path.exists(drive_path):
                        reachable += 1
                return reachable, total

            def _on_done(result: tuple[int, int]) -> None:
                reachable, total = result
                if total == 0:
                    self._on_status("warn", "Сеть: нет дисков")
                elif reachable == total:
                    self._on_status("ok", f"Сеть: {reachable}/{total} дисков доступны")
                elif reachable > 0:
                    self._on_status("warn", f"Сеть: {reachable}/{total} дисков доступны")
                else:
                    self._on_status("err", f"Сеть: {reachable}/{total} дисков доступны")

            def runner() -> None:
                try:
                    result = _probe()
                except Exception:
                    logging.exception("Network drive poll failed")
                    result = (0, 0)

                def safe_done() -> None:
                    try:
                        _on_done(result)
                    except tk.TclError:
                        pass

                try:
                    self._host.after(0, safe_done)
                except tk.TclError:
                    pass

            threading.Thread(target=runner, daemon=True).start()
        except Exception:
            self._on_status("warn", "Сеть: ошибка проверки")
        finally:
            self.schedule(self.POLL_INTERVAL_MS)
