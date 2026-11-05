"""情景测试：摆好场面，按顺序执行玩家动作，在指定时点检查场面。

情景是一个 JSON 对象：

    {
      "name": "雷击：对方场上的怪兽全部破坏",
      "field": {"0": {"hand": [12580477]}, "1": {"mzone": [15025844, 89631139]}},
      "actions": [
        {"player": 0, "do": "activate", "card": 12580477},
        {"check": "count", "player": 1, "in": "mzone", "eq": 0},
        {"check": "count", "player": 1, "in": "grave", "eq": 2}
      ]
    }

玩家 0 先攻，可以第一回合攻击；双方卡组默认用 20 张青眼白龙填满；开局不抽卡。

动作（按顺序消耗；引擎问到某个玩家时，只有轮到该玩家的动作才会被用上）：
    activate  发动（主要阶段 / 战斗阶段 / 连锁时 / 「是否发动」）    card、from、nth
    summon / spsummon / mset / sset / reposition                    card
    attack    攻击                                                    card、target（卡号；省略则直接攻击）
    battle / main2 / end_turn                                         进入战斗阶段 / 第二主要阶段 / 结束回合
    select    选卡（取对象、检索、代价……）                            cards: [卡号或 {"code","player","in"}]
    yes / no / pass / option(index)
    announce  宣言卡名                                                card
其余提问用默认应答：不连锁、「是否发动」选是、选卡选前几张、区域选第一个空格、表示形式优先表侧攻击。

检查（默认在下一个「主要阶段 / 战斗阶段等待操作」的时点执行，连锁处理完之后；"when": "next" 则在下一个提问时执行）：
    count     {"player", "in", "card"?}          某区域（某卡）的数量
    lp        {"player"}                         基本分
    atk / def / level  {"player", "card", "in"?}  攻击力 / 守备力 / 等级
    disabled  {"player", "card", "in"?}          效果是否被无效
    faceup    {"player", "card", "in"?}          是否表侧表示
    overlay   {"player", "card"}                 超量素材数
    event     {"name"}                           自上一个 mark 以来某种消息的条数（chain_disabled、attack_disabled……）
    drawn     {"player"}                         自上一个 mark 以来抽了几张
    win       {"player"}                         对局结束且该玩家胜利（对局结束后剩下的检查照样执行）
    offered   {"card", "as"}                     当前的主要阶段 / 战斗阶段命令里是否提供某操作（spsummon、activate、attack……）；
                                                 "as": "chain" 时看到下一个稳定时点为止，player 的连锁机会里出现过没有
                                                 "as": "battle_phase" 时看当前能不能进入战斗阶段（不用 card）
比较用 eq（默认）、ge、le。
    {"mark": true}  重置 event / drawn 的计数起点
"""

import argparse
import json
import sys

from .duel import Duel, LOC, LOC_NAME

PHASE = {0x1: "抽卡阶段", 0x2: "准备阶段", 0x4: "主要阶段1", 0x8: "战斗阶段开始", 0x10: "战斗步骤",
         0x20: "伤害步骤", 0x40: "伤害计算", 0x80: "战斗阶段", 0x100: "主要阶段2", 0x200: "结束阶段"}
STABLE = ("select_idlecmd", "select_battlecmd")
IDLE_LISTS = {"summon": ("summonable", 0), "spsummon": ("spsummonable", 1), "reposition": ("repositionable", 2),
              "mset": ("msetable", 3), "sset": ("ssetable", 4), "activate": ("activatable", 5)}


class ScenarioError(Exception):
    pass


class Runner:
    def __init__(self, core, scenario, verbose=False):
        self.core = core
        self.sc = scenario
        self.verbose = verbose
        self.actions = [dict(a) for a in scenario["actions"]]
        self.failures = []
        self.lines = []
        self.mark = 0
        self.lp = list(scenario.get("lp", (8000, 8000)))
        self.duel = None

    # ------------------------------------------------------------ 主循环

    def run(self, max_steps=400):
        self.core.errors.clear()
        self.duel = d = Duel(self.core, seed=self.sc.get("seed", 20261022), lp=self.lp)
        try:
            d.setup(self.sc["field"])
            d.start()
            for _ in range(max_steps):
                msgs, req = d.advance()
                for m in msgs:
                    self.note(m)
                    if m["type"] == "retry":
                        raise ScenarioError("引擎拒绝了上一个应答（MSG_RETRY）")
                if req is None:
                    self.say("对局结束")
                    while self.actions and "check" in self.actions[0]:
                        self.check(self.actions.pop(0), {})
                    break
                if self.finished(req):
                    break
                self.respond(req)
            else:
                raise ScenarioError("超过 %d 步还没有结束" % max_steps)
            leftover = [a for a in self.actions if "mark" not in a]
            if leftover:
                self.fail("还有 %d 个动作 / 检查没有执行到，第一个是 %s" % (len(leftover), json.dumps(leftover[0], ensure_ascii=False)))
        except ScenarioError as ex:
            self.fail(str(ex))
        except RuntimeError as ex:      # 引擎自己转不停（脚本写坏时会这样）
            self.fail("引擎：%s" % ex)
        finally:
            d.end()
        for e in self.core.errors:
            self.fail("Lua 错误：" + e)
        return not self.failures

    def finished(self, req):
        self.flush_checks(req)
        return not self.actions and req["type"] in STABLE

    def flush_checks(self, req):
        while self.actions:
            a = self.actions[0]
            if "mark" in a:
                self.mark = len(self.duel.log)
                self.actions.pop(0)
            elif "check" in a and a.get("as") == "chain":
                # 「连锁时能否发动」：一次操作可能带来好几个连锁时点（比如召唤中、召唤成功后），
                # 把到下一个稳定时点为止该玩家所有的连锁机会都看一遍，出现过就算「可以」
                if req["type"] == "select_chain" and req["player"] == a.get("player", 0):
                    a["_seen"] = a.get("_seen", False) or any(e["code"] == a["card"] for e in req["chains"])
                    break
                if req["type"] not in STABLE:
                    break
                self.check(self.actions.pop(0), req)
            elif "check" in a and (req["type"] in STABLE or a.get("when") == "next"):
                self.check(self.actions.pop(0), req)
            else:
                break

    def next_action(self, player):
        if self.actions and "check" not in self.actions[0] and self.actions[0].get("player", 0) == player:
            return self.actions[0]
        return None

    def fail(self, text):
        self.failures.append(text)
        self.say("✗ " + text)

    def say(self, text):
        self.lines.append(text)
        if self.verbose:
            print("    " + text)

    # ------------------------------------------------------------ 应答

    def respond(self, req):
        t = req["type"]
        handler = getattr(self, "on_" + t, None)
        if handler is None:
            raise ScenarioError("还不会应答 %s" % t)
        handler(req, self.next_action(req["player"]))

    def take(self):
        return self.actions.pop(0)

    @staticmethod
    def matches(entry, spec, player=None):
        if isinstance(spec, dict):
            if spec.get("code") is not None and entry["code"] != spec["code"]:
                return False
            if "player" in spec and entry.get("controller") != spec["player"]:
                return False
            if "in" in spec and not (entry.get("location", 0) & LOC[spec["in"]]):
                return False
            return True
        return entry["code"] == spec

    def find(self, entries, a, key="card"):
        spec = {"code": a.get(key)}
        if "from" in a:
            spec["in"] = a["from"]
        hits = [i for i, e in enumerate(entries) if self.matches(e, spec)]
        nth = a.get("nth", 0)
        return hits[nth] if len(hits) > nth else None

    def listing(self, entries):
        return "、".join("%s(%s)" % (self.core.name(e["code"]), LOC_NAME.get(e.get("location"), "?")) for e in entries) or "无"

    def on_select_idlecmd(self, req, a):
        p = req["player"]
        if a is None:
            if self.actions:
                raise ScenarioError("玩家%d的主要阶段，但下一个动作是 %s" % (p, json.dumps(self.actions[0], ensure_ascii=False)))
            return
        do = a["do"]
        if do in IDLE_LISTS:
            key, t = IDLE_LISTS[do]
            idx = self.find(req[key], a)
            if idx is None:
                raise ScenarioError("玩家%d不能%s %s；可以的有：%s" % (p, do, self.core.name(a["card"]), self.listing(req[key])))
            self.take()
            self.say("→ 玩家%d %s %s" % (p, do, self.core.name(a["card"])))
            self.duel.respond_int((idx << 16) | t)
        elif do == "battle" and req["can_bp"]:
            self.take()
            self.say("→ 玩家%d 进入战斗阶段" % p)
            self.duel.respond_int(6)
        elif do in ("end_turn", "battle", "main2") and req["can_ep"]:
            if do == "end_turn":
                self.take()
            self.say("→ 玩家%d 结束回合" % p)
            self.duel.respond_int(7)
        else:
            raise ScenarioError("主要阶段做不了 %s" % do)

    def on_select_battlecmd(self, req, a):
        p = req["player"]
        if a is None:
            if self.actions:
                raise ScenarioError("玩家%d的战斗阶段，但下一个动作是 %s" % (p, json.dumps(self.actions[0], ensure_ascii=False)))
            return
        do = a["do"]
        if do == "activate":
            idx = self.find(req["activatable"], a)
            if idx is None:
                raise ScenarioError("战斗阶段不能发动 %s" % self.core.name(a["card"]))
            self.take()
            self.say("→ 玩家%d 发动 %s" % (p, self.core.name(a["card"])))
            self.duel.respond_int(idx << 16)
        elif do == "attack":
            idx = self.find(req["attackable"], a)
            if idx is None:
                raise ScenarioError("%s 不能攻击；可以攻击的有：%s" % (self.core.name(a["card"]), self.listing(req["attackable"])))
            self.take()
            if a.get("target"):
                self.actions.insert(0, {"player": p, "do": "select", "cards": [a["target"]]})
            self.say("→ 玩家%d 用 %s 攻击 %s" % (p, self.core.name(a["card"]),
                                              self.core.name(a["target"]) if a.get("target") else "（直接攻击）"))
            self.duel.respond_int((idx << 16) | 1)
        elif do == "main2" and req["can_m2"]:
            self.take()
            self.duel.respond_int(2)
        elif do in ("end_turn", "main2") and req["can_ep"]:
            if do == "end_turn":
                self.take()
            self.say("→ 玩家%d 结束回合" % p)
            self.duel.respond_int(3)
        else:
            raise ScenarioError("战斗阶段做不了 %s" % do)

    def on_select_chain(self, req, a):
        p = req["player"]
        if req["chains"]:
            self.say("  （玩家%d 可以连锁：%s）" % (p, self.listing(req["chains"])))
        if a and a["do"] == "activate":
            idx = self.find(req["chains"], a)
            if idx is not None:
                self.take()
                self.say("→ 玩家%d 连锁发动 %s" % (p, self.core.name(a["card"])))
                self.duel.respond_int(idx)
                return
        if a and a["do"] == "pass":
            self.take()
        if req["forced"] and req["chains"]:
            self.duel.respond_int(0)
        else:
            self.duel.respond_int(-1)

    def on_select_effectyn(self, req, a):
        p = req["player"]
        yes = 1
        if a and a["do"] in ("activate", "yes") and (a.get("card") in (None, req["code"])):
            self.take()
        elif a and a["do"] == "no":
            self.take()
            yes = 0
        self.say("→ 玩家%d 是否发动 %s：%s" % (p, self.core.name(req["code"]), "是" if yes else "否"))
        self.duel.respond_int(yes)

    def on_select_yesno(self, req, a):
        yes = 1
        if a and a["do"] in ("yes", "no"):
            self.take()
            yes = 1 if a["do"] == "yes" else 0
        self.say("→ 玩家%d 选择%s" % (req["player"], "是" if yes else "否"))
        self.duel.respond_int(yes)

    def on_select_option(self, req, a):
        idx = 0
        if a and a["do"] == "option":
            self.take()
            idx = a["index"]
        self.duel.respond_int(idx)

    def pick(self, entries, a, lo, hi):
        if a and a["do"] == "select":
            self.take()
            chosen = []
            for spec in a["cards"]:
                idx = next((i for i, e in enumerate(entries) if i not in chosen and self.matches(e, spec)), None)
                if idx is None:
                    raise ScenarioError("要选的 %s 不在可选范围里；可选：%s" % (
                        self.core.name(spec["code"] if isinstance(spec, dict) else spec), self.listing(entries)))
                chosen.append(idx)
            return chosen
        return list(range(max(lo, 1)))

    def on_select_card(self, req, a):
        chosen = self.pick(req["cards"], a, req["min"], req["max"])
        self.say("→ 玩家%d 选择 %s" % (req["player"], "、".join(self.core.name(req["cards"][i]["code"]) for i in chosen)))
        self.duel.respond_bytes([len(chosen)] + chosen)

    on_select_tribute = on_select_card

    def on_select_sum(self, req, a):
        """数值合计（同调素材的等级、仪式解放的等级……）：找最少的几张，加上必选的卡，合计正好 / 至少是要求的数。
        应答：总张数（含必选）、必选的占位、再是可选卡的下标。"""
        import itertools

        def values(c):
            v1, v2 = c["param"] & 0xffff, c["param"] >> 16
            return {v1, v2} if v2 else {v1}

        def reach(cards, target):
            sums = {0}
            for c in cards:
                sums = {s + v for s in sums for v in values(c)}
            return any((s == target) if req["mode"] == 0 else (s >= target) for s in sums)
        must, cards = req["must"], req["cards"]
        for k in range(1, len(cards) + 1):
            pick = next((p for p in itertools.combinations(range(len(cards)), k)
                         if reach(must + [cards[i] for i in p], req["acc"])), None)
            if pick is not None:
                break
        else:
            pick = tuple(range(len(cards)))
        self.say("→ 玩家%d 选择 %s" % (req["player"], "、".join(self.core.name(cards[i]["code"]) for i in pick)))
        self.duel.respond_bytes([len(must) + len(pick)] + [0] * len(must) + list(pick))

    def on_select_unselect_card(self, req, a):
        if a and a["do"] == "select":
            want = [s for s in a["cards"] if not any(self.matches(e, s) for e in req["selected"])]
            if not want:
                self.take()
                if req["finishable"]:
                    self.duel.respond_int(-1)
                    return
            for spec in want:
                idx = next((i for i, e in enumerate(req["cards"]) if self.matches(e, spec)), None)
                if idx is not None:
                    if len(want) == 1:
                        self.take()
                    self.say("→ 玩家%d 选择 %s" % (req["player"], self.core.name(req["cards"][idx]["code"])))
                    self.duel.respond_bytes([1, idx])
                    return
            raise ScenarioError("要选的卡不在可选范围里；可选：%s" % self.listing(req["cards"]))
        if req["finishable"] and req["selected"]:
            self.duel.respond_int(-1)
        else:
            self.say("→ 玩家%d 选择 %s" % (req["player"], self.core.name(req["cards"][0]["code"])))
            self.duel.respond_bytes([1, 0])

    def on_select_place(self, req, a):
        p, flag = req["player"], req["flag"]
        out = []
        for bit in range(32):
            if not flag & (1 << bit) and len(out) < 3 * req["count"]:
                pl = p if bit < 16 else 1 - p
                b = bit % 16
                loc, seq = (LOC["mzone"], b) if b < 8 else (LOC["szone"], b - 8)
                out += [pl, loc, seq]
        self.duel.respond_bytes(out)

    on_select_disfield = on_select_place

    def on_select_position(self, req, a):
        for pos in (0x1, 0x4, 0x8, 0x2):
            if req["positions"] & pos:
                self.duel.respond_int(pos)
                return

    def on_sort_card(self, req, a):
        self.duel.respond_int(-1)

    def on_rock_paper_scissors(self, req, a):
        self.duel.respond_int(1)

    def on_announce_race(self, req, a):
        self.announce_bits(req)

    on_announce_attrib = on_announce_race

    def announce_bits(self, req):
        val, n = 0, req["count"]
        for bit in range(32):
            if n and req["available"] & (1 << bit):
                val |= 1 << bit
                n -= 1
        self.duel.respond_int(val)

    def on_announce_card(self, req, a):
        code = 89631139
        if a and a["do"] == "announce":
            self.take()
            code = a["card"]
        self.say("→ 玩家%d 宣言 %s" % (req["player"], self.core.name(code)))
        self.duel.respond_int(code)

    def on_announce_number(self, req, a):
        self.duel.respond_int(0)

    # ------------------------------------------------------------ 检查

    def find_card(self, c):
        zones = [c["in"]] if "in" in c else ["mzone", "szone", "hand", "grave", "banished", "extra"]
        for z in zones:
            for card in self.duel.query(c.get("player", 0), z):
                if card["code"] == c["card"]:
                    return card
        return None

    def since_mark(self):
        return self.duel.log[self.mark:]

    def check(self, c, req):
        kind = c["check"]
        p = c.get("player", 0)
        if kind == "count":
            cards = self.duel.query(p, c["in"])
            if "card" in c:
                cards = [x for x in cards if x["code"] == c["card"]]
            val = len(cards)
            what = "玩家%d %s%s 的数量" % (p, c["in"], (" 中 " + self.core.name(c["card"])) if "card" in c else "")
        elif kind == "lp":
            val = self.lp[p]
            what = "玩家%d 的基本分" % p
        elif kind in ("atk", "def", "level", "disabled", "faceup", "overlay"):
            card = self.find_card(c)
            what = "玩家%d 的 %s 的%s" % (p, self.core.name(c["card"]),
                                        {"atk": "攻击力", "def": "守备力", "level": "等级", "disabled": "效果无效",
                                         "faceup": "表侧表示", "overlay": "超量素材数"}[kind])
            if card is None:
                self.fail("%s：找不到这张卡" % what)
                return
            val = {"atk": card["atk"], "def": card["def"], "level": card["level"], "disabled": card["disabled"],
                   "faceup": bool(card["position"] & 0x5), "overlay": len(card["overlay"])}[kind]
        elif kind == "win":
            wins = [m for m in self.duel.log if m["type"] == "win"]
            val = bool(wins) and wins[-1]["player"] == p
            what = "玩家%d 胜利" % p
            c.setdefault("eq", True)
        elif kind == "event":
            val = sum(1 for m in self.since_mark() if m["type"] == c["name"]
                      and ("card" not in c or m.get("code") == c["card"]))
            what = "消息 %s 的条数" % c["name"]
        elif kind == "drawn":
            val = sum(len(m["codes"]) for m in self.since_mark() if m["type"] == "draw" and m["player"] == p)
            what = "玩家%d 抽卡张数" % p
        elif kind == "offered" and c["as"] == "battle_phase":
            val = bool(req.get("can_bp"))
            what = "玩家%d 是否可以进入战斗阶段" % req.get("player", 0)
        elif kind == "offered":
            key = {"attack": "attackable", "chain": "chains"}.get(c["as"], IDLE_LISTS.get(c["as"], (None,))[0])
            entries = req.get(key, [])
            val = c.get("_seen", False) if c["as"] == "chain" else any(e["code"] == c["card"] for e in entries)
            what = "是否可以 %s %s" % (c["as"], self.core.name(c["card"]))
        else:
            raise ScenarioError("不认识的检查 %r" % kind)
        ok = (val >= c["ge"]) if "ge" in c else (val <= c["le"]) if "le" in c else (val == c["eq"])
        expect = c.get("eq", c.get("ge", c.get("le")))
        if ok:
            self.say("✓ %s = %s" % (what, val))
        else:
            self.fail("%s：期望 %s%s，实际 %s" % (what, {"ge": "≥", "le": "≤"}.get(next((k for k in ("ge", "le") if k in c), ""), ""), expect, val))

    # ------------------------------------------------------------ 日志

    ZONE_ZH = {"deck": "卡组", "hand": "手卡", "mzone": "怪兽区", "szone": "魔陷区", "grave": "墓地",
               "banished": "除外", "extra": "额外卡组", "overlay": "超量素材"}

    def where(self, loc):
        if loc["location"] & 0x80:
            return "玩家%d的超量素材" % loc["controller"]
        name = LOC_NAME.get(loc["location"])
        return "玩家%d的%s" % (loc["controller"], self.ZONE_ZH.get(name, hex(loc["location"])))

    def note(self, m):
        t = m["type"]
        n = self.core.name
        if t == "damage":
            self.lp[m["player"]] -= m["value"]
        elif t == "pay_lpcost":
            self.lp[m["player"]] -= m["value"]
        elif t == "recover":
            self.lp[m["player"]] += m["value"]
        elif t == "lpupdate":
            self.lp[m["player"]] = m["value"]
        text = {
            "new_turn": lambda: "== 玩家%d 的回合" % m["player"],
            "new_phase": lambda: "-- %s" % PHASE.get(m["phase"], hex(m["phase"])),
            "move": lambda: "%s：%s → %s" % (n(m["code"]) if m["code"] else "?", self.where(m["from"]), self.where(m["to"])),
            "chaining": lambda: "连锁%d：%s 发动" % (m["chain"], n(m["code"])),
            "chain_solving": lambda: "连锁%d 处理" % m["chain"],
            "chain_negated": lambda: "连锁%d 的发动被无效" % m["chain"],
            "chain_disabled": lambda: "连锁%d 的效果被无效" % m["chain"],
            "summoning": lambda: "%s 召唤" % n(m["code"]),
            "spsummoning": lambda: "%s 特殊召唤" % n(m["code"]),
            "draw": lambda: "玩家%d 抽 %d 张" % (m["player"], len(m["codes"])),
            "damage": lambda: "玩家%d 受到 %d 伤害（%d）" % (m["player"], m["value"], self.lp[m["player"]]),
            "recover": lambda: "玩家%d 回复 %d" % (m["player"], m["value"]),
            "attack": lambda: "攻击宣言",
            "attack_disabled": lambda: "攻击被无效",
            "pos_change": lambda: "%s 改变表示形式" % n(m["code"]),
            "win": lambda: "玩家%d 胜利" % m["player"],
        }.get(t)
        if text:
            self.say(text())


def run_file(core, path, overrides=None, verbose=False):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    scenarios = data["scenarios"] if "scenarios" in data else [data]
    core.overrides = overrides or {}
    results = []
    for sc in scenarios:
        r = Runner(core, sc, verbose)
        results.append((sc["name"], r.run(), r))
    return results


def main():
    ap = argparse.ArgumentParser(description="运行情景测试")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--script", action="append", default=[], help="卡号=Lua 文件，用它代替官方脚本")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    from .core import Core
    core = Core()
    overrides = {}
    for s in args.script:
        code, path = s.split("=", 1)
        with open(path, "rb") as f:
            overrides[int(code)] = f.read()
    bad = 0
    for path in args.files:
        for name, ok, r in run_file(core, path, overrides, args.verbose):
            print("%s  %s" % ("通过" if ok else "失败", name))
            if not ok and not args.verbose:
                for line in r.failures:
                    print("    ✗ " + line)
            bad += not ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
