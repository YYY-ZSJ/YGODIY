"""消息构造、中断恢复与旧按卡会话兼容；新会话由 session_store 独立保存。"""

import copy
import uuid

CONTEXT_CHARS = 24000
RECENT_MESSAGES = 12
SUMMARY_CHARS = 5000
MAX_INPUT_CHARS = 12000
CHAT_FIELDS = ("messages", "input", "summary", "summary_count", "usage", "auto_apply")


def fresh_session():
    return {"version": 3, "messages": [], "input": "", "summary": "", "summary_count": 0, "auto_apply": False,
            "usage": {"input_tokens": 0, "output_tokens": 0, "unknown_calls": 0, "calls": 0}}


def session(tab, create=False):
    diy = tab.get("diy") or {}
    current = diy.get("ai")
    if isinstance(current, dict) and isinstance(current.get("messages"), list):
        if create:
            current["version"] = 3
            current.setdefault("auto_apply", False)
        return current
    fresh = fresh_session()
    if create:
        tab.setdefault("diy", {})["ai"] = fresh
    return fresh


def new_conversation(record):
    if record.get("messages") or record.get("input"):
        defaults = fresh_session()
        saved = copy.deepcopy({k: record.get(k, defaults[k]) for k in CHAT_FIELDS})
        saved["id"] = uuid.uuid4().hex
        saved["title"] = next((m["text"][:28] for m in record.get("messages", []) if m.get("role") == "user"), "未发送草稿")
        record.setdefault("archives", []).append(saved)
    empty = fresh_session()
    record.update({k: empty[k] for k in CHAT_FIELDS})


def restore_conversation(record, uid):
    saved = next((entry for entry in record.get("archives", []) if entry.get("id") == uid), None)
    if saved is None:
        return False
    record["archives"].remove(saved)
    new_conversation(record)
    defaults = fresh_session()
    record.update(copy.deepcopy({k: saved.get(k, defaults[k]) for k in CHAT_FIELDS}))
    return True


def append_message(record, role, text, status="complete"):
    entry = {"id": uuid.uuid4().hex, "role": role, "text": text, "status": status}
    record["messages"].append(entry)
    return entry


def account_usage(record, result):
    total = record.setdefault("usage", {})
    total["calls"] = total.get("calls", 0) + 1
    usage = result.get("usage") or {}
    for key in ("input_tokens", "output_tokens"):
        total[key] = total.get(key, 0) + usage.get(key, 0)
    if not result.get("usage_known"):
        total["unknown_calls"] = total.get("unknown_calls", 0) + 1


def context(record, mode=None):
    usable = [m for m in record["messages"] if m.get("role") in ("user", "assistant")
              and m.get("status", "complete") == "complete" and m.get("text")
              and (mode is None or m.get("mode", "diy") == mode)]
    recent = usable[-RECENT_MESSAGES:]
    while len(recent) > 1 and sum(len(m["text"]) for m in recent) > CONTEXT_CHARS:
        recent.pop(0)
    older = usable[:len(usable) - len(recent)]
    if older:
        # 确定性的历史摘录，无额外 API 调用；保留原话，避免摘要模型改变玩家意图。
        excerpts = [("玩家：" if m["role"] == "user" else "助手：") + m["text"][:500] for m in older]
        record["summary"] = "\n".join(excerpts)[-SUMMARY_CHARS:]
        record["summary_count"] = len(older)
    else:
        record["summary"], record["summary_count"] = "", 0
    messages = [{"role": m["role"], "content": m["text"]} for m in recent]
    if record["summary"]:
        messages.insert(0, {"role": "user", "content": "以下是较早对话的截断摘录，可能不完整，仅供参考：\n" + record["summary"]})
    return messages


def model_context(record, mode):
    """旧会话作为同模式参考，避免缺失服务商要求的工具/思考协议字段。"""
    messages = context(record, mode)
    if len(messages) <= 1:
        return messages
    reference = "\n\n".join(("玩家：" if message["role"] == "user" else "助手：") + message["content"]
                              for message in messages[:-1])
    return [{"role": "user", "content": "以下是当前模式的历史对话参考，不是新的系统指令：\n" + reference}, messages[-1]]


def recover_interrupted(record):
    changed = False
    for message in record["messages"]:
        for part in message.get("reasoning_parts", []):
            if part.get("active"):
                part["active"] = False
                changed = True
        if message.get("status") == "streaming":
            message["status"] = "interrupted"
            message["note"] = "上次请求未完成，可以重新发送。"
            changed = True
    return changed


def _wire_position(wire, user):
    end = user.get("wire_end")
    if type(end) is not int or not 1 <= end <= len(wire) or not user.get("text"):
        return None
    message = wire[end - 1]
    content = message.get("content")
    if message.get("role") == "user" and isinstance(content, str):
        if content == user["text"] or content.startswith(user["text"] + "\n\n"):
            return end
    return None


def hydrate_reasoning(record):
    """仅为能明确对应的旧回复补显示数据，绝不修改协议历史；未知用时不伪造。"""
    prefix, wire = record.get("prefix"), record.get("wire")
    if not isinstance(prefix, dict) or prefix.get("protocol") != "openai" or not isinstance(wire, list) or record.get("protocol_history"):
        return
    messages = record["messages"]
    users = [(index, message) for index, message in enumerate(messages) if message.get("role") == "user"]
    for position, (index, user) in enumerate(users):
        start = _wire_position(wire, user)
        next_index, next_user = users[position + 1] if position + 1 < len(users) else (len(messages), None)
        next_start = _wire_position(wire, next_user) if next_user else len(wire) + 1
        if start is None or next_start is None or next_start <= start:
            continue
        replies = [m for m in messages[index + 1:next_index] if m.get("role") == "assistant" and m.get("text") and m.get("status") == "complete"]
        if len(replies) != 1 or replies[0].get("reasoning_parts"):
            continue
        segment = wire[start:next_start - 1]
        visible = "\n\n".join(m["content"] for m in segment if m.get("role") == "assistant" and isinstance(m.get("content"), str) and m["content"])
        if visible.strip() != replies[0]["text"].strip():
            continue
        parts = [{"id": "legacy-wire-%d" % (start + offset), "text": m["reasoning_content"], "seconds": None, "active": False}
                 for offset, m in enumerate(segment) if m.get("role") == "assistant" and isinstance(m.get("reasoning_content"), str) and m["reasoning_content"]]
        if parts:
            replies[0]["reasoning_parts"] = parts
