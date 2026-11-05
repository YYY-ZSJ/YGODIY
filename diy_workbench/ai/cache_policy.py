"""Claude 的四个断点与可复现的模型输入前缀；控制标记不改写存档。"""

import copy
import hashlib
from datetime import datetime
from urllib.parse import urlsplit

from .request_context import stable_json


def mark_claude(payload, previous_end=0):
    payload = copy.deepcopy(payload)
    control = {"type": "ephemeral"}
    system = payload.get("system", "")
    payload["system"] = [{"type": "text", "text": system, "cache_control": dict(control)}]
    if payload.get("tools"):
        payload["tools"][-1]["cache_control"] = dict(control)
    messages = payload["messages"]
    for message in messages:
        if isinstance(message["content"], str):
            message["content"] = [{"type": "text", "text": message["content"]}]
    # 前一请求的末尾也保留一个断点，避免一次工具批次超过20个块的回查范围。
    ends = {len(messages), min(previous_end, len(messages))}
    for end in sorted(ends):
        for message in reversed(messages[:end]):
            candidates = [block for block in message["content"] if block.get("type") in ("text", "tool_use", "tool_result")
                          and (block.get("type") != "text" or block.get("text"))]
            if candidates:
                candidates[-1]["cache_control"] = dict(control)
                break
    return payload


def prompt_units(system, messages, tools):
    """逐块规范编码，不含请求ID、时间和cache_control等非模型文本元数据。"""
    return [stable_json(tools), system] + [stable_json(message) for message in messages]


def prefix_report(previous, current):
    matched = 0
    for old, new in zip(previous, current):
        if old != new:
            break
        matched += 1
    chars = sum(len(part) for part in current[:matched])
    return {"matched_units": matched, "previous_units": len(previous), "units": len(current),
            "prefix_unchanged": matched == len(previous), "common_prefix_chars": chars,
            "new_chars": sum(len(part) for part in current[matched:]),
            "prefix_sha256": hashlib.sha256("\0".join(current[:matched]).encode()).hexdigest()}


def cache_diagnostic(config, when):
    if urlsplit(config.get("base_url", "")).hostname != "api.deepseek.com":
        return ""
    text = "DeepSeek：缓存构建为秒级；当前官方按完整落盘前缀单元匹配，未公布固定的最小词元数。"
    previous = config.get("cache_previous_finished_at")
    if previous:
        try:
            gap = (when - datetime.fromisoformat(previous)).total_seconds()
            text += " 距上次请求结束 %.3f 秒。" % max(0, gap)
            if 0 <= gap < 1:
                text += " 间隔不足1秒，缓存可能尚未落盘（推测，不能由用量确定原因）。"
        except (ValueError, TypeError):
            pass
    return text + " 不额外等待；实际命中以服务返回为准。"
