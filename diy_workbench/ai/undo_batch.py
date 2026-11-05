"""整批撤销的审查与执行；部分撤销只写安全字段，不恢复整个旧编辑器。"""

from .field_rules import FIELD_LABELS, MODE_LABELS

FC_ART_FIELDS = {"mode", "center", "center_full", "center_back", "border"}


def cell_label(plan, cell):
    key = cell["key"]
    if key[0] == "editor":
        return MODE_LABELS[key[1]] + " 当前编辑器"
    return "「%s」· %s" % (plan.cards[key[1]].get("title", "卡片"), FIELD_LABELS.get(key[-1], key[-1]))


def _partial_editor(book, cell, actual):
    before, expected = cell["before"], cell["current"]
    changed = {key for key in expected["fields"] if before["fields"].get(key) != expected["fields"][key]}
    conflicts = {key for key in expected["fields"] if actual["fields"].get(key) != expected["fields"][key]}
    same_art = ({k: id(v) for k, v in actual["objects"].items()} == {k: id(v) for k, v in expected["objects"].items()} and
                {k: p.cacheKey() for k, p in actual["pixmaps"].items()} == {k: p.cacheKey() for k, p in expected["pixmaps"].items()})
    mode = cell["key"][1]
    if mode == "fc" and (conflicts & FC_ART_FIELDS or not same_art or actual["extras"] != expected["extras"]):
        conflicts |= changed & FC_ART_FIELDS
    elif mode == "past" and not same_art:
        # 旧版类型/卡框与卡图联动；文本和数值仍可单独恢复。
        conflicts |= changed - {"name", "effect_text", "ATK", "DEF", "card_pass", "pack"}
    if mode == "rd" and conflicts & {"max_atk", "max_atk_enabled"}:
        conflicts |= changed & {"max_atk", "max_atk_enabled"}
    safe = changed - conflicts
    desired = book.access.candidate_session(mode, actual, {key: before["fields"][key] for key in safe})
    if same_art and mode == "fc" and safe & FC_ART_FIELDS:
        desired = dict(desired, objects=before["objects"], pixmaps=before["pixmaps"])
    kept = list(conflicts)
    if not same_art:
        kept.append("卡图 / 编辑器图像")
    return desired, safe, kept


def _creation_uids(creation):
    cards = creation["document"]["tabs"] if creation["kind"] == "pack" else [creation["document"]]
    return {card["_card_uid"] for card in cards}


def review(book, plan):
    from .change_book import creation_state
    cells, removals, kept, conflicts, actual_cells, actual_objects = [], [], [], [], {}, {}
    retained_uids = set()
    retained_packs = set()
    later = False
    dependents = []
    for item in book.plans.values():
        if item is plan:
            later = True
        elif later and item.state in ("pending", "applied") and (item.cells or item.creations):
            dependents.append(item)
    for creation in plan.creations:
        if not creation["applied"]:
            continue
        title = creation["document"].get("title", "新对象")
        uids = _creation_uids(creation)
        reason = ""
        try:
            if creation["kind"] == "pack":
                book.project.pack(creation["id"])
            elif book.project.card(creation["id"]) is not creation["document"]:
                raise ValueError()
            actual = actual_objects[creation["id"]] = creation_state(creation, book.project, book.access)
            if any(uids & other.dependencies for other in dependents):
                reason = "有后续批次引用，请先撤销后续批次"
            elif actual != creation["expected"]:
                reason = "创建后已有其他改动"
        except ValueError:
            reason = "创建的对象已不存在"
        if reason:
            conflicts.append(title + "：" + reason)
            kept.append(title + "（整个新对象；" + reason + "）")
            retained_uids.update(uids)
            if creation["kind"] == "pack":
                retained_packs.add(creation["id"])
        else:
            removals.append(creation)
    removals = [c for c in removals if c["kind"] == "pack" or c["pack_id"] not in retained_packs]
    pack_ids = {c["id"] for c in removals if c["kind"] == "pack"}
    removals = [c for c in reversed(removals) if c["kind"] == "pack" or c["pack_id"] not in pack_ids]
    removed_uids = set().union(*(_creation_uids(c) for c in removals)) if removals else set()
    for cell in plan.cells.values():
        if not cell["applied"]:
            continue
        key, label = cell["key"], cell_label(plan, cell)
        if key[0] != "editor" and key[1] in removed_uids | retained_uids:
            continue
        try:
            actual = actual_cells[key] = book.access.value(cell)
        except (ValueError, KeyError):
            conflicts.append(label + "：目标已不存在")
            kept.append(label)
            continue
        if book._equal(cell, actual, cell["current"]):
            cells.append(dict(cell, undo_value=cell["before"]))
        else:
            conflicts.append(label + "：应用后已变动")
            if key[0] == "editor":
                desired, safe, preserved = _partial_editor(book, cell, actual)
                kept += [label + " · " + FIELD_LABELS.get(field, field) for field in preserved]
                if safe:
                    cells.append(dict(cell, undo_value=desired, undo_fields=sorted(safe)))
            else:
                kept.append(label)
    return {"cells": cells, "removals": removals, "kept": list(dict.fromkeys(kept)), "conflicts": conflicts,
            "actual_cells": actual_cells, "actual_objects": actual_objects}


def _same_review(book, before, after):
    if before["actual_objects"] != after["actual_objects"] or before["conflicts"] != after["conflicts"]:
        return False
    if before["actual_cells"].keys() != after["actual_cells"].keys():
        return False
    return all(book._equal({"key": key}, value, after["actual_cells"][key]) for key, value in before["actual_cells"].items())


def execute(book, plan, partial=False, expected=None):
    if not plan.finished or plan.state != "applied":
        return book._fail(plan, "这批修改尚未完成，或已撤销。")
    checked = review(book, plan)
    if expected is not None and not _same_review(book, expected, checked):
        return book._fail(plan, "确认期间目标发生变化，未执行撤销，请重新检查。")
    if checked["conflicts"] and not partial:
        return book._fail(plan, "无法整批撤销，应用后已有改动：\n" + "\n".join(checked["conflicts"]))
    cells, removals = checked["cells"], checked["removals"]
    pack_ids = {c["id"] for c in removals if c["kind"] == "pack"}
    if len(book.project.manager.packs) <= len(pack_ids):
        return book._fail(plan, "不能通过撤销删除最后一个卡包。")
    card_ids = {c["id"] for c in removals if c["kind"] == "card"}
    for pack in book.project.manager.packs:
        if book.project.pack_id(pack) not in pack_ids and all(tab.get("_card_uid") in card_ids for tab in pack["tabs"]):
            return book._fail(plan, "该卡包只剩本批创建的卡片，请先新建另一张卡，再整批撤销。")
    selection = book.project.selection()
    book.project.flush()
    original = {cell["key"]: book.access.value(cell) for cell in cells}
    removed = []
    try:
        book.access.write(cells, lambda cell: cell["undo_value"], restore_assets=True)
        for creation in removals:
            removed.append((creation, book.project.remove(creation)))
        if removals:
            book._refresh(selection)
    except Exception:
        for creation, saved in reversed(removed):
            book.project.restore_removed(creation, saved)
        book.access.write(cells, lambda cell: original[cell["key"]], restore_assets=True)
        book._refresh(selection)
        return book._fail(plan, "撤销未能完成，已恢复撤销前状态。")
    for cell in plan.cells.values():
        cell["applied"] = False
    for creation in removals:
        creation["applied"] = False
    plan.state = "partially_undone" if checked["kept"] else "undone"
    plan.undo_kept = checked["kept"]
    plan.undo_restored = [cell_label(plan, cell) + ("：" + "、".join(cell["undo_fields"]) if cell.get("undo_fields") else "") for cell in cells]
    plan.error = "保留玩家改动：\n" + "\n".join(checked["kept"]) if checked["kept"] else ""
    book._notify(plan)
    return True
