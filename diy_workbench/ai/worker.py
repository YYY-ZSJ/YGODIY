"""QThread 只发信号，不持有或修改卡片及界面控件。"""

import copy
import threading
import time

from PyQt5.QtCore import QObject, QThread, pyqtSignal

from .client import Cancelled, RequestTimeout, stream_chat
from .conversation import run_conversation
from .providers import ServiceError
from .service_info import balance_spec, fetch_balance
from .task_budget import BudgetPause, for_task

OPERATION_TIMEOUT = 30


class ChatWorker(QThread):
    text_received = pyqtSignal(str)
    status_received = pyqtSignal(str)
    completed = pyqtSignal(dict)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()
    operation_requested = pyqtSignal(object)
    transcript_received = pyqtSignal(object)
    request_received = pyqtSignal(dict)
    compression_received = pyqtSignal(dict)
    reasoning_received = pyqtSignal(dict)

    def __init__(self, config, system, messages, probe=False, parent=None, tools=None, context_record=None, journal=None):
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        if journal is not None:
            self.config["_request_journal"] = journal
        self.system = system
        self.messages = list(messages)
        self.probe = probe
        self.cancel_flag = threading.Event()
        self.tools = list(tools or [])
        self.context_record = context_record
        self.segment_wire = (context_record or {}).get("wire", self.messages)
        self.active_length = len(self.messages)

    def _transcript(self, messages):
        wire = self.segment_wire + messages[self.active_length:]
        if self.context_record is not None:
            self.context_record = dict(self.context_record, wire=wire)
        self.transcript_received.emit(wire)

    def _fit_context(self, messages, config):
        from .context_budget import estimate, input_budget
        budget = input_budget(config)
        if budget and estimate(self.system, messages, self.tools, config.get("token_ratio", 1)) > budget:
            self.config = config
            self._prepare_context()
            return self.messages, self.config
        return messages, config

    def _prepare_context(self):
        from .context_budget import active_messages, compact, estimate, input_budget
        record = self.context_record
        if record is None:
            return
        self.messages = active_messages(record)
        budget = input_budget(self.config)
        ratio = self.config.get("token_ratio", 1)
        if self.config.get("compress_only") or (budget and estimate(self.system, self.messages, self.tools, ratio) > budget):
            self.status_received.emit("对话接近容量上限，正在压缩较早的完整轮次；原文仍保留。")
            summary = compact(self.config, record, self.cancel_flag, self.status_received.emit, self.request_received.emit,
                              self.reasoning_received.emit)
            record = dict(record, compression=summary)
            self.messages = active_messages(record)
            if budget and estimate(self.system, self.messages, self.tools, ratio) > budget:
                raise ServiceError("压缩后仍超过模型上下文容量，本次没有继续发送。请缩短本轮输入或调整高级设置。")
            self.compression_received.emit(summary)
            self.config = dict(self.config, cache_hashes=[], cache_previous_end=0)
        self.context_record = record
        self.segment_wire = record.get("wire", [])
        self.active_length = len(self.messages)

    def cancel(self):
        self.cancel_flag.set()

    def _execute(self, call, error_result=None):
        request = {"call": call, "ready": threading.Event(), "result": None,
                   "expires_at": time.monotonic() + OPERATION_TIMEOUT, "error_result": error_result}
        self.operation_requested.emit(request)
        while not request["ready"].wait(0.05):
            if self.cancel_flag.is_set():
                raise Cancelled()
            if time.monotonic() > request["expires_at"]:
                raise ServiceError("程序操作未能及时完成，请重试。")
        if self.cancel_flag.is_set():
            raise Cancelled()
        return request["result"]

    def run(self):
        try:
            self.config = for_task(self.config, (self.context_record or {}).get("resume"))
            if not self.probe:
                self._prepare_context()
            if self.config.get("compress_only"):
                self.completed.emit({"compression_only": True, "usage": {"input_tokens": 0, "output_tokens": 0}, "usage_known": True})
                return
            if self.tools and not self.probe:
                result = run_conversation(self.config, self.system, self.messages, self.cancel_flag,
                                          self.text_received.emit, self.status_received.emit, self.tools, self._execute,
                                          self._transcript, self.request_received.emit, self._fit_context, self.reasoning_received.emit,
                                          resume=(self.context_record or {}).get("resume"), on_tool_error=self._execute)
            else:
                result = stream_chat(self.config, self.system, self.messages, self.cancel_flag,
                                     self.text_received.emit, self.status_received.emit, self.probe,
                                     on_request=(lambda _: None) if self.probe else self.request_received.emit,
                                     on_reasoning=(lambda _: None) if self.probe else self.reasoning_received.emit)
                if not self.probe:
                    from .conversation import final_message
                    self._transcript(self.messages + [final_message(self.config["protocol"], result)])
            if self.cancel_flag.is_set():
                self.cancelled.emit()
            else:
                self.completed.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except (RequestTimeout, BudgetPause) as ex:
            if self.probe:
                self.failed.emit(str(ex))
            else:
                from .tool_loop import LoopGuard, paused
                self.completed.emit(paused(None, [], LoopGuard(), self.messages, [], {}, False,
                                           reason=str(ex), budget=self.config["_task_budget"]))
        except ServiceError as ex:
            self.failed.emit(str(ex))
        except Exception:
            # 第三方异常可能含 URL/认证数据，不能原样写日志或显示。
            self.failed.emit("AI 请求未能完成，请检查配置并重试。")
        finally:
            self.config["api_key"] = ""


class BalanceWorker(QThread):
    completed = pyqtSignal(dict)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        self.cancel_flag = threading.Event()

    def cancel(self):
        self.cancel_flag.set()

    def run(self):
        try:
            result = fetch_balance(self.config, self.cancel_flag)
            if not self.cancel_flag.is_set():
                self.completed.emit(result)
        except Exception:
            self.completed.emit({"supported": True, "error": "余额暂时无法查询；聊天不受影响。"})
        finally:
            self.config["api_key"] = ""


class BalanceMonitor(QObject):
    updated = pyqtSignal(dict)
    idle = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.workers = set()
        self.generation = 0

    def refresh(self, config):
        self.cancel()
        if not balance_spec(config):
            return
        worker = BalanceWorker(config, self)
        worker.generation = self.generation
        self.workers.add(worker)
        worker.completed.connect(self._result)
        worker.finished.connect(self._finished)
        worker.start()

    def _result(self, result):
        worker = self.sender()
        if worker.generation == self.generation and not worker.cancel_flag.is_set():
            self.updated.emit(result)

    def _finished(self):
        worker = self.sender()
        self.workers.discard(worker)
        worker.deleteLater()
        if not self.workers:
            self.idle.emit()

    def cancel(self):
        self.generation += 1
        for worker in self.workers:
            worker.cancel()

    def shutdown(self):
        self.cancel()
        for worker in self.workers:
            worker.wait()
