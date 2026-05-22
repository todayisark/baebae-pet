from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from engine.macos_window import apply_macos_always_on_top


class ReminderBubble(QWidget):
    """
    A floating speech-bubble widget that appears above the pet.

    Signals:
        dismissed – emitted when the user clicks "我知道了" or the 30-s timer fires.
    """

    dismissed = Signal()

    AUTO_DISMISS_MS = 30_000  # 30 seconds

    def __init__(
        self,
        message: str,
        parent: QWidget | None = None,
        dismiss_label: str = "我知道了",
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._setup_ui(message, dismiss_label)

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._on_dismiss)
        self._auto_timer.start(self.AUTO_DISMISS_MS)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_native_level_with_retries()

    def _apply_native_level_with_retries(self, attempts: int = 5) -> None:
        if apply_macos_always_on_top(self):
            return
        if attempts > 1:
            QTimer.singleShot(
                100,
                lambda: self._apply_native_level_with_retries(attempts - 1),
            )

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------

    def _setup_ui(self, message: str, dismiss_label: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        label = QLabel(message)
        label.setStyleSheet(
            "color: #333333; font-size: 13px; background: transparent;"
        )
        label.setWordWrap(True)
        label.setMaximumWidth(220)
        layout.addWidget(label)

        btn = QPushButton(dismiss_label)
        btn.setStyleSheet(
            """
            QPushButton {
                background: #5B8CFF;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 5px 18px;
                font-size: 12px;
            }
            QPushButton:hover { background: #4A7BEE; }
            QPushButton:pressed { background: #3A6BDE; }
            """
        )
        btn.clicked.connect(self._on_dismiss)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

    # -------------------------------------------------------------------------
    # Paint – rounded white bubble
    # -------------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)
        painter.fillPath(path, QColor(255, 255, 255, 245))
        painter.setPen(QColor(210, 210, 210))
        painter.drawPath(path)

    # -------------------------------------------------------------------------
    # Dismiss
    # -------------------------------------------------------------------------

    def _on_dismiss(self) -> None:
        self._auto_timer.stop()
        self.close()
        self.dismissed.emit()
