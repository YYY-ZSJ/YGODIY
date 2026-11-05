"""程序日志与崩溃保护。

- 普通日志写进程序目录下的「制卡器标签页.log」；
- 崩溃保护：未捕获的 Python 异常写日志后程序继续运行（否则 PyQt 会直接 qFatal 结束程序，
  而 pythonw 没有控制台，以前每次闪退都毫无记录）；原生崩溃（访问冲突等）由 faulthandler
  把调用栈写进「崩溃记录.log」；Qt 自身的 critical / fatal 消息也写日志。
"""
import faulthandler
import os
import sys
import threading
import time
import traceback

LOG_NAME = "制卡器标签页.log"
CRASH_LOG_NAME = "崩溃记录.log"
_EXCEPTION_LOG_LIMIT = 200  # 同一次运行最多记录的异常数，防止异常风暴把日志撑爆
_state = {"count": 0, "file": None}


def app_dir():
    """程序目录：由启动器 fast_launch.py 通过环境变量告知，否则取解释器所在目录。"""
    return os.environ.get("YGODIY_APP_DIR") or os.path.dirname(os.path.abspath(sys.executable))


def log(message):
    try:
        with open(os.path.join(app_dir(), LOG_NAME), "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except Exception:
        pass


def log_exception(title, detail=None):
    """带时间戳记录一次异常；detail 缺省时取当前正在处理的异常。"""
    _state["count"] += 1
    if _state["count"] > _EXCEPTION_LOG_LIMIT:
        return
    if detail is None:
        detail = traceback.format_exc()
    log("[%s] %s\n%s" % (time.strftime("%Y-%m-%d %H:%M:%S"), title, detail.rstrip()))


def _excepthook(exc_type, exc_value, exc_tb):
    try:
        if issubclass(exc_type, KeyboardInterrupt):
            return
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log_exception("未捕获的异常（已拦截，程序继续运行）:", detail)
    except Exception:
        pass


def _thread_excepthook(args):
    try:
        detail = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        log_exception("后台线程 %s 未捕获的异常:" % getattr(args.thread, "name", "?"), detail)
    except Exception:
        pass


def _qt_message_handler(mode, context, message):
    try:
        from PyQt5.QtCore import QtCriticalMsg, QtFatalMsg

        if mode in (QtCriticalMsg, QtFatalMsg):
            where = ""
            if context is not None and context.file:
                where = " (%s:%s)" % (context.file, context.line)
            log_exception("Qt %s 消息%s:" % ("致命" if mode == QtFatalMsg else "严重", where), str(message))
    except Exception:
        pass


def install_crash_guard():
    # 回归测试 / 离屏诊断脚本会自己设置 excepthook 来收集异常，不覆盖它们。
    if sys.excepthook is not sys.__excepthook__:
        return
    sys.excepthook = _excepthook
    try:
        threading.excepthook = _thread_excepthook
    except Exception:
        pass
    try:
        handle = open(os.path.join(app_dir(), CRASH_LOG_NAME), "a", encoding="utf-8")
        handle.write("\n==== 启动 %s pid=%d ====\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), os.getpid()))
        handle.flush()
        faulthandler.enable(file=handle, all_threads=True)
        _state["file"] = handle  # 文件对象必须一直存活，faulthandler 只保存文件描述符
    except Exception:
        pass
    try:
        from PyQt5.QtCore import qInstallMessageHandler

        qInstallMessageHandler(_qt_message_handler)
    except Exception:
        pass
