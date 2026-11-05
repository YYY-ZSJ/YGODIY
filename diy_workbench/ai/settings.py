"""AI 服务设置与 Windows 本机密钥保护，不接触制卡器的全局设置。"""

import base64
import ctypes
import json
import math
import os
from pathlib import Path
from urllib.parse import urlsplit

SETTINGS_FILE = "AI服务设置.json"
SETTINGS_VERSION = 3
DEFAULT_READ_TIMEOUT = 120
LEGACY_READ_TIMEOUT = 30
DEFAULT_REQUEST_TIMEOUT = 600
DEFAULTS = {"service_type": "text", "preset": "custom", "protocol": "openai", "base_url": "", "model": "",
            "api_key": "", "read_timeout": DEFAULT_READ_TIMEOUT, "request_timeout": DEFAULT_REQUEST_TIMEOUT,
            "max_tokens": 0, "tool_call_limit": 60, "task_cost_limit": 0.0, "model_overrides": {}, "reasoning_level": ""}
PROFILE_FIELDS = ("service_type", "protocol", "base_url", "model", "read_timeout", "request_timeout",
                  "max_tokens", "tool_call_limit", "task_cost_limit", "model_overrides", "reasoning_level")


def model_overrides(saved):
    result = {}
    if not isinstance(saved, dict):
        return result
    for model, value in saved.items():
        if not isinstance(model, str) or not isinstance(value, dict):
            continue
        item = {}
        context = value.get("context_window")
        if type(context) is int and 0 < context <= 2000000000:
            item["context_window"] = context
        rates = value.get("prices")
        fields = ("input", "cache_read", "cache_write", "output")
        if isinstance(rates, dict) and all(type(rates.get(k)) in (int, float) and math.isfinite(rates[k])
                                         and 0 <= rates[k] <= 1000000 for k in fields):
            item["prices"] = {k: rates[k] for k in fields}
            item["prices"]["currency"] = str(rates.get("currency") or "CNY")[:12]
        if item:
            result[model] = item
    return result


def settings_path():
    from ygopack.mdpro3 import app_dir
    return Path(os.environ.get("YGODIY_AI_SETTINGS_DIR") or app_dir()) / SETTINGS_FILE


class _Blob(ctypes.Structure):
    _fields_ = [("size", ctypes.c_uint32), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(data, protect):
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    buffer = ctypes.create_string_buffer(data)
    source = _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    if protect:
        call = crypt32.CryptProtectData
        call.argtypes = [ctypes.POINTER(_Blob), ctypes.c_wchar_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_Blob)]
        args = (ctypes.byref(source), "YGODIY AI", None, None, None, 1, ctypes.byref(target))
    else:
        call = crypt32.CryptUnprotectData
        call.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_Blob)]
        args = (ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    call.restype = ctypes.c_int
    if not call(*args):
        raise OSError("无法使用 Windows 本机密钥保护，请重填 API Key")
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree(target.data)


def upgrade_settings_data(data):
    """原位升级已解析配置；只改版本/旧默认，不解密Key或写盘。"""
    version = data.get("version", 1)
    version = version if type(version) is int else 1
    if version >= SETTINGS_VERSION:
        return False
    for saved in data.get("profiles", {}).values():
        if not isinstance(saved, dict):
            continue
        if version < 2 and saved.get("max_tokens") == 4096:
            saved["max_tokens"] = 0
        if type(saved.get("read_timeout")) is int and saved["read_timeout"] == LEGACY_READ_TIMEOUT:
            saved["read_timeout"] = DEFAULT_READ_TIMEOUT
    data["version"] = SETTINGS_VERSION
    return True


def load_settings():
    """返回配置和中文提示；读取或解密失败时仍可打开工作台。"""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("profiles", {}), dict):
            raise ValueError()
    except FileNotFoundError:
        return {"active": "custom", "profiles": {}, "consents": [], "ui": {"send_with_enter": True}}, ""
    except (OSError, ValueError):
        return {"active": "custom", "profiles": {}, "consents": [], "ui": {"send_with_enter": True}}, "AI 设置未能读取，请重新设置服务商。"
    upgrade_settings_data(data)
    notices = []
    profiles = {}
    for key, saved in data.get("profiles", {}).items():
        if not isinstance(saved, dict):
            continue
        profile = dict(DEFAULTS, preset=key)
        profile.update({k: saved[k] for k in PROFILE_FIELDS if k in saved and isinstance(saved[k], type(DEFAULTS[k]))})
        cost = saved.get("task_cost_limit", 0)
        profile["task_cost_limit"] = float(cost) if type(cost) in (int, float) and math.isfinite(cost) and 0 <= cost <= 1000000 else 0.0
        profile["model_overrides"] = model_overrides(profile["model_overrides"])
        if saved.get("key_dpapi"):
            try:
                profile["api_key"] = _crypt(base64.b64decode(saved["key_dpapi"]), False).decode("utf-8")
            except (OSError, ValueError, TypeError):
                notices.append("已保存的 API Key 无法在本机解密，请重新填写。")
        profiles[key] = profile
    consents = data.get("consents", [])
    ui = data.get("ui") if isinstance(data.get("ui"), dict) else {}
    return {"active": data.get("active", "custom"), "profiles": profiles,
            "consents": consents if isinstance(consents, list) else [],
            "ui": {"send_with_enter": ui.get("send_with_enter", True) is not False,
                   "token_format": "wan" if ui.get("token_format") == "wan" else "grouped"}}, "；".join(set(notices))


def save_settings(data):
    profiles = {}
    for key, profile in data["profiles"].items():
        saved = {k: profile[k] for k in PROFILE_FIELDS if k in profile}
        if profile.get("api_key"):
            saved["key_dpapi"] = base64.b64encode(_crypt(profile["api_key"].encode("utf-8"), True)).decode("ascii")
        profiles[key] = saved
    payload = {"version": SETTINGS_VERSION, "active": data["active"], "profiles": profiles, "consents": data["consents"],
               "ui": data.get("ui", {"send_with_enter": True})}
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    os.replace(temp, path)


def consent_key(config):
    return config["protocol"] + ":" + config["base_url"].rstrip("/")


def validate(config):
    if config.get("service_type", "text") != "text":
        return "伊格尼斯目前只支持文本对话服务。"
    if config.get("protocol") not in ("openai", "claude"):
        return "请选择支持的接口类型。"
    try:
        url = urlsplit(config.get("base_url", ""))
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            return "服务地址须为 http 或 https 地址，不能在地址中填写 Key。"
        if url.query or url.fragment:
            return "服务地址不能包含查询参数或锚点，请只填写 base_url。"
        url.port
    except ValueError:
        return "服务地址格式不正确。"
    if not config.get("model", "").strip():
        return "请选择或填写模型名。"
    local = url.hostname in ("localhost", "127.0.0.1", "::1")
    if not local and not config.get("api_key", "").strip():
        return "未设置 API Key，请先打开 AI 服务设置。"
    if not isinstance(config.get("read_timeout"), int) or not 5 <= config["read_timeout"] <= 600:
        return "读取超时应在 5～600 秒之间。"
    if type(config.get("request_timeout", DEFAULT_REQUEST_TIMEOUT)) is not int or not 30 <= config.get("request_timeout", DEFAULT_REQUEST_TIMEOUT) <= 7200:
        return "单次请求时限应在 30～7200 秒之间。"
    if not isinstance(config.get("max_tokens"), int) or not 0 <= config["max_tokens"] <= 2000000:
        return "单次输出上限应为「不限制」或 1～2000000 token。"
    if type(config.get("tool_call_limit", 60)) is not int or not 0 <= config.get("tool_call_limit", 60) <= 10000:
        return "工具调用上限应为「不限制」或1～10000次。"
    cost = config.get("task_cost_limit", 0)
    if type(cost) not in (int, float) or not math.isfinite(cost) or not 0 <= cost <= 1000000:
        return "单次任务费用上限应为「关闭」或0～1000000之间的金额。"
    return ""
