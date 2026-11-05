"""一次请求的候选副本和原值；此模块不修改真实项目。"""

import copy
import re
import uuid

from .block_edits import custom_nodes, validate_tree
from .field_access import location
from .field_rules import FIELD_LABELS, MODE_LABELS, SESSION_NOTE, affected, display_value, field_rules, is_session, validate_patch
from .project_access import candidate_document, card_document


def block_feedback(document):
    from diy_workbench.store import generate
    result = generate(copy.deepcopy(document))
    reading = "\n".join(text for text in (result.pdesc, result.desc) if text)
    warnings = [{"level": level, "message": text} for level, text in result.issues]
    if result.error:
        warnings.append({"level": "生成提示", "message": result.error})
    from blocks.compile import walk
    if any(node["block"] == "f_name" and node["code"] == 0 for node in walk((result.model or {}).get("effects", []))):
        warnings.append({"level": "警告", "message": "f_name.code=0：name只用于读回，不会按卡名查卡号。指定卡名须填真实卡号；比较这张卡的原本卡名可用f_same_code(card=[this_card])，排除这些同名卡再套f_not；f_not_self只排除实体卡自己。此候选尚未完整实现。"})
    if any(node["block"] == "f_set" and re.fullmatch(r"0x0+", str(node.get("setcode", "")).lower()) for node in walk((result.model or {}).get("effects", []))):
        warnings.append({"level": "警告", "message": "f_set.setcode=0x0：name只用于读回，不能据此查字段。请提供实际编号，不要把此候选当作已完整实现。"})
    if (document.get("diy") or {}).get("script"):
        warnings.append({"level": "警告", "message": "这张卡用玩家的手写脚本，积木改动不会进入导出的脚本；要让积木生效，请玩家在「脚本」页改回积木生成。"})
    intent = (document.get("data") or {}).get("effect_text") or ""
    if re.search(r"(?:成为融合召唤的素材|作为融合素材).*(?:送去墓地|送墓)", intent):
        for index, effect in enumerate((result.model or {}).get("effects", [])):
            if effect.get("block") == "effect" and effect.get("event") in ("to_grave", "be_material"):
                warnings.append({"level": "语义差异", "message": "effects[%d].event：当前%s组合尚未精确覆盖官方EVENT_BE_MATERIAL、墓地去向及原因判断；这是近似候选，编译成功不代表严格素材语义已验证。" % (index, effect["event"])})
    return {"reading": reading.strip(), "warnings": warnings, "compiled": result.error is None}


def _feedback_text(feedback):
    lines = [feedback["reading"]] + [row["level"] + "：" + row["message"] for row in feedback["warnings"]]
    return "\n".join(filter(None, lines)) or "尚无可读回的效果；本步不进行沙盒验证。"


def block_reading(document):
    return _feedback_text(block_feedback(document))


class ChangePlan:
    def __init__(self, project, access, owner, answer, mode, auto):
        self.id = uuid.uuid4().hex
        self.project, self.access, self.owner, self.answer = project, access, owner, answer
        self.mode, self.auto = mode, auto
        self.cards, self.packs, self.images = project.capture()
        self.target = (owner or {}).get("_card_uid")
        self.pack_id = next((key for key, pack in self.packs.items() if self.target in pack["tabs"]), None)
        self.sessions = {kind: access.session(kind) for kind in ("past", "fc", "back", "rd") if access.ready(kind)}
        self.cells, self.creations = {}, []
        self.finished, self.state, self.error = False, "pending", ""
        self._rows_cache, self._readings = None, {}
        self._created_previews = {}
        self.dependencies = set()
        self.undo_kept, self.undo_restored = [], []

    def invalidate(self, uid=None):
        self._rows_cache, self._readings = None, {}
        if uid is None:
            self._created_previews.clear()
        else:
            self._created_previews.pop(uid, None)

    def reading(self, uid):
        return _feedback_text(self.feedback(uid))

    def feedback(self, uid):
        if uid not in self._readings:
            self._readings[uid] = block_feedback(self.working_document(uid))
        return self._readings[uid]

    def observe_mode(self, mode):
        if mode in ("past", "fc", "back", "rd") and mode not in self.sessions and self.access.ready(mode):
            self.sessions[mode] = self.access.session(mode)

    def release_unused(self):
        retained = {cell["key"][1] for cell in self.cells.values() if cell["key"][0] != "editor"}
        for creation in self.creations:
            cards = creation["document"]["tabs"] if creation["kind"] == "pack" else [creation["document"]]
            retained.update(card["_card_uid"] for card in cards)
        self.cards = {uid: data for uid, data in self.cards.items() if uid in retained}
        self.packs.clear()
        self.images.clear()
        self.sessions.clear()

    def document(self, uid):
        if uid:
            self.dependencies.add(uid)
        for creation in self.creations:
            cards = creation["document"]["tabs"] if creation["kind"] == "pack" else [creation["document"]]
            for tab in cards:
                if tab["_card_uid"] == uid and not creation["applied"]:
                    return tab
        if uid not in self.cards:
            raise ValueError("请先读取目标卡片并明确填写 card_uid；目标须存在于请求开始时。")
        return self.cards[uid]

    def _cell(self, key, mode, before, after):
        if key in self.cells:
            self.cells[key]["after"] = after
            return self.cells[key]
        cell = {"key": key, "mode": mode, "before": before, "after": after, "applied": False, "current": before}
        self.cells[key] = cell
        return cell

    def working_document(self, uid):
        document = candidate_document(self.document(uid))
        for cell in self.cells.values():
            if cell["key"][0] != "editor" and cell["key"][1] == uid:
                self.access.put_document(document, cell["mode"], {cell["key"][-1]: cell["after"]})
        return document

    def fields(self, mode, fields, card_uid=None):
        uid = card_uid or self.target
        document = self.document(uid)
        patch = validate_patch(self.project.app, mode, fields)
        before_values = self.access.values(self.cards[uid], mode, patch)
        session_patch = {key: value for key, value in patch.items() if is_session(mode, key)}
        if session_patch:
            if mode not in self.sessions:
                raise ValueError("该编辑器在请求开始时尚未打开，请先用 switch_mode 打开它，再生成候选。")
            key = ("editor", mode)
            previous = self.cells[key]["after"] if key in self.cells else self.sessions[mode]
            after = self.access.candidate_session(mode, previous, session_patch)
            self._cell(key, mode, self.sessions[mode], after)
            self.cells[key].setdefault("card_uid", uid)
        for field, value in patch.items():
            if is_session(mode, field):
                continue
            key = location(uid, mode, field)
            pending_new = any(not creation["applied"] and (document is creation["document"] or
                              (creation["kind"] == "pack" and any(document is card for card in creation["document"]["tabs"])))
                              for creation in self.creations)
            if pending_new:
                self.access.put_document(document, mode, {field: value})
                if field == "name":
                    from card_tabs import _tab_title_from_data
                    document["title"] = _tab_title_from_data(document["data"], document["title"])
            else:
                self._cell(key, mode, before_values[field], copy.deepcopy(value))
        return {"card_uid": uid, "mode": mode, "fields": list(patch),
                "affected_modes": list(dict.fromkeys(label for field in patch for label in affected(mode, field))),
                "note": SESSION_NOTE if session_patch else "基础资料保持现有共用设计。"}

    def blocks(self, model, card_uid=None, custom=()):
        from blocks import SCHEMA
        uid = card_uid or self.target
        document = self.document(uid)
        original = (self.cards[uid].get("diy") or {}).get("blocks", {"schema": SCHEMA, "effects": []})
        kept = custom_nodes(original) + custom_nodes((self.working_document(uid).get("diy") or {}).get("blocks", {})) + list(custom)
        canonical = validate_tree(model, original, kept)
        if document is not self.cards[uid]:
            document.setdefault("diy", {})["blocks"] = canonical
        else:
            self._cell(("diy", uid, "blocks"), "diy", copy.deepcopy(original), canonical)
        return {"card_uid": uid, "effects": len(canonical["effects"]), "affected_modes": ["DIY 工作台"],
                **self.feedback(uid),
                "note": "只修改积木，不自动覆盖卡面的效果文字；不执行 Lua 或沙盒。"}

    def design_text(self, text, card_uid=None):
        uid = card_uid or self.target
        document = self.document(uid)
        if document is not self.cards[uid]:
            document.setdefault("diy", {})["design_text"] = text
        else:
            self._cell(("diy", uid, "design_text"), "diy", (self.cards[uid].get("diy") or {}).get("design_text"), text)
        return {"card_uid": uid, "affected_modes": ["DIY 工作台"], "note": "设计稿单独保存，不改卡面效果文字和积木。"}

    def script(self, code, card_uid=None):
        uid = card_uid or self.target
        document = self.document(uid)
        if document is not self.cards[uid]:
            document.setdefault("diy", {})["script"] = code
        else:
            self._cell(("diy", uid, "script"), "diy", (self.cards[uid].get("diy") or {}).get("script"), code)
        return {"card_uid": uid, "affected_modes": ["DIY 工作台"], "note": "这张卡改用手写脚本，积木不再生成脚本。"}

    def card_data(self, strings=None, category=None, card_uid=None):
        from blocks.categories import NAMES, bit
        uid = card_uid or self.target
        document = self.document(uid)
        diy = self.cards[uid].get("diy") or {}
        changes = {}
        if strings is not None:
            if any(not re.fullmatch(r"[1-9]|1[0-6]", key) or not isinstance(text, str) or len(text) > 100 for key, text in strings.items()):
                raise ValueError('strings：键是"1"到"16"（对应str1～str16，str1是aux.Stringid(id,0)），值是最多100字的文字。')
            changes["strings"] = {str(int(key) - 1): text for key, text in strings.items() if text.strip()} or None
        if category is not None:
            unknown = [name for name in category if name not in NAMES]
            if unknown:
                raise ValueError("category：没有这些分类：%s；可选值=%s。" % ("、".join(map(str, unknown)), "、".join(NAMES)))
            changes["category"] = sum(bit(name) for name in set(category))
        if not changes:
            raise ValueError("strings和category至少填一个。")
        for field, value in changes.items():
            if document is not self.cards[uid]:
                document.setdefault("diy", {})[field] = value
            else:
                self._cell(("diy", uid, field), "diy", copy.deepcopy(diy.get(field)), value)
        return {"card_uid": uid, "fields": list(changes), "affected_modes": ["DIY 工作台"], "note": "提示文本和效果分类随卡保存，导出时写进卡片数据。"}

    def new_card(self, name=None, source_uid=None, pack_id=None):
        pack_id = pack_id or self.pack_id
        if pack_id not in self.packs and not any(c["kind"] == "pack" and c["id"] == pack_id for c in self.creations):
            raise ValueError("卡包不在请求快照中。")
        source = self.working_document(source_uid) if source_uid else None
        tab = self.project.new_card(name, source)
        uid = tab["_card_uid"]
        self.cards[uid] = card_document(tab)
        images = {uid: self.images[source_uid]} if source_uid in self.images else {}
        self.creations.append({"id": uid, "kind": "card", "pack_id": pack_id,
                               "document": tab, "images": images, "applied": False, "expected": None})
        return {"card_uid": uid, "pack_id": pack_id, "title": tab["title"], "affected_modes": list(affected("ocg", "name")),
                "note": "新建或复制卡片资料和积木；新卡不继承 AI 会话。"}

    def tests(self, tests, card_uid=None):
        from sandbox.test_data import coverage
        uid = card_uid or self.target
        document = self.document(uid)
        original = copy.deepcopy((self.cards[uid].get("diy") or {}).get("tests"))
        if document is not self.cards[uid]:
            document.setdefault("diy", {})["tests"] = copy.deepcopy(tests)
        else:
            self._cell(("diy", uid, "tests"), "diy", original, copy.deepcopy(tests))
        return {"card_uid": uid, "scenarios": len(tests["scenarios"]), "affected_modes": ["DIY 工作台"],
                "verification": coverage(self.working_document(uid), tests), "note": "情景和结果随卡片保存，旧结果在效果修改后过期。"}

    def new_pack(self, title, source_id=None):
        if source_id is not None and source_id not in self.packs:
            raise ValueError("源卡包不在请求快照中。")
        source = self.packs.get(source_id)
        tabs, images = [], {}
        for uid in source["tabs"] if source else [None]:
            tab = self.project.new_card(None, self.working_document(uid) if uid else None)
            tabs.append(tab)
            self.cards[tab["_card_uid"]] = card_document(tab)
            if uid in self.images:
                images[tab["_card_uid"]] = self.images[uid]
        pack_id = uuid.uuid4().hex
        pack = {"title": title, "current_index": 0, "tabs": tabs}
        if source and source.get("diy"):
            pack["diy"] = copy.deepcopy(source["diy"])
        self.creations.append({"id": pack_id, "kind": "pack", "document": pack, "images": images,
                               "applied": False, "expected": None})
        return {"pack_id": pack_id, "title": title, "cards": [{"card_uid": tab["_card_uid"], "title": tab["title"]} for tab in tabs],
                "affected_modes": list(affected("ocg", "name")), "note": "新卡不继承 AI 会话。"}

    def rows(self):
        if self._rows_cache is not None:
            return self._rows_cache
        rows = []
        for cell in self.cells.values():
            key = cell["key"]
            if key[0] == "editor":
                before, after = cell["before"]["fields"], cell["after"]["fields"]
                for field in after:
                    if before.get(field) != after[field]:
                        rule = field_rules(self.project.app, key[1]).get(field, {})
                        rows.append({"target": MODE_LABELS[key[1]] + " 当前编辑器", "field": field,
                                     "card_uid": cell.get("card_uid"), "mode": key[1],
                                     "before": before.get(field), "after": after[field],
                                     "before_display": display_value(before.get(field), rule),
                                     "after_display": display_value(after[field], rule),
                                     "affected_modes": affected(key[1], field), "note": SESSION_NOTE})
            elif cell["before"] != cell["after"]:
                title = self.cards[key[1]].get("title", key[1])
                rule = field_rules(self.project.app, cell["mode"]).get(key[-1], {})
                rows.append({"target": title, "field": key[-1], "before": cell["before"], "after": cell["after"],
                             "card_uid": key[1], "mode": cell["mode"],
                             "before_display": display_value(cell["before"], rule),
                             "after_display": display_value(cell["after"], rule),
                             "affected_modes": affected(cell["mode"], key[-1])})
                if key[0] == "diy" and key[-1] == "blocks":
                    rows[-1]["reading_after"] = self.reading(key[1])
                if key[0] == "diy" and key[-1] == "tests":
                    for side in ("before", "after"):
                        value = cell[side] or {}
                        rows[-1][side + "_display"] = "%d 个情景，%d 条结果" % (len(value.get("scenarios", [])), len(value.get("results", [])))
        for creation in self.creations:
            rows.append(copy.deepcopy(creation["applied_row"]) if "applied_row" in creation else self.creation_row(creation))
        self._rows_cache = rows
        return rows

    def creation_row(self, creation):
        document = creation["document"]
        if creation["kind"] == "pack":
            value = {"卡包": document["title"], "卡片": [self._created_preview(tab) for tab in document["tabs"]]}
        else:
            value = self._created_preview(document)
        return {"target": document.get("title", "新对象"), "field": "新增卡包" if creation["kind"] == "pack" else "新增卡片",
                "card_uid": document["tabs"][0]["_card_uid"] if creation["kind"] == "pack" else document["_card_uid"], "mode": self.mode,
                "before": None, "after": value, "affected_modes": list(affected("ocg", "name")),
                "note": "保留复制来源或默认卡图；AI 会话单独开始。"}

    def _created_preview(self, document):
        uid = document["_card_uid"]
        if uid in self._created_previews:
            return self._created_previews[uid]
        value = {}
        for mode in ("ocg", "rd", "manga"):
            rules = field_rules(self.project.app, mode)
            value[MODE_LABELS[mode]] = {FIELD_LABELS.get(key, key): display_value(item, rules[key])
                                      for key, item in self.access.values(document, mode).items()}
        diy = document.get("diy") or {}
        value["DIY 字段"] = copy.deepcopy(diy.get("setcodes", []))
        if diy.get("blocks"):
            value["DIY 积木"] = copy.deepcopy(diy["blocks"])
            value["积木读回文字"] = block_reading(document)
        self._created_previews[uid] = value
        return value

    def report(self):
        return {"id": self.id, "state": self.state, "auto": self.auto, "finished": self.finished,
                "rows": self.rows(), "error": self.error, "title": (self.owner or {}).get("title", "卡片修改"),
                "undo_kept": list(self.undo_kept), "undo_restored": list(self.undo_restored)}
