"""使用当前虚拟环境构建 Windows 独立程序。"""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "win32":
        raise SystemExit("请在 64 位 Windows 上构建。")
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("已验证的构建环境为 Python 3.12，请用 py -3.12 -m venv .venv 创建环境。")
    from PyQt5.QtCore import QLibraryInfo

    if not Path(QLibraryInfo.location(QLibraryInfo.PluginsPath)).is_dir():
        raise SystemExit("Qt 5 无法识别当前虚拟环境路径。请在纯英文目录创建虚拟环境并安装 requirements-build.txt，再使用该环境运行本脚本。")
    subprocess.run([sys.executable, "scripts/prepare_resources.py", "--check"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "YGODIY.spec"], cwd=ROOT, check=True)
    print(f"构建完成，程序位于 {ROOT / 'dist' / 'YGODIY' / 'YGODIY.exe'}")


if __name__ == "__main__":
    main()
