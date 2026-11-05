"""服务商用量归一化、逐档计价和中文数字显示。未返回的统计保持未知。"""

from decimal import Decimal

FIELDS = ("input_tokens", "output_tokens", "uncached_input_tokens", "cache_read_tokens", "cache_write_tokens")


def number(value, style="grouped"):
    if value is None:
        return "未返回"
    value = int(value)
    if style == "wan" and value >= 10000:
        return "%.1f 万" % (value / 10000)
    digits = str(value)
    groups = []
    while digits:
        groups.append(digits[-4:])
        digits = digits[:-4]
    return " ".join(reversed(groups)) or "0"


def _integer(value):
    return value if type(value) is int and value >= 0 else None


def normalize(raw, protocol):
    if protocol == "claude":
        uncached, output = _integer(raw.get("input_tokens")), _integer(raw.get("output_tokens"))
        read = _integer(raw.get("cache_read_input_tokens"))
        write = _integer(raw.get("cache_creation_input_tokens"))
        total = (uncached or 0) + (read or 0) + (write or 0)
        input_known = uncached is not None
    else:
        total, output = _integer(raw.get("prompt_tokens")), _integer(raw.get("completion_tokens"))
        read = _integer(raw.get("prompt_cache_hit_tokens"))
        if read is None:
            read = _integer((raw.get("prompt_tokens_details") or {}).get("cached_tokens"))
        uncached = _integer(raw.get("prompt_cache_miss_tokens"))
        if uncached is None and total is not None and read is not None and read <= total:
            uncached = total - read
        write, input_known = 0, total is not None
    cache_known = read is not None and write is not None and uncached is not None
    reasoning = _integer((raw.get("completion_tokens_details") or {}).get("reasoning_tokens"))
    return {"input_tokens": total or 0, "output_tokens": output or 0, "reasoning_tokens": reasoning,
            "uncached_input_tokens": uncached, "cache_read_tokens": read, "cache_write_tokens": write,
            "input_known": input_known, "output_known": output is not None, "cache_known": cache_known}


def estimate_cost(usage, rates):
    if not rates:
        return {"known": False, "reason": "未设置该模型单价"}
    mapping = {"input": "uncached_input_tokens", "cache_read": "cache_read_tokens",
               "cache_write": "cache_write_tokens", "output": "output_tokens"}
    if not usage.get("input_known") or not usage.get("output_known") or not usage.get("cache_known"):
        return {"known": False, "reason": "服务未完整返回用量或缓存统计", "currency": rates.get("currency", "")}
    parts = {}
    for key, tokens in mapping.items():
        if rates.get(key) is None:
            return {"known": False, "reason": "单价未填全"}
        parts[key] = str(Decimal(usage[tokens]) * Decimal(str(rates[key])) / Decimal(1000000))
    return {"known": True, "currency": rates.get("currency", "CNY"), "parts": parts,
            "total": str(sum(Decimal(value) for value in parts.values()))}


def accumulate(total, usage, cost=None):
    result = dict(total or {})
    if result.get("calls") and "cache_read_tokens" not in result:
        result["cache_unknown_calls"] = result["calls"]
        result["cache_measured_input"] = 0
        result["unpriced_calls"] = result["calls"]
    for key in FIELDS:
        result[key] = result.get(key, 0) + (usage.get(key) or 0)
    result["calls"] = result.get("calls", 0) + 1
    if usage.get("reasoning_tokens") is not None:
        result["reasoning_tokens"] = result.get("reasoning_tokens", 0) + usage["reasoning_tokens"]
        result["reasoning_reported_calls"] = result.get("reasoning_reported_calls", 0) + 1
    for flag, count in (("input_known", "input_unknown_calls"), ("output_known", "output_unknown_calls"), ("cache_known", "cache_unknown_calls")):
        result[count] = result.get(count, 0) + (0 if usage.get(flag) else 1)
    result["unknown_calls"] = result.get("unknown_calls", 0) + (0 if usage.get("input_known") and usage.get("output_known") else 1)
    if usage.get("cache_known"):
        result["cache_measured_input"] = result.get("cache_measured_input", 0) + usage.get("input_tokens", 0)
    costs = dict(result.get("costs", {}))
    if cost and cost.get("known"):
        currency = cost["currency"]
        costs[currency] = str(Decimal(costs.get(currency, "0")) + Decimal(cost["total"]))
    else:
        result["unpriced_calls"] = result.get("unpriced_calls", 0) + 1
    result["costs"] = costs
    return result


def hit_rate(usage):
    if "cache_measured_input" in usage:
        denominator = usage["cache_measured_input"]
    else:
        denominator = usage.get("input_tokens", 0) if usage.get("cache_known") else 0
    if not denominator:
        return "未返回" if usage.get("cache_unknown_calls") or not usage.get("cache_known") else "0.0%"
    rate = min(100, 100 * (usage.get("cache_read_tokens") or 0) / denominator)
    return "%.1f%%" % rate + ("（已知部分）" if usage.get("cache_unknown_calls") else "")


def money(costs):
    if not costs:
        return "约计费用待补全"
    return "约 " + " / ".join(currency + " " + format(Decimal(value), ".6f") for currency, value in costs.items())


def tooltip(usage, style="grouped"):
    labels = (("输入", "input_tokens"), ("未缓存输入", "uncached_input_tokens"),
              ("缓存读取", "cache_read_tokens"), ("缓存写入", "cache_write_tokens"), ("输出", "output_tokens"))
    lines = [label + "：" + number(token_value(usage, key), style) + " 词元" for label, key in labels]
    if usage.get("reasoning_reported_calls") or (not usage.get("calls") and usage.get("reasoning_tokens") is not None):
        lines.append("其中思考：" + number(usage["reasoning_tokens"], style) + " 词元（已含在输出中）")
    lines += ["缓存命中率：" + hit_rate(usage), money(usage.get("costs", {}))]
    if usage.get("unknown_calls") or usage.get("cache_unknown_calls"):
        lines.append("部分请求未返回完整统计，以上为已知部分。")
    if usage.get("unpriced_calls"):
        lines.append("另有 %d 次请求费用未知。" % usage["unpriced_calls"])
    return "\n".join(lines)


def token_value(usage, key):
    if key in ("uncached_input_tokens", "cache_read_tokens", "cache_write_tokens"):
        if usage.get("cache_unknown_calls") and not usage.get("cache_measured_input"):
            return None
    return usage.get(key)
