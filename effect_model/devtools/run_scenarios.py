"""在测试沙盒里跑样例卡的情景：每个情景分别用官方脚本和 Effect Model 生成的脚本各跑一次。

官方脚本通过、生成脚本不通过 → 生成器或模型有问题；
两边都不通过 → 情景本身写错了（或者官方脚本与裁定不同）。

用法（在 YGODIY_src 下）：
    python -m effect_model.devtools.run_scenarios                # 全部
    python -m effect_model.devtools.run_scenarios 灰流丽 -v       # 文件名包含「灰流丽」的，打印详细过程
"""

import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, SRC)

from effect_model import load, build  # noqa: E402
from sandbox.core import Core  # noqa: E402
from sandbox.scenario import run_file  # noqa: E402

PKG = os.path.dirname(HERE)

# 变异测试：故意把生成的脚本改坏一处，情景应该能发现。(卡号, 原文, 改成, 说明)
MUTATIONS = [
    (12580477, "tp,0,LOCATION_MZONE", "tp,LOCATION_MZONE,0", "雷击改成破坏自己的怪兽"),
    (83764718, "Duel.SpecialSummon(tc,0,tp,tp,", "Duel.SpecialSummon(tc,0,tp,1-tp,", "死者苏生特召到对方场上"),
    (44095762, "c:IsAttackPos()", "c:IsDefensePos()", "反射镜力改成破坏守备表示"),
    (26202165, "SetTargetRange(1,0)", "SetTargetRange(0,1)", "三眼怪的发动限制加到对方身上"),
    (70095154, "GetFieldGroupCount(tp,LOCATION_MZONE,0)==0", "GetFieldGroupCount(tp,LOCATION_MZONE,0)>=0", "电子龙不再要求自己场上没有怪兽"),
    (14558127, " or re:IsHasCategory(CATEGORY_DRAW)", "", "灰流丽不再回应抽卡"),
    (23434538, "1,nil,1-tp) and Duel.IsChainSolving()", "1,nil,tp) and Duel.IsChainSolving()", "增殖的G 连锁中只数自己的特召"),
    (24224830, "RESET_PHASE+PHASE_END,2", "RESET_PHASE+PHASE_END", "墓穴的指名者只持续到本回合结束"),
    (10045474, "GetFieldGroupCount(tp,LOCATION_ONFIELD,0)==0", "GetFieldGroupCount(tp,LOCATION_ONFIELD,0)<=1", "无限泡影场上有1张卡也能从手卡发动"),
    (72302403, "if ct==3 then", "if ct==2 then", "光之护封剑提前一回合破坏"),
    (84013237, "GetOverlayCount()==0", "GetOverlayCount()==1", "霍普在还剩1个素材时就自我破坏"),
    (1861629, "GetLinkedGroupCount()*500", "GetLinkedGroupCount()*400", "解码语者每只只加400"),
    (44508094, "\tc:RegisterFlagEffect(id,", "\t-- c:RegisterFlagEffect(id,", "星尘龙不记录①已适用"),
    (16178681, "DOUBLE_DAMAGE", "HALF_DAMAGE", "异色眼的伤害2倍改成一半"),
    (72270339, "Duel.GetTurnPlayer()==1-tp", "Duel.GetTurnPlayer()==tp", "迪亚贝尔斯塔尔③改成自己回合"),
    # v0.2 压力卡
    (10443957, "c:GetOverlayCount()*200", "c:GetOverlayCount()*100", "电子龙·无限每个素材只加100"),
    (10443957, "c:IsPosition(POS_FACEUP_ATTACK) and c:IsCanOverlay()", "c:IsFaceup() and c:IsCanOverlay()",
     "电子龙·无限②守备表示怪兽也能吸收"),
    (15693423, "GetFieldGroupCount(tp,LOCATION_ONFIELD,0)==0", "GetFieldGroupCount(tp,LOCATION_ONFIELD,0)<=1",
     "颉颃胜负自己场上有1张卡也能从手卡发动"),
    (27693363, "math.abs(a:GetLevel()-b:GetLevel())==1", "math.abs(a:GetLevel()-b:GetLevel())>=1", "勾陈一不检查等级差"),
    (31036355, "pe2:SetCode(EFFECT_CANNOT_CHANGE_POSITION)", "pe2:SetCode(EFFECT_CANNOT_ATTACK)",
     "强制转移换来的怪兽可以变更表示形式"),
    (32841045, "e:GetHandler():GetColumnGroup():IsContains(re:GetHandler())", "true", "卡斯帕不检查纵列"),
    (32841045, " and not c:IsCode(e:GetLabelObject():GetCode())", "", "卡斯帕能检索同名魔弹"),
    (35316708, "se:SetCode(EFFECT_SKIP_DP)", "se:SetCode(EFFECT_SKIP_SP)", "刻之封印跳过的是准备阶段"),
    (37742478, "ae:SetValue(d:GetAttack())", "ae:SetValue(a:GetAttack())", "欧尼斯特加的是自己怪兽的攻击力"),
    (37742478, "c:IsAttribute(ATTRIBUTE_LIGHT) and ", "", "欧尼斯特不限光属性"),
    (40605147, "re:IsActiveType(TYPE_MONSTER)", "re:IsActiveType(TYPE_SPELL)", "神之通告①只回应魔法卡"),
    (40605147, "Duel.PayLPCost(tp,1500)", "Duel.PayLPCost(tp,1000)", "神之通告只付1000"),
    (46052429, "c:IsType(TYPE_NORMAL) and ", "", "高等仪式术能用效果怪兽作素材"),
    (52624755, "c:IsCode(52624755)", "c:IsCode(89631139)", "彼得特殊召唤的是别的怪兽"),
    (65518099, "return not (c:IsSetCard(0xaa))", "return false", "丑恶不再限制特殊召唤"),
    (65518099, "not c:IsCode(65518099) and ", "", "丑恶能检索同名卡"),
    (65681983, "\tDuel.NegateEffect(ev)", "\t-- Duel.NegateEffect(ev)", "抹杀之指名者不再无效发动的效果"),
    (70791313, "IsCanRemoveCounter(tp,0x1,3,REASON_COST)", "IsCanRemoveCounter(tp,0x1,2,REASON_COST)",
     "王立魔法图书馆2个指示物就能抽卡"),
    (71625222, "Duel.Damage(tp,math.floor(sum/2),REASON_EFFECT)", "Duel.Damage(tp,sum,REASON_EFFECT)",
     "时间魔术师猜错时受到全额伤害"),
    (71625222, "GetMatchingGroup(aux.TRUE,tp,0,LOCATION_MZONE", "GetMatchingGroup(aux.TRUE,tp,LOCATION_MZONE,0",
     "时间魔术师猜中时破坏自己的怪兽"),
    (73915051, "oe1:SetCode(EFFECT_CANNOT_SUMMON)", "oe1:SetCode(EFFECT_CANNOT_MSET)", "替罪羊不再禁止通常召唤"),
    (74117290, "Duel.DiscardHand(1-tp,", "Duel.DiscardHand(tp,", "暗黑界的取引对方不用丢弃"),
    (75500286, "if ct~=2 then return end", "if ct~=1 then return end", "封印之黄金柜第1次准备阶段就加入手卡"),
    (79229522, "c:GetMaterialCount()*1000", "c:GetMaterialCount()*500", "嵌合要塞龙每个素材只算500"),
    (81674782, "e1:SetValue(LOCATION_REMOVED)", "e1:SetValue(LOCATION_HAND)", "次元的裂缝改成回到手卡"),
    (82732705, "e2:SetCode(EFFECT_DISABLE)", "e2:SetCode(EFFECT_CANNOT_ATTACK)", "技能抽取不再无效效果"),
    (84815190, "c:IsLevelBelow(9)", "c:IsLevelBelow(3)", "鲜花女男爵③只能苏生3星以下"),
    (85138716, "\tDuel.Destroy(tg,REASON_EFFECT)", "\t-- Duel.Destroy(tg,REASON_EFFECT)", "救援兔召唤的怪兽结束阶段不破坏"),
    (91932350, "e0:SetValue(76812113)", "e0:SetValue(89631139)", "鹰身女郎1不再当作鹰身女郎"),
    (95308449, "if ct==20 then", "if ct==19 then", "终焉的倒计时提前一回合胜利"),
    (95453143, "c:IsAttribute(ATTRIBUTE_DARK)", "c:IsAttribute(ATTRIBUTE_LIGHT)", "百眼龙除外的是光属性怪兽"),
    (98127546, "GetMatchingGroup(s.filter1,tp,0,LOCATION_MZONE", "GetMatchingGroup(s.filter1,tp,LOCATION_MZONE,0",
     "冥神①无效的是自己的怪兽"),
    # 自肃
    (10118318, "Duel.GetActivityCount(tp,ACTIVITY_BATTLE_PHASE)==0", "true", "休战增援不检查这回合进行过战斗阶段"),
    (10118318, "SetCode(EFFECT_CANNOT_BP)", "SetCode(EFFECT_CANNOT_ATTACK)", "休战增援不再禁止进行战斗阶段"),
    # 永续第一批
    (21015833, "e1:SetValue(1)", "e1:SetValue(0)", "隼骑士只能攻击1次"),
    (11125718, "SetCode(EFFECT_PIERCE)", "SetCode(EFFECT_DIRECT_ATTACK)", "枪兵龙人没有贯通"),
    (97021916, "SetCountLimit(1)", "SetCountLimit(2)", "暗黑共鸣者1回合2次不会被战斗破坏"),
    (97021916, "r&(REASON_BATTLE)~=0", "r&(REASON_EFFECT)~=0", "暗黑共鸣者的抗性改成对效果"),
    (36717258, "SetCode(EFFECT_ATTACK_ALL)", "SetCode(EFFECT_PIERCE)", "朱罗纪单脊龙不能向全部怪兽攻击"),
]


def generated_scripts():
    out = {}
    for path in glob.glob(os.path.join(PKG, "samples", "*.json")):
        model = load(path)
        out[model["card"]["code"]] = build(model)["lua"].encode("utf-8")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("filter", nargs="?", default="")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--mutate", action="store_true", help="变异测试：确认情景能发现故意改坏的脚本")
    args = ap.parse_args()
    import json
    core = Core()
    scripts = generated_scripts()
    files = [p for p in sorted(glob.glob(os.path.join(PKG, "scenarios", "*.json"))) if args.filter in os.path.basename(p)]
    if args.mutate:
        return mutate(core, scripts, files)
    rows, bad, aliased = [], 0, set()
    for path in files:
        with open(path, encoding="utf-8") as f:
            code = json.load(f)["card"]
        if args.verbose:
            print("## 官方脚本：%s" % os.path.basename(path))
        official = run_file(core, path, {}, args.verbose)
        if args.verbose:
            print("## 生成脚本：%s" % os.path.basename(path))
        with core.as_exported(code):
            generated = run_file(core, path, {code: scripts[code]}, args.verbose)
        for (name, ok_o, r_o), (_, ok_g, r_g) in zip(official, generated):
            rows.append((name, ok_o, ok_g, r_o, r_g))
            bad += ok_o and not ok_g
            if not ok_o and core.cdb.get(code, (0, 0))[1]:
                aliased.add(core.name(code))
    print("%-6s %-6s %s" % ("官方", "生成", "情景"))
    for name, ok_o, ok_g, r_o, r_g in rows:
        print("%-6s %-6s %s" % ("通过" if ok_o else "失败", "通过" if ok_g else "失败", name))
        for line in ([] if ok_o else ["[官方] " + x for x in r_o.failures]) + ([] if ok_g else ["[生成] " + x for x in r_g.failures]):
            print("              ✗ " + line)
    n = len(rows)
    print("官方脚本通过 %d / %d，生成脚本通过 %d / %d" % (
        sum(r[1] for r in rows), n, sum(r[2] for r in rows), n))
    if aliased:
        print("注：%s 在官方卡库里有 alias，MDPro3 带的引擎会改去加载 alias 那张卡的脚本，官方脚本在沙盒里跑不起来；"
              "生成脚本照导出后的样子（alias 为 0）测试。" % "、".join(sorted(aliased)))
    return 1 if bad else 0


def mutate(core, scripts, files):
    import json
    by_code = {}
    for path in files:
        with open(path, encoding="utf-8") as f:
            by_code.setdefault(json.load(f)["card"], []).append(path)
    missed = 0
    for code, old, new, desc in MUTATIONS:
        if code not in by_code:
            continue
        src = scripts[code].decode("utf-8")
        if old not in src:
            print("没命中  %s（生成的脚本里找不到要改的那段）" % desc)
            missed += 1
            continue
        bad = src.replace(old, new, 1).encode("utf-8")
        with core.as_exported(code):
            caught = [name for path in by_code[code] for name, ok, _ in run_file(core, path, {code: bad}) if not ok]
        print("%s  %s%s" % ("检出" if caught else "漏检", desc, ("：" + caught[0]) if caught else ""))
        missed += not caught
    print("漏检 %d / %d" % (missed, len([m for m in MUTATIONS if m[0] in by_code])))
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
