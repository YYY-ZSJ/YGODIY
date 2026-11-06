# -*- mode: python ; coding: utf-8 -*-
import json
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
manifest = json.loads((root / "resources-manifest.json").read_text(encoding="utf-8"))
datas = [(str(root / "resources" / name), str(Path(name).parent)) for name in manifest["files"]]
for package in ("blocks", "diy_workbench", "effect_model", "sandbox", "ygopack"):
    datas.extend(collect_data_files(package))
datas.extend(collect_data_files("opencc"))
datas.extend([(str(root / "LICENSE"), "."), (str(root / "THIRD_PARTY.md"), ".")])
datas.append((str(root / "licenses" / "Qwen3-LICENSE"), "licenses"))

analysis = Analysis([str(root / "main.py")], pathex=[str(root)], datas=datas,
                    hiddenimports=["sandbox.worker"], excludes=["tkinter"],
                    runtime_hooks=[str(root / "scripts" / "preload_translation.py")])
archive = PYZ(analysis.pure)
executable = EXE(archive, analysis.scripts, [], exclude_binaries=True,
                 name="YGODIY", console=False, upx=False)
collection = COLLECT(executable, analysis.binaries, analysis.datas,
                     name="YGODIY", upx=False)
