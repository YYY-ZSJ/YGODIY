"""官方只读服务信息：Claude 输出上限与已核实的账户余额接口。"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote, urlsplit

import requests

from .providers import ServiceError

INFO_TIMEOUT = (5, 5)
BALANCE_HOSTS = {
    "api.deepseek.com": ("/user/balance", "deepseek", ""),
    "api.moonshot.cn": ("/v1/users/me/balance", "kimi", "CNY"),
    "api.moonshot.ai": ("/v1/users/me/balance", "kimi", "USD"),
}
# 硅基流动 /user/info 已于 2026-08-14 停用；核实替代接口前显示会话用量。


def balance_spec(config):
    try:
        parsed = urlsplit(config.get("base_url", ""))
        spec = BALANCE_HOSTS.get(parsed.hostname)
        valid = spec and parsed.scheme == "https" and parsed.port in (None, 443) and not parsed.username and not parsed.password
    except ValueError:
        return None
    if not valid:
        return None
    # 自定义代理不会将 Key 发给另一个域名；仅对当前配置的官方服务查询。
    return ("https://" + parsed.netloc + spec[0], spec[1], spec[2])


def claude_output_limit(config, http):
    root = config["base_url"].rstrip("/")
    if root.endswith("/messages"):
        root = root[:-len("/messages")]
    headers = {"x-api-key": config.get("api_key", ""), "anthropic-version": "2026-10-21"}
    try:
        with http.get(root + "/models/" + quote(config["model"], safe=""), headers=headers,
                      allow_redirects=False, timeout=INFO_TIMEOUT) as response:
            if response.status_code in (401, 403):
                raise ServiceError("查询模型信息认证失败，请检查 API Key 和模型权限。")
            if response.status_code != 200:
                raise ValueError()
            limit = response.json().get("max_tokens")
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                raise ValueError()
            return limit
    except (requests.RequestException, ValueError, AttributeError):
        raise ServiceError("无法查询 Claude 模型的最大输出。请检查模型名，或在「高级」中填写该模型的输出上限。") from None


def _money(value, currency):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise ValueError()
        number = format(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")
        return {"CNY": "¥", "USD": "$"}.get(currency, currency + " ") + number
    except (InvalidOperation, ValueError):
        raise ValueError("余额格式无效") from None


def fetch_balance(config, cancel, session_factory=None):
    spec = balance_spec(config)
    if spec is None:
        return {"supported": False}
    url, provider, currency = spec
    headers = {"Authorization": "Bearer " + config.get("api_key", "")}
    if cancel.is_set():
        return {"supported": True, "error": "余额查询已取消"}
    try:
        with (session_factory or requests.Session)() as http:
            with http.get(url, headers=headers, timeout=INFO_TIMEOUT, allow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError()
                data = response.json()
        if provider == "deepseek":
            entries = data["balance_infos"]
            if not entries:
                raise ValueError()
            text = " / ".join(_money(row["total_balance"], row["currency"]) for row in entries)
        else:
            text = _money(data["data"]["available_balance"], currency)
        return {"supported": True, "text": text}
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return {"supported": True, "error": "余额暂时无法查询；聊天不受影响。"}
