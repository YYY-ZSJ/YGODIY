"""每次HTTP先留开始记录；进程被终止也能在重开会话时说明中断与未知用量。"""

from datetime import datetime, timezone
import uuid

from .file_jobs import read_json, write_json


class RequestJournal:
    def __init__(self, root, session_id, message_id):
        self.root = root / session_id
        self.message_id = message_id
        self.current = None

    def begin(self, config):
        from .providers import ServiceError
        record = {"request_id": uuid.uuid4().hex, "message_id": self.message_id, "state": "running",
                  "at": datetime.now(timezone.utc).isoformat(),
                  "service": {k: config.get(k) for k in ("model", "preset", "protocol")}}
        try:
            write_json(self.root / (record["request_id"] + ".json"), record)
        except OSError:
            raise ServiceError("无法保存请求开始记录，本次没有发送。请检查磁盘空间及目录权限。") from None
        self.current = record
        return record["request_id"]

    def finish(self, info=None, reason=None):
        record = self.current
        if record is None or record["state"] != "running":
            return True
        record = dict(record, state="complete" if info and info.get("completed") else "interrupted",
                      reason=reason, finished_at=datetime.now(timezone.utc).isoformat())
        if info is not None:
            keys = ("model", "actual_model", "purpose", "usage", "usage_known", "cost", "rates", "completed", "truncated", "error_type", "at", "finished_at", "request_id")
            record["info"] = {key: info[key] for key in keys if key in info}
        try:
            write_json(self.root / (record["request_id"] + ".json"), record)
        except OSError:
            return False
        self.current = record
        return True


def recover(record, root):
    from .usage import accumulate
    known = {r.get("request_id") for r in record.get("requests", [])}
    messages = {m["id"]: m for m in record["messages"]}
    changed = False
    entries = [(path, read_json(path, {})) for path in (root / record["id"]).glob("*.json")]
    for path, item in sorted(entries, key=lambda pair: pair[1].get("at") or ""):
        uid, message = item.get("request_id"), messages.get(item.get("message_id"))
        if not uid or uid in known or message is None:
            continue
        if item.get("state") == "running":
            item.update(state="interrupted", reason="程序未正常结束，具体退出原因未记录。")
            write_json(path, item)
        info = item.get("info") or {"model": item.get("service", {}).get("model"), "at": item.get("at"),
            "usage_known": False, "completed": False, "interrupted": True,
            "usage": {"input_tokens": 0, "output_tokens": 0, "input_known": False, "output_known": False,
                      "cache_known": False, "cache_read_tokens": None, "uncached_input_tokens": None, "cache_write_tokens": None}}
        info = dict(info, request_id=uid)
        record["requests"] = record.get("requests", []) + [info]
        record["usage"] = accumulate(record.get("usage"), info["usage"], info.get("cost"))
        message["usage"] = accumulate(message.get("usage"), info["usage"], info.get("cost"))
        message["usage_known"] = not message["usage"].get("unknown_calls")
        if not info.get("completed"):
            message.update(status="interrupted", note="上次请求中断，已保留收到的内容；本次完整用量和费用未知，未自动重发。")
        message.setdefault("events", []).append("恢复请求记录 · %s · %s" % (uid[:8], "已保存服务用量" if info.get("completed") else "请求中断，用量可能未知"))
        known.add(uid)
        changed = True
    return changed
