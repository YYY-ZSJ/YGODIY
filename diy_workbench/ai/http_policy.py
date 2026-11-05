"""单次 HTTP 的截止检查、错误提示和可取消重试等待策略。"""

import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .providers import ServiceError

CONNECT_TIMEOUT = 8
MAX_RETRIES = 2
MAX_RETRY_AFTER = 60
RETRY_STATUS = (408, 429, 500, 502, 503, 504)
BALANCE_CODES = {"insufficient_quota", "insufficient_balance", "insufficient_funds", "balance_not_enough"}
BALANCE_MESSAGES = ("余额不足", "insufficient balance", "insufficient credits", "credit balance is too low")


class Cancelled(Exception):
    pass


class RequestTimeout(ServiceError):
    """当前响应未完成；已完成的工具结果仍可续接。"""


def check(cancel, started=None, timeout=0):
    if cancel.is_set():
        raise Cancelled()
    if started is not None and timeout and time.monotonic() - started >= timeout:
        raise RequestTimeout("单次请求超过 %d 秒，已保留完成的进度，可点「继续」接着执行；可在高级设置调整时限。" % timeout)


def retry_delay(response, attempt, now=None):
    fallback = min(2 ** attempt, 4)
    if response.status_code not in (429, 503):
        return fallback
    value = (getattr(response, "headers", None) or {}).get("Retry-After", "").strip()
    try:
        if value.isascii() and value.isdigit():
            delay = int(value)
        else:
            at = parsedate_to_datetime(value)
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            delay = (at - (now or datetime.now(timezone.utc))).total_seconds()
        return max(0, min(delay, MAX_RETRY_AFTER))
    except (ValueError, TypeError, OverflowError):
        return fallback


def status_error(status, probe):
    if status in (401, 403):
        return "认证失败，请检查 API Key、服务地址及模型权限。"
    if status == 402:
        return "账户余额不足（HTTP 402），请到当前服务商充值或手动更换服务。此错误不会自动重试。"
    if status == 429:
        return "请求速率或并发达到上限（HTTP 429），请稍后再试；如仍失败，请检查服务商的额度提示。"
    if status == 404:
        return "没有找到接口或模型，请检查 base_url、接口类型和模型名。"
    if status == 400 and probe:
        return "服务拒绝了工具调用检查，请确认该模型支持工具调用且参数设置正确。"
    return "服务请求失败（HTTP %d），请检查配置或稍后重试。" % status


def balance_error(response):
    if response.status_code == 402:
        return True
    if response.status_code not in (400, 403, 429):
        return False
    try:
        body = json.loads(response.content[:8192])
        error = body.get("error", {})
        if not isinstance(error, dict):
            return False
        message = str(error.get("message", "")).casefold()
        return (error.get("code") in BALANCE_CODES or error.get("type") in BALANCE_CODES or
                any(part in message for part in BALANCE_MESSAGES))
    except (ValueError, TypeError, AttributeError):
        return False
