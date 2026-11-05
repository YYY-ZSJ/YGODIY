"""候选批次的应用、冲突检测和撤销；批准只来自界面，模型没有批准入口。"""

import copy
import json

from PyQt5.QtCore import QObject, pyqtSignal

from .change_plan import ChangePlan
from .card_context import RD_PANEL_FIELDS
from .field_access import FieldAccess
from .field_rules import FIELD_LABELS, MODE_LABELS
from .project_access import ProjectAccess, candidate_document

MAX_CREATED_CARDS = 100


def creation_state(creation, project, access):
    from mode_styles import _data_for_mode, _extract_style, _is_style_key
    result = copy.deepcopy(creation["document"])
    result.pop("current_index", None)
    originals = creation["document"]["tabs"] if creation["kind"] == "pack" else [creation["document"]]
    targets = result["tabs"] if creation["kind"] == "pack" else [result]
    for tab, target in zip(originals, targets):
        data = dict(project.manager._default_data, **project.data(tab))
        styles = {mode: _extract_style(_data_for_mode(data, mode)) for mode in ("ocg", "rd", "manga")}
        rd = access.values(dict(target, data=data), "rd")
        styles["rd_panel"] = {key: rd[key] for key in RD_PANEL_FIELDS if key in rd}
        target["data"] = {key: value for key, value in data.items() if key != "_mode_styles" and not _is_style_key(key)}
        target["data"]["_mode_styles"] = styles
        image = project.manager._image_cache.get(id(tab))
        if project.manager._current_tab() is tab:
            image = getattr(project.manager.editor, "card_img", image)
        target["_visual_revision"] = id(image)
    return json.loads(json.dumps(result, ensure_ascii=False))


class ChangeBook(QObject):
    changed = pyqtSignal(object)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.project = ProjectAccess(app)
        self.access = FieldAccess(app, self.project)
        self.plans, self.current = {}, None

    def begin(self, owner, answer, mode, auto):
        self.current = ChangePlan(self.project, self.access, owner, answer, mode, auto)
        self.plans[self.current.id] = self.current
        return self.current

    def finish(self, suspended=False):
        if self.current is not None:
            self.current.finished = not suspended
            self._notify(self.current)
            if not suspended:
                self.current.release_unused()
            if not suspended and not self.current.cells and not self.current.creations:
                self.plans.pop(self.current.id, None)
        self.current = None

    def observe_created(self, tab):
        """新卡首次套用由宿主补全默认值；只认可套用前数据仍与创建凭据一致的对象。"""
        uid = tab.get("_card_uid")
        for plan in self.plans.values():
            for creation in plan.creations:
                cards = creation["document"]["tabs"] if creation["kind"] == "pack" else [creation["document"]]
                if not creation["applied"] or not any(tab is card for card in cards):
                    continue
                self.access.sync_hidden_card_fields(tab)
                pending = creation.get("unobserved", {})
                if uid not in pending or pending[uid] != tab:
                    continue
                actual = creation_state(creation, self.project, self.access)
                cards = actual["tabs"] if creation["kind"] == "pack" else [actual]
                saved = creation["expected"]["tabs"] if creation["kind"] == "pack" else [creation["expected"]]
                index = next(i for i, card in enumerate(cards) if card["_card_uid"] == uid)
                saved[index].clear()
                saved[index].update(cards[index])
                pending.pop(uid)
                creation.setdefault("observed", set()).add(uid)

    def release(self):
        self.current = None
        self.plans.clear()
        self.project.pack_refs.clear()

    def _notify(self, plan):
        if plan.cells or plan.creations:
            plan.answer["changes"] = plan.report()
            self.changed.emit(plan)

    def stage(self, operation, **params):
        plan = self.current
        if plan is None or plan.finished:
            raise ValueError("修改必须属于当前请求，不能在没有请求快照时执行。")
        old_cells, old_creations, old_cards = {key: dict(cell) for key, cell in plan.cells.items()}, list(plan.creations), dict(plan.cards)
        target = params.get("card_uid") or plan.target
        pending_docs = []
        if operation in ("fields", "blocks", "tests", "design_text", "card_data", "script"):
            for creation in plan.creations:
                if not creation["applied"]:
                    cards = creation["document"]["tabs"] if creation["kind"] == "pack" else [creation["document"]]
                    pending_docs += [(card, candidate_document(card)) for card in cards if card["_card_uid"] == target]
        plan.invalidate(target)
        try:
            result = getattr(plan, operation)(**params)
            created = sum(len(c["document"]["tabs"]) if c["kind"] == "pack" else 1 for c in plan.creations)
            if created > MAX_CREATED_CARDS:
                raise ValueError("单批最多新建或复制 100 张卡片，请拆分请求。")
            if plan.auto and not self.apply(plan.id, automatic=True):
                raise ValueError(plan.error)
        except Exception:
            plan.cells, plan.creations, plan.cards = old_cells, old_creations, old_cards
            for card, document in pending_docs:
                card.clear()
                card.update(document)
            plan.invalidate()
            self._notify(plan)
            raise
        plan.error = ""
        self._notify(plan)
        return dict(result, batch_id=plan.id, status="applied" if plan.auto else "pending",
                    note=result.get("note", "") + (" 已自动应用，可整批撤销。" if plan.auto else " 候选已生成，等待玩家应用。"))

    def _equal(self, cell, actual, expected):
        return self.access.same_session(actual, expected) if cell["key"][0] == "editor" else actual == expected

    def conflicts(self, plan, undo=False):
        result = []
        for cell in plan.cells.values():
            key = cell["key"]
            label = MODE_LABELS[key[1]] + "当前编辑器" if key[0] == "editor" else "「%s」· %s" % (
                plan.cards[key[1]].get("title", "卡片"), FIELD_LABELS.get(key[-1], key[-1]))
            if undo and not cell["applied"]:
                continue
            try:
                actual = self.access.value(cell)
                if not self._equal(cell, actual, cell["current"]):
                    result.append(label + "：请求之后已变动")
            except (ValueError, KeyError):
                result.append(label + "：目标已不存在")
        for creation in plan.creations:
            if creation["applied"]:
                try:
                    if creation["kind"] == "pack":
                        self.project.pack(creation["id"])
                    else:
                        if self.project.card(creation["id"]) is not creation["document"]:
                            raise ValueError("对象已被替换")
                    if creation_state(creation, self.project, self.access) != creation["expected"]:
                        result.append(creation["document"].get("title", "新对象") + "：创建后已有其他改动")
                except ValueError:
                    result.append("创建的对象已不存在")
            elif creation["kind"] == "card":
                pending_pack = any(c["kind"] == "pack" and c["id"] == creation["pack_id"] for c in plan.creations)
                if not pending_pack:
                    try:
                        self.project.pack(creation["pack_id"])
                    except ValueError:
                        result.append("新卡片的目标卡包已不存在")
        return result

    def _fail(self, plan, message):
        plan.error = message
        self._notify(plan)
        return False

    def _refresh(self, selection):
        self.project.refresh(*selection)
        tab = self.project.manager._current_tab()
        if tab is not None:
            self.access.sync_hidden_card_fields(tab)

    def apply(self, batch_id, automatic=False):
        plan = self.plans[batch_id]
        if plan.state in ("rejected", "undone", "partially_undone"):
            return self._fail(plan, "这批候选已放弃或撤销；如需再次修改，请重新发送请求。")
        if not automatic and not plan.finished:
            return self._fail(plan, "请等待本次请求结束后再应用整批候选。")
        problems = self.conflicts(plan)
        if problems:
            return self._fail(plan, "检测到冲突，未覆盖玩家改动：\n" + "\n".join(problems))
        cells = [c for c in plan.cells.values() if not c["applied"] or not self._equal(c, c["after"], c["current"])]
        additions = [c for c in plan.creations if not c["applied"]]
        selection = self.project.selection()
        self.project.flush()
        original = {id(c): self.access.value(c) for c in cells}
        metadata = {id(c): (c["after"], c["current"], c["applied"]) for c in cells}
        inserted = []
        try:
            for creation in additions:
                self.project.insert(creation)
                inserted.append(creation)
            self.access.write(cells, lambda cell: cell["after"])
            if additions:
                self._refresh(selection)
            for cell in cells:
                actual = self.access.value(cell)
                expected = cell["after"]["fields"] if cell["key"][0] == "editor" else cell["after"]
                compared = actual["fields"] if cell["key"][0] == "editor" else actual
                if compared != expected:
                    raise ValueError("编辑器联动结果与候选不一致，已撤回本次应用，请缩小修改范围。")
                cell["after"], cell["current"], cell["applied"] = actual, actual, True
        except Exception as error:
            self.access.write(cells, lambda cell: original[id(cell)], restore_assets=True)
            for creation in reversed(inserted):
                self.project.remove(creation)
            if additions:
                self._refresh(selection)
            for cell in cells:
                cell["after"], cell["current"], cell["applied"] = metadata[id(cell)]
            return self._fail(plan, str(error) if isinstance(error, ValueError) else "应用未能完成，已恢复应用前状态。")
        for creation in plan.creations:
            creation["applied"] = True
            creation["expected"] = creation_state(creation, self.project, self.access)
            creation["applied_row"] = plan.creation_row(creation)
            cards = creation["document"]["tabs"] if creation["kind"] == "pack" else [creation["document"]]
            creation["unobserved"] = {card["_card_uid"]: copy.deepcopy(card) for card in cards
                                      if card["_card_uid"] not in creation.get("observed", set())}
        plan.state, plan.error = "applied", ""
        plan.invalidate()
        self._notify(plan)
        return True

    def reject(self, batch_id):
        plan = self.plans[batch_id]
        if plan.state != "pending" or not plan.finished:
            return False
        plan.state, plan.error = "rejected", ""
        self._notify(plan)
        return True

    def undo_review(self, batch_id):
        from .undo_batch import review
        return review(self, self.plans[batch_id])

    def undo(self, batch_id, confirm=None, partial=False, expected=None):
        from .undo_batch import execute
        return execute(self, self.plans[batch_id], partial, expected)
