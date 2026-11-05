"""同步流式 HTTP 客户端，只由 QThread 使用；取消标志不跨线程操作 socket。"""

import time
import sys
import hashlib
from datetime import datetime, timezone

import requests

from .providers import ServiceError, StreamResult, request_data, sse_events
from .settings import DEFAULTS, validate
from .service_info import claude_output_limit
from .stream_metrics import StreamMetrics
from .http_policy import (Cancelled, RequestTimeout, check as _check, retry_delay, balance_error,
                          status_error as _status_error, CONNECT_TIMEOUT, MAX_RETRIES, RETRY_STATUS)
from .task_budget import for_task


def request_record(config, system, messages, tools, result, when):
    from .cache_policy import prompt_units
    from .cache_policy import cache_diagnostic
    from .context_budget import estimate
    from .model_info import prices
    from .usage import estimate_cost
    from .model_catalog import cache_key
    units = prompt_units(system, messages, tools or [])
    hashes = [hashlib.sha256(part.encode()).hexdigest() for part in units]
    previous = config.get("cache_hashes", [])
    matched = 0
    for old, new in zip(previous, hashes):
        if old != new:
            break
        matched += 1
    rates = prices(config, result["usage"].get("input_tokens", 0), when)
    return {"request_id": config.get("_request_id"), "model": config["model"], "protocol": config["protocol"], "preset": config.get("preset", "custom"),
            "scope": cache_key(config),
            "purpose": config.get("purpose", "chat"), "usage": result["usage"], "usage_known": result["usage_known"],
            "cache_debug": cache_diagnostic(config, when),
            "rates": rates, "cost": estimate_cost(result["usage"], rates), "at": when.isoformat(),
            "request_end": len(messages), "estimate": estimate(system, messages, tools or []),
            "cache_hashes": hashes, "prefix": {"matched_units": matched, "previous_units": len(previous),
                "unchanged": matched == len(previous), "common_chars": sum(len(part) for part in units[:matched])}}


def _read_stream(response, result, check, on_text, probe, allow_tools=False, metrics=None):
    for frame in sse_events(response, check):
        check()
        previous_reasoning = len(result.reasoning_content or "")
        text = result.feed(frame)
        if metrics is not None:
            metrics.observe(text, (result.reasoning_content or "")[previous_reasoning:], bool(result.calls) or thinking_block_present(result))
        if text:
            on_text(text)
        if result.terminal:
            break
    check()
    return result.result(probe, allow_tools)


def _record_result(result, metrics, config, system, messages, tools, when, completed, on_request):
    usage = dict(result.usage)
    if completed is None:
        usage["output_known"] = False
    timing = metrics.finish(usage)
    if thinking_block_present(result) and result.reasoning_content is None:
        timing["reasoning_seconds"] = None
    info = request_record(config, system, messages, tools,
                          {"usage": usage, "usage_known": completed is not None and result.usage_known}, when)
    info.update(timing, completed=completed is not None, truncated=bool(completed and completed.get("truncated")),
                finished_at=datetime.now(timezone.utc).isoformat())
    info["actual_model"] = result.model
    budget = config["_task_budget"]
    budget.record(info)
    if budget.limit:
        info["task_cost"] = budget.snapshot()
    journal = config.get("_request_journal")
    error = sys.exc_info()[0]
    if error is not None:
        info["error_type"] = error.__name__
    reason = None if completed is not None else error.__name__ if error else "HTTP未返回完整结果"
    if journal is not None and not journal.finish(info, reason=reason):
        info["record_warning"] = "请求结果日志未能写入；会话仍保存已返回用量，请检查磁盘。"
    on_request(info)
    return info


def _receive(response, result, metrics, config, system, messages, tools, when, check, on_text, probe, on_request):
    completed = None
    try:
        completed = _read_stream(response, result, check, on_text, probe, bool(tools), metrics)
    finally:
        info = _record_result(result, metrics, config, system, messages, tools, when, completed, on_request)
    return dict(completed, output_limit=config.get("max_tokens", 0), request_record=info)


def stream_chat(config, system, messages, cancel, on_text, on_status, probe=False, session_factory=None,
                tools=None, on_request=lambda _: None, on_reasoning=lambda _: None):
    error = validate(config)
    if error:
        raise ServiceError(error)
    config = for_task(config)
    budget = config["_task_budget"]
    with (session_factory or requests.Session)() as http:
        _check(cancel)
        if config["protocol"] == "claude" and not config.get("max_tokens"):
            on_status("正在查询 Claude 模型的最大输出上限……")
            config = dict(config, max_tokens=claude_output_limit(config, http))
            _check(cancel)
        url, headers, payload = request_data(config, system, messages, probe, tools)
        for attempt in range(MAX_RETRIES + 1):
            _check(cancel)
            budget.before_request(config)
            when = datetime.now(timezone.utc)
            result = StreamResult(config["protocol"])
            metrics = StreamMetrics(lambda data: on_reasoning(dict(data, purpose=config.get("purpose", "chat"))))
            timeout = config.get("request_timeout", DEFAULTS["request_timeout"])
            started = time.monotonic()
            check = lambda: _check(cancel, started, timeout)
            journal = config.get("_request_journal")
            if journal is not None:
                config = dict(config, _request_id=journal.begin(config))
            receiving = False
            try:
                with http.post(url, headers=headers, json=payload, stream=True, allow_redirects=False,
                               timeout=(CONNECT_TIMEOUT, min(config["read_timeout"], timeout))) as response:
                    check()
                    if response.status_code == 200:
                        receiving = True
                        return _receive(response, result, metrics, config, system, messages, tools, when,
                                        check, on_text, probe, on_request)
                    if balance_error(response):
                        raise ServiceError(_status_error(402, probe) if response.status_code == 402 else
                                           "账户余额或付费额度不足，请到当前服务商检查账户或手动更换服务；不会自动重试。")
                    # 部分兼容服务不接受 stream_options，仅在明确指出这个字段时重试一次。
                    if response.status_code == 400 and "stream_options" in payload and attempt < MAX_RETRIES:
                        detail = response.content[:8192].decode("utf-8", "replace")
                        if "stream_options" in detail:
                            payload = dict(payload)
                            payload.pop("stream_options")
                            on_status("服务不支持流式用量参数，改用兼容格式重试……")
                            continue
                    if response.status_code == 400 and attempt < MAX_RETRIES:
                        detail = response.content[:8192].decode("utf-8", "replace")
                        rejected = [name for name in ("reasoning_effort", "output_config", "thinking") if name in payload and name in detail]
                        if rejected:
                            payload = {key: value for key, value in payload.items() if key not in rejected}
                            on_status("这个模型不支持思考等级，已改用默认设置。")
                            continue
                    if response.status_code not in RETRY_STATUS or attempt == MAX_RETRIES:
                        raise ServiceError(_status_error(response.status_code, probe))
                    delay = retry_delay(response, attempt)
                    on_status("服务繁忙，%.1f 秒后第 %d 次重试（等待最多60秒，可停止）……" % (delay, attempt + 1))
            except (RequestTimeout, requests.Timeout):
                _check(cancel)
                budget.uncertain()
                raise RequestTimeout("单次请求超时，已保留完成的工具进度和部分回复；点击「继续」接着执行，可在高级调整请求时限和读取超时。") from None
            except requests.ConnectionError:
                _check(cancel)
                budget.uncertain()
                if result.text or result.calls or result.reasoning_content or result.content_blocks or result.usage_known or attempt == MAX_RETRIES:
                    raise ServiceError("网络超时或连接中断，可重试；已显示的部分回复会保留。") from None
                budget.before_request(config)
                delay = min(2 ** attempt, 4)
                on_status("网络连接失败，准备第 %d 次重试……" % (attempt + 1))
            except requests.RequestException:
                _check(cancel)
                raise ServiceError("网络请求失败，请检查服务地址、网络或代理设置。") from None
            finally:
                if journal is not None:
                    error = sys.exc_info()[0]
                    if not receiving:
                        _record_result(result, metrics, config, system, messages, tools, when, None, on_request)
                    if not journal.finish(reason=error.__name__ if error else "HTTP未返回完整结果"):
                        on_status("请求记录未能写入，请检查磁盘；本次不会被记作零费用。")
            if cancel.wait(delay):
                raise Cancelled()
    raise ServiceError("服务暂时不可用，请稍后重试。")


def thinking_block_present(result):
    return any(block.get("type") in ("thinking", "redacted_thinking") for block in result.content_blocks.values())
