"""编辑器各面板共享的本机偏好，沿用制卡器设置文件。"""
import json
import os
from functools import lru_cache

from common import _app_dir, _tab_log


@lru_cache(maxsize=1)
def _settings(path):
    try:
        with open(path, encoding="utf-8") as source:
            value = json.load(source)
            return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        _tab_log("读取制卡器设置失败：" + str(error))
        return {}


def get(key, default=None):
    return _settings(os.path.join(_app_dir(), "制卡器设置.json")).get(key, default)


def set_value(key, value):
    path = os.path.join(_app_dir(), "制卡器设置.json")
    settings = _settings(path)
    if os.environ.get("YGODIY_NO_STATE_WRITE"):
        settings[key] = value
        return
    updated = dict(settings)
    updated[key] = value
    with open(path + ".tmp", "w", encoding="utf-8") as target:
        json.dump(updated, target, ensure_ascii=False, indent=2)
    os.replace(path + ".tmp", path)
    settings.update(updated)
