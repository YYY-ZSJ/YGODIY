"""按需获取服务商模型列表，缓存只含模型 ID，不含 Key 或请求正文。"""

import copy
import hashlib
import json
import threading
import time

import requests
from PyQt5.QtCore import QObject, QThread, pyqtSignal

from .settings import settings_path
from .service_info import INFO_TIMEOUT

MODEL_LIST_BUDGET = 20
MAX_MODEL_PAGES = 20
_MEMORY_CACHE = {}
_CACHE_LOCK = threading.Lock()


def cache_key(config):
    scope = "\0".join(config.get(k, "") for k in ("protocol", "base_url", "api_key"))
    return hashlib.sha256(scope.encode("utf-8")).hexdigest()


def _cache_path():
    return settings_path().with_name(settings_path().name + ".models")


def _read_cache():
    try:
        saved = json.loads(_cache_path().read_text(encoding="utf-8"))
        return saved if isinstance(saved, dict) else {}
    except (OSError, ValueError):
        return {}


def _ids(data):
    if not isinstance(data, list):
        return []
    return list(dict.fromkeys(row["id"] for row in data if isinstance(row, dict)
                             and isinstance(row.get("id"), str) and 0 < len(row["id"]) <= 200))


def cached_models(config):
    return _ids(_MEMORY_CACHE.get(str(_cache_path()), {}).get(cache_key(config)))


def warm_cache():
    _MEMORY_CACHE[str(_cache_path())] = _read_cache()


def model_metadata(config):
    rows = _MEMORY_CACHE.get(str(_cache_path()), {}).get(cache_key(config), [])
    return next((dict(row) for row in rows if row.get("id") == config.get("model")), {})


def _save_models(key, models):
    from .file_jobs import write_json
    with _CACHE_LOCK:
        saved = _read_cache()
        saved[key] = [dict(model) if isinstance(model, dict) else {"id": model} for model in models]
        _MEMORY_CACHE[str(_cache_path())] = saved
        write_json(_cache_path(), saved)


def fetch_models(config, cancel, session_factory=None, metadata=False):
    root = config["base_url"].rstrip("/")
    for suffix in ("/chat/completions", "/messages"):
        if root.endswith(suffix):
            root = root[:-len(suffix)]
    headers = {"Accept": "application/json"}
    if config["protocol"] == "claude":
        headers.update({"x-api-key": config.get("api_key", ""), "anthropic-version": "2026-10-21"})
    elif config.get("api_key"):
        headers["Authorization"] = "Bearer " + config["api_key"]
    models, params, started = [], {}, time.monotonic()
    with (session_factory or requests.Session)() as http:
        for _ in range(MAX_MODEL_PAGES):
            if cancel.is_set() or time.monotonic() - started > MODEL_LIST_BUDGET:
                raise ValueError("模型查询已停止或超时")
            with http.get(root + "/models", headers=headers, params=params,
                          allow_redirects=False, timeout=INFO_TIMEOUT) as response:
                if response.status_code != 200:
                    raise ValueError("模型查询失败")
                data = response.json()
            for row in data.get("data") or []:
                if not isinstance(row, dict) or not _ids([row]):
                    continue
                model = {"id": row["id"]}
                for field in ("context_window", "max_input_tokens", "max_output_tokens", "max_tokens"):
                    value = row.get(field)
                    if type(value) is int and value > 0:
                        model[field] = value
                models.append(model)
            if not data.get("has_more"):
                break
            after = data.get("last_id")
            if not isinstance(after, str) or not after or after == params.get("after_id"):
                raise ValueError("模型分页无效")
            params = {"after_id": after}
        else:
            raise ValueError("模型分页过多")
    if not models:
        raise ValueError("服务未返回模型")
    models = list({row["id"]: row for row in models}.values())
    return models if metadata else _ids(models)


class ModelWorker(QThread):
    completed = pyqtSignal(dict)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        self.cancel_flag = threading.Event()

    def run(self):
        result = {"key": cache_key(self.config)}
        try:
            rows = fetch_models(self.config, self.cancel_flag, metadata=True)
            result["models"], result["metadata"] = _ids(rows), rows
            if not self.cancel_flag.is_set():
                try:
                    _save_models(result["key"], rows)
                except OSError:
                    result["notice"] = "模型已获取，但本机缓存未能保存。"
        except (requests.RequestException, ValueError, TypeError, AttributeError, KeyError):
            result["error"] = "模型列表暂时无法获取，使用本机缓存或预设示例，仍可手填。"
        finally:
            self.config["api_key"] = ""
        if not self.cancel_flag.is_set():
            self.completed.emit(result)


class ModelCatalog(QObject):
    updated = pyqtSignal(dict)
    idle = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.workers = set()
        self.current_key = None

    def refresh(self, config):
        self.cancel()
        self.current_key = cache_key(config)
        worker = ModelWorker(config, self)
        self.workers.add(worker)
        worker.completed.connect(self._result)
        worker.finished.connect(self._finished)
        worker.start()

    def _result(self, result):
        if self.sender().cancel_flag.is_set() or result["key"] != self.current_key:
            return
        self.updated.emit(result)

    def _finished(self):
        worker = self.sender()
        self.workers.discard(worker)
        worker.deleteLater()
        if not self.workers:
            self.idle.emit()

    def cancel(self):
        for worker in self.workers:
            worker.cancel_flag.set()

    def shutdown(self):
        self.cancel()
        for worker in self.workers:
            worker.wait()
