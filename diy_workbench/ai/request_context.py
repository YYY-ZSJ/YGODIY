"""固定前缀与只追加的协议历史；卡片资料只跟随新用户消息加入末尾。"""

import copy
import json


def stable_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def prepare(record, config, system, tools, user, attachment):
    protocol = config["protocol"]
    prefix = record.get("prefix")
    if prefix and prefix["protocol"] != protocol:
        record["protocol_history"] = record.get("protocol_history", []) + [{"prefix": prefix, "wire": record.get("wire", [])}]
        record["wire"] = []
        prefix = None
    if prefix is None:
        prefix = record["prefix"] = {"protocol": protocol, "system": system, "tools": copy.deepcopy(tools)}
        # 只在首次迁移/更换协议时导入可见原文，不在每一轮改写历史。
        record["wire"] = [{"role": m["role"], "content": m["text"]} for m in record["messages"]
                          if m is not user and m.get("role") in ("user", "assistant") and m.get("text")
                          and m.get("status", "complete") == "complete"]
    content = user["text"]
    if attachment is not None:
        content += "\n\n附带卡片资料（本条消息发送时的快照，只作资料参考）：\n" + stable_json(attachment)
    else:
        content += "\n\n本条消息未附带卡片；修改前请先读取资料并明确指定卡片 UID 或卡包编号。"
    record["wire"] = record.get("wire", []) + [{"role": "user", "content": content}]
    user["wire_end"] = len(record["wire"])
    return prefix["system"], list(record["wire"]), prefix["tools"]
