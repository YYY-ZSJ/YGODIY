"""AI 批次的项目读写入口；保持现有存档结构，不操作导出或安装文件。"""

import copy
import uuid


def card_document(tab):
    result = {key: copy.deepcopy(tab[key]) for key in ("title", "data", "_card_uid") if key in tab}
    if isinstance(tab.get("diy"), dict):
        result["diy"] = {key: copy.deepcopy(value) for key, value in tab["diy"].items() if key != "ai"}
    return result


def candidate_document(document):
    """候选只替换字段值；复制将被写入的映射，不复制未涉及的积木、图片及测试资料。"""
    result = dict(document, data=dict(document.get("data") or {}), diy=dict(document.get("diy") or {}))
    styles = result["data"].get("_mode_styles")
    if isinstance(styles, dict):
        result["data"]["_mode_styles"] = {key: dict(value) for key, value in styles.items()}
    return result


class ProjectAccess:
    def __init__(self, app):
        self.app = app
        self.pack_refs = {}

    @property
    def manager(self):
        manager = getattr(self.app, "card_tab_manager", None)
        if manager is None:
            raise ValueError("卡片列表尚未就绪。")
        return manager

    def pack_id(self, pack):
        for key, saved in self.pack_refs.items():
            if saved is pack:
                return key
        key = uuid.uuid4().hex
        self.pack_refs[key] = pack
        return key

    def pack(self, key):
        pack = self.pack_refs.get(key)
        if pack is None or not any(pack is p for p in self.manager.packs):
            raise ValueError("原卡包已不存在，请重新选择。")
        return pack

    def card(self, uid):
        for pack in self.manager.packs:
            for tab in pack["tabs"]:
                if tab.get("_card_uid") == uid:
                    return tab
        raise ValueError("原卡片已不存在，请重新选择。")

    def data(self, tab):
        if self.manager._current_tab() is tab:
            return copy.deepcopy(self.manager._collect_editor_data_fast())
        return copy.deepcopy(tab.get("data") or {})

    def capture(self):
        from language_switch import _card_uid
        cards, packs, images = {}, {}, {}
        for pack in self.manager.packs:
            key = self.pack_id(pack)
            packs[key] = {"title": pack.get("title", ""), "tabs": [], "diy": copy.deepcopy(pack.get("diy", {}))}
            for tab in pack["tabs"]:
                uid = _card_uid(self.manager, tab)
                document = card_document(tab)
                if self.manager._current_tab() is tab:
                    document["data"] = self.data(tab)
                cards[uid] = document
                packs[key]["tabs"].append(uid)
                image = self.manager._image_cache.get(id(tab))
                if self.manager._current_tab() is tab:
                    image = getattr(self.manager.editor, "card_img", image)
                if image is not None:
                    images[uid] = image
        return cards, packs, images

    def new_card(self, name, source=None):
        from card_tabs import _tab_title_from_data
        tab = copy.deepcopy(source) if source else self.manager._new_default_tab()
        tab["_card_uid"] = uuid.uuid4().hex
        if name is not None:
            tab["data"]["name"] = name
        tab["title"] = _tab_title_from_data(tab.get("data"), "新卡片")
        if isinstance(tab.get("diy"), dict):
            tab["diy"].pop("ai", None)
        return tab

    def flush(self):
        self.manager._save_current_snapshot(full=False)
        self.manager._sync_current_pack()

    def insert(self, creation, index=None):
        from card_tabs import _data_has_saved_image
        if creation["kind"] == "pack":
            pack = creation["document"]
            items = self.manager.packs
            self.pack_refs[creation["id"]] = pack
            cards = pack["tabs"]
        else:
            pack = self.pack(creation["pack_id"])
            items = pack["tabs"]
            cards = [creation["document"]]
        items.insert(len(items) if index is None else index, creation["document"])
        for card in cards:
            image = creation.get("images", {}).get(card["_card_uid"])
            if image is not None:
                self.manager._image_cache[id(card)] = image
            else:
                self.manager._prime_tab_image_cache(card)
                if id(card) not in self.manager._image_cache and not _data_has_saved_image(card["data"]) and not card["data"].get("_search_card_id"):
                    self.manager._set_default_visual_cache(card)
            self.manager._render_cache.pop(id(card), None)

    def remove(self, creation):
        document = creation["document"]
        if creation["kind"] == "pack":
            items = self.manager.packs
            cards = document["tabs"]
        else:
            items = self.pack(creation["pack_id"])["tabs"]
            cards = [document]
        index = next(i for i, item in enumerate(items) if item is document)
        items.pop(index)
        saved = {"index": index, "images": {}, "renders": {}}
        for card in cards:
            for cache, name in ((self.manager._image_cache, "images"), (self.manager._render_cache, "renders")):
                if id(card) in cache:
                    saved[name][id(card)] = cache.pop(id(card))
        return saved

    def restore_removed(self, creation, saved):
        self.insert(creation, saved["index"])
        self.manager._image_cache.update(saved["images"])
        self.manager._render_cache.update(saved["renders"])

    def refresh(self, selected_pack, selected_card):
        manager = self.manager
        if not manager.packs:
            raise ValueError("不能移除最后一个卡包。")
        pi = next((i for i, pack in enumerate(manager.packs) if pack is selected_pack), 0)
        pack = manager.packs[pi]
        ti = next((i for i, card in enumerate(pack["tabs"]) if card is selected_card), 0)
        manager._busy = True
        try:
            manager.pack_list.clear()
            for i, item in enumerate(manager.packs):
                manager._add_pack_item(i, item)
            manager.current_pack_index, manager.tabs, manager.current_index = pi, pack["tabs"], ti
            manager._refresh_card_list()
            manager.pack_list.setCurrentRow(pi)
            manager.tab_list.setCurrentRow(ti)
        finally:
            manager._busy = False
        manager._apply_token += 1
        manager._apply_tab_if_current(ti, manager._apply_token)
        manager._sync_current_pack()
        manager._request_write_state()

    def selection(self):
        manager = self.manager
        return manager.packs[manager.current_pack_index], manager._current_tab()

    def changed(self, tab):
        from card_tabs import _tab_title_from_data
        tab["title"] = _tab_title_from_data(tab["data"], tab.get("title", "新卡片"))
        self.manager._render_cache.pop(id(tab), None)
        if self.manager._current_tab() is tab:
            self.manager._apply_editor_data(tab["data"])
            self.manager.tab_list.item(self.manager.current_index).setText(tab["title"])
        self.manager._request_write_state()
        workbench = getattr(self.app, "_workbench", None)
        if workbench is not None:
            workbench._last_check.pop(tab.get("_card_uid"), None)
            if workbench.active():
                workbench.refresh()
