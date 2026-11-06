"""按公开清单准备运行资源，支持下载资源包或导入已有程序目录。"""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from runtime_paths import RESOURCE_FOLDERS

MANIFEST = ROOT / "resources-manifest.json"
CHUNK_SIZE = 1024 * 1024


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for name in manifest["files"]:
        path = PurePosixPath(name)
        if not path.parts or path.is_absolute() or ".." in path.parts or "\\" in name or path.parts[0] not in (*RESOURCE_FOLDERS, "ygo_translator"):
            raise ValueError(f"资源清单包含不安全路径 {name}")
    return manifest


def valid_file(path, expected):
    return path.is_file() and path.stat().st_size == expected["size"] and sha256(path) == expected["sha256"]


def verify_resources(target, manifest):
    invalid = [name for name, expected in manifest["files"].items() if not valid_file(target / name, expected)]
    if invalid:
        raise ValueError("运行资源缺失或校验失败\n" + "\n".join(invalid[:20]))
    print(f"资源校验通过，共 {len(manifest['files'])} 个文件。", flush=True)


def source_file(folder, name):
    candidates = (folder / name, folder / "resources" / name,
                  folder / "提取文件" / "_internal" / name, folder / "提取文件" / name)
    return next((path for path in candidates if path.is_file()), candidates[0])


def copy_verified(source, target, expected):
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            shutil.copyfileobj(source, temporary, CHUNK_SIZE)
        except BaseException:
            temporary.close()
            temporary_path.unlink(missing_ok=True)
            raise
    try:
        if not valid_file(temporary_path, expected):
            raise ValueError(f"资源校验失败 {target.name}")
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)


def import_directory(folder, target, manifest):
    for name, expected in manifest["files"].items():
        destination = target / name
        if not valid_file(destination, expected):
            with source_file(folder, name).open("rb") as source:
                copy_verified(source, destination, expected)


def import_archive(archive, target, manifest):
    if sha256(archive) != manifest["archive_sha256"]:
        raise ValueError("资源包 SHA-256 与清单不符，请重新下载。")
    with ZipFile(archive) as bundle:
        for name, expected in manifest["files"].items():
            destination = target / name
            if not valid_file(destination, expected):
                with bundle.open(name) as source:
                    copy_verified(source, destination, expected)


def download_archive(manifest):
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    archive = cache / manifest["archive"]
    if archive.is_file() and sha256(archive) == manifest["archive_sha256"]:
        return archive
    temporary = archive.with_suffix(".download")
    print(f"下载运行资源，约 {manifest['archive_size'] / 1024**3:.2f} GiB。", flush=True)
    try:
        with urlopen(manifest["url"], timeout=60) as source, temporary.open("wb") as target:
            shutil.copyfileobj(source, target, CHUNK_SIZE)
        if sha256(temporary) != manifest["archive_sha256"]:
            raise ValueError("下载的资源包校验失败。")
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--from", dest="source", type=Path, help="导入已有程序目录或资源目录")
    mode.add_argument("--archive", type=Path, help="导入已下载的资源 ZIP")
    mode.add_argument("--check", action="store_true", help="只校验资源")
    parser.add_argument("--output", type=Path, default=ROOT / "resources")
    args = parser.parse_args()
    manifest = read_manifest()
    target = args.output.resolve()
    if args.source:
        import_directory(args.source.resolve(), target, manifest)
    elif not args.check:
        import_archive(args.archive.resolve() if args.archive else download_archive(manifest), target, manifest)
    verify_resources(target, manifest)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        raise SystemExit(f"资源准备失败\n{error}") from error
