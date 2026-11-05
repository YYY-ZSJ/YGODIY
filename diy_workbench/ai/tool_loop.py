"""工具循环的进度与重复检测；不执行操作、不接触界面。"""

import json

from .request_context import stable_json
from .tool_results import for_model

REPEAT_LIMIT = 3
MAX_TOOL_RESULT_CHARS = 24000


def argument_error(call):
    try:
        value = json.loads(call.get("arguments"))
        if isinstance(value, dict):
            return None
        detail = "收到的 JSON 顶层不是对象。"
    except json.JSONDecodeError as error:
        detail = "JSON 在第%d行第%d列无法解析。" % (error.lineno, error.colno)
    except RecursionError:
        detail = "JSON 嵌套过深。"
    except (ValueError, TypeError):
        detail = "参数必须为 JSON 字符串。"
    return {"ok": False, "error": "arguments：" + detail + '请修正后重发此工具，格式例如{"字段名":"值"}，无参数用{}。',
            "error_code": "invalid_tool_arguments", "path": "arguments", "expected": "JSON object",
            "received": str(call.get("arguments", ""))[:1000]}


def _error_key(error):
    if not error or "无效（" not in error:
        return error
    prefix, _, remaining = error.partition("无效（")
    _, end, expected = remaining.partition("）；")
    return prefix + "无效；" + expected if end else error


class LoopGuard:
    def __init__(self, saved=None):
        self.state = dict(saved or {})

    def call(self, call):
        key = call["name"] + stable_json(json.loads(call["arguments"]))
        count = self.state.get("call_count", 0) + 1 if self.state.get("call_key") == key else 1
        self.state.update(call_key=key, call_count=count)
        if count >= REPEAT_LIMIT:
            return "循环已停止：%s连续3次使用相同参数，第3次未执行。请检查缺少的资料或调整要求。" % call["name"]
        return ""

    def result(self, call, output):
        error = output.get("error") if not output.get("ok") else None
        key = output.get("error_code") or _error_key(error)
        count = self.state.get("error_count", 0) + 1 if error and self.state.get("error_key") == key else int(bool(error))
        self.state.update(error=error, error_key=key, error_count=count)
        return "循环已停止：%s连续3次返回同一错误，卡在：%s" % (call["name"], error) if count >= REPEAT_LIMIT else ""


def encode_result(call, output, legend_sent):
    compact = for_model(call["name"], output)
    if not legend_sent:
        compact["tool_result_legend"] = {"affects": "o=OCG,r=RD,m=漫画,d=DIY,p=旧版,f=场地中心,b=卡背",
                                        "scope": "editor=当前编辑器状态，不随卡保存"}
    encoded = stable_json(compact)
    if len(encoded) > MAX_TOOL_RESULT_CHARS and call["name"] != "get_block_catalog":
        encoded = stable_json({"ok": output.get("ok"), "truncated": True, "excerpt": encoded[:MAX_TOOL_RESULT_CHARS]})
    return encoded


def paused(result, outputs, guard, transcript, text, usage, known, limit=None, reason=None, budget=None):
    pending = {"result": result, "outputs": list(outputs), "guard": dict(guard.state)}
    if budget is not None:
        pending["budget"] = budget.snapshot()
    return dict(result or {}, text="\n\n".join(text), usage=usage, usage_known=known, transcript=transcript, paused=True,
                pause_reason=reason or "已达到本次%d次工具调用上限，进度已保留，点击「继续」接着执行。" % limit,
                pending=pending)
