"""原生沙盒放在可终止进程；复制资源、JSON和进程等待均在QThread。"""

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from PyQt5.QtCore import QThread, pyqtSignal
from sandbox import WORKER_ARGUMENT

from sandbox.test_data import digest, revision
from sandbox.test_templates import apply_template

SCENE_TIMEOUT = 25
RESOURCES = ("MDPro3_Data/Plugins/x86_64/ocgcore.dll", "Data/script.zip", "Data/locales/zh-CN/cards.cdb")
BOOTSTRAP = '''import os,sys
root=sys.argv[1]
internal=os.path.join(root,"提取文件","_internal")
sys.path[:0]=[root,internal,os.path.join(root,"提取文件")]
import fast_launch
import faulthandler
faulthandler.enable()
if fast_launch.USE_SOURCE: sys.path.insert(0,fast_launch.SRC_DIR)
sys.meta_path.insert(0,fast_launch.ExtractedPycFinder())
handles=[os.add_dll_directory(p) for p in (internal,os.path.join(internal,"PyQt5","Qt5","bin")) if os.path.isdir(p)]
from sandbox.worker import main
main(sys.argv[2],sys.argv[3])
'''


def command(source, target):
    root = Path(sys.prefix)
    executable = next(root.glob("YGODIY_*.app.exe"), None)
    if executable:
        return [str(executable), "-c", BOOTSTRAP, str(root), str(source), str(target)]
    if getattr(sys, "frozen", False):
        return [sys.executable, WORKER_ARGUMENT, str(source), str(target)]
    return [sys.executable, "-m", "sandbox.worker", str(source), str(target)]


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SandboxWorker(QThread):
    progressed = pyqtSignal(dict)
    completed = pyqtSignal(dict)

    def __init__(self, document, scenarios, parent=None, runtime=None):
        super().__init__(parent)
        self.document, self.scenarios = copy.deepcopy(document), copy.deepcopy(scenarios)
        self.runtime = runtime
        self.cancel_flag = threading.Event()

    def cancel(self):
        self.cancel_flag.set()

    def _scene(self, scene, folder, runtime):
        source, target = folder / "input.json", folder / "output.json"
        target.unlink(missing_ok=True)
        source.write_text(json.dumps({"document": self.document, "scenario": scene, "runtime": str(runtime)},
            ensure_ascii=False), encoding="utf-8", newline="\n")
        env = {k: v for k, v in os.environ.items() if not any(p in k.upper() for p in ("API_KEY", "APIKEY", "SECRET", "TOKEN"))}
        started = time.monotonic()
        with tempfile.TemporaryFile() as error_log:
            process = subprocess.Popen(command(source, target), env=env, cwd=Path(__file__).resolve().parents[2], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=error_log, creationflags=subprocess.CREATE_NO_WINDOW)
            stopped = None
            try:
                while process.poll() is None:
                    if self.cancel_flag.wait(.05):
                        stopped = "已取消"
                        break
                    if time.monotonic() - started > SCENE_TIMEOUT:
                        stopped = "超时"
                        break
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait()
            if stopped:
                return {"status": stopped, "errors": ["本情景未完成，不能视为通过。"], "checks": []}
            if target.exists():
                result = _read(target)
                if not isinstance(result, dict):
                    raise ValueError("沙盒返回的结果不是对象。")
                return result
            error_log.seek(0)
            detail = error_log.read(4000).decode("utf-8", "replace")
            return {"status": "进程异常", "exit_code": process.returncode, "errors": [detail or "沙盒进程未返回结果。"], "checks": []}

    def run(self):
        results = []
        try:
            from sandbox.core import default_mdpro3
            source = Path(self.runtime or default_mdpro3())
            with tempfile.TemporaryDirectory(prefix="ygodiy-sandbox-") as temporary:
                folder = Path(temporary)
                runtime = folder / "runtime"
                for relative in RESOURCES:
                    if self.cancel_flag.is_set():
                        break
                    target = runtime / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source / relative, target)
                for scene in self.scenarios:
                    if self.cancel_flag.is_set():
                        break
                    started = time.monotonic()
                    expected = scene.get("expect", [])
                    try:
                        expected = apply_template(copy.deepcopy(scene))["expect"]
                        result = self._scene(scene, folder, runtime)
                    except Exception as error:
                        result = {"status": "环境异常", "errors": [type(error).__name__ + "：" + str(error)[:600]], "checks": []}
                    if result["status"] != "通过" and "unreached_assertions" not in result:
                        result["unreached_assertions"] = expected
                    result.update(scenario_id=scene["id"], name=scene["name"], effect=scene["effect"], basis=scene["basis"],
                        template=scene["template"], revision=revision(self.document), scenario_revision=digest(scene),
                        seconds=round(time.monotonic() - started, 3))
                    results.append(result)
                    self.progressed.emit(result)
        except Exception as error:
            self.completed.emit({"results": results, "error": "沙盒无法运行：%s：%s" % (type(error).__name__, str(error)[:600]),
                                 "cancelled": self.cancel_flag.is_set()})
            return
        self.completed.emit({"results": results, "cancelled": self.cancel_flag.is_set()})
