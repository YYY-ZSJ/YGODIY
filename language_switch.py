"""切换语言时翻译 / 还原效果文字，以及语言旁的「AI翻译」开关。

由补丁分片 p36、p43 整理而来。
"""

import json
import os
import re
import sys
import threading
import traceback

from PyQt5.QtCore import QTimer

from common import (
    _app_dir,
    _call_original,
    _json_clone,
    _plain_text_from,
    _safe_call,
    _set_line_text_silent,
    _set_plain_text,
    _set_plain_text_silent,
    _tab_log,
    _text_from,
)


def _preload_translation_model():
    """神经翻译模型必须在 Qt 应用创建之前载入（之后再载入 llama.cpp 会访问违例，
    见 ygo_translator/neural.py 的 preload）。补丁包在程序建立 Qt 应用之前导入，正好在这里载入。"""
    try:
        import ygo_translator

        if ygo_translator.USE_NEURAL and not ygo_translator.neural.preload():
            reason = ygo_translator.neural.last_reason()
            if reason:
                _tab_log("神经翻译模型未载入，改用实例翻译模型：" + reason)
    except Exception:
        _tab_log("预载神经翻译模型失败:\n" + traceback.format_exc())


def _translate_snapshot(editor):
    return (
        _text_from(getattr(editor, "card_name_edit", None)),
        _plain_text_from(getattr(editor, "text_input", None)),
        _plain_text_from(getattr(editor, "LB_text_edit", None)),
    )


def _translate_apply(editor, values):
    name, text, pend = values
    # 卡名输入框的 textChanged 会触发「按卡名搜索」，可能把整张卡换掉；
    # 这里静默写入，再手动刷新卡面上的卡名。
    _set_line_text_silent(getattr(editor, "card_name_edit", None), name)
    _safe_call(getattr(editor, "update_card_name", None))
    _set_plain_text(getattr(editor, "text_input", None), text)
    _set_plain_text(getattr(editor, "LB_text_edit", None), pend)
    # 效果文字的卡面重排是防抖的（p09：textChanged 先启动计时器，到时才 update_text），
    # 而切卡/保存时会停掉所有防抖计时器 —— 翻译结果到达后若计时器被停，卡面就停在旧文字。
    # 这里直接重排卡面，不依赖计时器；RD / 漫画卡的卡面也一并刷新。
    _safe_call(getattr(editor, "update_text", None))
    _safe_call(getattr(editor, "update_lb_text", None))
    app = getattr(editor, "parent_app", None)
    _safe_call(globals().get("_schedule_rd_frame_sync"), app)
    refresh = globals().get("_manga_refresh")
    if refresh is not None and getattr(app, "current_mode", None) == getattr(app, "_manga_mode_index", object()):
        _safe_call(refresh, app, force=True)


# ---------------------------------------------------------------------------
# 每张卡的「各语言文本记录」
#
# 切走某种语言时，把卡上当时的文字记为该语言的版本；切回这种语言时原样还原，不再翻译。
# 翻译到没记录过的语言时，优先从记录里的简体中文翻译（简中 -> 日/英 是模型的强项）。
# 记录存在这张卡的标签页条目上（与标题同级的键 _language_texts，不放进 tab["data"]：
# 保存/撤销会用重新导出的字典整个替换 tab["data"]），切换标签页、重启程序都不会丢。
#
# 认卡靠「内部编号」：每张卡（标签页条目）带一个不显示、随机生成的编号 _card_uid
# （128 位随机数，另外还会避开所有现有卡片的编号）。改卡名、改效果都不影响编号；
# 复制卡片/卡包时副本领新编号；只有卡片（或所在卡包）被删除，它的编号才不再被占用。
# ---------------------------------------------------------------------------
_LANGUAGE_RECORD_KEY = "_language_texts"
_CARD_UID_KEY = "_card_uid"
_SOURCE_PREFERENCE = ("简体中文", "繁体中文", "繁体中文2")


def _all_tabs(manager):
    for pack in getattr(manager, "packs", None) or []:
        for tab in (pack.get("tabs") if isinstance(pack, dict) else None) or []:
            if isinstance(tab, dict):
                yield tab


def _new_card_uid(manager):
    import uuid

    in_use = {tab.get(_CARD_UID_KEY) for tab in _all_tabs(manager)}
    while True:
        uid = uuid.uuid4().hex
        if uid not in in_use:
            return uid


def _assign_card_uids(manager):
    """给没有编号的卡补上编号；同一编号出现在多张卡上时（如旧数据），后出现的改发新编号。"""
    seen = set()
    for tab in _all_tabs(manager):
        uid = tab.get(_CARD_UID_KEY)
        if not uid or uid in seen:
            uid = tab[_CARD_UID_KEY] = _new_card_uid(manager)
        seen.add(uid)


def _card_uid(manager, tab):
    uid = tab.get(_CARD_UID_KEY)
    if not uid:
        uid = tab[_CARD_UID_KEY] = _new_card_uid(manager)
    return uid


def _current_tab(editor):
    manager = getattr(getattr(editor, "parent_app", None), "card_tab_manager", None)
    if manager is None or getattr(manager, "editor", None) is not editor:
        return None, None
    index = getattr(manager, "current_index", -1)
    tabs = getattr(manager, "tabs", None) or []
    if 0 <= index < len(tabs) and isinstance(tabs[index], dict):
        return manager, tabs[index]
    return manager, None


def _language_record(editor):
    """取当前这张卡的记录 {"card": 内部编号, "texts": {语言: [卡名, 效果, 灵摆效果]}}。"""
    manager, tab = _current_tab(editor)
    if tab is None:  # PAST 等没有标签页的编辑器：记在编辑器上
        holder = editor.__dict__.setdefault("_ygodiy_language_holder", {})
        uid = "editor"
    else:
        holder = tab
        uid = _card_uid(manager, tab)
    record = holder.get(_LANGUAGE_RECORD_KEY)
    if not isinstance(record, dict) or not isinstance(record.get("texts"), dict):
        record = holder[_LANGUAGE_RECORD_KEY] = {"card": uid, "texts": {}}
    record["card"] = uid  # 复制来的记录归新编号所有
    return record


def _renew_copied_tab_uids(manager, before, source):
    """复制卡片之后：副本领新的内部编号，并带上原卡的各语言文字记录（before 是复制前所有卡片的 id）。"""
    for tab in _all_tabs(manager):
        if id(tab) not in before:
            tab[_CARD_UID_KEY] = _new_card_uid(manager)
            record = source.get(_LANGUAGE_RECORD_KEY) if isinstance(source, dict) else None
            if isinstance(record, dict):
                tab[_LANGUAGE_RECORD_KEY] = _json_clone(record)
                tab[_LANGUAGE_RECORD_KEY]["card"] = tab[_CARD_UID_KEY]


def _renew_copied_pack_uids(manager, before):
    """复制卡包之后：整个卡包是深拷贝来的，编号也被复制了，副本里的卡都发新编号。"""
    for tab in _all_tabs(manager):
        if id(tab) not in before:
            tab[_CARD_UID_KEY] = _new_card_uid(manager)
            if isinstance(tab.get(_LANGUAGE_RECORD_KEY), dict):
                tab[_LANGUAGE_RECORD_KEY]["card"] = tab[_CARD_UID_KEY]


_KANA_TEXT_RE = re.compile(r"[぀-ヿ]")
_HAN_TEXT_RE = re.compile(r"[㐀-鿿]")


def _language_family(language):
    language = str(language or "")
    if language.startswith("日文"):
        return "ja"
    if language == "英文":
        return "en"
    return "zh"


def _actual_language(text, labelled):
    """看文字本身是哪种语言；与标注的语言（labelled）同类时沿用标注，否则给出实际的语言名。
    文字太少判断不了时也沿用标注。"""
    plain = _RUBY_MARK_RE.sub(r"\1", text or "")
    # 引号里是卡名，不算：英文效果里常有中文卡名（"卡片甲"），日文效果里也有汉字卡名
    plain = re.sub(r"「[^」]*」|\"[^\"]*\"|“[^”]*”", "", plain)
    kana = len(_KANA_TEXT_RE.findall(plain))
    han = len(_HAN_TEXT_RE.findall(plain))
    latin = len(re.findall(r"[A-Za-z]", plain))
    if kana >= 3:
        family = "ja"
    elif han >= 4 and han * 3 >= latin:
        family = "zh"
    elif latin >= 3:
        family = "en"
    elif han:
        family = "zh"
    else:
        return labelled
    if family == "zh" and _language_family(labelled) == "zh":
        # 简体和繁体同属中文，也要分清：否则「繁体中文」名下会记进一份简体文字，
        # 之后切到繁体时直接还原这份记录，看起来就是「打开 AI 翻译也不翻译」。
        return _chinese_script(plain, labelled)
    if family == _language_family(labelled):
        return labelled
    if family == "ja":
        return "日文"
    if family == "en":
        return "英文"
    try:
        from ygo_translator import chinese

        return "繁体中文" if chinese.to_simplified(plain) != plain else "简体中文"
    except Exception:
        return "简体中文"


def _chinese_script(plain, labelled):
    """中文文字实际是简体还是繁体。只有明确含某一边的特有字时才推翻标注；
    简繁写法相同（或两边的特有字都有）时沿用标注。"""
    try:
        from ygo_translator import chinese

        has_traditional = chinese.to_simplified(plain) != plain
        has_simplified = chinese.to_traditional(plain) != plain
    except Exception:
        return labelled
    labelled_traditional = str(labelled or "").startswith("繁体")
    if labelled_traditional and has_simplified and not has_traditional:
        return "简体中文"
    if not labelled_traditional and has_traditional and not has_simplified:
        return "繁体中文"
    return labelled


def _translation_source(record, old_language, snapshot):
    for language in _SOURCE_PREFERENCE:
        entry = record["texts"].get(language)
        if language == old_language or not entry:
            continue
        if _actual_language(entry[1] + "\n" + entry[2], language) == language:
            return language, entry
        record["texts"].pop(language, None)  # 记错语言的旧记录，不能当翻译来源
    return old_language, snapshot


_TRANSLATION_RELAY = {}


def _translation_relay():
    """把后台线程的翻译结果送回界面线程。"""
    relay = _TRANSLATION_RELAY.get("relay")
    if relay is None:
        from PyQt5.QtCore import QObject, pyqtSignal

        class _Relay(QObject):
            done = pyqtSignal(object, object)

        relay = _Relay()
        relay.done.connect(_translation_done)
        _TRANSLATION_RELAY["relay"] = relay
    return relay


def _translation_done(job, values):
    editor, token, language, placed = job
    try:
        from PyQt5.QtWidgets import QApplication

        QApplication.restoreOverrideCursor()
    except Exception:
        pass
    if getattr(editor, "_ygodiy_translation_job", None) is not token:
        return  # 期间又切换了语言或卡片，这次结果作废
    editor._ygodiy_translation_job = None
    if values is None:
        return
    current = str(getattr(editor, "language", "") or "")
    if current != language or _translate_snapshot(editor) != placed:
        return  # 用户在翻译期间改了文字、语言或换了卡，不覆盖
    _translate_apply(editor, values)


def _ai_translate_previous_after_switch(editor):
    pending = getattr(editor, "_ygodiy_language_before", None)
    editor._ygodiy_language_before = None
    if not pending:
        return
    old_language, snapshot = pending
    new_language = str(getattr(editor, "language", "") or "")
    if not old_language or not new_language or old_language == new_language:
        return
    if not any(value.strip() for value in snapshot):
        return
    editor._ygodiy_translation_job = None
    record = _language_record(editor)
    # 文字实际是哪种语言：模式切换等情况下可能出现「语言设为简中、文字却是日文」，
    # 这种文字不能记成简中，否则会覆盖真正的简中原文；翻译时也按实际语言翻
    actual_language = _actual_language(snapshot[1] + "\n" + snapshot[2], old_language)
    if actual_language == old_language:
        record["texts"][old_language] = list(snapshot)  # 切走前的文字，留到切回这种语言时还原
    else:
        _tab_log("切换语言：%s 下的文字实际是%s，未记入该语言的记录" % (old_language, actual_language))
    saved = record["texts"].get(new_language)
    if saved and _actual_language(saved[1] + "\n" + saved[2], new_language) != new_language:
        # 早期版本可能把别种语言的文字记在了这个语言名下（如把日文记成「简体中文」）：
        # 这种记录不能还原，丢掉，改为重新翻译
        record["texts"].pop(new_language, None)
        _tab_log("切换语言：%s 的记录实际不是该语言，已丢弃并重新翻译" % new_language)
        saved = None
    if saved:
        # 卡名不翻译：始终用当前卡名（期间可能改过名），只还原效果与灵摆效果
        _translate_apply(editor, (snapshot[0], saved[1], saved[2]))
        return
    if actual_language == new_language:
        # 文字本来就是目标语言（模式切换遗留），保持不动、不翻译
        _translate_apply(editor, snapshot)
        return
    source_language, source = _translation_source(record, actual_language, snapshot)
    # 神经模型翻一张卡要几秒：先把原文放回去（宿主可能已清空），在后台翻译，
    # 翻完再替换；界面不卡住。
    _translate_apply(editor, snapshot)
    placed = _translate_snapshot(editor)
    token = object()
    editor._ygodiy_translation_job = token
    job = (editor, token, new_language, placed)
    is_monster = str(getattr(editor, "card_type", "怪兽卡") or "怪兽卡") == "怪兽卡"
    relay = _translation_relay()
    try:
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QApplication

        QApplication.setOverrideCursor(Qt.BusyCursor)
    except Exception:
        pass

    def work():
        try:
            import ygo_translator

            values = tuple(ygo_translator.translate_card(
                snapshot[0], source[1], source[2], source_language, new_language, is_monster))
        except Exception:
            _tab_log("切换语言翻译失败:\n" + traceback.format_exc())
            values = None
        relay.done.emit(job, values)

    threading.Thread(target=work, name="ygo-translate", daemon=True).start()


_RUBY_MARK_RE = re.compile(r"\[([^\[\]()（）]*?)[(（][^()（）]*?[)）]\]")

# ---------------------------------------------------------------------------
# 卡名按「卡名自己的语言」绘制
#
# 卡名不翻译，但宿主按当前语言给卡名换字体/字号/位置，英文还会走专门的英文排版
# （setName 的 enflag）。英文卡名字体没有汉字字形，中文卡名在英文模式下直接消失。
# 处理：每次绘制卡名时，按卡名文字本身判断它的语言，临时用那种语言的设置绘制。
# ---------------------------------------------------------------------------
_KANA_RE = re.compile(r"[぀-ヿㇰ-ㇿ]")
_HAN_RE = re.compile(r"[㐀-鿿豈-﫿]")
_NAME_FONT_FAMILIES = {}


def _name_language(editor, name):
    current = str(getattr(editor, "language", "") or "")
    fonts = getattr(getattr(editor, "config", None), "card_name_font", None) or {}
    plain = _RUBY_MARK_RE.sub(r"\1", name or "").strip()
    if not plain:
        return current
    if _KANA_RE.search(plain):
        language = current if current.startswith("日文") else "日文"
    elif _HAN_RE.search(plain):
        try:
            from ygo_translator import chinese

            traditional = chinese.to_simplified(plain) != plain
        except Exception:
            traditional = False
        if traditional:
            language = current if current.startswith("繁体") else "繁体中文"
        else:
            language = "简体中文"
    elif re.search(r"[A-Za-z]", plain):
        language = "英文"
    else:
        language = current
    return language if language in fonts else current


def _name_font_family(editor, path):
    family = _NAME_FONT_FAMILIES.get(path)
    if family is None:
        from PyQt5.QtGui import QFontDatabase

        module = sys.modules.get(type(editor).__module__)
        resolve = getattr(module, "rpath", None) or (lambda value: value)
        families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(resolve(path)))
        family = families[0] if families else ""
        _NAME_FONT_FAMILIES[path] = family
    return family


def _name_config_by_language(editor, value):
    """卡名配置的「语言 → 值」表。OCG 直接是字典；旧卡（PastWidget）是按卡模分的列表，
    宿主用 config.X[self.template_index][language] 取值，这里保持一致。"""
    if isinstance(value, (list, tuple)):
        try:
            index = int(getattr(editor, "template_index", 0) or 0)
        except Exception:
            index = 0
        value = value[max(0, min(len(value) - 1, index))] if value else {}
    return value if isinstance(value, dict) else {}


def _apply_name_language_style(editor, language):
    """把卡名相关的字体、字号、位置设成指定语言的（与宿主 update_language 中卡名那几行一致）。"""
    from PyQt5.QtGui import QFont

    config = editor.config
    current = str(getattr(editor, "language", "") or "")
    family = _name_font_family(editor, _name_config_by_language(editor, config.card_name_font)[language])
    if not family:
        return
    size = _name_config_by_language(editor, config.card_name_size)[language]
    font = QFont(family)
    font.setPixelSize(size)
    posy = _name_config_by_language(editor, config.card_name_posy)
    x = _name_config_by_language(editor, config.card_name_posx)[language]
    y = posy[language]
    official_y = getattr(config, "ocard_name_posy", None)
    groups = [getattr(editor, "name_text_group", None), getattr(editor, "mixname_text_group", None)]
    if isinstance(official_y, dict) and current in official_y and groups[0] is not None:
        # 「官方」卡模用另一组纵坐标：看卡名现在更接近哪一组，就沿用同一组
        now = groups[0].pos().y()
        if abs(now - official_y[current]) < abs(now - posy.get(current, now)):
            y = official_y.get(language, y)
    compressor = getattr(editor, "name_compresstor", None)
    if compressor is not None:
        compressor.setRubyFont(font)
        compressor.setFontSize(size)
    for group in groups:
        if group is None:
            continue
        group.setRubyFont(font)
        group.setRubyFontSize(size)
        group.setPos(x, y)


def _render_name_in_own_language(editor, original, args, kwargs):
    current = getattr(editor, "language", None)
    try:
        language = _name_language(editor, _text_from(getattr(editor, "card_name_edit", None)))
    except Exception:
        language = current
    if not language or language == current:
        previous = getattr(editor, "_ygodiy_name_style_language", None)
        if previous and previous != current:
            try:
                _apply_name_language_style(editor, current)
            except Exception:
                pass
            editor._ygodiy_name_style_language = None
        return _call_original(original, editor, args, kwargs)
    try:
        _apply_name_language_style(editor, language)
    except Exception:
        _tab_log("按卡名语言设置字体失败:\n" + traceback.format_exc())
        return _call_original(original, editor, args, kwargs)
    editor.language = language  # 宿主 update_card_name 只用它判断是否走英文排版
    try:
        return _call_original(original, editor, args, kwargs)
    finally:
        editor.language = current
        # 下次 update_language 会把字体改回当前语言，这里记下以便语言相同时恢复
        editor._ygodiy_name_style_language = language


def _strip_ruby_for_language(editor):
    """切到英文前去掉日文注音标记「[漢字(よみ)]」：宿主英文排版没有注音字号，
    排带注音的文字会在 CompressText 里除以零，整个 update_language 中途中断
    （属性图标、字体等都不会更新）。原文已在快照里，翻译不受影响。"""
    try:
        target = str(editor.lan_selector.currentText() or "")
    except Exception:
        return
    if target.startswith("日文"):
        return
    name = _text_from(getattr(editor, "card_name_edit", None))
    if _RUBY_MARK_RE.search(name):
        _set_line_text_silent(editor.card_name_edit, _RUBY_MARK_RE.sub(r"\1", name))
    for field in ("text_input", "LB_text_edit"):
        widget = getattr(editor, field, None)
        value = _plain_text_from(widget)
        if _RUBY_MARK_RE.search(value):
            _set_plain_text_silent(widget, _RUBY_MARK_RE.sub(r"\1", value))


def _update_language_keeping_text(editor, standard, args, kwargs):
    """OTCGWidget / PastWidget.update_language 的实现：standard 是编辑器原本的切换语言方法。

    调用前记下旧语言与卡名 / 效果 / 灵摆效果，供用户亲手切换语言（activated）时翻译或还原。
    """
    try:
        before = (str(getattr(editor, "language", "") or ""), _translate_snapshot(editor))
    except Exception:
        before = None
    # 宿主 update_language 末尾在「没有任何输入框被标记为用户输入」时，把卡名/效果/卡密/卡包
    # 重置成演示卡（演示卡文字是空的，见 p23）。不只用户切语言，载入不同语言的卡、切换
    # OCG/RD/漫画卡模式（各模式语言不同）时程序也会改语言，卡名就这样被清空。
    # 标记一个输入框为「用户输入」即可让宿主跳过这次重置（p11 载入搜索卡时也是这样做的）。
    pass_edit = getattr(editor, "card_pass_edit", None)
    if pass_edit is not None and hasattr(pass_edit, "has_user_type"):
        pass_edit.has_user_type = True
    try:
        _strip_ruby_for_language(editor)
        # 宿主会把卡名字体改成新语言的；记下来，下次绘制卡名时按卡名自己的语言改回
        editor._ygodiy_name_style_language = str(
            getattr(getattr(editor, "lan_selector", None), "currentText", lambda: "")() or "")
        return _call_original(standard, editor, args, kwargs)
    finally:
        editor._ygodiy_language_before = before
        # 用户选择时 activated 紧跟在本次调用之后（同一个事件里）；程序自己改语言
        # 不会有 activated，事件循环转一圈就把记录作废，免得之后被误用。
        try:
            QTimer.singleShot(0, lambda target=editor: setattr(target, "_ygodiy_language_before", None))
        except Exception:
            pass


def _setup_language_translation(editor):
    """OCG / 旧版编辑器 __init__ 末尾调用：用户亲手切换语言时翻译效果文字，并预热翻译模型。"""
    selector = getattr(editor, "lan_selector", None)
    if selector is not None:
        selector.activated.connect(lambda _index, target=editor: _translate_after_user_switch(target))
    try:
        import ygo_translator

        ygo_translator.warm_up()
    except Exception:
        _tab_log("预载翻译模型失败:\n" + traceback.format_exc())


def _install_rd_language_bar(app):
    _translate_previous_install_rd_language_bar(app)
    bar = getattr(app, "_rd_language_bar", None)
    if bar is None or getattr(bar, "_ygodiy_translation_connected", False):
        return
    bar._ygodiy_translation_connected = True
    bar.selector.activated.connect(
        lambda _index, app=app: _translate_after_user_switch(getattr(app, "otcg_widget", None))
        if getattr(app, "otcg_widget", None) is not None
        else None
    )


# ---------------------------------------------------------------------------
# 模式切换（OCG/TCG、RD、漫画卡）
#
# 三种模式共用卡片文字，但各有自己的语言设置（p34）：切模式时语言会被程序改掉、文字却不变，
# 于是出现「RD 是简中、文字却是日文」。切模式后若语言变了，就按用户切换语言同样处理：
# 记下旧语言的文字，新语言有记录就还原，没有就翻译。
# ---------------------------------------------------------------------------
def _switch_mode_keeping_language(app, index, switch):
    """由 switch(index) 完成模式切换，之后把 OCG 编辑器的语言改回切换前的（主窗口 switch_mode 调用）。"""
    editor = getattr(app, "otcg_widget", None)
    selector = getattr(editor, "lan_selector", None)
    before_index = selector.currentIndex() if selector is not None else -1
    before = None
    if editor is not None:
        try:
            before = (str(getattr(editor, "language", "") or ""), _translate_snapshot(editor))
        except Exception:
            before = None
    result = switch(index)
    try:
        ocg_family = _mode_style_key_of(app, getattr(app, "current_mode", None)) is not None
        if ocg_family and selector is not None and before_index >= 0 and selector.currentIndex() != before_index:
            # 无论切到哪个模式都保持当前语言：p34 会套用新模式自己记的语言，这里改回切换前的。
            # 卡片文字是三个模式共用的，本来就是这种语言，所以不需要翻译。
            selector.setCurrentIndex(before_index)
            _safe_call(globals().get("_rd_language_bar_sync"), app)
            _safe_call(globals().get("_schedule_rd_frame_sync"), app)
            refresh = globals().get("_manga_refresh")
            if refresh is not None and getattr(app, "current_mode", None) == getattr(app, "_manga_mode_index", object()):
                _safe_call(refresh, app, force=True)
        after = str(getattr(editor, "language", "") or "") if editor is not None else ""
        if before and ocg_family and after and after != before[0]:
            # 改不回去时（例如新模式没有这种语言）才按切换语言处理：记录、还原或翻译
            editor._ygodiy_language_before = before
            _translate_after_user_switch(editor)
    except Exception:
        _tab_log("切换模式后同步语言文字失败:\n" + traceback.format_exc())
    return result


_AI_TRANSLATE_SETTINGS_FILE = "制卡器设置.json"
_AI_TRANSLATE_KEY = "ai_translate"
_AI_TRANSLATE_CACHE = {}


def _ai_settings_path():
    return os.path.join(_app_dir(), _AI_TRANSLATE_SETTINGS_FILE)


def _ai_load_settings():
    if "settings" in _AI_TRANSLATE_CACHE:
        return _AI_TRANSLATE_CACHE["settings"]
    settings = {}
    try:
        with open(_ai_settings_path(), encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            settings = loaded
    except FileNotFoundError:
        pass
    except Exception:
        _tab_log("读取制卡器设置失败:\n" + traceback.format_exc())
    _AI_TRANSLATE_CACHE["settings"] = settings
    return settings


def _ai_translate_enabled(mode):
    states = _ai_load_settings().get(_AI_TRANSLATE_KEY)
    return bool(states.get(mode, False)) if isinstance(states, dict) else False


def _ai_set_translate_enabled(mode, enabled):
    settings = _ai_load_settings()
    states = settings.get(_AI_TRANSLATE_KEY)
    if not isinstance(states, dict):
        states = settings[_AI_TRANSLATE_KEY] = {}
    states[mode] = bool(enabled)
    if os.environ.get("YGODIY_NO_STATE_WRITE"):
        return
    path = _ai_settings_path()
    temp = path + ".tmp"
    try:
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, ensure_ascii=False, indent=2)
        os.replace(temp, path)
    except Exception:
        _tab_log("保存制卡器设置失败:\n" + traceback.format_exc())


def _ai_translate_mode_of(editor):
    """这次语言切换属于哪个模式：旧版卡看编辑器本身，其余按当前模式。"""
    app = getattr(editor, "parent_app", None)
    if editor is not None and editor is getattr(app, "past_widget", None):
        return "past"
    mode = getattr(app, "current_mode", 0)
    if mode == 1:
        return "rd"
    if mode == getattr(app, "_manga_mode_index", object()):
        return "manga"
    return "ocg"


def _translate_after_user_switch(editor):
    if editor is None or _ai_translate_enabled(_ai_translate_mode_of(editor)):
        return _ai_translate_previous_after_switch(editor)
    pending = getattr(editor, "_ygodiy_language_before", None)
    editor._ygodiy_language_before = None
    editor._ygodiy_translation_job = None  # 作废进行中的翻译
    if not pending:
        return None
    _old_language, snapshot = pending
    if any(value.strip() for value in snapshot):
        # 宿主切语言时可能改动文字（如去掉注音标记），原样放回切换前的内容
        _translate_apply(editor, snapshot)
    return None


def _ai_find_row(layout, widget):
    """找到直接包含 widget 的那一层布局。"""
    if layout is None:
        return None
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        if item.widget() is widget:
            return layout
        if item.layout() is not None:
            found = _ai_find_row(item.layout(), widget)
            if found is not None:
                return found
    return None


def _ai_add_toggle(container, selector, mode, editors):
    """在语言下拉所在那一组的末尾加「AI翻译」标签和开关。"""
    from PyQt5.QtWidgets import QLabel
    import customComponents as components

    if container is None or selector is None:
        return None
    existing = getattr(container, "_ai_translate_toggle", None)
    if existing is not None:
        return existing
    row = _ai_find_row(container.layout(), selector)
    if row is None:
        _tab_log("AI翻译开关：找不到 %s 的语言行" % mode)
        return None
    label = QLabel("AI翻译", container)
    toggle = components.ToggleButton(container, check=_ai_translate_enabled(mode), width=42, height=20)
    toggle.setToolTip("打开后，切换语言时用 AI 翻译效果文字；关闭时效果文字保持不变")
    row.addWidget(label)
    row.addWidget(toggle)
    # 同一行多了开关，别让语言下拉被挤到显示不全（旧版卡那一行还有「类型」下拉）
    try:
        # sizeHint 按最长选项算，含下拉箭头的位置
        selector.setMinimumWidth(max(selector.minimumWidth(), selector.sizeHint().width()))
    except Exception:
        pass
    for widget in (label, toggle):
        widget.show()

    def changed(checked, _mode=mode):
        _ai_set_translate_enabled(_mode, checked)
        if not checked:
            for editor in editors:
                if editor is not None:
                    editor._ygodiy_translation_job = None

    toggle.toggled.connect(changed)
    container._ai_translate_toggle = toggle
    return toggle


def _ai_install_toggles(app):
    editor = getattr(app, "otcg_widget", None)
    past = getattr(app, "past_widget", None)
    _ai_add_toggle(editor, getattr(editor, "lan_selector", None), "ocg", (editor,))
    bar = getattr(app, "_rd_language_bar", None)
    _ai_add_toggle(bar, getattr(bar, "selector", None), "rd", (editor,))
    _ai_add_toggle(past, getattr(past, "lan_selector", None), "past", (past,))
    panel = getattr(app, "_manga_panel", None)
    _ai_add_toggle(panel, getattr(panel, "lan_selector", None), "manga", (editor,))


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from rd_frame import _schedule_rd_frame_sync
from manga import _manga_refresh
from mode_styles import _mode_style_key_of, _rd_language_bar_sync, _translate_previous_install_rd_language_bar
