"""源码运行、独立打包和旧启动器共用的资源与用户数据位置。"""

import os
from pathlib import Path
import sys


SOURCE_DIR = Path(__file__).resolve().parent
RESOURCE_FOLDERS = ("mold", "CardBack", "Field_Center", "Past_Version", "Rush_Duel", "config")
CONFIG_FILES = ("config.json", "rd_config.json", "fc_config.json", "back_config.json", "past_config.json")


def resource_dir():
    configured = os.environ.get("YGODIY_RESOURCES")
    if configured:
        return Path(configured).expanduser().resolve()
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return SOURCE_DIR / "resources"


def rpath(relative_path):
    return str(resource_dir() / relative_path)


def app_dir():
    configured = os.environ.get("YGODIY_APP_DIR")
    if configured:
        return str(Path(configured).expanduser().resolve())
    if getattr(sys, "frozen", False):
        return str(Path(sys.executable).resolve().parent)
    return str(SOURCE_DIR / "data")


def prepare_runtime():
    Path(app_dir()).mkdir(parents=True, exist_ok=True)
    required = [resource_dir() / "config" / name for name in CONFIG_FILES]
    required.append(resource_dir() / "mold" / "secret.key")
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "缺少运行资源，请先运行 python scripts/prepare_resources.py。\n" + "\n".join(missing)
        )
