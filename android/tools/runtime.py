"""安装已固定版本并核对完整性的本地 Python/Wasm 运行环境。"""
import base64
import hashlib
import json
import shutil
import tarfile
import urllib.request
from pathlib import Path

VERSION = "0.26.4"
INTEGRITY = "z2CHsjVlhhJi5tYBF0AYAfNEPo3zq/z+xOpFtk1tweJkRaTqU4UK/7pLvo8DBU2VDPH31vB3pSI+8fnoqrVrFg=="
FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip")


def prepare(output, cache):
    cache.mkdir(parents=True, exist_ok=True)
    package = cache / f"pyodide-{VERSION}.tgz"
    if not package.is_file():
        with urllib.request.urlopen(f"https://registry.npmjs.org/pyodide/-/{package.name}", timeout=120) as response:
            package.write_bytes(response.read())
    if base64.b64encode(hashlib.sha512(package.read_bytes()).digest()).decode() != INTEGRITY:
        raise ValueError(f"运行库校验失败，请重新下载 {package}")
    target = output / "runtime"
    target.mkdir(exist_ok=True)
    with tarfile.open(package, "r:gz") as archive:
        for name in FILES:
            with archive.extractfile("package/" + name) as source, (target / ("stdlib.data" if name == "python_stdlib.zip" else name)).open("wb") as dest:
                shutil.copyfileobj(source, dest)
        lock = json.load(archive.extractfile("package/pyodide-lock.json"))
        lock["packages"] = {}
        (target / "pyodide-lock.json").write_text(json.dumps(lock), "utf-8")
