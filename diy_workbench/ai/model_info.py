"""已核实的容量/单价兜底；手填值按当前服务配置和实际模型隔离。"""

import copy
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

VERIFIED = "2026-11-02"
DEEPSEEK_SOURCE = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
CLAUDE_SOURCE = "https://platform.claude.com/docs/en/build-with-claude/prompt-caching"
KIMI_SOURCE = "https://www.kimi.com/membership/pricing?tab=api"
GROK_SOURCE = "https://docs.x.ai/developers/pricing"
OPENAI_SOURCE = "https://developers.openai.com/api/docs/models/"

# 输入、缓存读取、缓存写入、输出，均为每百万词元；不为未知模型猜价格。
BUILTIN = {
    "api.openai.com": {
        "gpt-4.1": (1047576, 32768, "USD", (2, .5, 2, 8), OPENAI_SOURCE + "gpt-4.1"),
        "gpt-4.1-mini": (1047576, 32768, "USD", (.4, .1, .4, 1.6), OPENAI_SOURCE + "gpt-4.1-mini"),
        "gpt-4o-mini": (128000, 16384, "USD", (.15, .075, .15, .6), OPENAI_SOURCE + "gpt-4o-mini"),
        "gpt-5.4": (1050000, 128000, "USD", (2.5, .25, 2.5, 15), OPENAI_SOURCE + "gpt-5.4"),
    },
    "api.deepseek.com": {
        "deepseek-flash": (1048576, 393216, "CNY", (2, .04, 2, 8), DEEPSEEK_SOURCE),
        "deepseek-v4-pro": (1048576, 393216, "CNY", (9, .30, 9, 27), DEEPSEEK_SOURCE),
    },
    "api.anthropic.com": {
        "claude-sonnet-4-5": (200000, 64000, "USD", (3, .30, 3.75, 15), CLAUDE_SOURCE),
        "claude-sonnet-4-6": (1000000, 128000, "USD", (3, .30, 3.75, 15), CLAUDE_SOURCE),
        "claude-opus-4-6": (1000000, 128000, "USD", (5, .50, 6.25, 25), CLAUDE_SOURCE),
        "claude-haiku-4-5": (200000, 64000, "USD", (1, .10, 1.25, 5), CLAUDE_SOURCE),
        "claude-sonnet-5-5": (1000000, 128000, "USD", (2, .10, 2.50, 10), CLAUDE_SOURCE),
        "claude-opus-5-5": (1000000, 128000, "USD", (4, .20, 5, 20), CLAUDE_SOURCE),
    },
    "api.moonshot.cn": {
        "kimi-k3.1-pro": (1000000, 0, "CNY", (13, 1.30, 13, 68), KIMI_SOURCE),
        "kimi-k3.1-pro-highspeed": (1000000, 0, "CNY", (26, 1.30, 26, 136), KIMI_SOURCE),
    },
    "api.x.ai": {
        "grok-4.7": (500000, 0, "USD", (2, .5, 2, 6), GROK_SOURCE),
    },
}
PRICE_FIELDS = ("input", "cache_read", "cache_write", "output")


def builtin(config):
    host = urlsplit(config.get("base_url", "")).hostname
    model = config.get("model", "")
    if host == "api.deepseek.com" and model in ("deepseek-v4-flash", "deepseek-v4-flash-vision-exp"):
        model = "deepseek-flash"
    table = BUILTIN.get(host, {})
    row = table.get(model)
    if row is None and host == "api.anthropic.com":
        row = next((v for key, v in table.items() if model.startswith(key + "-20")), None)
    if row is None:
        return {}
    context, output, currency, rates, source = row
    return {"context_window": context, "max_output_tokens": output,
            "prices": dict(zip(PRICE_FIELDS, rates), currency=currency, source=source,
                           verified="2026-11-03" if host == "api.openai.com" else VERIFIED)}


def limits(config, metadata=None):
    result = builtin(config)
    result["source"] = "内置表 · " + VERIFIED if result else "未知，请在高级中填写"
    for key in ("context_window", "max_input_tokens", "max_output_tokens"):
        value = (metadata or {}).get(key)
        if type(value) is int and value > 0:
            result[key] = value
            result["source"] = "服务商模型信息"
    output = (metadata or {}).get("max_tokens")
    if type(output) is int and output > 0:
        result["max_output_tokens"] = output
    if not result.get("context_window") and result.get("max_input_tokens"):
        result["context_window"] = result["max_input_tokens"]
    override = config.get("model_overrides", {}).get(config.get("model"), {})
    if override.get("context_window", 0) > 0:
        result["context_window"] = override["context_window"]
        result["max_input_tokens"] = override["context_window"]
        result["source"] = "手动设置"
    return result


def prices(config, input_tokens=0, now=None):
    override = config.get("model_overrides", {}).get(config.get("model"), {}).get("prices")
    if override:
        return dict(copy.deepcopy(override), source="手动设置")
    result = copy.deepcopy(builtin(config).get("prices"))
    if result is None:
        return None
    host = urlsplit(config.get("base_url", "")).hostname
    if host == "api.deepseek.com":
        local = (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=8)))
        peak = local.weekday() < 5 and (9 <= local.hour < 12 or 14 <= local.hour < 18)
        if not peak:
            result.update({key: result[key] / 2 for key in PRICE_FIELDS})
        result["tier"] = ("高峰" if peak else "空闲") + "时段估算（未自动识别法定节假日）"
    elif host == "api.x.ai" and input_tokens >= 200000:
        result.update({key: result[key] * 2 for key in PRICE_FIELDS})
        result["tier"] = "长上下文档 ≥ 20万"
    elif host == "api.openai.com" and config.get("model") == "gpt-5.4" and input_tokens > 272000:
        result.update({key: result[key] * 2 for key in ("input", "cache_read", "cache_write")})
        result["output"] *= 1.5
        result["tier"] = "长上下文档 > 27.2万"
    else:
        result["tier"] = "标准档；Claude 缓存写入按5分钟"
    return result
