"""上下文与用量的界面协调，计数在文件/计算队列，网络仍由聊天线程执行。"""

import copy

from PyQt5.QtCore import QObject, QTimer

from . import card_context, history, settings
from .context_budget import active_messages, estimate_parts
from .model_catalog import cache_key, model_metadata
from .model_info import limits
from .request_context import stable_json
from .usage import accumulate, hit_rate, number
from .usage_view import UsageDialog
from .transcript_view import TranscriptDialog
from .context_view import ContextDialog, position_popup


class ContextMeter(QObject):
    def __init__(self, controller):
        super().__init__(controller)
        self.controller, self.panel = controller, controller.panel
        self.generation, self.dialog = 0, None
        self.context_dialog = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(180)
        self.timer.timeout.connect(self._estimate)
        self.panel.usage_requested.connect(self.show_usage)
        self.panel.compress_requested.connect(self.compress)
        self.panel.summary_requested.connect(self.show_summary)
        self.panel.context_requested.connect(self.show_context)
        self.panel.stats_requested.connect(self.show_stats)

    def config(self, config, record):
        result = dict(config, context_limits=limits(config, model_metadata(config)), conversation_id=record["id"])
        previous = record.get("last_request") or {}
        same = (previous.get("model") == config.get("model") and previous.get("protocol") == config.get("protocol")
                and previous.get("scope") == cache_key(config))
        result.update(cache_previous_end=previous.get("request_end", 0) if same else 0,
                      cache_previous_finished_at=previous.get("finished_at") if same else None,
                      cache_hashes=previous.get("cache_hashes", []) if same else [])
        measured = previous.get("usage", {}).get("input_tokens")
        if same and measured and previous.get("estimate"):
            result["token_ratio"] = max(.3, min(3, measured / previous["estimate"]))
        return result

    def refresh(self):
        self.timer.start()

    def _estimate(self):
        ctl = self.controller
        if ctl.record is None or not ctl.loaded:
            return
        record = ctl.record
        config = self.config(ctl.data["profiles"].get(ctl.data["active"]) or {}, record)
        prefix = record.get("prefix") or {"system": ctl.system, "tools": ctl.operations.tools()}
        messages = active_messages(record)
        draft = record.get("input", "")
        if draft:
            attachment = card_context.snapshot(ctl.app) if record.get("attached", True) and ctl.tab is not None else None
            messages.append({"role": "user", "content": draft + (stable_json(attachment) if attachment else "")})
        self.generation += 1
        generation, uid = self.generation, record["id"]
        def counted(parts, error):
            if error or generation != self.generation or ctl.record is None or ctl.record["id"] != uid:
                return
            self.panel.set_context(parts["total"], config["context_limits"], bool(record.get("compression")), parts)
            self._refresh_context_dialog()
        ctl.files.submit(estimate_parts, prefix["system"], messages, prefix["tools"], config.get("token_ratio", 1), callback=counted)

    def request(self, info):
        ctl = self.controller
        if not ctl._target_exists() or ctl.answer is None:
            return
        record, answer = ctl.target, ctl.answer
        record["requests"] = record.get("requests", []) + [info]
        record["usage"] = accumulate(record.get("usage"), info["usage"], info.get("cost"))
        answer["usage"] = accumulate(answer.get("usage"), info["usage"], info.get("cost"))
        answer["usage_known"] = not answer["usage"].get("unknown_calls")
        if info.get("purpose") != "compression":
            record["last_request"] = info
        detail = "请求 %d · 缓存命中 %s / 未命中 %s 词元 · 命中率 %s" % (len(record["requests"]),
            number(info["usage"].get("cache_read_tokens")), number((info["usage"].get("uncached_input_tokens") or 0) +
            (info["usage"].get("cache_write_tokens") or 0)) if info["usage"].get("cache_known") else "未返回", hit_rate(info["usage"]))
        answer.setdefault("events", []).append(detail)
        if info.get("record_warning"):
            answer["events"].append(info["record_warning"])
        if info.get("cache_debug") and not record.get("cache_notice_shown"):
            record["cache_notice_shown"] = True
            if not any(request.get("cache_debug") for request in record["requests"][:-1]):
                answer["events"].append(info["cache_debug"])
        ctl._schedule_save()
        ctl._render()
        self.refresh()
        if self.dialog is not None:
            self.dialog.refresh()

    def compressed(self, summary):
        ctl = self.controller
        if not ctl._target_exists():
            return
        record = ctl.target
        record["compression"] = summary
        record["summaries"] = record.get("summaries", []) + [summary]
        record.pop("last_request", None)
        if ctl.answer is not None:
            ctl.answer["note"] = "已压缩较早对话；原文完整保存在本地，可点击「摘要 / 原文」查看。"
            ctl.answer.setdefault("events", []).append(ctl.answer["note"])
        ctl._schedule_save()
        ctl._render()
        self.refresh()

    def compress(self):
        ctl = self.controller
        if ctl.worker is not None or ctl.record is None or not ctl.loaded:
            return
        config = ctl.data["profiles"].get(ctl.data["active"])
        if not config or settings.validate(config):
            self.panel.status.setText("请先配置可用的 AI 服务。")
            return
        if not ctl._consent(config):
            return
        prefix = ctl.record.get("prefix")
        if not prefix:
            self.panel.status.setText("当前没有需要压缩的旧对话。")
            return
        ctl.target = ctl.record
        ctl.answer = history.append_message(ctl.record, "assistant", "", "streaming")
        ctl.request_tools = prefix["tools"]
        ctl._start(dict(config, compress_only=True), prefix["system"], active_messages(ctl.record))
        ctl._render()

    def show_usage(self):
        ctl = self.controller
        if ctl.record is None:
            return
        style = ctl.data.get("ui", {}).get("token_format", "grouped")
        dialog = self.dialog = UsageDialog(ctl.record, style, self.panel)
        from PyQt5.QtCore import Qt
        dialog.setWindowFlags(Qt.Popup)
        position_popup(dialog, self.panel.footer.tokens, fit=False)
        dialog.format_changed.connect(self.set_format)
        dialog.exec_()
        self.dialog = None
        dialog.deleteLater()

    def _refresh_context_dialog(self):
        if self.context_dialog is not None:
            count, limits, parts, has_summary = self.panel.context_data
            self.context_dialog.set_data(count, limits, parts, self.controller.worker is not None, has_summary)

    def show_context(self):
        dialog = self.context_dialog = ContextDialog(self.panel)
        self._refresh_context_dialog()
        dialog.compress.clicked.connect(lambda: (dialog.accept(), self.compress()))
        dialog.originals.clicked.connect(lambda: (dialog.accept(), self.show_summary()))
        position_popup(dialog, self.panel.footer.context)
        dialog.exec_()
        self.context_dialog = None
        dialog.deleteLater()

    def show_stats(self):
        from .status_view import StatsDialog
        if self.controller.record is not None:
            dialog = StatsDialog(self.controller.record, self.panel)
            position_popup(dialog, self.panel.footer.stats)
            dialog.exec_()
            dialog.deleteLater()

    def set_format(self, style):
        ctl = self.controller
        ctl.data.setdefault("ui", {})["token_format"] = style
        ctl.panel.number_style = style
        ctl.sessions.store.number_style = style
        ctl.files.submit(settings.save_settings, copy.deepcopy(ctl.data))
        ctl._render()

    def show_summary(self):
        record = self.controller.record
        if not record:
            return
        dialog = TranscriptDialog(record, self.panel)
        dialog.exec_()
        dialog.deleteLater()
