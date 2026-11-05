"""读已有的扩展包：列出信息、读出卡片，供「已安装」页和导入用。只读取已知的路径，不解压包里的文件。"""

import os
import re
import tempfile
import zipfile

from . import cardinfo, sqlite

MEDIA_FOLDERS = {"closeup": (".png",), "overframe": (".png", ".jpg"), "art2": (".png",), "video": (".mp4",)}
YGODIY_PREFIX = "ygodiy-"
UNVERIFIED_FOLDER = "ygodiy-verify/"


def _database(archive, folder):
    name = next((item for item in archive.namelist() if item.lower().endswith(".cdb")), None)
    if name is None:
        return None
    path = os.path.join(folder, "pack.cdb")
    with open(path, "wb") as stream:
        stream.write(archive.read(name))
    return path


def _title(archive, fallback):
    if "corres_srv.ini" in archive.namelist():
        found = re.search(r"^PackName\s*=\s*(.+)$", archive.read("corres_srv.ini").decode("utf-8", "replace"), re.M)
        if found:
            return found.group(1).strip()
    return fallback


def summary(path):
    name = os.path.basename(path)
    stem = os.path.splitext(name)[0]
    row = {"path": path, "file": name, "title": stem, "cards": 0, "size": os.path.getsize(path), "time": os.path.getmtime(path),
           "ours": name.startswith(YGODIY_PREFIX), "unverified": False}
    try:
        with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as folder:
            row["title"] = _title(archive, stem)
            row["unverified"] = any(item.startswith(UNVERIFIED_FOLDER) for item in archive.namelist())
            database = _database(archive, folder)
            if database:
                connection = sqlite.connect(database, readonly=True)
                row["cards"] = connection.query("select count(*) from datas")[0][0]
                connection.close()
    except (OSError, zipfile.BadZipFile, ValueError):
        row["title"] = stem + "（读取失败）"
    return row


def list_packs(folder):
    if not folder or not os.path.isdir(folder):
        return []
    names = sorted(name for name in os.listdir(folder) if name.lower().endswith((".ypk", ".zip")))
    return [summary(os.path.join(folder, name)) for name in names]


def read_cards(path):
    """→ (卡包名, 卡片列表)。每张卡：cdb 记录、脚本、提示文字、卡图字节、资源 {种类: (后缀, 字节)}。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory() as folder:
        names = set(archive.namelist())
        database = _database(archive, folder)
        if database is None:
            raise ValueError("这个文件里没有卡片数据库。")
        connection = sqlite.connect(database, readonly=True)
        columns = ",".join("t.str%d" % i for i in range(1, 17))
        rows = connection.query("select d.id,d.alias,d.setcode,d.type,d.atk,d.def,d.level,d.race,d.attribute,d.category,t.name,t.desc,%s "
                                "from datas d join texts t on d.id=t.id" % columns)
        connection.close()
        cards = []
        for row in rows:
            code = row[0]
            rec = dict(zip(("code", "alias", "setcode", "type", "atk", "def", "level", "race", "attribute", "category", "name", "desc"), row))
            script = "script/c%d.lua" % code
            art = next((item for item in ("art/%d.jpg" % code, "pics/%d.jpg" % code) if item in names), None)
            media = {}
            for kind, extensions in MEDIA_FOLDERS.items():
                for extension in extensions:
                    item = "%s/%d%s" % (kind, code, extension)
                    if item in names:
                        media[kind] = (extension, archive.read(item))
            cards.append({"record": rec, "strings": {str(i): text for i, text in enumerate(row[12:28]) if text},
                          "script": archive.read(script).decode("utf-8", "replace") if script in names else "",
                          "art": archive.read(art) if art else None, "media": media})
        return _title(archive, stem), cards


def setcodes(value):
    return ["0x%x" % (value >> shift & 0xffff) for shift in (0, 16, 32, 48) if value >> shift & 0xffff]


def card_data(rec):
    """cdb 记录 → 编辑器的卡片数据；和 cardinfo.from_ygodiy 相反。"""
    return cardinfo.to_ygodiy(rec)
