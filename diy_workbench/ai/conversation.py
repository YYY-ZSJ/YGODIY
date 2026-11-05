"""有界的工具对话循环；操作经桥接信号在主线程执行，工作线程不访问控件。"""

import json
import copy

from .client import RequestTimeout, _check, stream_chat
from .providers import ServiceError
from .request_context import stable_json
from .task_budget import BudgetPause, for_task
from .tool_loop import LoopGuard, argument_error, encode_result, paused

DEFAULT_TOOL_CALL_LIMIT = 60


def _tool_messages(protocol, result, outputs):
    calls = result["tool_calls"]
    if protocol == "claude":
        content = copy.deepcopy(result.get("provider_content") or [])
        by_id = {call["id"]: call for call in calls}
        for block in content:
            if block.get("type") == "tool_use" and block.get("id") in by_id:
                call = by_id[block["id"]]
                # Claude 的 input 只能是对象；坏原文保留在结构化错误的 received 中。
                block["input"] = {} if argument_error(call) else json.loads(call["arguments"])
        return [{"role": "assistant", "content": content}, {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call["id"], "content": output,
             "is_error": not json.loads(output).get("ok", False)} for call, output in zip(calls, outputs)]}]
    assistant = {"role": "assistant", "content": result["text"] or None, "tool_calls": [
        {"id": call["id"], "type": "function", "function": {"name": call["name"], "arguments": call["arguments"]}}
        for call in calls]}
    if result.get("reasoning_content") is not None:
        assistant["reasoning_content"] = result["reasoning_content"]
    return [assistant] + [{"role": "tool", "tool_call_id": call["id"], "content": output} for call, output in zip(calls, outputs)]


def final_message(protocol, result):
    if protocol == "claude" and result.get("provider_content"):
        return {"role": "assistant", "content": copy.deepcopy(result["provider_content"])}
    message = {"role": "assistant", "content": result["text"]}
    if result.get("reasoning_content") is not None:
        message["reasoning_content"] = result["reasoning_content"]
    return message


def _checked_calls(result):
    calls = result["tool_calls"]
    if any(not isinstance(call, dict) or not isinstance(call.get("id"), str) or not 0 < len(call["id"]) <= 200 for call in calls) or len({call["id"] for call in calls}) != len(calls):
        raise ServiceError("服务返回的工具编号无效，本轮操作未执行。")
    return calls


def _run_call(call, execute, report_error, guard):
    error = argument_error(call)
    if error is not None:
        guard.state.update(call_key=None, call_count=0)
        report_error(call, error)
        return error, guard.result(call, error)
    stopped = guard.call(call)
    if stopped:
        return {"ok": False, "error": stopped, "not_executed": True}, stopped
    output = execute(call)
    return output, guard.result(call, output)


def run_conversation(config, system, messages, cancel, on_text, on_status, tools, execute, on_transcript=lambda _: None,
                     on_request=lambda _: None, fit_context=None, on_reasoning=lambda _: None, resume=None,
                     on_tool_error=lambda call, output: None, session_factory=None, on_response=lambda _: None):
    calls_used, transcript = 0, list(messages)
    config = for_task(config, resume)
    budget = config["_task_budget"]
    usage = {"input_tokens": 0, "output_tokens": 0}
    known, text = True, []
    legend_sent = "affects代号" in system or any("tool_result_legend" in str(message.get("content", "")) for message in messages)
    limit = config.get("tool_call_limit", DEFAULT_TOOL_CALL_LIMIT)
    pending, guard = resume if (resume or {}).get("result") else None, LoopGuard((resume or {}).get("guard"))
    while True:
        _check(cancel)
        if pending is None:
            try:
                if fit_context is not None:
                    transcript, config = fit_context(transcript, config)
                result = stream_chat(config, system, transcript, cancel, on_text, on_status, tools=tools,
                                     on_request=on_request, on_reasoning=on_reasoning, session_factory=session_factory)
            except (RequestTimeout, BudgetPause) as error:
                return paused(None, [], guard, transcript, text, usage, known, reason=str(error), budget=budget)
            known = known and result["usage_known"]
            on_response(result)
            for key in usage:
                usage[key] += result["usage"][key]
            if result["text"]:
                text.append(result["text"])
        else:
            result = pending["result"]
        info = result.get("request_record", {})
        config = dict(config, max_tokens=result["output_limit"], cache_previous_end=len(transcript),
                      cache_previous_finished_at=info.get("finished_at"),
                      cache_hashes=info.get("cache_hashes", []))
        calls = result["tool_calls"]
        if not calls:
            transcript = transcript + [final_message(config["protocol"], result)]
            on_transcript(transcript)
            return dict(result, text="\n\n".join(text), usage=usage, usage_known=known, transcript=transcript)
        calls = _checked_calls(result)
        outputs, stopped = list((pending or {}).get("outputs", [])), ""
        reason = budget.reason(config)
        if reason:
            return paused(result, outputs, guard, transcript, text, usage, known, reason=reason, budget=budget)
        for call in calls[len(outputs):]:
            _check(cancel)
            if not stopped and limit and calls_used >= limit:
                return paused(result, outputs, guard, transcript, text, usage, known, limit, budget=budget)
            if stopped:
                outputs.append(stable_json({"ok": False, "error": stopped, "not_executed": True}))
                continue
            output, stopped = _run_call(call, execute, on_tool_error, guard)
            calls_used += 1
            outputs.append(encode_result(call, output, legend_sent))
            legend_sent = True
        transcript = transcript + _tool_messages(config["protocol"], result, outputs)
        on_transcript(transcript)
        on_text("\n\n" if result["text"] else "")
        pending = None
        if stopped:
            return dict(result, text="\n\n".join(text), usage=usage, usage_known=known, transcript=transcript, stopped=stopped)
