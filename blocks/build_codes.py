"""从引擎的常量表（MDPro3 的 script.zip 里的 constant.lua）整理出全部效果代码，写成 effect_codes.json：
名字、数值、中文（常量表自带的注释）、类别、是否常用。积木「登记效果」的效果代码下拉就读这份表。

用法（在 YGODIY_src 下）：python -m blocks.build_codes
"""

import json
import os
import re
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT_ZIP = r"D:\Game\MDPro3\Data\script.zip"

# 类别：按名字里的关键字分，先匹配的优先
CATEGORIES = [
    ("破坏与抗性", r"INDESTRUCTABLE|IMMUNE|CANNOT_BE_EFFECT_TARGET|CANNOT_BE_BATTLE_TARGET|DESTROY_REPLACE|DESTROY_SUBSTITUTE|CANNOT_REMOVE|CANNOT_TO_|CANNOT_RELEASE|UNRELEASABLE|CANNOT_CHANGE_CONTROL"),
    ("攻击与战斗", r"ATTACK_|_ATTACK$|ATTACK$|PIERCE|DIRECT|BATTLE|DAMAGE_STEP|MUST_ATTACK|AVOID|REFLECT"),
    ("攻守数值", r"ATTACK|DEFENSE"),
    ("等级·阶级·刻度·连接", r"LEVEL|RANK|SCALE|LSCALE|RSCALE|LINK_MARKER"),
    ("卡名·种族·属性·种类", r"CODE|RACE|ATTRIBUTE|_TYPE|SETCODE"),
    ("召唤与素材", r"SUMMON|MATERIAL|SPSUM|TRIBUTE|SET_PROC|PROC|XYZ|SYNCHRO|FUSION|RITUAL|LINK|MSET|SSET|TURN_SET|FLIP"),
    ("发动与无效", r"ACTIVATE|DISABLE|NEGATE|CHAIN|TRIGGER|INACTIVATE|DISEFFECT|QP_ACT|TRAP_ACT"),
    ("移动与去向", r"REDIRECT|TO_HAND|TO_DECK|TO_GRAVE|REMOVE|LEAVE|DRAW|DISCARD|HAND|DECK|GRAVE|RETURN"),
    ("伤害与基本分", r"DAMAGE|LP|RECOVER|LPCOST"),
    ("指示物", r"COUNTER"),
    ("阶段与回合", r"SKIP|PHASE|TURN|BP"),
]
# 常用：积木下拉里排在最前面（按卡库里官方卡的用量挑的）
COMMON = ["EFFECT_UPDATE_ATTACK", "EFFECT_UPDATE_DEFENSE", "EFFECT_SET_ATTACK", "EFFECT_SET_ATTACK_FINAL",
          "EFFECT_SET_DEFENSE", "EFFECT_SET_BASE_ATTACK", "EFFECT_UPDATE_LEVEL", "EFFECT_CHANGE_LEVEL",
          "EFFECT_INDESTRUCTABLE_BATTLE", "EFFECT_INDESTRUCTABLE_EFFECT", "EFFECT_INDESTRUCTABLE_COUNT",
          "EFFECT_CANNOT_BE_EFFECT_TARGET", "EFFECT_IMMUNE_EFFECT", "EFFECT_CANNOT_ATTACK",
          "EFFECT_CANNOT_ATTACK_ANNOUNCE", "EFFECT_CANNOT_DIRECT_ATTACK", "EFFECT_DIRECT_ATTACK", "EFFECT_PIERCE",
          "EFFECT_EXTRA_ATTACK", "EFFECT_ATTACK_ALL", "EFFECT_CANNOT_BE_BATTLE_TARGET", "EFFECT_DISABLE",
          "EFFECT_DISABLE_EFFECT", "EFFECT_CANNOT_ACTIVATE", "EFFECT_CANNOT_SPECIAL_SUMMON", "EFFECT_CANNOT_SUMMON",
          "EFFECT_CANNOT_TRIGGER", "EFFECT_CANNOT_CHANGE_POSITION", "EFFECT_LEAVE_FIELD_REDIRECT",
          "EFFECT_TO_GRAVE_REDIRECT", "EFFECT_CANNOT_BE_SYNCHRO_MATERIAL", "EFFECT_CANNOT_BE_XYZ_MATERIAL",
          "EFFECT_CANNOT_BE_LINK_MATERIAL", "EFFECT_CANNOT_BE_FUSION_MATERIAL", "EFFECT_UNRELEASABLE_SUM",
          "EFFECT_UNRELEASABLE_NONSUM", "EFFECT_CHANGE_CODE", "EFFECT_CHANGE_RACE", "EFFECT_CHANGE_ATTRIBUTE",
          "EFFECT_CHANGE_DAMAGE", "EFFECT_CHANGE_BATTLE_DAMAGE", "EFFECT_AVOID_BATTLE_DAMAGE",
          "EFFECT_REFLECT_BATTLE_DAMAGE", "EFFECT_SKIP_DP", "EFFECT_SKIP_BP", "EFFECT_CANNOT_DRAW",
          "EFFECT_CANNOT_TO_HAND", "EFFECT_CANNOT_SSET", "EFFECT_CANNOT_MSET"]


def main():
    text = zipfile.ZipFile(SCRIPT_ZIP).read("script/constant.lua").decode("utf-8", "replace")
    codes = []
    for name, value, note in re.findall(r"^(EFFECT_[A-Z0-9_]+)\s*=\s*(\d+)\s*(--.*)?$", text, re.M):
        short = name[len("EFFECT_"):]
        cat = next((c for c, p in CATEGORIES if re.search(p, short)), "其他")
        codes.append({"name": name, "value": int(value), "zh": note.strip(" -\r\t") or short.lower(),
                      "category": cat, "common": name in COMMON})
    codes.sort(key=lambda c: (not c["common"], COMMON.index(c["name"]) if c["common"] else 0, c["value"]))
    with open(os.path.join(HERE, "effect_codes.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({"来源": "MDPro3 script/constant.lua（萌卡一系 ygopro-scripts）", "条数": len(codes), "codes": codes},
                  f, ensure_ascii=False, indent=1)
    by = {}
    for c in codes:
        by[c["category"]] = by.get(c["category"], 0) + 1
    print(len(codes), "常用", sum(c["common"] for c in codes), by)
    missing = [n for n in COMMON if n not in {c["name"] for c in codes}]
    if missing:
        print("常用里写错的名字：", missing)


if __name__ == "__main__":
    main()
