"""本地离线卡库：加载与索引、按条件搜索、本地优先的卡片资料 / 卡图 / 随机一卡。

由补丁分片 p01、p02、p03、p13 整理而来。
"""

import json
import os
import random
import threading

from PIL import Image
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from common import (
    _ABILITY_FILTERS,
    _ATTRIBUTES,
    _CARD_TYPE_FILTERS,
    _LINK_MARKERS,
    _MAIN_TYPES,
    _RACES,
    _SPELL_TRAP_FILTERS,
    _app_dir,
    _freeze_cache_value,
)


_CARD_LOCK = threading.Lock()
_CARDS_BY_ID = None
_CARD_IDS = None
_CARD_SEARCH_RECORDS = None
_SEARCH_RESULT_CACHE = {}
_SEARCH_RESULT_CACHE_LIMIT = 8
_PACKS_BY_ID = None
_PACKS_BY_ID_FOLDED = None
_LOCAL_IMAGE_PATHS = {}

_IMAGE_SUFFIXES = (".png", ".jpg", ".webp")

_CARD_NAME_KEYS = (
    "sc_name",
    "cn_name",
    "md_name",
    "nwbbs_n",
    "cnocg_n",
    "jp_name",
    "en_name",
)

_SPELL_TRAP_SUBTYPE_MASK = 0x80 | 0x10000 | 0x20000 | 0x40000 | 0x80000 | 0x100000
_CARD_TYPE_MASKS = dict(_CARD_TYPE_FILTERS)


def _library_dir():
    return os.path.join(_app_dir(), "离线卡库")


def _load_cards():
    global _CARDS_BY_ID, _CARD_IDS, _CARD_SEARCH_RECORDS
    if _CARDS_BY_ID is not None:
        return _CARDS_BY_ID

    with _CARD_LOCK:
        if _CARDS_BY_ID is not None:
            return _CARDS_BY_ID

        cards_path = os.path.join(_library_dir(), "cards.json")
        try:
            with open(cards_path, "r", encoding="utf-8") as card_file:
                cards = json.load(card_file)
            by_id = {}
            for card in cards.values():
                card_id = card.get("id")
                if isinstance(card_id, int) and card_id > 0:
                    by_id[str(card_id)] = card
            _CARDS_BY_ID = by_id
            _CARD_IDS = tuple(int(card_id) for card_id in by_id)
        except Exception:
            _CARDS_BY_ID = {}
            _CARD_IDS = ()
            _CARD_SEARCH_RECORDS = ()
    return _CARDS_BY_ID


def _load_search_records():
    global _CARD_SEARCH_RECORDS
    _load_cards()
    if _CARD_SEARCH_RECORDS is not None:
        return _CARD_SEARCH_RECORDS
    with _CARD_LOCK:
        if _CARD_SEARCH_RECORDS is None:
            _CARD_SEARCH_RECORDS = tuple(
                _make_search_record(card) for card in _CARDS_BY_ID.values()
            )
    return _CARD_SEARCH_RECORDS


def _card_for(card_pass):
    return _load_cards().get(str(card_pass).lstrip("0"))


def _make_search_record(card):
    card_id = str(card.get("id") or "")
    names = tuple(str(card.get(key) or "") for key in _CARD_NAME_KEYS)
    folded_names = tuple(value.casefold() for value in names)
    folded_id = card_id.casefold()
    padded_id = card_id.zfill(8).casefold()
    searchable = (folded_id,) + folded_names
    return card, searchable, folded_names, folded_id, padded_id, len(names[0])


def _card_display_name(card):
    return (
        card.get("sc_name")
        or card.get("cn_name")
        or card.get("md_name")
        or card.get("jp_name")
        or card.get("en_name")
        or str(card.get("id") or "")
    )


def _load_packs():
    global _PACKS_BY_ID, _PACKS_BY_ID_FOLDED
    if _PACKS_BY_ID is not None:
        return _PACKS_BY_ID

    with _CARD_LOCK:
        if _PACKS_BY_ID is not None:
            return _PACKS_BY_ID

        packs_path = os.path.join(_library_dir(), "card_packs.json")
        try:
            with open(packs_path, "r", encoding="utf-8") as pack_file:
                packs = json.load(pack_file)
            _PACKS_BY_ID = {
                str(card_id).lstrip("0"): pack
                for card_id, pack in packs.items()
                if isinstance(pack, str) and pack
            }
            _PACKS_BY_ID_FOLDED = {
                card_id: pack.casefold() for card_id, pack in _PACKS_BY_ID.items()
            }
        except Exception:
            _PACKS_BY_ID = {}
            _PACKS_BY_ID_FOLDED = {}
    return _PACKS_BY_ID


def _pack_for(card_pass):
    return _load_packs().get(str(card_pass).lstrip("0"), "")


def _pack_for_folded(card_pass):
    _load_packs()
    return _PACKS_BY_ID_FOLDED.get(str(card_pass).lstrip("0"), "")


def _matches_mask_group(card_type, selected, masks):
    if not selected:
        return True
    return all(card_type & masks[name] for name in selected)


def _matches_single_value_group(value, selected):
    if not selected:
        return True
    return all(value == selected_value for selected_value in selected)


def _matches_spell_trap_group(card_type, selected):
    if not selected:
        return True

    def matches(name, mask):
        if name == "通常魔法":
            return bool(card_type & 0x2) and not card_type & _SPELL_TRAP_SUBTYPE_MASK
        if name == "通常陷阱":
            return bool(card_type & 0x4) and not card_type & _SPELL_TRAP_SUBTYPE_MASK
        if name.endswith("魔法"):
            return bool(card_type & 0x2 and card_type & mask)
        return bool(card_type & 0x4 and card_type & mask)

    return all(matches(name, mask) for name, mask in _SPELL_TRAP_FILTERS if name in selected)


def _matches_ability_group(card_type, selected):
    if not selected:
        return True

    def matches(name, mask):
        if name == "效果以外":
            return bool(card_type & 0x1 and not card_type & 0x20)
        return bool(card_type & mask)

    return all(matches(name, mask) for name, mask in _ABILITY_FILTERS if name in selected)


def _numeric_value(card, field):
    data = card.get("data") or {}
    if field == "星数":
        raw_level = data.get("level")
        return (raw_level & 255) if isinstance(raw_level, int) else None
    if field == "刻度":
        raw_level = data.get("level")
        return ((raw_level >> 24) & 255) if isinstance(raw_level, int) else None
    value = data.get("atk" if field == "攻击力" else "def")
    if field == "守备力" and (data.get("type") or 0) & 0x4000000:
        return None
    return value if isinstance(value, int) and value >= 0 else None


def _matches_advanced(card, filters, pack_query):
    data = card.get("data") or {}
    card_type = data.get("type") or 0

    if not _matches_mask_group(card_type, filters.get("卡片种类"), _CARD_TYPE_MASKS):
        return False
    if not _matches_single_value_group(data.get("attribute"), filters.get("属性")):
        return False
    if not _matches_single_value_group(data.get("race"), filters.get("种族")):
        return False
    if not _matches_spell_trap_group(card_type, filters.get("魔法·陷阱的种类")):
        return False
    if not _matches_ability_group(card_type, filters.get("能力·其他")):
        return False

    for field, limits in (filters.get("数值") or {}).items():
        minimum, maximum = limits
        value = _numeric_value(card, field)
        if minimum is not None and (value is None or value < minimum):
            return False
        if maximum is not None and (value is None or value > maximum):
            return False

    selected_links = filters.get("连接箭头") or set()
    if selected_links:
        if not card_type & 0x4000000:
            return False
        link_markers = data.get("def") if isinstance(data.get("def"), int) else 0
        if not all(link_markers & marker for marker in selected_links):
            return False

    if pack_query and pack_query not in _pack_for_folded(card.get("id")):
        return False
    return True


def _search_cache_get(key):
    result = _SEARCH_RESULT_CACHE.pop(key, None)
    if result is not None:
        _SEARCH_RESULT_CACHE[key] = result
    return result


def _search_cache_put(key, result):
    _SEARCH_RESULT_CACHE[key] = result
    while len(_SEARCH_RESULT_CACHE) > _SEARCH_RESULT_CACHE_LIMIT:
        del _SEARCH_RESULT_CACHE[next(iter(_SEARCH_RESULT_CACHE))]


def _search_cards(advanced_filters=None, legacy_query=""):
    _load_search_records()
    filters = advanced_filters or {}
    is_advanced_search = advanced_filters is not None
    keyword_source = filters.get("keyword") if is_advanced_search else legacy_query
    keyword = str(keyword_source or "").strip().casefold()
    name_query = str(filters.get("卡名搜索") or "").strip().casefold()
    pass_query = str(filters.get("卡密搜索") or "").strip().casefold()
    pack_query = str(filters.get("卡包") or "").strip().casefold()
    cache_key = (
        keyword,
        name_query,
        pass_query,
        _freeze_cache_value(advanced_filters),
    )
    results = _search_cache_get(cache_key)
    if results is not None:
        return results

    ranked = []
    for (
        card,
        searchable,
        names,
        card_id,
        padded_id,
        primary_name_length,
    ) in _CARD_SEARCH_RECORDS:
        if is_advanced_search and not _matches_advanced(card, filters, pack_query):
            continue
        if keyword and not any(keyword in value for value in searchable):
            continue
        if name_query and not any(name_query in value for value in names):
            continue
        if pass_query and pass_query not in card_id and pass_query not in padded_id:
            continue
        rank_query = name_query or pass_query or keyword
        exact = 0 if rank_query and (rank_query in searchable or rank_query == padded_id) else 1
        prefix = 0 if rank_query and (
            any(value.startswith(rank_query) for value in searchable)
            or padded_id.startswith(rank_query)
        ) else 1
        ranked.append((exact, prefix, primary_name_length, card))

    ranked.sort(key=lambda item: item[:3])
    results = tuple(item[3] for item in ranked)
    _search_cache_put(cache_key, results)
    return results


def _local_image_path(card_pass):
    key = str(card_pass).lstrip("0")
    cached = _LOCAL_IMAGE_PATHS.get(key)
    if cached and os.path.exists(cached):
        return cached

    image_dir = os.path.join(_library_dir(), "卡图")
    candidates = dict.fromkeys((str(card_pass), key, key.zfill(8)))
    for candidate in candidates:
        if not candidate:
            continue
        for suffix in _IMAGE_SUFFIXES:
            image_path = os.path.join(image_dir, candidate + suffix)
            if os.path.exists(image_path):
                _LOCAL_IMAGE_PATHS[key] = image_path
                return image_path
    return None


def _apply_detail_types(fetcher, type_text):
    first_line = type_text.splitlines()[0] if type_text else ""
    left = first_line.find("[")
    right = first_line.find("]")
    if left < 0 or right <= left:
        return

    detail_types = first_line[left + 1 : right].split("|")
    if not detail_types:
        return

    fetcher.card_type = detail_types[0] + "卡"
    if fetcher.card_type in ("魔法卡", "陷阱卡"):
        fetcher.MT_type = detail_types[1] if len(detail_types) > 1 else "通常"
        return

    extras = []
    for detail in detail_types[1:]:
        if detail == "效果":
            continue
        if detail in _MAIN_TYPES:
            fetcher.call_way = detail
        else:
            extras.append(detail)
    if not fetcher.call_way:
        fetcher.call_way = "效果"
    if "效果" in detail_types and "通常" in detail_types:
        extras.append("通常")
    fetcher.extra1 = extras[0] if extras else ""
    fetcher.extra2 = extras[1] if len(extras) > 1 else ""


def _apply_local_info(fetcher):
    if fetcher.language != "简体中文":
        return False

    card = _card_for(fetcher.card_pass)
    if not card:
        return False

    text = card.get("text") or {}
    data = card.get("data") or {}
    type_text = text.get("types") or ""
    _apply_detail_types(fetcher, type_text)

    fetcher.card_name = (
        card.get("sc_name")
        or card.get("cn_name")
        or card.get("md_name")
        or card.get("jp_name")
        or ""
    ).replace("·", "・")
    fetcher.effect_text = text.get("desc") or ""
    fetcher.lb_text = text.get("pdesc") or ""
    fetcher.card_pack = _pack_for(fetcher.card_pass)
    fetcher.race = _RACES.get(data.get("race"), "")
    fetcher.attribute = _ATTRIBUTES.get(data.get("attribute"), "")

    atk = data.get("atk")
    defense = data.get("def")
    fetcher.atk_num = str(atk) if isinstance(atk, int) and atk >= 0 else "?"

    raw_level = data.get("level")
    raw_level = raw_level if isinstance(raw_level, int) else 0
    fetcher.level = raw_level & 255
    fetcher.lb_level = str((raw_level >> 24) & 255) if fetcher.extra1 == "灵摆" else ""

    if fetcher.call_way == "连接":
        marker_bits = defense if isinstance(defense, int) else 0
        fetcher.def_num = "-"
        fetcher.link_arrow_status = [
            bool(marker_bits & marker) for marker in _LINK_MARKERS
        ]
    else:
        fetcher.def_num = (
            str(defense) if isinstance(defense, int) and defense >= 0 else "?"
        )

    fetcher.valid = True
    return True


def _local_card_image(card_pass):
    """离线卡库里这张卡的卡图（RGBA）；没有本地卡图时返回 None，由调用方联网获取。"""
    image_path = _local_image_path(card_pass)
    if not image_path:
        return None
    with Image.open(image_path) as image:
        return image.convert("RGBA")


def _search_local_cards(self, search_text, current_page):
    """在离线卡库里搜索，按页写进 CardNameFetcher（self）。卡库为空时返回 False，由调用方联网搜索。"""
    cards = _load_cards()
    if not cards:
        return False

    self.serach_text = search_text
    self.current_page = current_page
    advanced_filters = getattr(self, "_advanced_filters", None)
    results = _search_cards(advanced_filters, search_text)

    self.total_len = len(results)
    start = max(0, current_page - 1) * self.page_size
    page = results[start : start + self.page_size]
    self.info_len = len(page)

    for index in range(self.page_size):
        self.card_img_list[index] = QPixmap()
        self.name_list[index] = ""
        self.code_list[index] = ""
        self.detail_list[index] = ""

    for index, card in enumerate(page):
        card_id = card["id"]
        self.name_list[index] = (
            card.get("sc_name") or card.get("cn_name") or card.get("jp_name") or ""
        )
        self.code_list[index] = str(card_id).zfill(8)
        self.detail_list[index] = ((card.get("text") or {}).get("types") or "").replace(
            "\n", " "
        )
        image_path = _local_image_path(card_id)
        if image_path:
            pixmap = QPixmap(image_path)
            self.card_img_list[index] = pixmap.scaledToHeight(
                self.img_height, Qt.SmoothTransformation
            )
    return True


def _random_card_pass():
    """离线卡库里随机一张卡的卡密（8 位）；卡库为空时返回 None，由调用方联网取。"""
    _load_cards()
    if not _CARD_IDS:
        return None
    return str(random.choice(_CARD_IDS)).zfill(8)
