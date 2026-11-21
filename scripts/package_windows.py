"""把 Windows 构建产物打成可分发的便携 ZIP，并生成 SHA-256 校验文件。"""

import argparse
import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_version import VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="发布文件的输出目录")
    parser.add_argument("--card-library", type=Path, help="附带公开卡片文字库的目录")
    args = parser.parse_args()
    build = ROOT / "dist" / "YGODIY"
    if not (build / "YGODIY.exe").is_file() or not (build / "_internal").is_dir():
        parser.error("请先运行 scripts/build.py 构建 Windows 程序。")
    if args.card_library and not (args.card_library / "cards.json").is_file():
        parser.error("卡库目录缺少 cards.json。")

    folder = f"YGODIY-{VERSION}-Windows-x64"
    args.output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.output) as tmp:
        archive = Path(tmp) / f"{folder}.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=6) as bundle:
            bundle.write(build / "YGODIY.exe", f"{folder}/YGODIY.exe")
            for path in sorted((build / "_internal").rglob("*")):
                if path.is_file():
                    bundle.write(path, f"{folder}/{path.relative_to(build).as_posix()}")
            if args.card_library:
                for name in ("cards.json", "card_packs.json"):
                    path = args.card_library / name
                    if path.is_file():
                        bundle.write(path, f"{folder}/离线卡库/{name}")
        with archive.open("rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        checksum = archive.with_suffix(".zip.sha256")
        checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii", newline="\n")
        archive.replace(args.output / archive.name)
        checksum.replace(args.output / checksum.name)
    print(f"{args.output / archive.name}\nSHA-256  {digest}")


if __name__ == "__main__":
    main()
