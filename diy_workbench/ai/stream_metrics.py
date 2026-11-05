"""仅在客户端记录输出阶段耗时，不向服务请求中加入时间或显示状态。"""

import time
import uuid


class StreamMetrics:
    def __init__(self, reasoning_callback):
        self.phase_id = uuid.uuid4().hex
        self.callback = reasoning_callback
        self.started = time.monotonic()
        self.output_at, self.thinking_at = None, None
        self.reasoning_seconds = 0.0

    def observe(self, text, reasoning, tool_output=False):
        now = time.monotonic()
        if self.output_at is None and (text or reasoning or tool_output):
            self.output_at = now
        if reasoning:
            if self.thinking_at is None:
                self.thinking_at = now
            self._emit(reasoning, now, True)
        if (text or tool_output) and self.thinking_at is not None:
            self._stop_thinking(now)

    def _emit(self, text, now, active):
        elapsed = self.reasoning_seconds + (now - self.thinking_at if self.thinking_at is not None else 0)
        self.callback({"id": self.phase_id, "text": text, "seconds": elapsed, "active": active})

    def _stop_thinking(self, now):
        self.reasoning_seconds += now - self.thinking_at
        self.thinking_at = None
        self._emit("", now, False)

    def finish(self, usage):
        now = time.monotonic()
        if self.thinking_at is not None:
            self._stop_thinking(now)
        generation = now - self.output_at if self.output_at is not None else 0
        speed = usage.get("output_tokens", 0) / generation if generation >= .01 and usage.get("output_known") else None
        return {"elapsed_seconds": now - self.started, "generation_seconds": generation,
                "output_speed": speed, "reasoning_seconds": self.reasoning_seconds}
