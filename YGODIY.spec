# -*- mode: python ; coding: utf-8 -*-
import json
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

root = Path(SPECPATH)
sys.path.insert(0, str(root))
from app_version import VERSION

windows_version = (*map(int, VERSION.split(".")), 0)
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=windows_version, prodvers=windows_version, fileType=1),
    kids=[StringFileInfo([StringTable("040904B0", [
        StringStruct("FileDescription", "YGODIY"), StringStruct("ProductName", "YGODIY"),
        StringStruct("FileVersion", VERSION), StringStruct("ProductVersion", VERSION),
        StringStruct("OriginalFilename", "YGODIY.exe"),
    ])]), VarFileInfo([VarStruct("Translation", [0x0409, 1200])])],
)
manifest = json.loads((root / "resources-manifest.json").read_text(encoding="utf-8"))
datas = [(str(root / "resources" / name), str(Path(name).parent)) for name in manifest["files"]]
for package in ("blocks", "diy_workbench", "effect_model", "sandbox", "ygopack"):
    datas.extend(collect_data_files(package))
datas.extend(collect_data_files("opencc"))
datas.extend([(str(root / "LICENSE"), "."), (str(root / "THIRD_PARTY.md"), ".")])
datas.append((str(root / "licenses" / "Qwen3-LICENSE"), "licenses"))
datas.append((str(root / "YGODIY.ico"), "."))

analysis = Analysis([str(root / "main.py")], pathex=[str(root)], datas=datas,
                    hiddenimports=["sandbox.worker"], excludes=["tkinter"],
                    runtime_hooks=[str(root / "scripts" / "preload_translation.py")])
archive = PYZ(analysis.pure)
executable = EXE(archive, analysis.scripts, [], exclude_binaries=True,
                 name="YGODIY", console=False, upx=False, icon=str(root / "YGODIY.ico"),
                 version=version_info)
collection = COLLECT(executable, analysis.binaries, analysis.datas,
                     name="YGODIY", upx=False)
