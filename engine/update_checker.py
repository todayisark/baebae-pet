from __future__ import annotations

import json
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

import config.settings as cfg

_RELEASES_API = "https://api.github.com/repos/todayisark/baebae-pet/releases/latest"
_CHECK_HOURS = (0, 12)


def _version_tuple(tag: str) -> tuple[tuple[int, ...], str]:
    tag = tag.lstrip("v")
    pre = ""
    if "-" in tag:
        tag, pre = tag.split("-", 1)
    parts: list[int] = []
    for p in tag.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts), pre


def _is_newer(remote: str, local: str) -> bool:
    r_nums, r_pre = _version_tuple(remote)
    l_nums, l_pre = _version_tuple(local)
    if r_nums != l_nums:
        return r_nums > l_nums
    if r_pre == l_pre:
        return False
    return r_pre == ""  # stable (no pre-release suffix) > any pre-release


class UpdateChecker(QObject):
    """Async GitHub release checker with twice-daily scheduled checks."""

    update_available = Signal(str, str)  # (tag, html_url)
    up_to_date = Signal()
    check_failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._nam = QNetworkAccessManager(self)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_tick)

    def check(self) -> None:
        """Fire an immediate async update check."""
        req = QNetworkRequest(QUrl(_RELEASES_API))
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setRawHeader(b"User-Agent", b"baebae-pet-updater")
        reply = self._nam.get(req)
        reply.finished.connect(lambda: self._handle_reply(reply))

    def start_scheduled(self) -> None:
        """Start the twice-daily schedule (00:00 and 12:00)."""
        self._schedule_next()

    def _schedule_next(self) -> None:
        ms = int(self._seconds_until_next() * 1000)
        self._timer.start(ms)

    def _on_tick(self) -> None:
        self.check()
        self._schedule_next()

    def _seconds_until_next(self) -> float:
        now = datetime.now()
        deltas: list[float] = []
        for h in _CHECK_HOURS:
            t = now.replace(hour=h, minute=0, second=0, microsecond=0)
            if t <= now:
                t += timedelta(days=1)
            deltas.append((t - now).total_seconds())
        return min(deltas)

    def _handle_reply(self, reply: QNetworkReply) -> None:
        reply.deleteLater()
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.check_failed.emit(reply.errorString())
            return
        try:
            data = json.loads(bytes(reply.readAll()))
            tag: str = data.get("tag_name", "")
            url: str = data.get("html_url", "")
            if _is_newer(tag, cfg.APP_VERSION):
                self.update_available.emit(tag, url)
            else:
                self.up_to_date.emit()
        except Exception as exc:
            self.check_failed.emit(str(exc))
