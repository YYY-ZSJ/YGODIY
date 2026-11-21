"""脚本积木的语法、存档与可编辑性回归。可选装 lupa 后还会核对 Lua 字节码。"""

import json
import unittest

from blocks import SCHEMA, TYPE_SPSUMMON, build, type_bits
from blocks.catalog import new
from blocks.compile import CompileError, walk
from . import ScriptError, parse, render
from .audit import bytecode_checker


def model(program, code=12):
    return {"schema": SCHEMA, "card": {"code": code, "kind": "spell"}, "effects": [program]}


class ScriptBlocks(unittest.TestCase):
    def test_tree_roundtrip_and_edit(self):
        source = "function c12.initial_effect(c) Duel.Draw(0,2,REASON_EFFECT) end"
        p = json.loads(json.dumps(parse(source)))
        call = next(n for n in walk(p) if n["block"] == "ls_api_Duel_Draw")
        self.assertEqual(call["arg1"], [{"block": "ls_number", "value": "2"}])
        call["arg1"][0]["value"] = "3"
        self.assertIn("Duel.Draw(0, 3, REASON_EFFECT)", build(model(p, 321))["lua"])
        self.assertIn("c321.initial_effect", render(p, 321))
        self.assertFalse({"raw", "custom_effect"} & {n["block"] for n in walk(p)})

    def test_self_code_binding(self):
        p = parse("""function c123.initial_effect(c) c123.x="c123 123"; other.c123=1234; aux.Stringid(123,0) end""")
        out = render(p, 456)
        self.assertIn("c456.initial_effect", out)
        self.assertIn('c456.x = "c123 123"', out)
        self.assertIn("other.c123 = 1234", out)
        self.assertIn("aux.Stringid(456, 0)", out)
        self.assertIn("aux.Stringid(123, 0)", render(dict(p, code=0), 456))

    def test_authoring_and_metadata(self):
        p = new("ls_program", desc="抽卡", pdesc="灵摆文字", card_types="spsummon+spirit",
                hints=[new("ls_hint", index=3, text="选项")])
        p["body"][-1]["body"].append(new("ls_run", call=[new("ls_api_Duel_Draw",
            arg0=[new("ls_number", value="0")], arg1=[new("ls_number", value="2")],
            arg2=[new("ls_name", value="REASON_EFFECT")])]))
        result = build(model(p))
        self.assertEqual((result["desc"], result["pdesc"], result["strings"]), ("抽卡", "灵摆文字", ["", "", "", "选项"]))
        self.assertIn("Duel.Draw(0, 2, REASON_EFFECT)", result["lua"])
        self.assertEqual(type_bits(model(p)), TYPE_SPSUMMON | 0x200)
        p["hints"].append(new("ls_hint", index=3))
        with self.assertRaises(CompileError):
            build(model(p))

    def test_rejects_invalid_edits(self):
        with self.assertRaisesRegex(ScriptError, "第 2 行"):
            parse("local x=2\nif ) then end")
        for p in (parse("local a=getmetatable(c)"), parse("local a=_G.x"), parse("break"),
                  parse("function f() return ... end"), parse("while true do local function f() break end end"),
                  new("ls_program", body=[new("ls_run", call=[new("ls_number", value="2")])]),
                  new("ls_program", body=[new("ls_local", names="a;error()")])):
            with self.subTest(p=p), self.assertRaises(CompileError):
                build(model(p))
        for v in ('"a";error()', "[", '"no end'):
            with self.subTest(v=v), self.assertRaises(CompileError):
                build(model(new("ls_program", body=[new("ls_return", values=[new("ls_string", value=v)])])))
        p = parse("f(1)")
        with self.assertRaises(CompileError):
            build(dict(model(p), effects=[p, new("effect")]))

    def test_card_database_metadata(self):
        from blocks.categories import bit, categories
        from ygopack.cardinfo import token_records
        token = new("create_token", name="试验衍生物", atk=1200)
        source = new("effect", operation=[token])
        p = parse("function c12.initial_effect(c) local e=Effect.CreateEffect(c); e:SetCategory(CATEGORY_DRAW|CATEGORY_DAMAGE) end")
        p["token_cards"] = [token]
        self.assertEqual(categories(model(p)) & (bit("抽卡") | bit("伤害")), bit("抽卡") | bit("伤害"))
        self.assertEqual(token_records(model(p), 12), token_records(model(source), 12))

    def test_compiled_semantics(self):
        try:
            dump = bytecode_checker()
        except ImportError:
            self.skipTest("字节码核对使用测试机的 lupa.lua54")
        cases = (
            "local x,y=...; return f(x,y), (f(x,y))",
            "local t={{3;4}, name='甲', [v]=3}; return t.name or t[v]",
            "local function multi(...) return ... end; return multi(1,2), multi(3,4)",
            "local a,b,c=...; return a-(b-c), a/(b*c), a^b^c, -a^b, (-a)^b, a..b..c",
            "local y=0; for i=1,4,2 do y=y+i end; for k,v in pairs(t) do if k then break end end",
            "while x do x=f(x) end; repeat x=x+1 until x>2",
            "function c12.t:f(x,...) if x then return ... elseif self then return x end end",
            "local f=function() return function(x) return x end end; local y=f()('a'); (f())(y)",
            "--[==[注释]==]\nlocal a=[=[x\n y]=]; return a",
            "local a='hello\\z \n\tworld'; return a",
            "local a=2; ::again:: a=a-1; if a>0 then goto again end",
        )
        for src in cases:
            with self.subTest(src=src):
                self.assertEqual(dump(src.encode()), dump(render(parse(src)).encode()))
        self.assertNotEqual(dump(b"return f()"), dump(b"return (f())"))
        self.assertNotEqual(dump(b"Duel.Draw(0,2,1)"), dump(b"Duel.Draw(0,3,1)"))
