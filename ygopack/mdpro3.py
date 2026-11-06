"""找到本机的 MDPro3，以及导出卡包要放进去的扩展目录（MDPro3\\Expansions）。

查找顺序（先找到的优先）：
  1. 自定义路径：平台设置.json 里的 expansions_dir（可以是 MDPro3 的安装目录，也可以直接是任意扩展目录，
     比如 ygopro2 的 expansions）
  2. 环境变量 YGODIY_MDPRO3
  3. 桌面、开始菜单里指向 MDPro3.exe 的快捷方式
  4. 注册表：卸载信息；系统记录过的「运行过的程序」（只看 MDPro3.exe 这一项）
  5. 各个本地硬盘的根目录和第一层子目录里名字带 MDPro 的文件夹

设置单独存在程序目录的 平台设置.json：制卡器在运行时会把它读进来的「制卡器设置.json」整体写回，
平台的设置放在那里有被覆盖掉的风险。

    python -m ygopack.mdpro3                 # 看找到了哪里
    python -m ygopack.mdpro3 --set 路径      # 自定义
    python -m ygopack.mdpro3 --clear         # 恢复自动查找
"""

import json
import os
import string
import struct
import sys
from runtime_paths import app_dir

EXE = "MDPro3.exe"
SETTINGS_FILE = "平台设置.json"
SETTINGS_KEY = "expansions_dir"


# ---------------------------------------------------------------- 设置

def settings_path():
    return os.path.join(app_dir(), SETTINGS_FILE)


def load_settings():
    try:
        with open(settings_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def save_settings(**changes):
    data = load_settings()
    for k, v in changes.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def set_custom_dir(path):
    """自定义扩展目录（或 MDPro3 安装目录）。传 None 恢复自动查找。"""
    if path is not None:
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            raise FileNotFoundError("文件夹不存在：%s" % path)
    save_settings(**{SETTINGS_KEY: path})


# ---------------------------------------------------------------- 查找

def is_mdpro3_dir(path):
    return bool(path) and os.path.isfile(os.path.join(path, EXE))


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def candidates():
    """所有找到的 MDPro3 安装目录 [(目录, 来源)]，按优先级排列，去重。"""
    seen, out = set(), []

    def add(path, source):
        if path and is_mdpro3_dir(path) and _norm(path) not in seen:
            seen.add(_norm(path))
            out.append((os.path.abspath(path), source))

    add(os.environ.get("YGODIY_MDPRO3"), "环境变量 YGODIY_MDPRO3")
    for lnk in _shortcut_files():
        target = read_shortcut_target(lnk)
        if target and os.path.basename(target).lower() == EXE.lower():
            add(os.path.dirname(target), "快捷方式 " + os.path.basename(lnk))
    for path, source in _registry_hits():
        add(path, source)
    for path in _scan_drives():
        add(path, "硬盘扫描")
    return out


def find_mdpro3():
    found = candidates()
    return found[0] if found else (None, None)


def official_setnames(md_dir=None):
    """MDPro3 的官方字段：[(编号, 中文名, 日文名)]，读 Data/locales/zh-CN/strings.conf 的 !setname 行。"""
    if md_dir is None:
        md_dir, _ = find_mdpro3()
    if not md_dir:
        return []
    path = os.path.join(md_dir, "Data", "locales", "zh-CN", "strings.conf")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        if line.startswith("!setname "):
            code, _, names = line[len("!setname "):].strip().partition(" ")
            zh, _, jp = names.partition("\t")
            out.append((code.lower(), zh.strip(), jp.strip()))
    return out


def expansions_dir():
    """导出卡包要放进去的目录。返回 (目录, 说明)；找不到时目录是 None。"""
    custom = load_settings().get(SETTINGS_KEY)
    if custom:
        if is_mdpro3_dir(custom):
            return os.path.join(custom, "Expansions"), "自定义的 MDPro3 目录"
        if os.path.isdir(custom):
            return custom, "自定义的扩展目录"
        return None, "自定义路径不存在：%s（可用 --clear 恢复自动查找）" % custom
    path, source = find_mdpro3()
    if not path:
        return None, "没有找到 MDPro3，请自定义路径"
    return os.path.join(path, "Expansions"), "自动找到的 MDPro3（%s）" % source


# ---------------------------------------------------------------- 快捷方式

def _shortcut_files():
    roots = []
    for var in ("USERPROFILE", "PUBLIC"):
        base = os.environ.get(var)
        if base:
            roots.append(os.path.join(base, "Desktop"))
    for var in ("APPDATA", "PROGRAMDATA"):
        base = os.environ.get(var)
        if base:
            roots.append(os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs"))
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(os.path.join(appdata, "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar"))
    for root in roots:
        for dirpath, _, files in _walk(root, 3):
            for f in files:
                if f.lower().endswith(".lnk"):
                    yield os.path.join(dirpath, f)


def _walk(root, depth):
    if not os.path.isdir(root):
        return
    base = root.rstrip("\\/").count(os.sep)
    for dirpath, dirs, files in os.walk(root):
        if dirpath.count(os.sep) - base >= depth:
            dirs[:] = []
        yield dirpath, dirs, files


def read_shortcut_target(path):
    """读 .lnk 指向的本地路径（Shell Link 二进制格式的 LinkInfo 部分）；读不出来返回 None。"""
    try:
        with open(path, "rb") as f:
            data = f.read()
        if len(data) < 0x4c or struct.unpack_from("<I", data, 0)[0] != 0x4c:
            return None
        flags = struct.unpack_from("<I", data, 0x14)[0]
        pos = 0x4c
        if flags & 0x1:                                   # HasLinkTargetIDList
            pos += 2 + struct.unpack_from("<H", data, pos)[0]
        if not flags & 0x2:                               # HasLinkInfo
            return None
        info = pos
        _, header_size, info_flags = struct.unpack_from("<III", data, info)
        if not info_flags & 0x1:                          # VolumeIDAndLocalBasePath
            return None
        local_off, _, suffix_off = struct.unpack_from("<III", data, info + 16)
        if header_size >= 0x24:
            local_u, suffix_u = struct.unpack_from("<II", data, info + 28)
            return _wstr(data, info + local_u) + _wstr(data, info + suffix_u)
        return _astr(data, info + local_off) + _astr(data, info + suffix_off)
    except (OSError, struct.error, UnicodeDecodeError):
        return None


def _astr(data, pos):
    end = data.index(b"\0", pos)
    return data[pos:end].decode("mbcs" if sys.platform == "win32" else "latin-1")


def _wstr(data, pos):
    end = pos
    while data[end:end + 2] != b"\0\0":
        end += 2
    return data[pos:end].decode("utf-16-le")


# ---------------------------------------------------------------- 注册表

def _registry_hits():
    try:
        import winreg
    except ImportError:
        return
    uninstall = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive, key in ((winreg.HKEY_CURRENT_USER, uninstall), (winreg.HKEY_LOCAL_MACHINE, uninstall),
                      (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")):
        for sub in _subkeys(winreg, hive, key):
            values = _values(winreg, hive, key + "\\" + sub)
            if "mdpro" in str(values.get("DisplayName", "")).lower():
                loc = values.get("InstallLocation") or os.path.dirname(str(values.get("DisplayIcon", "")).split(",")[0])
                yield loc, "注册表卸载信息"
    # 系统记录过运行的程序：值名就是完整的 exe 路径，只取 MDPro3.exe
    for key in (r"Software\Classes\Local Settings\Software\Microsoft\Windows\Shell\MuiCache",
                r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Store"):
        for name in _values(winreg, winreg.HKEY_CURRENT_USER, key):
            exe = name.split(".FriendlyAppName")[0].split(".ApplicationCompany")[0]
            if os.path.basename(exe).lower() == EXE.lower():
                yield os.path.dirname(exe), "运行记录"


def _subkeys(winreg, hive, key):
    try:
        with winreg.OpenKey(hive, key) as k:
            i = 0
            while True:
                try:
                    yield winreg.EnumKey(k, i)
                except OSError:
                    return
                i += 1
    except OSError:
        return


def _values(winreg, hive, key):
    out = {}
    try:
        with winreg.OpenKey(hive, key) as k:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                out[name] = value
                i += 1
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- 硬盘扫描

def _fixed_drives():
    if sys.platform != "win32":
        return []
    import ctypes
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    out = []
    for i, letter in enumerate(string.ascii_uppercase):
        if mask & (1 << i):
            root = letter + ":\\"
            if ctypes.windll.kernel32.GetDriveTypeW(root) == 3:   # DRIVE_FIXED
                out.append(root)
    return out


def _scan_drives():
    """根目录与第一层子目录里名字带 mdpro 的文件夹（例如 D:\\MDPro3、D:\\Game\\MDPro3）。"""
    for root in _fixed_drives():
        for first in _listdirs(root):
            path = os.path.join(root, first)
            if "mdpro" in first.lower():
                yield path
                continue
            if first.lower() in ("windows", "$recycle.bin", "system volume information"):
                continue
            for second in _listdirs(path):
                if "mdpro" in second.lower():
                    yield os.path.join(path, second)


def _listdirs(path):
    try:
        return [e.name for e in os.scandir(path) if e.is_dir(follow_symlinks=False)]
    except OSError:
        return []


def main():
    import argparse
    ap = argparse.ArgumentParser(description="查找 MDPro3 的扩展目录")
    ap.add_argument("--set", metavar="路径", help="自定义 MDPro3 安装目录或扩展目录")
    ap.add_argument("--clear", action="store_true", help="清除自定义，恢复自动查找")
    args = ap.parse_args()
    if args.set:
        set_custom_dir(args.set)
    elif args.clear:
        set_custom_dir(None)
    for path, source in candidates():
        print("找到 MDPro3：%s（%s）" % (path, source))
    target, note = expansions_dir()
    print("导出到：%s —— %s" % (target or "（无）", note))
    return 0 if target else 1


if __name__ == "__main__":
    sys.exit(main())
