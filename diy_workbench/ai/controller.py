"""全局 AI 会话、服务设置与后台请求的调度；卡片及浏览操作在主线程执行。"""

import copy
import time
from pathlib import Path

from PyQt5.QtCore import QEvent, QObject, QTimer, Qt
from PyQt5.QtWidgets import QDialog, QMessageBox

from . import card_context, history, settings
from .file_jobs import FileJobs
from .session_controller import Sessions
from .request_context import prepare
from .context_meter import ContextMeter
from .model_catalog import ModelCatalog
from .change_coordinator import ChangeCoordinator
from .operations import Operations
from .providers import PROBE_MESSAGE
from .settings_dialog import ServiceDialog
from .service_info import balance_spec
from .worker import BalanceMonitor, ChatWorker
from .continuation import Continuation


def _load_resources():
    from .model_catalog import warm_cache
    data, notice = settings.load_settings()
    warm_cache()
    system = Path(__file__).with_name("system_prompt.md").read_text(encoding="utf-8")
    from .block_reference import reference
    system += "\n\n" + reference()
    system += "\n\n" + Path(__file__).with_name("test_guide.md").read_text(encoding="utf-8")
    return data, notice, system


class AssistantController(QObject):
    def __init__(self, app, panel):
        super().__init__(panel)
        self.app, self.panel = app, panel
        self.operations = Operations(app)
        from .risky_actions import RiskyController
        from .sandbox_controller import SandboxController
        self.tests = SandboxController(self)
        self.risky = RiskyController(self)
        self.risky = RiskyController(self)
        self.continuation = Continuation(self)
        self.changes = ChangeCoordinator(self)
        self.tab = None
        self.record = None
        self.dirty = set()
        self.loaded = False
        self.system = ""
        host = getattr(app, "_ai_dock", None)
        self.owns_files = host is None
        self.files = host.files if host is not None else FileJobs(self)
        self.files.failed.connect(panel.status.setText)
        self.worker = None
        self.target = None
        self.answer = None
        self.dialog = None
        self.closing = False
        self.request_config = None
        self.balance_source = None
        self.balance_monitor = BalanceMonitor(self)
        self.balance_monitor.updated.connect(self._balance_result)
        self.balance_monitor.idle.connect(self._close_when_idle)
        self.model_catalog = ModelCatalog(self)
        self.model_catalog.updated.connect(self._models_result)
        self.model_catalog.idle.connect(self._close_when_idle)
        self.data, self.notice = {"active": "custom", "profiles": {}, "consents": [], "ui": {}}, "正在读取 AI 设置……"
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(1000)
        self.save_timer.timeout.connect(self._save)
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(80)
        self.render_timer.timeout.connect(self._render)
        self.checkpoint_timer = QTimer(self)
        self.checkpoint_timer.setInterval(5000)
        self.checkpoint_timer.timeout.connect(self._save)
        self.sessions = Sessions(self)
        self.meter = ContextMeter(self)
        panel.send_requested.connect(self.send)
        panel.stop_requested.connect(self.cancel)
        panel.settings_requested.connect(self.open_settings)
        panel.input_changed.connect(self._input_changed)
        panel.new_requested.connect(self.new_conversation)
        panel.restore_requested.connect(self.restore_conversation)
        panel.retry_requested.connect(self.retry)
        panel.auto_apply_changed.connect(self._auto_apply_changed)
        panel.reasoning_changed.connect(self._reasoning_changed)
        panel.tests_requested.connect(self.tests.show_results)
        app.installEventFilter(self)
        self.files.idle.connect(self._close_when_idle)
        self.files.submit(_load_resources, callback=self._resources_loaded)
        self.sessions.initialize()
        self._profile_changed()

    def _profile_changed(self):
        self.balance_monitor.cancel()
        self.balance_source = None
        config = self.data["profiles"].get(self.data["active"])
        self.panel.set_service(config)
        self.panel.set_send_mode(self.data.get("ui", {}).get("send_with_enter", True))
        self.panel.set_balance(pending=bool(config and balance_spec(config)))
        self.panel.number_style = self.data.get("ui", {}).get("token_format", "grouped")
        self.sessions.store.number_style = self.panel.number_style
        self._update_context()

    def _balance_result(self, result):
        active = self.data["profiles"].get(self.data["active"]) or {}
        if self.balance_source and all(active.get(k) == v for k, v in self.balance_source.items()):
            self.panel.set_balance(result.get("text"), result.get("error", ""))

    def _resources_loaded(self, result, error):
        if self.closing:
            return
        if error:
            self.panel.status.setText("AI 设置或系统提示词未能读取，请检查安装目录。")
            return
        self.data, self.notice, self.system = result
        self.loaded = True
        self._profile_changed()
        self.panel.status.setText(self.notice or self._configuration_note())

    def bind(self, tab):
        self.tab = tab
        self._show_location()

    def _show_location(self):
        self.sessions.location()
        self._update_context()

    def _reasoning_changed(self, level):
        config = self.data["profiles"].get(self.data["active"])
        if config is not None:
            config["reasoning_level"] = level
            self.files.submit(settings.save_settings, copy.deepcopy(self.data))

    def _auto_apply_changed(self, enabled):
        if self.record is not None:
            self.record["auto_apply"] = enabled
            self._schedule_save()

    def _update_context(self):
        self.meter.refresh()

    def _configuration_note(self):
        config = self.data["profiles"].get(self.data["active"])
        return settings.validate(config) if config else "尚未配置 AI 服务，请点「服务设置」。"

    def _input_changed(self, text):
        if self.record is not None:
            self.record["input"] = text
            self._schedule_save()
            self._update_context()

    def _schedule_save(self):
        for record in (self.record, self.target):
            if record is not None:
                self.dirty.add(record["id"])
        self.save_timer.start()

    def _save(self):
        self.save_timer.stop()
        for uid in list(self.dirty):
            record = self.sessions.store.records.get(uid)
            if record is not None:
                self.sessions.store.save(record)
        self.dirty.clear()

    def _render(self):
        if self.record is not None:
            self.panel.show_history(self.record)

    def _consent(self, config):
        key = settings.consent_key(config)
        if key in self.data["consents"]:
            return True
        box = QMessageBox(self.dialog or self.panel)
        box.setWindowTitle("启用 AI 前的隐私提示")
        box.setTextFormat(Qt.PlainText)
        box.setText("卡片文字资料和对话将发送给你选择的服务商：\n%s\n\n"
                    "API Key 只在本机加密保存，并用于向该服务商认证，不写入对话、日志或卡包。"
                    "卡图不会发送。更换服务地址后会再次确认。是否同意？" % config["base_url"])
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        box.button(QMessageBox.Yes).setText("同意并启用")
        box.button(QMessageBox.No).setText("暂不启用")
        if box.exec_() != QMessageBox.Yes:
            return False
        self.data["consents"].append(key)
        self.files.submit(settings.save_settings, copy.deepcopy(self.data))
        return True

    def send(self, retry_text=None):
        if self.record is None or not self.loaded or self.worker is not None or self.closing:
            return
        text = retry_text if retry_text is not None else self.panel.input.toPlainText().strip()
        if not text:
            self.panel.status.setText("先输入想讨论的卡片创意或效果文字。")
            return
        if len(text) > history.MAX_INPUT_CHARS:
            self.panel.status.setText("一次输入最多 %d 个字符，请分段发送。" % history.MAX_INPUT_CHARS)
            return
        config = self.data["profiles"].get(self.data["active"])
        error = settings.validate(config) if config else self._configuration_note()
        if error:
            self.panel.status.setText(error)
            return
        if not self._consent(config):
            return
        record = self.record
        self.continuation.abandon(record)
        system = self.system
        mode = card_context.active_mode(self.app)
        user = history.append_message(record, "user", text)
        self.answer = history.append_message(record, "assistant", "", "streaming")
        try:
            owner = self.tab if record.get("attached", True) else None
            self.operations.changes.begin(owner, self.answer, mode["id"], record.get("auto_apply", False))
        except (ValueError, KeyError) as error:
            self.answer.update(status="failed", note=str(error))
            self.panel.show_session(self.tab, record)
            self.panel.status.setText(str(error))
            self._schedule_save()
            return
        for entry in (user, self.answer):
            entry.update(mode=mode["id"], mode_label=mode["label"], card_label=(owner or {}).get("title", ""), card_uid=(owner or {}).get("_card_uid", ""))
        self.answer["service"] = {k: config[k] for k in ("preset", "protocol", "model")}
        if retry_text is None:
            record["input"] = ""
        self.panel.show_session(self.tab, record)
        self._show_location()
        attachment = card_context.snapshot(self.app) if owner is not None else None
        system, messages, self.request_tools = prepare(record, config, system, self.operations.tools(), user, attachment)
        self.target = record
        if record.get("title") == "新对话":
            record["title"] = text[:28]
        self._start(config, system, messages)
        self.checkpoint_timer.start()
        self._schedule_save()

    def _start(self, config, system, messages, probe=False, resume=None):
        context_record = None
        if not probe:
            config = self.meter.config(config, self.target)
            context_record = {key: self.target[key] for key in ("wire", "compression") if key in self.target}
            context_record["resume"] = resume
        self.request_config = copy.deepcopy(config)
        journal = None
        if not probe:
            from .request_journal import RequestJournal
            journal = RequestJournal(settings.settings_path().parent / "AI会话" / "_requests", self.target["id"], self.answer["id"])
        worker = self.worker = ChatWorker(config, system, messages, probe, self,
                                         tools=None if probe else self.request_tools, context_record=context_record, journal=journal)
        worker.text_received.connect(self._text)
        worker.status_received.connect(self._status)
        worker.completed.connect(self._completed)
        worker.failed.connect(self._failed)
        worker.cancelled.connect(self._cancelled)
        worker.operation_requested.connect(self._operation)
        worker.transcript_received.connect(self._transcript)
        worker.request_received.connect(self.meter.request)
        worker.compression_received.connect(self.meter.compressed)
        worker.reasoning_received.connect(self._reasoning)
        worker.finished.connect(self._finished)
        self.panel.set_busy(True, True)
        if probe:
            self.dialog.set_testing(True, "正在检查连接及工具调用能力……")
        else:
            self.panel.status.setText("正在生成……")
            if resume is None:
                self.answer["events"] = ["开始流式对话：%s" % config["model"]]
        if probe:
            worker.start()
        else:
            def persisted(_metadata, error):
                if self.worker is not worker:
                    return
                if error or self.closing:
                    self._finish_answer("failed", "会话未能保存，本次没有发送请求。" if error else "程序已关闭，本次未发送。")
                    worker.config["api_key"] = ""
                    self._finished()
                    return
                worker.start()
            self.sessions.store.save(self.target, callback=persisted)

    def _text(self, text):
        if self.worker is None or self.worker.cancel_flag.is_set() or self.worker.probe:
            return
        if self._target_exists() and self.answer is not None:
            self.answer["text"] += text
            if not self.render_timer.isActive():
                self.render_timer.start()
            self._schedule_save()

    def _reasoning(self, data):
        if self.worker is None or self.worker.probe or not self._target_exists() or self.answer is None:
            return
        parts = self.answer.setdefault("reasoning_parts", [])
        if not parts and self.worker.cancel_flag.is_set():
            return
        if not parts or parts[-1]["id"] != data["id"]:
            parts.append({"id": data["id"], "text": "", "seconds": 0.0, "active": False, "purpose": data.get("purpose", "chat")})
        part = parts[-1]
        if not self.worker.cancel_flag.is_set():
            part["text"] += data["text"]
        part.update(seconds=data["seconds"], active=data["active"] and not self.worker.cancel_flag.is_set())
        if not self.render_timer.isActive():
            self.render_timer.start()
        self._schedule_save()

    def _status(self, text):
        if self.worker is not None and self.worker.cancel_flag.is_set():
            return
        if self.answer is not None and self._target_exists():
            self.answer.setdefault("events", []).append(text)
            self._render()
        if self.dialog is not None and self.worker is not None and self.worker.probe:
            self.dialog.status.setText(text)
        else:
            self.panel.status.setText(text)

    def _target_exists(self):
        return self.target is not None and self.target.get("id") not in self.sessions.store.deleted

    def _transcript(self, messages):
        if self._target_exists():
            self.target["wire"] = messages
            self._schedule_save()

    def _operation(self, request):
        deferred = False
        try:
            worker = self.sender()
            if (worker is not self.worker or worker.cancel_flag.is_set() or self.closing
                    or time.monotonic() > request["expires_at"] or not self._target_exists()):
                result = {"ok": False, "error": "请求已停止、超时或原目标已不存在，操作未执行。"}
            else:
                call = request["call"]
                self.answer["tool_steps"] = self.answer.get("tool_steps", 0) + 1
                result = request.get("error_result") or self.operations.execute(call["name"], call["arguments"])
                result = self.tests.resolve(request, result)
                if result is not None:
                    result = self.risky.resolve(request, result)
                if result is None:
                    deferred = True
                    return
            self._operation_done(request, result)
        except Exception:
            request["result"] = {"ok": False, "error": "操作未能完成，请检查当前页面后重试。"}
        finally:
            if not deferred:
                request["ready"].set()

    def _operation_done(self, request, result):
        call = request["call"]
        if self.answer is not None and self._target_exists():
            detail = "%s(%s) · %s" % (call["name"], call["arguments"], "完成" if result["ok"] else result["error"])
            if result.get("risk") == "modify":
                data = result["data"]
                detail = "%s · %s\n%s" % (call["name"], "已自动应用，可撤销" if data.get("status") == "applied" else "候选待应用", data.get("note", ""))
                if data.get("affected_modes"):
                    detail += "\n会同时影响的模式：" + "、".join(data["affected_modes"])
            self.answer.setdefault("events", []).append(detail)
            self._render()
            self._schedule_save()
        request["result"] = result

    def _finish_answer(self, status, note, result=None):
        if self.answer is None or not self._target_exists():
            return
        self.answer["status"] = status
        for part in self.answer.get("reasoning_parts", []):
            part["active"] = False
        self.answer["note"] = note or self.answer.get("note", "")
        if "usage" not in self.answer:
            from .usage import accumulate
            usage = (result or {}).get("usage") or {}
            usage = dict(usage, input_known=bool((result or {}).get("usage_known")),
                         output_known=bool((result or {}).get("usage_known")))
            self.answer["usage"] = accumulate({}, usage)
            self.target["usage"] = accumulate(self.target.get("usage"), usage)
            self.answer["usage_known"] = bool((result or {}).get("usage_known"))
        self._render()
        self._schedule_save()
        self._update_context()

    def _completed(self, result):
        if self.worker.cancel_flag.is_set():
            self._cancelled()
            return
        if self.worker.probe:
            usage = result["usage"]
            self._status("连接与工具调用检查通过（输入 %d / 输出 %d token%s）。" % (
                usage["input_tokens"], usage["output_tokens"], "，服务未完整返回用量" if not result["usage_known"] else ""))
        else:
            if self.continuation.outcome(result):
                return
            note = "对话已压缩，原文保存在本地。" if result.get("compression_only") else "回复达到输出上限，可继续追问。" if result.get("truncated") else ""
            evidence_notice = self.tests.bind_evidence(self.answer)
            if evidence_notice:
                note = (note + " " + evidence_notice).strip()
            self._finish_answer("complete", note, result)
            if not self._target_exists():
                message = "会话已删除，本次回复未保存。"
            elif self.record is not self.target:
                message = "「%s」的回复已完成，可在会话列表查看。" % self.target.get("title", "会话")
            else:
                report = self.answer.get("changes") or {}
                message = note or ("回复完成。已应用的修改可整批撤销。" if report.get("state") == "applied" else
                                   "回复完成。请检查候选后点「应用整批」。" if report.get("rows") else "回复完成。卡片内容未修改。")
            self.panel.status.setText(message)

    def _failed(self, message):
        if self.worker.cancel_flag.is_set():
            self._cancelled()
            return
        if self.worker.probe:
            self._status(message)
        else:
            self._finish_answer("failed", message)
            self.panel.status.setText(message)

    def _cancelled(self):
        self._status("请求已停止。")
        if self.answer is not None:
            report = self.answer.get("changes") or {}
            note = "请求已停止，保留已收到的部分回复。"
            if report.get("rows"):
                note += " 已应用部分仍可整批撤销。" if report["state"] == "applied" else " 已生成的候选仍待玩家检查和应用。"
            self._finish_answer("cancelled", note)

    def _finished(self):
        worker = self.worker
        self.worker = None
        if not worker.probe:
            self.operations.changes.finish(suspended=bool((self.answer or {}).get("continuation")))
        if worker.cancel_flag.is_set() and (worker.probe or self.record is self.target):
            self.panel.status.setText("请求已停止。")
        if self.dialog is not None:
            self.dialog.set_testing(False, "测试已停止。" if worker.cancel_flag.is_set() else "")
        self._save()
        self.checkpoint_timer.stop()
        self.answer, self.target = None, None
        self.panel.set_busy(False, True)
        self._update_context()
        worker.deleteLater()
        if not self.closing and self.request_config:
            self.balance_source = {k: self.request_config.get(k) for k in ("protocol", "base_url", "api_key")}
            self.balance_monitor.refresh(self.request_config)
        self.request_config = None
        self._close_when_idle()

    def _close_when_idle(self):
        if (self.closing and self.worker is None and self.tests.worker is None and not self.balance_monitor.workers
                and not self.model_catalog.workers and not self.files.pending):
            QTimer.singleShot(0, self.app.close)

    def new_conversation(self):
        self.sessions.new()

    def restore_conversation(self, uid):
        self._save()
        self.sessions.store.open(uid)

    def retry(self, uid):
        self.continuation.retry(uid)

    def cancel(self):
        self.tests.cancel()
        if self.worker is not None:
            self.worker.cancel()
            self.panel.status.setText("已请求停止，正在等待网络读取结束……")

    def open_settings(self):
        if not self.loaded or self.worker is not None:
            return
        dialog = self.dialog = ServiceDialog(self.data, self.notice, self.panel)
        dialog.test_requested.connect(self._test)
        dialog.stop_requested.connect(self.cancel)
        dialog.models_requested.connect(self.model_catalog.refresh)
        if dialog.exec_() == QDialog.Accepted:
            updated = copy.deepcopy(self.data)
            updated["active"] = dialog.current
            updated["profiles"] = dialog.profiles
            updated["ui"] = dialog.ui_value()
            self.data, self.notice = updated, ""
            self.files.submit(settings.save_settings, copy.deepcopy(updated))
            self._profile_changed()
            self.panel.status.setText("AI 服务设置已更新，正在保存。")
        elif self.worker is not None:
            self.cancel()
        self.model_catalog.cancel()
        self.dialog = None
        dialog.deleteLater()

    def _models_result(self, result):
        if self.dialog is not None:
            self.dialog.show_models(result)

    def _test(self, config):
        if not self.closing and self.worker is None and self._consent(config):
            self.answer, self.target = None, None
            self._start(config, "你在执行无副作用的连接检查。", [{"role": "user", "content": PROBE_MESSAGE}], True)

    def eventFilter(self, watched, event):
        if watched is self.app and event.type() == QEvent.Close and (self.worker is not None or self.tests.worker is not None or self.balance_monitor.workers or self.model_catalog.workers or self.files.pending):
            self.closing = True
            self._save()
            self.cancel()
            self.balance_monitor.cancel()
            self.model_catalog.cancel()
            event.ignore()
            return True
        if watched is self.app and event.type() == QEvent.Close:
            QTimer.singleShot(0, self._release_closed)
        return super().eventFilter(watched, event)

    def _release_closed(self):
        if not self.app.isVisible():
            self.operations.changes.release()

    def shutdown(self):
        self.closing = True
        self.meter.timer.stop()
        self.cancel()
        if self.worker is not None:
            self.worker.wait()  # 操作系统直接退出时也等协作取消，避免 QThread 尚运行就被销毁。
        self.balance_monitor.shutdown()
        self.model_catalog.shutdown()
        self.tests.shutdown()
        self.checkpoint_timer.stop()
        self.save_timer.stop()
        self._save()
        self.operations.changes.release()
        if self.owns_files:
            self.files.shutdown()
