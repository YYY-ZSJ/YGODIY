"""AI 文件的顺序后台队列。调用方只提交已冻结的纯数据，不传活动控件。"""

import json
import os
import time
import uuid
from queue import Empty, Queue

from PyQt5.QtCore import QObject, QThread, pyqtSignal

REPLACE_ATTEMPTS = 6
REPLACE_RETRY_SECONDS = .02


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(REPLACE_ATTEMPTS):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(REPLACE_RETRY_SECONDS)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


class _FileWorker(QThread):
    result = pyqtSignal(int, object, str)

    def __init__(self, parent):
        super().__init__(parent)
        self.jobs = Queue()

    def run(self):
        while True:
            try:
                job = self.jobs.get_nowait()
            except Empty:
                return
            number, function, args = job
            try:
                self.result.emit(number, function(*args), "")
            except Exception:
                self.result.emit(number, None, "文件操作失败，请检查目录权限或磁盘空间。")


class FileJobs(QObject):
    failed = pyqtSignal(str)
    idle = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.callbacks, self.serial, self.stopped = {}, 0, False
        self.running = False
        self.worker = _FileWorker(self)
        self.worker.result.connect(self._result)
        self.worker.finished.connect(self._finished)

    @property
    def pending(self):
        return bool(self.callbacks) or self.worker.isRunning() or not self.worker.jobs.empty()

    def submit(self, function, *args, callback=None):
        if self.stopped:
            return
        self.serial += 1
        self.callbacks[self.serial] = callback
        self.worker.jobs.put((self.serial, function, args))
        if not self.running:
            self.running = True
            self.worker.start()
        return self.serial

    def _finished(self):
        self.running = False
        if not self.stopped and not self.worker.jobs.empty():
            self.running = True
            self.worker.start()
        elif not self.callbacks:
            self.idle.emit()

    def _result(self, number, result, error):
        callback = self.callbacks.pop(number, None)
        if callback:
            callback(result, error)
        elif error:
            self.failed.emit(error)
        if not self.callbacks:
            self.idle.emit()

    def shutdown(self):
        self.stopped = True
        self.worker.wait()
        if not self.worker.jobs.empty():
            self.worker.start()
            self.worker.wait()
