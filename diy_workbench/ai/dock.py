"""局部 QMainWindow 停靠容器；保留 QWidget 外壳和原有 hbox 业务布局。"""

from PyQt5.QtCore import QByteArray, QEvent, QObject, QTimer, Qt
from PyQt5.QtGui import QResizeEvent
from PyQt5.QtWidgets import QDockWidget, QHBoxLayout, QMainWindow, QToolButton, QVBoxLayout, QWidget

from .file_jobs import FileJobs, read_json, write_json


def make_shell(app):
    shell = QMainWindow(app)
    shell.setWindowFlags(Qt.Widget)
    central = QWidget(shell)
    central.setLayout(app.hbox)
    shell.setCentralWidget(central)
    root = QVBoxLayout(app)
    root.setContentsMargins(0, 0, 0, 0)
    root.addWidget(shell)
    app._workspace_shell = shell


def _layout_path():
    from .settings import settings_path
    return settings_path().with_name(settings_path().name + ".layout")


class AssistantDock(QObject):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.controller, self.manager = app, None, None
        self.files = FileJobs(self)
        self.preferred_width = 400
        self.preferred_floating, self.preferred_geometry = False, ""
        self.refit_timer = QTimer(self)
        self.refit_timer.setSingleShot(True)
        self.refit_timer.timeout.connect(self._refit_now)
        self.bind_timer = QTimer(self)
        self.bind_timer.setSingleShot(True)
        self.bind_timer.timeout.connect(self._bind_current)
        self._last_geometry = None
        self.dock = QDockWidget("伊格尼斯", app._workspace_shell)
        self.dock.setObjectName("global_ai_dock")
        self.dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea)
        app._workspace_shell.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.dock.hide()
        self._add_toggle()
        self.dock.visibilityChanged.connect(self._visibility)
        self.dock.topLevelChanged.connect(lambda *_: QTimer.singleShot(0, self._refit))
        self.bind_manager()
        self._restore_layout()
        app.installEventFilter(self)

    def _add_toggle(self):
        combo = self.app.combo_box
        parent = combo.parentWidget()
        layout = parent.layout()
        index = layout.indexOf(combo)
        layout.removeWidget(combo)
        bar = QWidget(parent)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(combo, 1)
        self.toggle = QToolButton()
        self.toggle.setText("伊格尼斯")
        self.toggle.setToolTip("展开或收起全局 AI 面板")
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self.set_visible)
        row.addWidget(self.toggle)
        layout.insertWidget(index, bar)
        from diy_workbench.card_text_button import CardTextButton
        row.insertWidget(1, CardTextButton(self.app))

    def set_visible(self, shown):
        created = shown and self.controller is None
        if created:
            from .controller import AssistantController
            from .panel import AssistantPanel
            panel = AssistantPanel()
            self.dock.setWidget(panel)
            self.controller = AssistantController(self.app, panel)
            self.bind_manager()
            self.context_changed()
        self.dock.setVisible(shown)
        if created:
            self.app._workspace_shell.resizeDocks([self.dock], [self.preferred_width], Qt.Horizontal)
            if self.preferred_floating:
                self.dock.setFloating(True)
                self.dock.restoreGeometry(QByteArray.fromBase64(self.preferred_geometry.encode("ascii")))
        self._refit()

    def _visibility(self, shown):
        self.toggle.blockSignals(True)
        self.toggle.setChecked(shown)
        self.toggle.blockSignals(False)
        self._refit()

    def _refit(self):
        self.refit_timer.start(0)

    def _refit_now(self):
        geometry = (self.app.size(), self.dock.isVisible(), self.dock.isFloating(), self.dock.size())
        if geometry == self._last_geometry:
            return
        self._last_geometry = geometry
        self.app.resizeEvent(QResizeEvent(self.app.size(), self.app.size()))

    def bind_manager(self):
        manager = getattr(self.app, "card_tab_manager", None)
        if manager is not None and manager is not self.manager:
            self.manager = manager
            manager.tab_list.currentRowChanged.connect(self.context_changed)
            manager.pack_list.currentRowChanged.connect(self.context_changed)
        self.context_changed()

    def context_changed(self, *_):
        if self.controller is not None:
            self.bind_timer.start(0)

    def _bind_current(self):
        from .card_context import current
        self.controller.bind(current(self.app)[0])

    def editor_applied(self, tab):
        if self.controller is not None:
            self.controller.operations.changes.observe_created(tab)

    def _restore_layout(self):
        def restored(saved, error):
            if not isinstance(saved, dict):
                return
            if saved.get("area") == "left":
                self.app._workspace_shell.addDockWidget(Qt.LeftDockWidgetArea, self.dock)
            width = saved.get("width", 400)
            if type(width) is int:
                self.preferred_width = max(320, min(width, 900))
            self.preferred_floating = saved.get("floating") is True
            geometry = saved.get("geometry", "")
            self.preferred_geometry = geometry if isinstance(geometry, str) and geometry.isascii() else ""
            if saved.get("visible") is True:
                QTimer.singleShot(0, lambda: self.set_visible(True))
        self.files.submit(read_json, _layout_path(), {}, callback=restored)

    def save_layout(self):
        area = self.app._workspace_shell.dockWidgetArea(self.dock)
        data = {"visible": not self.dock.isHidden(), "width": self.dock.width(),
                "area": "left" if area == Qt.LeftDockWidgetArea else "right",
                "floating": self.dock.isFloating(), "geometry": bytes(self.dock.saveGeometry().toBase64()).decode("ascii")}
        self.files.submit(write_json, _layout_path(), data)

    def eventFilter(self, watched, event):
        if watched is self.app and event.type() == QEvent.Close:
            self.save_layout()
        return super().eventFilter(watched, event)


def install(app):
    host = app._ai_dock = AssistantDock(app)
    from PyQt5.QtWidgets import QApplication
    def shutdown():
        if host.controller is not None:
            host.controller.shutdown()
        host.save_layout()
        host.files.shutdown()
    QApplication.instance().aboutToQuit.connect(shutdown)
    return host
