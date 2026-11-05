"""两种服务协议的请求与流式事件，界面不依赖服务商响应格式。"""

import json
import copy

# 预设仅提供填写示例；模型权限、工具能力由「测试连接」实际检查。
PRESETS = {
    "custom": ("自定义服务", "openai", "", ()),
    "deepseek": ("DeepSeek", "openai", "https://api.deepseek.com", ("deepseek-flash", "deepseek-v4-pro")),
    "grok": ("Grok（xAI）", "openai", "https://api.x.ai/v1", ("grok-4.7",)),
    "kimi": ("Kimi（Moonshot 中国）", "openai", "https://api.moonshot.cn/v1", ("kimi-k3.1-pro", "kimi-k3.1-pro-highspeed")),
    "qwen": ("通义千问（百炼北京）", "openai", "https://dashscope.aliyuncs.com/compatible-mode/v1", ("qwen-plus", "qwen-max")),
    "siliconflow": ("硅基流动", "openai", "https://api.siliconflow.cn/v1", ("Pro/zai-org/GLM-5.1", "Pro/moonshotai/Kimi-K2.6")),
    "zhipu": ("智谱 GLM", "openai", "https://open.bigmodel.cn/api/paas/v4", ("glm-5.3", "glm-4.7")),
    "openai": ("OpenAI（Chat Completions）", "openai", "https://api.openai.com/v1", ("gpt-4.1-mini", "gpt-4.1")),
    "claude": ("Anthropic Claude", "claude", "https://api.anthropic.com/v1", ("claude-sonnet-4-5", "claude-opus-4-6")),
    "ollama": ("Ollama 本地", "openai", "http://localhost:11434/v1", ("gpt-oss:20b",)),
}
KEY_URLS = {
    "deepseek": "https://platform.deepseek.com/api_keys",
    "grok": "https://console.x.ai/team/default/api-keys",
    "kimi": "https://platform.kimi.com/console/api-keys",
    "qwen": "https://bailian.console.aliyun.com/?tab=model#/api-key",
    "siliconflow": "https://cloud.siliconflow.cn/account/ak",
    "zhipu": "https://bigmodel.cn/usercenter/proj-mgmt/apikeys",
    "openai": "https://platform.openai.com/api-keys",
    "claude": "https://platform.claude.com/settings/keys",
    "ollama": "https://ollama.com/settings/keys",
}
REASONING_LEVELS = (("", "默认"), ("off", "不思考"), ("low", "低"), ("medium", "中"), ("high", "高"), ("max", "最高"))
PROBE_NAME = "ygodiy_connection_check"
PROBE_SCHEMA = {"type": "object", "properties": {"value": {"type": "string", "enum": ["ok"]}},
                "required": ["value"], "additionalProperties": False}
PROBE_MESSAGE = "请只调用 ygodiy_connection_check 工具，参数 value 填写 ok。这只是连接检查，没有其他动作。"
MAX_EVENT_BYTES = 1024 * 1024


class ServiceError(Exception):
    """可直接显示给玩家的错误；不携带请求头、Key 或原始 HTTP 响应。"""


def reasoning_fields(config, deepseek):
    """思考等级对应的请求字段。默认不发送，由服务商决定；服务商不接受时 client 会去掉这些字段重试。"""
    level = config.get("reasoning_level", "")
    if not level:
        return {}
    if config["protocol"] == "claude":
        return {"output_config": {"effort": "low" if level == "off" else level}}
    if deepseek:
        if level == "off":
            return {"thinking": {"type": "disabled"}}
        return {"thinking": {"type": "enabled"}, "reasoning_effort": level}
    return {} if level == "off" else {"reasoning_effort": "high" if level == "max" else level}


def request_data(config, system, messages, probe=False, tools=None):
    protocol = config["protocol"]
    suffix = "/messages" if protocol == "claude" else "/chat/completions"
    base = config["base_url"].rstrip("/")
    url = base if base.endswith(suffix) else base + suffix
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    key = config.get("api_key", "")
    payload = {"model": config["model"], "messages": messages, "stream": True}
    if config.get("max_tokens"):
        payload["max_tokens"] = config["max_tokens"]
    if protocol == "claude":
        if not config.get("max_tokens"):
            raise ServiceError("尚未取得 Claude 模型输出上限，请重试或在高级设置中填写。")
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
        payload["system"] = system
        if probe:
            payload["tools"] = [{"name": PROBE_NAME, "description": "无副作用的连接检查，不修改任何数据。",
                                 "input_schema": PROBE_SCHEMA}]
        elif tools:
            payload["tools"] = [{"name": tool["name"], "description": tool["description"],
                                 "input_schema": tool["parameters"]} for tool in tools]
    else:
        if key:
            headers["Authorization"] = "Bearer " + key
        history = messages
        if not tools and not probe:
            from urllib.parse import urlsplit
            if urlsplit(base).hostname == "api.deepseek.com" or config.get("model", "").startswith("deepseek-"):
                history = [{key: value for key, value in message.items() if key != "reasoning_content"} for message in messages]
        payload["messages"] = [{"role": "system", "content": system}] + history
        payload["stream_options"] = {"include_usage": True}
        if probe:
            payload["tools"] = [{"type": "function", "function": {
                "name": PROBE_NAME, "description": "无副作用的连接检查，不修改任何数据。", "parameters": PROBE_SCHEMA}}]
        elif tools:
            payload["tools"] = [{"type": "function", "function": tool} for tool in tools]
    if not probe:
        from urllib.parse import urlsplit
        payload.update(reasoning_fields(config, urlsplit(base).hostname == "api.deepseek.com"))
    if protocol == "claude" and not probe:
        from .cache_policy import mark_claude
        payload = mark_claude(payload, config.get("cache_previous_end", 0))
    if config.get("conversation_id") and base.startswith("https://api.x.ai/"):
        headers["x-grok-conv-id"] = config["conversation_id"]
    from .request_context import stable_json
    payload = json.loads(stable_json(payload))
    return url, headers, payload


def sse_events(response, check=lambda: None):
    """解析 SSE 数据帧，支持注释心跳、多行 data 和最后一帧无空行。"""
    data, size = [], 0
    for raw in response.iter_lines(chunk_size=128):
        check()
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not line:
            if data:
                yield "\n".join(data)
            data, size = [], 0
        elif line.startswith("data:"):
            fragment = line[5:].lstrip(" ")
            size += len(fragment.encode("utf-8"))
            if size > MAX_EVENT_BYTES:
                raise ServiceError("服务返回的单条流式消息过大，请减少输入或输出上限。")
            data.append(fragment)
    if data:
        yield "\n".join(data)


class StreamResult:
    def __init__(self, protocol):
        self.protocol = protocol
        self.text = ""
        self.calls = {}
        from .usage import normalize
        self.usage = normalize({}, protocol)
        self.usage_known = False
        self.raw_usage = {}
        self.finished = False
        self.terminal = False
        self.stop_reason = ""
        self.reasoning_content = None
        self.content_blocks = {}
        self.model = None

    def _usage(self, usage):
        from .usage import normalize
        if not isinstance(usage, dict):
            return
        self.raw_usage.update(usage)
        self.usage = normalize(self.raw_usage, self.protocol)
        self.usage_known = self.usage["input_known"] and self.usage["output_known"]

    def _model(self, value):
        if isinstance(value, str):
            self.model = value[:200]

    def feed(self, frame):
        if frame == "[DONE]":
            self.finished = self.terminal = True
            return ""
        try:
            event = json.loads(frame)
            if not isinstance(event, dict):
                raise ValueError()
        except ValueError:
            raise ServiceError("服务返回了无法解析的流式数据，请检查接口类型。") from None
        if event.get("error") or event.get("type") == "error":
            raise ServiceError("服务在生成过程中返回错误，请检查额度或稍后重试。")
        delta = self._claude(event) if self.protocol == "claude" else self._openai(event)
        self.text += delta
        return delta

    def _openai(self, event):
        self._model(event.get("model"))
        self._usage(event.get("usage"))
        text = ""
        for choice in event.get("choices") or []:
            if choice.get("index", 0) != 0:
                continue
            delta = choice.get("delta") or {}
            if isinstance(delta.get("reasoning_content"), str):
                self.reasoning_content = (self.reasoning_content or "") + delta["reasoning_content"]
            content = delta.get("content")
            if isinstance(content, str):
                text += content
            for call in delta.get("tool_calls") or []:
                entry = self.calls.setdefault(call.get("index", 0), {"id": "", "name": "", "arguments": ""})
                entry["id"] = call.get("id") or entry["id"]
                fn = call.get("function") or {}
                entry["name"] += fn.get("name") or ""
                entry["arguments"] += fn.get("arguments") or ""
            if choice.get("finish_reason"):
                self.stop_reason = choice["finish_reason"]
                self.finished = True
        return text

    def _claude(self, event):
        kind = event.get("type")
        if kind == "message_start":
            self._model((event.get("message") or {}).get("model"))
            self._usage((event.get("message") or {}).get("usage"))
        elif kind == "content_block_start":
            block = event.get("content_block") or {}
            self.content_blocks[event.get("index", 0)] = copy.deepcopy(block)
            if block.get("type") == "tool_use":
                self.calls[event.get("index", 0)] = {"id": block.get("id", ""), "name": block.get("name", ""),
                                                     "arguments": json.dumps(block["input"]) if block.get("input") else ""}
        elif kind == "content_block_delta":
            delta = event.get("delta") or {}
            block = self.content_blocks.get(event.get("index", 0))
            field = {"text_delta": "text", "thinking_delta": "thinking", "signature_delta": "signature"}.get(delta.get("type"))
            if block is not None and field and isinstance(delta.get(field), str):
                block[field] = block.get(field, "") + delta[field]
            if delta.get("type") == "text_delta":
                return delta.get("text", "")
            if delta.get("type") == "input_json_delta":
                entry = self.calls.setdefault(event.get("index", 0), {"id": "", "name": "", "arguments": ""})
                entry["arguments"] += delta.get("partial_json", "")
        elif kind == "message_delta":
            self._usage(event.get("usage"))
            self.stop_reason = (event.get("delta") or {}).get("stop_reason", "")
        elif kind == "message_stop":
            self.finished = self.terminal = True
        return ""

    def result(self, probe=False, allow_tools=False):
        if not self.finished:
            raise ServiceError("连接提前中断，回复未完成，可以重新发送。")
        if self.protocol == "claude":
            for block in self.content_blocks.values():
                call = next((call for call in self.calls.values() if call["id"] == block.get("id")), None)
                if block.get("type") == "tool_use" and call is not None and call["arguments"] == "":
                    call["arguments"] = json.dumps(block.get("input", {}), ensure_ascii=False)
        if probe:
            valid = len(self.calls) == 1
            for call in self.calls.values():
                try:
                    valid = valid and call["name"] == PROBE_NAME and json.loads(call["arguments"]) == {"value": "ok"}
                except ValueError:
                    valid = False
            if not valid:
                raise ServiceError("连接成功，但模型未返回有效的工具调用；请换用支持工具调用的模型。")
        elif self.calls and not allow_tools:
            raise ServiceError("本次请求未开放工具，调用已拒绝，卡片未修改。")
        elif not self.calls and not self.text.strip() and self.stop_reason not in ("length", "max_tokens"):
            raise ServiceError("模型未返回回复文字，请检查模型名或输出上限。")
        return {"text": self.text, "usage": dict(self.usage), "usage_known": self.usage_known, "model": self.model,
                "tool_calls": list(self.calls.values()), "truncated": self.stop_reason in ("length", "max_tokens"),
                "reasoning_content": self.reasoning_content, "provider_content": list(self.content_blocks.values())}
