"""读已有的扩展包：列出信息、读出卡片，供「已安装」页和导入用。只读取已知的路径，不解压包里的文件。"""

from contextlib import closing, contextmanager
from functools import lru_cache
import os
import re
import shutil
import tempfile
import zipfile

from . import cardinfo, cdb, sqlite
from .string_names import read_names

MEDIA_FOLDERS = {"closeup": (".png",), "overframe": (".png", ".jpg"), "art2": (".png",), "video": (".mp4",)}
YGODIY_PREFIX = "ygodiy-"
UNVERIFIED_FOLDER = "ygodiy-verify/"


def copy_database(archive, name, path):
    with archive.open(name) as source, open(path, "wb") as output:
        shutil.copyfileobj(source, output)


def archive_names(archive):
    texts = (archive.read(item).decode("utf-8-sig", "replace") for item in archive.namelist()
             if item.lower().endswith(".conf"))
    return read_names(texts)


def archive_setnames(archive):
    return archive_names(archive)["setnames"]


def _title(archive, fallback):
    if "corres_srv.ini" in archive.namelist():
        found = re.search(r"^PackName\s*=\s*(.+)$", archive.read("corres_srv.ini").decode("utf-8", "replace"), re.M)
        if found:
            return found.group(1).strip()
    return fallback


def summary(path):
    stat = os.stat(path)
    return dict(_summary(path, stat.st_size, stat.st_mtime_ns))


@lru_cache(maxsize=128)
def _summary(path, size, modified):
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    row = {"path": path, "file": name, "title": stem, "cards": 0, "size": size, "time": modified / 1e9,
           "ours": name.startswith(YGODIY_PREFIX), "unverified": False}
    try:
        with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as folder:
            row["title"] = _title(archive, stem)
            row["unverified"] = any(item.startswith(UNVERIFIED_FOLDER) for item in archive.namelist())
            database = os.path.join(folder, "pack.cdb")
            for member in archive.namelist():
                if member.lower().endswith(".cdb"):
                    copy_database(archive, member, database)
                    with closing(sqlite.connect(database, readonly=True)) as connection:
                        row["cards"] += connection.query("select count(*) from datas")[0][0]
    except (OSError, sqlite.DatabaseError, zipfile.BadZipFile, ValueError):
        row["title"] = stem + "（读取失败）"
    return row


def list_packs(folder):
    if not folder or not os.path.isdir(folder):
        return []
    names = sorted(name for name in os.listdir(folder) if name.lower().endswith((".ypk", ".zip")))
    return [summary(os.path.join(folder, name)) for name in names]


def _records(archive, folder):
    names = set(archive.namelist())
    databases = [name for name in archive.namelist() if name.lower().endswith(".cdb")]
    if not databases:
        raise ValueError("这个文件里没有卡片数据库。")
    for member in databases:
        path = os.path.join(folder, "pack.cdb")
        copy_database(archive, member, path)
        for card in cdb.read_cards(path):
            yield _archive_card(archive, names, card)


def _archive_card(archive, names, card):
    code = card["record"]["code"]
    script = "script/c%d.lua" % code
    art = next((item for item in ("art/%d.jpg" % code, "pics/%d.jpg" % code) if item in names), None)
    media = {}
    for kind, extensions in MEDIA_FOLDERS.items():
        for extension in extensions:
            item = "%s/%d%s" % (kind, code, extension)
            if item in names:
                media[kind] = (extension, archive.read(item))
    card.update(script=archive.read(script).decode("utf-8", "replace") if script in names else "",
                art=archive.read(art) if art else None, media=media)
    return card


@contextmanager
def open_cards(path, *, pack_settings=False):
    """逐张读取卡图和媒体，避免把整个扩展包的视频一起保存在内存。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    if os.path.splitext(path)[1].lower() == ".cdb":
        yield stem, ({"setnames": {}, "counters": {}} if pack_settings else {}), cdb.read_cards(path)
        return
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as folder:
        names = archive_names(archive)
        yield _title(archive, stem), (names if pack_settings else names["setnames"]), _records(archive, folder)


def read_cards(path):
    with open_cards(path) as (title, _, cards):
        return title, list(cards)


def setcodes(value):
    return ["0x%x" % part for part in cdb.unpack_setcode(value)]


def card_data(rec):
    """cdb 记录 → 编辑器的卡片数据；和 cardinfo.from_ygodiy 相反。"""
    return cardinfo.to_ygodiy(rec)
