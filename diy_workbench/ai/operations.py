"""统一操作目录：读取、浏览、受批次保护的修改，以及每次都要玩家确认的高风险操作。"""

import copy
import json
from dataclasses import dataclass, replace

from . import card_context
from .block_edits import catalog
from .change_book import ChangeBook
from .field_rules import describe

MAX_ARGUMENT_CHARS = 128000


@dataclass(frozen=True)
class Operation:
    name: str
    description: str
    risk: str
    parameters: dict
    handler: object
    modes: tuple = ()

    def tool(self):
        return {"name": self.name, "description": self.description, "parameters": copy.deepcopy(self.parameters)}


def _schema(properties=None, required=()):
    return {"type": "object", "properties": properties or {}, "required": list(required), "additionalProperties": False}


def _arguments(raw, schema):
    if not isinstance(raw, str) or len(raw) > MAX_ARGUMENT_CHARS:
        raise ValueError("操作参数过大或格式无效。")
    params = json.loads(raw)
    properties = schema["properties"]
    if not isinstance(params, dict) or set(params) - set(properties) or set(schema["required"]) - set(params):
        raise ValueError("操作参数缺失或包含未开放的字段。")
    for name, value in params.items():
        rule = properties[name]
        expected = {"string": str, "integer": int, "boolean": bool, "object": dict, "array": list}[rule["type"]]
        if type(value) is not expected or ("enum" in rule and value not in rule["enum"]):
            raise ValueError("参数 %s 的类型或取值无效。" % name)
        if isinstance(value, str) and not 0 < len(value.strip()) <= rule.get("maxLength", 200):
            raise ValueError("参数 %s 为空或过长。" % name)
        if type(value) is int and not rule.get("minimum", 0) <= value <= rule.get("maximum", 100000):
            raise ValueError("参数 %s 超出范围。" % name)
        if isinstance(value, list) and (not rule.get("minItems", 0) <= len(value) <= rule.get("maxItems", 60) or
                                       any(not isinstance(item, str) or not 0 < len(item) <= 100 for item in value)):
            raise ValueError("参数 %s 须为1～60个积木ID的字符串数组。" % name)
    return params


class Operations:
    def __init__(self, app):
        self.app = app
        self.changes = ChangeBook(app, app)
        from .sandbox_tools import SandboxTools
        self.sandbox = SandboxTools(self)
        from .design_tools import DesignTools
        from .lua_tools import LuaTools
        from .risky_actions import RiskyActions
        self.design, self.lua, self.risky = DesignTools(self), LuaTools(self), RiskyActions(self)
        mode_ids = [row["id"] for row in card_context.modes(app)]
        uid = {"type": "string", "description": "list_cards 返回的卡片内部编号", "maxLength": 200}
        definitions = (
            Operation("get_context", "读取当前模式及当前卡的文字快照，不含其他模式数据或卡图。", "read", _schema(), self._context),
            Operation("list_modes", "列出 YGODIY 可浏览的模式及标识。", "read", _schema(), lambda: card_context.modes(app)),
            Operation("describe_fields", "说明当前模式字段的类型、选项、共享影响及编辑器状态范围。", "read", _schema(), self._describe),
            Operation("list_packs", "列出卡包名称、编号和卡数，不返回卡片内容。", "read", _schema(), self._packs),
            Operation("list_cards", "按明确指定的卡包列出卡片内部编号与标题，不读取其他模式字段。", "read",
                      _schema({"pack_index": {"type": "integer", "minimum": 0, "description": "list_packs 的编号；省略表示当前卡包"}}), self._cards),
            Operation("read_card", "在当前模式读取指定卡片；省略编号读取当前卡。", "read", _schema({"card_uid": uid}), self._read_card),
            Operation("switch_mode", "直接浏览指定模式，不修改卡片内容，调用过程会记录。", "browse",
                      _schema({"mode": {"type": "string", "enum": mode_ids}}, ("mode",)), self._switch_mode),
            Operation("select_card", "直接选择指定卡片，可跨卡包浏览；不会修改卡片字段。", "browse", _schema({"card_uid": uid}, ("card_uid",)), self._select_card),
            Operation("open_page", "直接打开编辑器或 DIY 工作台的效果/卡包页面。", "browse",
                      _schema({"page": {"type": "string", "enum": ["editor", "diy_effects", "diy_pack"]}}, ("page",)), self._open_page),
            Operation("search_cards", "在本机离线卡库搜索卡名或卡密，返回有限条文字资料。", "read",
                      _schema({"query": {"type": "string", "maxLength": 100}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, ("query",)), self._search),
        )
        definitions += self._modifications(mode_ids, uid)
        definitions += (
            Operation("write_test_scenario", "为一个编号效果写入一个意图情景（布场、选择意图、预期）；不写select/yes/no。与积木同批预览/撤销，失败反例改弱须玩家确认。", "modify",
                _schema({"scenario": {"type": "object"}, "card_uid": uid}, ("scenario",)), self.sandbox.write),
            Operation("run_sandbox_test", "运行一个编号效果的已写情景，可选单个scenario_id；异步、可停止。返回断言证据、当前提问/可选项及未到达断言，不会把缺项当通过。", "modify",
                _schema({"effect": {"type": "integer", "minimum": 1, "maximum": 20}, "card_uid": uid,
                         "scenario_id": {"type": "string", "maxLength": 80}}, ("effect",)), self.sandbox.prepare),
        )
        definitions += self._design(uid) + self._custom_lua(uid) + self._risky(uid)
        self.entries = {op.name: replace(op, modes=tuple(mode_ids)) for op in definitions}

    def _design(self, uid):
        return (
            Operation("set_effect_text", "保存效果文本设计稿（玩家认可的意图）。与卡面效果文字、积木分开保存；写情景时以它为原文。", "modify",
                      _schema({"text": {"type": "string", "maxLength": 4000}, "card_uid": uid}, ("text",)),
                      lambda **p: self.changes.stage("design_text", **p)),
            Operation("check_effect_text", "检查效果文本的书写规范；省略text时检查设计稿。level=确认的项会影响规则含义，要向玩家说明。", "read",
                      _schema({"text": {"type": "string", "maxLength": 4000}, "card_uid": uid}), self.design.check),
            Operation("compare_effect_text", "逐个编号对比设计稿和积木读回。文字一致不等于效果一致，运行结果看沙盒。", "read",
                      _schema({"card_uid": uid}), self.design.compare),
        )

    def _custom_lua(self, uid):
        text = {"type": "string", "maxLength": 1000}
        code = {"type": "string", "maxLength": 20000}
        return (
            Operation("write_custom_lua", "积木拼不出时才用。kind=statement把处理语句追加到effect_index指定的效果；kind=effect新增或替换一个完整效果，code写在initial_effect里（可用c），helpers写顶层函数（以s.cl_开头）。必须写reason说明积木为什么不行。", "modify",
                      _schema({"kind": {"type": "string", "enum": ["statement", "effect"]}, "description": dict(text, description="这段代码对应的中文效果文字"),
                               "code": code, "helpers": code, "reason": text,
                               "effect_index": {"type": "integer", "minimum": 0, "maximum": 50}, "card_uid": uid},
                              ("kind", "description", "code", "reason")), self.lua.write),
            Operation("write_card_script", "写这张卡的完整Lua脚本，导出和测试都用它，积木不再生成脚本。只在玩家要求写整份脚本，或大部分效果积木都拼不出时用；只差一部分用write_custom_lua。reason写为什么不用积木。", "modify",
                      _schema({"code": {"type": "string", "maxLength": 40000}, "reason": text, "card_uid": uid}, ("code", "reason")), self.lua.write_script),
            Operation("get_lua_reference", "查 Lua 资料：symbol查接口或常量的参数、含义、本机数值和官方用法（例如Duel.Damage、EFFECT_IMMUNE_EFFECT）；code取一张官方卡的脚本；query搜任意文字。三者只填一个。", "read",
                      _schema({"symbol": {"type": "string", "maxLength": 100}, "code": {"type": "integer", "minimum": 1, "maximum": 999999999}, "query": {"type": "string", "maxLength": 100},
                               "limit": {"type": "integer", "minimum": 1, "maximum": 10}}), self.lua.reference),
            Operation("report_block_gap", "记录积木表达不了的效果，供以后补积木。write_custom_lua已自动记录，不用重复调用。", "read",
                      _schema({"text": text, "reason": text, "card_uid": uid}, ("text", "reason")), self.lua.gap),
        )

    def _risky(self, uid):
        pack = {"type": "string", "maxLength": 200, "description": "list_packs 返回的 pack_id"}
        return (
            Operation("delete_card", "请求删除卡片；每次都由玩家在弹窗确认，不能撤销。", "confirm", _schema({"card_uid": uid}, ("card_uid",)), self.risky.delete_card),
            Operation("delete_pack", "请求删除卡包及其全部卡片；每次都由玩家在弹窗确认，不能撤销。", "confirm", _schema({"pack_id": pack}, ("pack_id",)), self.risky.delete_pack),
            Operation("export_pack", "请求导出卡包；玩家确认并选择保存位置。未通过测试时玩家可强制导出，卡包会标记未通过验证。", "confirm",
                      _schema({"pack_id": pack}, ("pack_id",)), self.risky.export_pack),
            Operation("install_pack", "请求把卡包安装进 MDPro3；玩家确认后才执行，可能覆盖同名卡包。", "confirm", _schema({"pack_id": pack}, ("pack_id",)), self.risky.install_pack),
        )

    def _modifications(self, modes, uid):
        name = {"type": "string", "maxLength": 128, "description": "卡片或卡包名称"}
        pack = {"type": "string", "maxLength": 200, "description": "list_packs 返回的稳定 pack_id；省略为请求开始时的卡包"}
        return (
            Operation("set_card_fields", "修改明确模式的字段；共用字段会标明所有受影响模式。默认预览，编辑器会话设置不随卡保存。", "modify",
                      _schema({"mode": {"type": "string", "enum": modes}, "fields": {"type": "object"}, "card_uid": uid}, ("mode", "fields")),
                      lambda **p: self.changes.stage("fields", **p)),
            Operation("set_effect_blocks", "替换DIY积木候选；返回中文读回和编译警告，无需再次get_effect_blocks核对。不写回效果文字，不运行脚本。", "modify",
                      _schema({"model": {"type": "object"}, "card_uid": uid}, ("model",)), lambda **p: self.changes.stage("blocks", **p)),
            Operation("new_card", "按程序默认资料新建卡片候选，可指定名称和卡包。", "modify", _schema({"name": name, "pack_id": pack}),
                      lambda **p: self.changes.stage("new_card", **p)),
            Operation("copy_card", "复制指定卡片资料和积木，新卡不继承 AI 会话。", "modify", _schema({"source_uid": uid, "name": name, "pack_id": pack}),
                      lambda **p: self.changes.stage("new_card", **dict(p, source_uid=p.get("source_uid") or self.changes.current.target))),
            Operation("new_pack", "新建卡包候选，包含一张默认卡片。", "modify", _schema({"title": name}, ("title",)),
                      lambda **p: self.changes.stage("new_pack", **p)),
            Operation("copy_pack", "复制卡包设置和卡片资料；每批最多新增 100 张卡片。", "modify", _schema({"source_id": pack, "title": name}, ("source_id", "title")),
                      lambda **p: self.changes.stage("new_pack", **p)),
            Operation("set_card_data", "设置DIY卡的提示文本和效果分类。strings的键是1～16（str1对应aux.Stringid(id,0)），填了就替换积木生成的那一格；category是分类名数组，不填就按积木自动判断。", "modify",
                      _schema({"strings": {"type": "object"}, "category": {"type": "array", "maxItems": 32}, "card_uid": uid}),
                      lambda **p: self.changes.stage("card_data", **p)),
            Operation("get_effect_blocks", "读取指定卡的 DIY 积木或本请求中的候选树，不包含卡图。", "read", _schema({"card_uid": uid}), self._blocks),
            Operation("get_block_catalog", "固定前缀已有完整积木文档；还需多个积木细节时用ids列表一次查完，query兼容单个ID。", "read",
                      _schema({"ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 60},
                               "query": {"type": "string", "maxLength": 100}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}), catalog),
        )

    def tools(self):
        return [entry.tool() for entry in self.entries.values()]

    def execute(self, name, raw):
        operation = self.entries.get(name)
        if operation is None:
            return {"ok": False, "error": "已拒绝：没有这项操作。"}
        if operation.risk in ("modify", "confirm") and self.changes.current is None:
            return {"ok": False, "error": "没有当前请求快照，不能修改项目。"}
        if card_context.active_mode(self.app)["id"] not in operation.modes:
            return {"ok": False, "error": "当前模式不支持这项操作。"}
        try:
            params = _arguments(raw, operation.parameters)
            return {"ok": True, "risk": operation.risk, "data": operation.handler(**params)}
        except (ValueError, TypeError, KeyError, IndexError) as error:
            return {"ok": False, "error": str(error)}

    def _manager(self):
        manager = getattr(self.app, "card_tab_manager", None)
        if manager is None:
            raise ValueError("卡片列表尚未就绪，请稍后重试。")
        return manager

    def _context(self):
        return card_context.snapshot(self.app)

    def _packs(self):
        return [{"index": i, "pack_id": self.changes.project.pack_id(pack), "title": pack.get("title", ""), "card_count": len(pack.get("tabs", []))}
                for i, pack in enumerate(self._manager().packs)]

    def _cards(self, pack_index=None):
        manager = self._manager()
        index = manager.current_pack_index if pack_index is None else pack_index
        if not 0 <= index < len(manager.packs):
            raise ValueError("卡包不存在。")
        return [{"card_uid": tab.get("_card_uid"), "title": tab.get("title", "")}
                for tab in manager.packs[index].get("tabs", [])]

    def _find(self, card_uid):
        for pi, pack in enumerate(self._manager().packs):
            for ti, tab in enumerate(pack.get("tabs", [])):
                if tab.get("_card_uid") == card_uid:
                    return pi, ti, tab
        raise ValueError("卡片不存在，可能已被玩家删除。")

    def _read_card(self, card_uid=None):
        plan = self.changes.current
        if plan is not None and card_uid is not None and card_uid in plan.cards:
            mode = card_context.active_mode(self.app)
            if mode["id"] not in ("fc", "back", "past"):
                document = plan.working_document(card_uid)
                return {"card_uid": card_uid, "mode": mode, "candidate": True, "test_progress": self.sandbox.progress(document),
                        "fields": self.changes.access.values(document, mode["id"])}
        tab = self._find(card_uid)[2] if card_uid else None
        result = card_context.snapshot(self.app, tab)
        target = tab or card_context.current(self.app)[0]
        if target is not None:
            result["test_progress"] = self.sandbox.progress(dict(target, data=self.changes.project.data(target)))
        return result

    def _switch_mode(self, mode):
        target = next(row for row in card_context.modes(self.app) if row["id"] == mode)
        self.app.combo_box.setCurrentIndex(target["index"])
        if self.app.current_mode != target["index"]:
            raise ValueError("该模式的资源尚未就绪，未能打开。")
        if self.changes.current is not None:
            self.changes.current.observe_mode(mode)
        return self._context()

    def _select_card(self, card_uid):
        pi, ti, tab = self._find(card_uid)
        manager = self._manager()
        manager.pack_list.setCurrentRow(pi)
        manager.tab_list.setCurrentRow(ti)
        if self.changes.current is not None:
            self.changes.current.target = card_uid
            self.changes.current.pack_id = self.changes.project.pack_id(manager.packs[pi])
        return {"card_uid": tab.get("_card_uid"), "title": tab.get("title", ""), "mode": card_context.active_mode(self.app)}

    def _open_page(self, page):
        if page == "editor":
            if card_context.active_mode(self.app)["id"] == "diy":
                self._switch_mode("ocg")
        else:
            self._switch_mode("diy")
            self.app._workbench.tabs.setCurrentIndex(0 if page == "diy_effects" else 1)
        return {"page": page, "mode": card_context.active_mode(self.app)}

    def _search(self, query, limit=5):
        from card_library import _search_cards
        cards = _search_cards(legacy_query=query)
        fields = ("id", "sc_name", "cn_name", "jp_name", "en_name", "text", "type", "atk", "def", "level", "race", "attribute")
        return {"total": len(cards), "cards": [{k: copy.deepcopy(card[k]) for k in fields if k in card} for card in cards[:limit]]}

    def _describe(self):
        return dict(describe(self.app, card_context.active_mode(self.app)["id"]), mode=card_context.active_mode(self.app))

    def _blocks(self, card_uid=None):
        from blocks import SCHEMA
        plan = self.changes.current
        if plan is not None:
            uid = card_uid or plan.target
            document = plan.document(uid)
            key = ("diy", uid, "blocks")
            tree = plan.cells[key]["after"] if key in plan.cells else (document.get("diy") or {}).get("blocks", {"schema": SCHEMA, "effects": []})
        else:
            document = self._find(card_uid)[2] if card_uid else card_context.current(self.app)[0]
            tree = ((document or {}).get("diy") or {}).get("blocks", {"schema": SCHEMA, "effects": []})
        return copy.deepcopy(tree)
