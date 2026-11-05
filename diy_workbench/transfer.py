"""卡片和卡包的文件：.ydiy 是 zip，里面一份 manifest.json 加卡图和资源；也能从 .ypk 读卡。"""

import copy
import hashlib
import json
import os
import shutil
import time
import uuid
import zipfile

from ygopack import cardinfo, expansion

from .media_dialog import MEDIA_FOLDER

FORMAT = "ygodiy-transfer/1"
EXTENSION = ".ydiy"
DROPPED_DIY = ("ai",)
MAX_MANIFEST_BYTES = 256 * 1024 * 1024


def _portable(tab):
    data = copy.deepcopy(tab.get("data") or {})
    data.pop("image", None)
    data.pop("_image_ref", None)
    diy = {key: copy.deepcopy(value) for key, value in (tab.get("diy") or {}).items() if key not in DROPPED_DIY}
    return {"title": tab.get("title", ""), "data": data, "diy": diy}


def export_file(path, kind, title, tabs, pack_settings, assets):
    """kind 是 card 或 pack。卡图和资源一起打包，换一台电脑也能导入。"""
    cards = []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, tab in enumerate(tabs):
            entry = _portable(tab)
            image = cardinfo.card_image_bytes(tab.get("data") or {}, assets)
            if image:
                entry["image"] = "images/%d.img" % index
                archive.writestr(entry["image"], image)
            files = {}
            for name, relative in (entry["diy"].get("media") or {}).items():
                source = os.path.join(assets, relative)
                if os.path.exists(source):
                    files[name] = "media/%d-%s%s" % (index, name, os.path.splitext(relative)[1].lower())
                    archive.write(source, files[name])
            entry["diy"].pop("media", None)
            entry["media"] = files
            cards.append(entry)
        manifest = {"format": FORMAT, "kind": kind, "title": title, "diy": copy.deepcopy(pack_settings or {}), "cards": cards}
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))


def _new_tab(title, data, diy, image, media, assets, default_data):
    uid = uuid.uuid4().hex
    merged = copy.deepcopy(default_data)
    merged.update(data)
    merged.pop("image", None)
    merged.pop("_image_ref", None)
    tab = {"title": title, "data": merged, "diy": diy, "_card_uid": uid}
    if image:
        os.makedirs(assets, exist_ok=True)
        reference = hashlib.sha256(image).hexdigest()       # 标签页按内容命名卡图
        with open(os.path.join(assets, reference + ".img"), "wb") as stream:
            stream.write(image)
        merged["_image_ref"] = reference
    if media:
        folder = os.path.join(assets, MEDIA_FOLDER)
        os.makedirs(folder, exist_ok=True)
        saved = {}
        for kind, (extension, content) in media.items():
            name = "%s-%s%s" % (uid, kind, extension)
            with open(os.path.join(folder, name), "wb") as stream:
                stream.write(content)
            saved[kind] = MEDIA_FOLDER + "/" + name
        diy["media"] = saved
    return tab


def read_ydiy(path, assets, default_data):
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("manifest.json")
        if info.file_size > MAX_MANIFEST_BYTES:
            raise ValueError("这个文件的内容太大。")
        manifest = json.loads(archive.read(info).decode("utf-8"))
        if manifest.get("format") != FORMAT or manifest.get("kind") not in ("card", "pack"):
            raise ValueError("不是 YGODIY 的卡片或卡包文件。")
        names = set(archive.namelist())
        tabs = []
        for entry in manifest.get("cards", []):
            image = archive.read(entry["image"]) if entry.get("image") in names else None
            media = {}
            for kind, name in (entry.get("media") or {}).items():
                if name in names and kind in expansion.MEDIA_FOLDERS and os.path.splitext(name)[1].lower() in expansion.MEDIA_FOLDERS[kind]:
                    media[kind] = (os.path.splitext(name)[1].lower(), archive.read(name))
            tabs.append(_new_tab(entry.get("title", "导入的卡"), entry.get("data") or {}, dict(entry.get("diy") or {}), image, media, assets, default_data))
    return {"kind": manifest["kind"], "title": manifest.get("title", "导入的卡包"), "diy": manifest.get("diy") or {}, "tabs": tabs}


def read_ypk(path, assets, default_data):
    """扩展包没有积木：脚本原样保留成手写脚本，卡片资料从 cdb 还原。"""
    title, cards = expansion.read_cards(path)
    tabs = []
    for card in cards:
        rec = card["record"]
        diy = {"setcodes": expansion.setcodes(rec["setcode"]), "category": rec["category"]}
        if card["script"]:
            diy["script"] = card["script"]
        if card["strings"]:
            diy["strings"] = card["strings"]
        if rec["alias"]:
            diy.update(alias=rec["alias"], alias_mode="art")
        tabs.append(_new_tab(rec["name"], expansion.card_data(rec), diy, card["art"], card["media"], assets, default_data))
    return {"kind": "pack", "title": title, "diy": {}, "tabs": tabs}


def read_file(path, assets, default_data):
    reader = read_ydiy if path.lower().endswith(EXTENSION) else read_ypk
    result = reader(path, assets, default_data)
    if not result["tabs"]:
        raise ValueError("这个文件里没有卡片。")
    return result


def _videos(path):
    with zipfile.ZipFile(path) as archive:
        return {os.path.basename(name) for name in archive.namelist() if name.startswith("video/") and name.lower().endswith(".mp4")}


def clean_videos(path, expansions):
    """MDPro3 把卡包里的动态卡图解压到 Video/Art。别的卡包也带着的同名文件要留下；恢复后 MDPro3 会重新解压。"""
    others = set()
    for name in os.listdir(expansions):
        other = os.path.join(expansions, name)
        if name.lower().endswith((".ypk", ".zip")) and os.path.normcase(other) != os.path.normcase(path):
            try:
                others |= _videos(other)
            except (OSError, zipfile.BadZipFile):
                continue
    folder = os.path.join(os.path.dirname(os.path.normpath(expansions)), "Video", "Art")
    removed = 0
    for name in _videos(path) - others:
        target = os.path.join(folder, name)
        if os.path.isfile(target):
            os.remove(target)
            removed += 1
    return removed


def uninstall(path, recycle_folder, expansions=None):
    """卸载进回收站：每次一个子目录，同名卡包卸载多次也不会互相覆盖。返回 (回收站里的路径, 清掉的动态卡图数)。"""
    removed = clean_videos(path, expansions or os.path.dirname(path))
    folder = os.path.join(recycle_folder, time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
    os.makedirs(folder)
    target = os.path.join(folder, os.path.basename(path))
    shutil.move(path, target)
    return target, removed


def recycled(recycle_folder):
    if not os.path.isdir(recycle_folder):
        return []
    rows = []
    for name in sorted(os.listdir(recycle_folder), reverse=True):
        folder = os.path.join(recycle_folder, name)
        if os.path.isdir(folder):
            rows += expansion.list_packs(folder)
    return rows


def restore(path, expansions):
    target = os.path.join(expansions, os.path.basename(path))
    if os.path.exists(target):
        raise ValueError("MDPro3 里已经有同名的卡包，请先卸载那个。")
    os.makedirs(expansions, exist_ok=True)
    shutil.move(path, target)
    os.rmdir(os.path.dirname(path))
    return target


def purge(path):
    os.remove(path)
    os.rmdir(os.path.dirname(path))
