"""独立会话文件及可重建索引。磁盘方法仅由 FileJobs 顺序调用。"""

import copy
import hashlib
import json
import uuid
from datetime import datetime

from PyQt5.QtCore import QObject, pyqtSignal

from . import history
from .file_jobs import read_json, write_json


def new_record(title="新对话"):
    return dict(history.fresh_session(), version=4, id=uuid.uuid4().hex, title=title, pinned=False,
                updated=datetime.now().isoformat(timespec="seconds"), attached=True, wire=[], summaries=[])


def snapshot(record):
    """历史正文和协议消息只追加；只复制仍可能变化的容器。"""
    result = dict(record)
    result["messages"] = [dict(m, **({"events": list(m["events"])} if "events" in m else {}),
                               **({"reasoning_parts": [dict(part) for part in m["reasoning_parts"]]} if "reasoning_parts" in m else {}),
                               **({"changes": dict(m["changes"])} if m.get("changes") else {}))
                          for m in record["messages"]]
    result["wire"] = list(record.get("wire", []))
    result["summaries"] = list(record.get("summaries", []))
    result["usage"] = copy.deepcopy(record.get("usage", {}))
    result["requests"] = list(record.get("requests", []))
    return result


def metadata(record):
    return {key: record.get(key) for key in ("id", "title", "pinned", "updated", "usage")}


def markdown(record):
    parts = ["# " + record.get("title", "新对话")]
    for message in record.get("messages", []):
        role = "玩家" if message.get("role") == "user" else "AI"
        parts += ["\n## " + role, message.get("text", "")]
        if message.get("note"):
            parts.append("> " + message["note"])
        if message.get("changes"):
            from .change_view import full_text
            parts += ["\n### 修改记录", "```text\n" + full_text(message["changes"]) + "\n```"]
    return "\n\n".join(parts) + "\n"


class _SessionDisk:
    def __init__(self, root):
        self.root, self.index = root, {}

    def path(self, uid):
        uid = uuid.UUID(uid).hex
        return self.root / (uid + ".json")

    def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True)
        saved = read_json(self.root / "index.json", {})
        self.index = saved if isinstance(saved, dict) else {}
        # 索引只是加速器；原子会话已落盘、索引尚未更新时也能恢复。
        changed = False
        for path in self.root.glob("*.json"):
            try:
                uid = uuid.UUID(path.stem).hex
            except ValueError:
                continue
            if uid not in self.index:
                record = read_json(path)
                if isinstance(record, dict) and isinstance(record.get("messages"), list):
                    self.index[uid] = metadata(dict(record, id=uid))
                    changed = True
        for uid in list(self.index):
            try:
                exists = self.path(uid).exists()
            except ValueError:
                exists = False
            if not exists:
                del self.index[uid]
                changed = True
        if changed:
            self._save_index()
        return list(self.index.values())

    def _save_index(self):
        write_json(self.root / "index.json", self.index)

    def load(self, uid):
        record = read_json(self.path(uid))
        if not isinstance(record, dict) or not isinstance(record.get("messages"), list):
            raise ValueError("会话文件无效")
        record["id"] = uid
        self._legacy_usage(record)
        history.hydrate_reasoning(record)
        from .request_journal import recover
        if recover(record, self.root / "_requests"):
            self.save(record)
        return record

    @staticmethod
    def _legacy_usage(record):
        usage = record.get("usage") or {}
        if usage.get("calls") and "cache_read_tokens" not in usage:
            record["usage"] = dict(usage, cache_unknown_calls=usage["calls"], cache_measured_input=0,
                                   unpriced_calls=usage["calls"])

    def save(self, record):
        write_json(self.path(record["id"]), record)
        self.index[record["id"]] = metadata(record)
        self._save_index()
        return metadata(record)

    def delete(self, uid):
        self.path(uid).unlink(missing_ok=True)
        self.index.pop(uid, None)
        self._save_index()

    def search(self, query):
        query = query.casefold()
        result = []
        for uid, item in self.index.items():
            if query in item.get("title", "").casefold():
                result.append(item)
                continue
            record = read_json(self.path(uid), {})
            if any(query in message.get("text", "").casefold() for message in record.get("messages", [])):
                result.append(item)
        return result

    def migrate(self, sources):
        imported = []
        ledger = read_json(self.root / "migration.json", {})
        for card_uid, title, legacy in sources:
            conversations = [("active", legacy)] + [(entry.get("id", str(i)), entry)
                                                    for i, entry in enumerate(legacy.get("archives", []))]
            for source_id, saved in conversations:
                if not saved.get("messages") and not saved.get("input"):
                    continue
                content = {k: v for k, v in saved.items() if k != "archives"}
                digest = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                uid = uuid.uuid5(uuid.NAMESPACE_URL, "ygodiy:" + card_uid + ":" + source_id + ":" + digest).hex
                if uid in ledger:
                    continue
                if uid in self.index or self.path(uid).exists():
                    ledger[uid] = True
                    write_json(self.root / "migration.json", ledger)
                    continue
                record = new_record(title + " · " + datetime.now().strftime("%Y-%m-%d"))
                record.update(copy.deepcopy(content))
                record.update(id=uid, version=4, title=title + " · " + datetime.now().strftime("%Y-%m-%d"),
                              migration={"card_uid": card_uid, "source_id": source_id, "digest": digest,
                                         "date_source": "迁移日期（旧对话没有时间戳）"})
                history.recover_interrupted(record)
                self._legacy_usage(record)
                for message in record["messages"]:
                    if message.get("changes"):
                        message["changes"]["available"] = False
                self.save(record)
                ledger[uid] = True
                write_json(self.root / "migration.json", ledger)
                imported.append(metadata(record))
        return imported

    def export(self, uid, path, overwrite=False, record=None):
        from pathlib import Path
        text = markdown(record or self.load(uid))
        path = Path(path)
        if not overwrite:
            try:
                with path.open("x", encoding="utf-8", newline="\n") as handle:
                    handle.write(text)
                return "saved"
            except FileExistsError:
                return "exists"
        temporary = path.with_name(path.name + ".ygodiy.tmp")
        temporary.write_text(text, encoding="utf-8", newline="\n")
        import os
        os.replace(temporary, path)
        return "saved"


class SessionStore(QObject):
    opened = pyqtSignal(dict)
    listed = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, io, root, parent=None):
        super().__init__(parent)
        self.io, self.disk = io, _SessionDisk(root)
        self.records, self.index, self.deleted = {}, {}, set()
        self.current_id, self.selection = None, 0
        self.ready = False

    def initialize(self, sources):
        def loaded(items, error):
            if error:
                self.failed.emit(error)
            self.index.update({m["id"]: m for m in items or []})
            self.ready = True
            self._list()
            self.io.submit(self.disk.migrate, sources, callback=migrated)
            if not self.current_id:
                if self.index:
                    self.open(max(self.index, key=lambda k: self.index[k].get("updated") or ""))
                else:
                    self.create()
        def migrated(items, error):
            if error:
                self.failed.emit("旧对话迁移未完成；原存档保持不变，下次打开会继续。")
            self.index.update({m["id"]: m for m in items or []})
            self._list()
        self.io.submit(self.disk.initialize, callback=loaded)

    def _list(self):
        self.listed.emit(sorted(self.index.values(), key=lambda m: (bool(m.get("pinned")), m.get("updated") or ""), reverse=True))

    def create(self):
        record = new_record()
        self.records[record["id"]] = record
        self.save(record)
        self.open(record["id"])
        return record

    def open(self, uid):
        if uid in self.deleted:
            return
        self.selection += 1
        selection = self.selection
        def loaded(record, error=""):
            if selection != self.selection or uid in self.deleted:
                return
            if error:
                self.failed.emit("会话无法读取，原文件仍保留。")
                return
            self.records[uid] = record
            self.current_id = uid
            history.recover_interrupted(record)
            self.opened.emit(record)
        if uid in self.records:
            self.current_id = uid
            self.opened.emit(self.records[uid])
        else:
            self.io.submit(self.disk.load, uid, callback=loaded)

    def save(self, record, callback=None):
        if record["id"] in self.deleted:
            return
        record["updated"] = datetime.now().isoformat(timespec="seconds")
        frozen = snapshot(record)
        self.index[record["id"]] = metadata(frozen)
        self.io.submit(self.disk.save, frozen, callback=callback)
        self._list()

    def delete(self, uid):
        self.deleted.add(uid)
        self.records.pop(uid, None)
        self.index.pop(uid, None)
        self.io.submit(self.disk.delete, uid)
        if self.current_id == uid:
            self.current_id = None
            self.open(next(iter(self.index))) if self.index else self.create()
        self._list()

    def edit_metadata(self, uid, **patch):
        def update(record, error=""):
            if error or uid in self.deleted:
                self.failed.emit(error or "会话已删除。")
                return
            record.update(patch)
            self.save(record)
        if uid in self.records:
            update(self.records[uid])
        else:
            self.io.submit(self.disk.load, uid, callback=update)

    def search(self, query, callback):
        self.io.submit(self.disk.search, query, callback=callback)
