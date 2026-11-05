"""主窗口的外围：程序图标、Windows 任务栏身份、窗口不超出屏幕（main.YuGiOhApp 调用）。

由补丁分片 p09、p15 整理而来。
"""

import os
import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from common import _app_dir


def _app_icon_path():
    for root in (_app_dir(), getattr(sys, "_MEIPASS", "")):
        if not root:
            continue
        for name in ("YGODIY.ico", "YGODIY-icon.png", os.path.join("mold", "YGODIY.ico")):
            path = os.path.join(root, name)
            if os.path.exists(path):
                return path
    return None


def _install_application_identity():
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "YGODIY.YGODIY.2.0.0"
            )
        except Exception:
            pass


def _apply_application_icon(window=None):
    icon_path = _app_icon_path()
    if not icon_path:
        return
    icon = QIcon(icon_path)
    if icon.isNull():
        return
    app_instance = QApplication.instance()
    if app_instance is not None:
        try:
            app_instance.setWindowIcon(icon)
        except Exception:
            pass
        for top_level in app_instance.topLevelWidgets():
            try:
                top_level.setWindowIcon(icon)
            except Exception:
                pass
    if window is not None:
        try:
            window.setWindowIcon(icon)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Keep the main window inside the available screen and make the RD rarity
# popup show all options even when its combo box is near the screen bottom.
# ---------------------------------------------------------------------------
def _fit_main_window_to_screen(window):
    if window is None:
        return
    try:
        if window.isMaximized() or window.isFullScreen():
            return
        app = QApplication.instance()
        if app is None:
            return
        anchor = window.frameGeometry().center()
        screen = app.screenAt(anchor) or app.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        geometry = window.frameGeometry()
        width = min(geometry.width(), available.width())
        height = min(geometry.height(), available.height())
        if width != geometry.width() or height != geometry.height():
            window.resize(int(width), int(height))
            geometry = window.frameGeometry()
        x = max(available.left(), min(geometry.x(), available.right() - geometry.width() + 1))
        y = max(available.top(), min(geometry.y(), available.bottom() - geometry.height() + 1))
        if x != geometry.x() or y != geometry.y():
            window.move(int(x), int(y))
    except Exception:
        pass
