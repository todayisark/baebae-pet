"""
todo_panel.py — Google Tasks 待办事项浮窗

结构：
  TodoPanel        主浮窗，含 Login 页 和 Task 页（QStackedWidget）
  _TaskItem        单条任务 widget，支持内联编辑
  _Worker(QThread) 通用后台任务线程
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import engine.google_tasks as gt


# ---------------------------------------------------------------------------
# 后台线程
# ---------------------------------------------------------------------------

class _Worker(QThread):
    result = Signal(object)
    error = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            self.result.emit(self._fn(*self._args, **self._kwargs))
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# 单条任务 Widget
# ---------------------------------------------------------------------------

class _TaskItem(QWidget):
    toggle_requested = Signal(dict, bool)
    edit_requested = Signal(dict, str)
    delete_requested = Signal(dict)

    _BTN_STYLE = (
        "QPushButton{background:none;border:none;color:#999;padding:2px 6px;font-size:14px;}"
        "QPushButton:hover{color:#333;}"
    )

    def __init__(self, task: dict, language: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._task = task
        self._language = language
        self._commit_guard = False
        self._setup_ui()

    def _t(self, key: str) -> str:
        from engine.i18n import t
        return t(key, self._language)

    def _setup_ui(self) -> None:
        self.setStyleSheet("QWidget{background:transparent;}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)

        is_done = self._task.get("status") == "completed"

        self._check = QCheckBox()
        self._check.setChecked(is_done)
        self._check.clicked.connect(
            lambda checked: self.toggle_requested.emit(self._task, checked)
        )
        layout.addWidget(self._check)

        title = self._task.get("title", "")

        self._label = QLabel(title)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if is_done:
            self._label.setStyleSheet(
                "color:#AAA;text-decoration:line-through;font-size:13px;background:transparent;"
            )
        else:
            self._label.setStyleSheet(
                "color:#333;font-size:13px;background:transparent;"
            )
        layout.addWidget(self._label)

        self._edit = QLineEdit(title)
        self._edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._edit.setStyleSheet(
            "QLineEdit{border:1px solid #4285F4;border-radius:4px;"
            "padding:2px 6px;font-size:13px;background:white;color:#333;}"
        )
        self._edit.hide()
        self._edit.returnPressed.connect(self._commit_edit)
        layout.addWidget(self._edit)

        self._confirm = QPushButton("✓")
        self._confirm.setStyleSheet(
            "QPushButton{background:#4285F4;color:white;border:none;"
            "border-radius:4px;padding:2px 8px;font-size:13px;}"
            "QPushButton:hover{background:#3367D6;}"
        )
        self._confirm.setFixedWidth(32)
        self._confirm.hide()
        self._confirm.clicked.connect(self._commit_edit)
        layout.addWidget(self._confirm)

        self._more = QPushButton("⋯")
        self._more.setStyleSheet(self._BTN_STYLE)
        self._more.setFixedWidth(28)
        self._more.clicked.connect(self._show_menu)
        layout.addWidget(self._more)

    def enter_edit_mode(self) -> None:
        self._commit_guard = False
        self._label.hide()
        self._more.hide()
        self._edit.show()
        self._confirm.show()
        self._edit.selectAll()
        self._edit.setFocus()

    def _commit_edit(self) -> None:
        if self._commit_guard:
            return
        self._commit_guard = True
        new_title = self._edit.text().strip()
        self._edit.hide()
        self._confirm.hide()
        self._more.show()
        self._label.show()
        if new_title and new_title != self._task.get("title", ""):
            self.edit_requested.emit(self._task, new_title)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:white;border:1px solid #E0E0E0;border-radius:6px;padding:4px;}"
            "QMenu::item{color:#333;padding:6px 16px;border-radius:4px;}"
            "QMenu::item:selected{background:#F0F4FF;color:#333;}"
        )
        edit_action = menu.addAction(self._t("todo.edit"))
        delete_action = menu.addAction(self._t("todo.delete"))
        action = menu.exec(self._more.mapToGlobal(self._more.rect().bottomLeft()))
        if action == edit_action:
            self.enter_edit_mode()
        elif action == delete_action:
            self.delete_requested.emit(self._task)


# ---------------------------------------------------------------------------
# 主浮窗
# ---------------------------------------------------------------------------

class TodoPanel(QWidget):
    PANEL_WIDTH = 310

    _TAB_ACTIVE = (
        "QPushButton{background:none;border:none;border-bottom:2px solid #4285F4;"
        "color:#4285F4;padding:8px 14px;font-size:13px;font-weight:bold;}"
    )
    _TAB_INACTIVE = (
        "QPushButton{background:none;border:none;border-bottom:2px solid transparent;"
        "color:#888;padding:8px 14px;font-size:13px;}"
        "QPushButton:hover{color:#555;}"
    )

    def __init__(self, language: str, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._language = language
        self._workers: list[_Worker] = []
        self._pending: list[dict] = []
        self._completed: list[dict] = []
        self._tab = "pending"
        self._drag_offset: QPoint | None = None

        self._setup_ui()
        self._check_auth()

    def _t(self, key: str) -> str:
        from engine.i18n import t
        return t(key, self._language)

    # -------------------------------------------------------------------------
    # UI 构建
    # -------------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 14)

        self._card = QWidget()
        self._card.setObjectName("card")
        self._card.setStyleSheet(
            "QWidget#card{background:white;border-radius:12px;border:1px solid #E0E0E0;}"
        )
        self._card.setFixedWidth(self.PANEL_WIDTH)

        shadow = QGraphicsDropShadowEffect(self._card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 45))
        self._card.setGraphicsEffect(shadow)

        outer.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        card_layout.addWidget(self._make_header())

        self._stack = QStackedWidget()
        self._login_page = self._make_login_page()
        self._task_page = self._make_task_page()
        self._stack.addWidget(self._login_page)
        self._stack.addWidget(self._task_page)
        card_layout.addWidget(self._stack)

    def _make_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet(
            "QWidget{background:#F8F8F8;border-radius:12px 12px 0 0;"
            "border-bottom:1px solid #EBEBEB;}"
        )
        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 10, 8, 10)

        title = QLabel(self._t("todo.title"))
        title.setStyleSheet(
            "font-size:14px;font-weight:bold;color:#333;"
            "background:transparent;border:none;"
        )
        layout.addWidget(title)
        layout.addStretch()

        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setStyleSheet(
            "QPushButton{background:none;border:none;font-size:16px;color:#999;"
            "padding:2px 6px;border-radius:4px;}"
            "QPushButton:hover{color:#333;background:#EBEBEB;}"
            "QPushButton:disabled{color:#CCC;}"
        )
        self._refresh_btn.setFixedSize(QSize(30, 28))
        self._refresh_btn.clicked.connect(self._refresh_tasks)
        layout.addWidget(self._refresh_btn)

        self._logout_btn = QPushButton("⇥")
        self._logout_btn.setToolTip(self._t("todo.logout"))
        self._logout_btn.setStyleSheet(
            "QPushButton{background:none;border:none;font-size:14px;color:#999;"
            "padding:2px 6px;border-radius:4px;}"
            "QPushButton:hover{color:#E53935;background:#FFF0F0;}"
        )
        self._logout_btn.setFixedSize(QSize(30, 28))
        self._logout_btn.clicked.connect(self._logout)
        layout.addWidget(self._logout_btn)

        close_btn = QPushButton("×")
        close_btn.setStyleSheet(
            "QPushButton{background:none;border:none;font-size:18px;color:#999;"
            "padding:2px 6px;border-radius:4px;}"
            "QPushButton:hover{color:#333;background:#EBEBEB;}"
        )
        close_btn.setFixedSize(QSize(30, 28))
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

        return header

    def _make_login_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("QWidget{background:transparent;border:none;}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 32, 24, 32)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel("G")
        icon.setStyleSheet(
            "font-size:28px;font-weight:bold;color:white;"
            "background:#4285F4;border-radius:24px;border:none;"
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(QSize(48, 48))
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        desc = QLabel(self._t("todo.login_desc"))
        desc.setStyleSheet(
            "font-size:13px;color:#666;background:transparent;border:none;"
        )
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc)

        self._login_btn = QPushButton(self._t("todo.login_btn"))
        self._login_btn.setStyleSheet(
            "QPushButton{background:#4285F4;color:white;border:none;"
            "border-radius:8px;padding:10px 20px;font-size:13px;font-weight:bold;}"
            "QPushButton:hover{background:#3367D6;}"
            "QPushButton:disabled{background:#B0C4F8;}"
        )
        self._login_btn.clicked.connect(self._start_auth)
        layout.addWidget(self._login_btn)

        return page

    def _make_task_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("QWidget{background:transparent;border:none;}")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab 栏
        tab_bar = QWidget()
        tab_bar.setStyleSheet(
            "QWidget{background:#F8F8F8;border-bottom:1px solid #EBEBEB;}"
        )
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(8, 0, 8, 0)
        tab_layout.setSpacing(0)

        self._tab_pending_btn = QPushButton(self._t("todo.tab_pending"))
        self._tab_done_btn = QPushButton(self._t("todo.tab_done"))
        self._tab_pending_btn.clicked.connect(lambda: self._switch_tab("pending"))
        self._tab_done_btn.clicked.connect(lambda: self._switch_tab("completed"))
        tab_layout.addWidget(self._tab_pending_btn)
        tab_layout.addWidget(self._tab_done_btn)
        tab_layout.addStretch()
        layout.addWidget(tab_bar)

        # 任务列表
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedHeight(280)
        scroll.setStyleSheet("QScrollArea{border:none;background:white;}")

        self._list_widget = QWidget()
        self._list_widget.setStyleSheet("QWidget{background:white;}")
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 4, 0, 4)
        self._list_layout.setSpacing(1)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._list_widget)
        layout.addWidget(scroll)

        # 添加栏
        add_bar = QWidget()
        add_bar.setStyleSheet(
            "QWidget{border-top:1px solid #EBEBEB;background:white;"
            "border-radius:0 0 12px 12px;}"
        )
        add_layout = QHBoxLayout(add_bar)
        add_layout.setContentsMargins(10, 8, 10, 10)
        add_layout.setSpacing(6)

        self._add_input = QLineEdit()
        self._add_input.setPlaceholderText(self._t("todo.add_placeholder"))
        self._add_input.setStyleSheet(
            "QLineEdit{border:1px solid #DDD;border-radius:6px;"
            "padding:6px 10px;font-size:13px;background:white;color:#333;}"
            "QLineEdit:focus{border-color:#4285F4;}"
        )
        self._add_input.returnPressed.connect(self._add_task)

        add_btn = QPushButton(self._t("todo.add_btn"))
        add_btn.setStyleSheet(
            "QPushButton{background:#4285F4;color:white;border:none;"
            "border-radius:6px;padding:6px 14px;font-size:13px;}"
            "QPushButton:hover{background:#3367D6;}"
        )
        add_btn.clicked.connect(self._add_task)

        add_layout.addWidget(self._add_input)
        add_layout.addWidget(add_btn)
        layout.addWidget(add_bar)

        self._switch_tab("pending")
        return page

    # -------------------------------------------------------------------------
    # 认证
    # -------------------------------------------------------------------------

    def _check_auth(self) -> None:
        if gt.has_token():
            self._show_task_page()
            self._refresh_tasks()
        else:
            self._stack.setCurrentWidget(self._login_page)
            self._refresh_btn.setVisible(False)
            self._logout_btn.setVisible(False)

    def _start_auth(self) -> None:
        self._login_btn.setText(self._t("todo.waiting_auth"))
        self._login_btn.setEnabled(False)
        w = self._run(gt.authenticate)
        w.result.connect(self._on_auth_done)
        w.error.connect(self._on_auth_error)

    def _on_auth_done(self, _creds: object) -> None:
        self._show_task_page()
        self._refresh_tasks()

    def _on_auth_error(self, _err: str) -> None:
        self._login_btn.setText(self._t("todo.login_btn"))
        self._login_btn.setEnabled(True)

    def _logout(self) -> None:
        gt.revoke_token()
        self._pending = []
        self._completed = []
        self._stack.setCurrentWidget(self._login_page)
        self._refresh_btn.setVisible(False)
        self._logout_btn.setVisible(False)
        self._login_btn.setText(self._t("todo.login_btn"))
        self._login_btn.setEnabled(True)
        self.adjustSize()

    def _show_task_page(self) -> None:
        self._stack.setCurrentWidget(self._task_page)
        self._refresh_btn.setVisible(True)
        self._logout_btn.setVisible(True)
        self.adjustSize()

    # -------------------------------------------------------------------------
    # 数据加载
    # -------------------------------------------------------------------------

    def _refresh_tasks(self) -> None:
        self._refresh_btn.setEnabled(False)
        w = self._run(gt.list_tasks)
        w.result.connect(self._on_tasks_loaded)
        w.error.connect(lambda _: self._refresh_btn.setEnabled(True))

    def _on_tasks_loaded(self, result: tuple[list[dict], list[dict]]) -> None:
        self._pending, self._completed = result
        self._render_list()
        self._refresh_btn.setEnabled(True)

    # -------------------------------------------------------------------------
    # Tab & 渲染
    # -------------------------------------------------------------------------

    def _switch_tab(self, tab: str) -> None:
        self._tab = tab
        self._tab_pending_btn.setStyleSheet(
            self._TAB_ACTIVE if tab == "pending" else self._TAB_INACTIVE
        )
        self._tab_done_btn.setStyleSheet(
            self._TAB_ACTIVE if tab == "completed" else self._TAB_INACTIVE
        )
        self._update_tab_labels()
        self._render_list()

    def _update_tab_labels(self) -> None:
        p, c = len(self._pending), len(self._completed)
        self._tab_pending_btn.setText(
            f"{self._t('todo.tab_pending')} ({p})" if p else self._t("todo.tab_pending")
        )
        self._tab_done_btn.setText(
            f"{self._t('todo.tab_done')} ({c})" if c else self._t("todo.tab_done")
        )

    def _render_list(self) -> None:
        self._update_tab_labels()
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if w := item.widget():
                w.deleteLater()

        tasks = self._pending if self._tab == "pending" else self._completed

        if not tasks:
            empty = QLabel(self._t("todo.empty"))
            empty.setStyleSheet(
                "color:#BBB;font-size:13px;padding:30px;background:transparent;"
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._list_layout.addWidget(empty)
            return

        for task in tasks:
            item = _TaskItem(task, self._language)
            item.toggle_requested.connect(self._toggle_task)
            item.edit_requested.connect(self._edit_task)
            item.delete_requested.connect(self._delete_task)
            self._list_layout.addWidget(item)

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    def _toggle_task(self, task: dict, completing: bool) -> None:
        fn = gt.complete_task if completing else gt.uncomplete_task
        w = self._run(fn, task["id"])
        w.result.connect(lambda _: self._refresh_tasks())
        w.error.connect(lambda _: self._refresh_tasks())

    def _edit_task(self, task: dict, new_title: str) -> None:
        w = self._run(gt.update_task, task["id"], title=new_title)
        w.result.connect(lambda _: self._refresh_tasks())
        w.error.connect(lambda _: None)

    def _delete_task(self, task: dict) -> None:
        w = self._run(gt.delete_task, task["id"])
        w.result.connect(lambda _: self._refresh_tasks())
        w.error.connect(lambda _: None)

    def _add_task(self) -> None:
        title = self._add_input.text().strip()
        if not title:
            return
        self._add_input.clear()
        w = self._run(gt.create_task, title)
        w.result.connect(lambda _: self._refresh_tasks())
        w.error.connect(lambda _: None)

    # -------------------------------------------------------------------------
    # 工具
    # -------------------------------------------------------------------------

    def _run(self, fn, *args, **kwargs) -> _Worker:
        w = _Worker(fn, *args, **kwargs)
        self._workers.append(w)
        w.finished.connect(lambda: self._workers.remove(w) if w in self._workers else None)
        w.start()
        return w

    def position_near(self, pet_pos: QPoint, pet_width: int, pet_height: int) -> None:
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        self.adjustSize()
        x = pet_pos.x() - self.width() - 12
        if x < 0:
            x = pet_pos.x() + pet_width + 12
        # 底部与宠物底部对齐
        y = pet_pos.y() + pet_height - self.height()
        y = max(0, min(y, screen.height() - self.height() - 20))
        self.move(x, y)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_offset is not None
        ):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_level()

    def _apply_level(self, attempts: int = 5) -> None:
        from engine.macos_window import apply_macos_always_on_top
        if apply_macos_always_on_top(self):
            return
        if attempts > 1:
            QTimer.singleShot(100, lambda: self._apply_level(attempts - 1))
