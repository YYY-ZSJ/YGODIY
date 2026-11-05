"""本次启动内暂停/续接同一回复与修改批次，继续不增加用户消息或重做已执行操作。"""

from . import settings
from .context_budget import active_messages


class Continuation:
    def __init__(self, controller):
        self.controller = controller

    def outcome(self, result):
        ctl = self.controller
        reason = result.get("pause_reason") or result.get("stopped")
        if not reason:
            return False
        if result.get("paused"):
            plan = ctl.operations.changes.current
            ctl.answer["continuation"] = {"plan_id": plan.id if plan is not None else None, "pending": result["pending"],
                                          "compress_only": bool(ctl.request_config.get("compress_only")),
                                          "service": {key: ctl.request_config.get(key) for key in ("protocol", "model", "base_url")}}
        ctl._finish_answer("paused" if result.get("paused") else "stopped", reason, result)
        ctl.panel.status.clear()
        return True

    def resume(self, message):
        ctl = self.controller
        saved = message.get("continuation") or {}
        plan = ctl.operations.changes.plans.get(saved.get("plan_id"))
        config = ctl.data["profiles"].get(ctl.data["active"])
        error = settings.validate(config) if config else "请先配置服务。"
        if plan is None and not saved.get("compress_only"):
            error = "继续需要本次启动内的修改快照；重启后请新发要求，已保存的调用过程和原文仍可查看。"
        elif not config or any(config.get(key) != value for key, value in saved["service"].items()):
            error = "请切回暂停时的服务地址、接口和模型，再继续。"
        elif plan is not None and plan.state in ("rejected", "undone", "partially_undone"):
            error = "该批次已被拒绝或撤销，请新发要求。"
        if error:
            ctl.panel.status.setText(error)
            return
        if not ctl._consent(config):
            return
        if plan is not None:
            ctl.operations.changes.current = plan
            plan.answer = message
            plan.finished = False
        ctl.answer, ctl.target = message, ctl.record
        message.update(status="streaming", note="")
        message.pop("continuation", None)
        message.setdefault("events", []).append("继续已有进度，已执行的工具不重复调用。")
        if message.get("text"):
            message["text"] += "\n\n"
        prefix = ctl.record["prefix"]
        ctl.request_tools = prefix["tools"]
        if saved.get("compress_only"):
            config = dict(config, compress_only=True)
        ctl._start(config, prefix["system"], active_messages(ctl.record), resume=saved["pending"])
        ctl.checkpoint_timer.start()
        ctl._render()

    def abandon(self, record):
        from .conversation import _tool_messages
        from .request_context import stable_json
        ctl = self.controller
        for message in record.get("messages", []):
            saved = message.pop("continuation", None)
            if saved is None:
                continue
            pending = saved["pending"]
            outputs = list(pending["outputs"])
            result = pending.get("result")
            for _ in (result or {}).get("tool_calls", [])[len(outputs):]:
                outputs.append(stable_json({"ok": False, "not_executed": True, "error": "玩家已发来新要求，此项没有执行。"}))
            if result is not None:
                record["wire"] = record.get("wire", []) + _tool_messages(record["prefix"]["protocol"], result, outputs)
            message.update(status="interrupted", note="已接受新的要求；此前已生成的修改仍在批次记录中。")
            plan = ctl.operations.changes.plans.get(saved["plan_id"])
            if plan is not None:
                plan.finished = True
                ctl.operations.changes._notify(plan)
                plan.release_unused()

    def retry(self, uid):
        ctl = self.controller
        if ctl.record is None or ctl.worker is not None:
            return
        messages = ctl.record["messages"]
        index = next((i for i, message in enumerate(messages) if message["id"] == uid), None)
        if index is None:
            return
        if messages[index].get("status") == "paused":
            self.resume(messages[index])
            return
        from .card_context import active_mode
        if messages[index].get("mode", "diy") != active_mode(ctl.app)["id"]:
            ctl.panel.status.setText("请先切回这条消息对应的模式，再重试。")
            return
        user = next((m for m in reversed(messages[:index]) if m.get("role") == "user"), None)
        if user:
            ctl.send(retry_text=user["text"])
