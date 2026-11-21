"""把 Windows 构建产物及原始卡图打包，可选生成中文安装向导。"""

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_version import VERSION

BUNDLE = f"YGODIY-{VERSION}-Windows-x64"
BUILD = ROOT / "dist" / "YGODIY"


def pack_program(archive, library):
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=6) as bundle:
        bundle.write(BUILD / "YGODIY.exe", f"{BUNDLE}/YGODIY.exe")
        for path in sorted((BUILD / "_internal").rglob("*")):
            if path.is_file():
                bundle.write(path, f"{BUNDLE}/{path.relative_to(BUILD).as_posix()}")
        if library:
            for name in ("cards.json", "card_packs.json"):
                path = library / name
                if path.is_file():
                    bundle.write(path, f"{BUNDLE}/离线卡库/{name}")


def pack_artwork(archive, source):
    images = sorted(p for p in source.iterdir() if re.fullmatch(r"[0-9]+\.(png|jpg|webp)", p.name, re.I))
    if not images or len({int(p.stem) for p in images}) != len(images):
        raise ValueError("原图库为空，或同一卡密对应多份文件。")
    with ZipFile(archive, "w", ZIP_STORED) as bundle:
        for path in images:
            bundle.write(path, f"离线卡库/卡图/{path.name}")


def checksum(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def expanded_size(path):
    with ZipFile(path) as bundle:
        return sum(entry.file_size for entry in bundle.infolist())


def make_installer(compiler, program, artwork, *, full_offline=False):
    options = ["/DFullOffline"] if full_offline else []
    subprocess.run([
        str(compiler), *options, f"/DArchiveDir={program.parent}", f"/DInstalledBytes={expanded_size(program)}",
        f"/DArtBytes={expanded_size(artwork)}", f"/DArtHash={checksum(artwork)}",
        str(ROOT / "scripts" / "windows-installer.iss"),
    ], check=True)
    return program.with_name(f"YGODIY_{VERSION}.exe" if full_offline else f"{BUNDLE}-Setup.exe")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="发布文件的输出目录")
    parser.add_argument("--card-library", type=Path, help="公开卡片文字库目录")
    parser.add_argument("--artwork", type=Path, help="以卡密命名的原始卡图目录")
    parser.add_argument("--iscc", type=Path, help="用指定的 Inno Setup 编译器生成安装向导")
    parser.add_argument("--full-offline", action="store_true", help="把全部原图内置到单个 EXE，可单独离线安装")
    args = parser.parse_args()
    if not (BUILD / "YGODIY.exe").is_file() or not (BUILD / "_internal").is_dir():
        parser.error("请先运行 scripts/build.py 构建 Windows 程序。")
    if args.card_library and not (args.card_library / "cards.json").is_file():
        parser.error("卡库目录缺少 cards.json。")
    if args.artwork and not args.artwork.is_dir():
        parser.error("找不到原始卡图目录。")
    if args.iscc and not args.artwork:
        parser.error("生成完整安装向导时，请用 --artwork 指定原始卡图目录。")
    if args.full_offline and not args.iscc:
        parser.error("--full-offline 需要用 --iscc 指定安装向导编译器。")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output) as tmp:
        program = Path(tmp) / f"{BUNDLE}.zip"
        pack_program(program, args.card_library)
        files = [program]
        if args.artwork:
            artwork = Path(tmp) / f"YGODIY-{VERSION}-HD-Art.zip"
            pack_artwork(artwork, args.artwork)
            files.append(artwork)
            if args.iscc:
                files.append(make_installer(args.iscc, program, artwork, full_offline=args.full_offline))
        for path in files:
            digest = checksum(path)
            sidecar = path.with_name(path.name + ".sha256")
            sidecar.write_text(f"{digest}  {path.name}\n", encoding="ascii", newline="\n")
            path.replace(output / path.name)
            sidecar.replace(output / sidecar.name)
            print(f"{output / path.name}\nSHA-256  {digest}")


if __name__ == "__main__":
    main()
