"""程序启动流程：单实例保护、启动加载界面。由 main.main() 调用。"""
import os
import sys
import time

import applog
from utils import rpath

# ---------------------------------------------------------------- 单实例保护
# YGODIY_2.0.0.exe 是 .NET 启动壳，会直接拉起 .app.exe，不做任何重复检查。上一次的窗口没退干净
# （或用户连点两次）就会再起一个实例，屏幕上出现两个一模一样的窗口。
# 用文件锁判定：拿不到锁说明已有实例在运行，明确提示用户而不是静默再开一个。
# 锁在进程结束（含异常退出）时由系统释放，不会因为上次崩溃而永久锁死。

INSTANCE_LOCK_NAME = ".ygodiy-instance.lock"
_instance_lock = []  # 锁文件要一直开着到进程结束


def single_instance_guard():
    """返回 True 表示可以继续启动；False 表示已有实例在运行。

    回归测试 / 诊断导出是无人值守启动的，设 YGODIY_ALLOW_MULTI_INSTANCE 跳过本判定。"""
    if os.environ.get("YGODIY_ALLOW_MULTI_INSTANCE"):
        return True
    try:
        import msvcrt
    except Exception:
        return True
    lock_path = os.path.join(applog.app_dir() or os.getcwd(), INSTANCE_LOCK_NAME)
    try:
        handle = open(lock_path, "a+b")
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    except Exception:
        return True
    _instance_lock.append(handle)
    return True


def notify_already_running():
    """尽量用图形提示；失败就退回标准错误。"""
    message = (
        "YGODIY 已经在运行了。\n\n"
        "请先关掉那个窗口（任务栏上标题为「YGODIY 2.0.0」的那个），再重新打开。\n"
        "如果确定没有窗口却仍提示，删掉程序目录下的 " + INSTANCE_LOCK_NAME + " 再试。"
    )
    if not os.environ.get("YGODIY_SUPPRESS_DIALOG"):  # 无人值守时不弹窗，避免卡住
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, message, "YGODIY", 0x40)
            return
        except Exception:
            pass
    try:
        sys.stderr.write(message + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- 启动加载界面
# 主窗口构建是同步阻塞的，期间进度条无法刷新，所以进度条「分段推进」：
# 构建前先动画推进一段，构建完成后再推到 100% 并淡出。

SPLASH_LOGO = "mold/splash_logo.png"
SPLASH_TITLE = "正在加载卡牌数据…"
_SPLASH_BEFORE_MS = 320
_SPLASH_AFTER_MS = 560
_SPLASH_TICK_S = 0.008
_SPLASH_PAD_X = 48
_SPLASH_PAD_TOP = 52
_SPLASH_PAD_BOTTOM = 92
_SPLASH_BAR_INSET = 72
_SPLASH_BAR_HEIGHT = 12
_SPLASH_BG_COLOR = "#ffffff"


def _splash_pixmap():
    """把 logo 画到一张白底画布上（直接用 logo 是透明背景，叠在桌面上很难看）。"""
    from PyQt5.QtGui import QColor, QPainter, QPixmap

    logo = QPixmap(rpath(SPLASH_LOGO))
    if logo.isNull():
        return None
    width = logo.width() + _SPLASH_PAD_X * 2
    height = logo.height() + _SPLASH_PAD_TOP + _SPLASH_PAD_BOTTOM
    canvas = QPixmap(width, height)
    canvas.fill(QColor(_SPLASH_BG_COLOR))
    painter = QPainter(canvas)
    painter.drawPixmap(_SPLASH_PAD_X, _SPLASH_PAD_TOP, logo)
    painter.end()
    return canvas


def _splash_widget():
    """创建加载界面。失败返回 (None, None)，调用方回退到无加载界面。"""
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QLabel, QProgressBar, QSplashScreen
    except Exception:
        return None, None
    pixmap = _splash_pixmap()
    if pixmap is None:
        return None, None
    splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
    hint = QLabel(SPLASH_TITLE, splash)
    hint.setStyleSheet("color: #556070; font-size: 13px;")
    hint.setGeometry(_SPLASH_BAR_INSET, pixmap.height() - _SPLASH_PAD_BOTTOM + 14, pixmap.width(), 22)
    bar = QProgressBar(splash)
    bar.setTextVisible(False)
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setGeometry(
        _SPLASH_BAR_INSET,
        pixmap.height() - _SPLASH_PAD_BOTTOM + 44,
        max(80, pixmap.width() - _SPLASH_BAR_INSET * 2),
        _SPLASH_BAR_HEIGHT,
    )
    bar.setStyleSheet(
        "QProgressBar { background: #e3e8ef; border: none; border-radius: %dpx; }"
        "QProgressBar::chunk { background: #2f7fd8; border-radius: %dpx; }"
        % (_SPLASH_BAR_HEIGHT // 2, _SPLASH_BAR_HEIGHT // 2)
    )
    return splash, bar


def _pump_progress(bar, start, end, milliseconds):
    """在给定时间内把进度条从 start 推到 end，并保持界面响应。"""
    from PyQt5.QtCore import QCoreApplication

    started = time.time()
    while True:
        elapsed = (time.time() - started) * 1000.0
        if elapsed >= milliseconds:
            break
        if bar is not None:
            bar.setValue(int(round(start + (end - start) * (elapsed / milliseconds))))
        QCoreApplication.processEvents()
        time.sleep(_SPLASH_TICK_S)
    if bar is not None:
        bar.setValue(int(end))


def build_with_splash(build):
    """显示加载界面，调用 build() 构建主窗口并返回它。加载界面出错时退回为直接构建。"""
    splash, bar = _splash_widget()
    if splash is None:
        return build()
    window = None
    try:
        splash.show()
        _pump_progress(bar, 0, 25, _SPLASH_BEFORE_MS)
        window = build()
        _pump_progress(bar, 25, 100, _SPLASH_AFTER_MS)
    except Exception:
        applog.log("加载界面异常:\n" + __import__("traceback").format_exc())
        if window is None:
            window = build()
    finally:
        try:
            if window is not None:
                splash.finish(window)
            splash.close()
        except Exception:
            pass
    return window
