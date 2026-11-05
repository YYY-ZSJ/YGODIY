"""生成器目前按固定写法识别的组合。中文与 Lua 两个后端共用，保证认出来的是同一种东西。

通用的数值表达式、选卡器组合做出来以后，这里的写法会逐个换成通用实现。
"""

from .normalize import is_ref

LINKED_MONSTERS = {"who": "both", "where": ["linked"]}


def linked_count_times(value):
    """「这张卡所连接区的怪兽数量×N」：返回 N；不是这种写法返回 None。"""
    if isinstance(value, dict) and len(value.get("mul", [])) == 2:
        a, n = value["mul"]
        if isinstance(a, dict) and a.get("count") == LINKED_MONSTERS and isinstance(n, int):
            return n
    return None


def same_original_name_ref(ap):
    """「这个效果除外的怪兽以及原本卡名和那只怪兽相同的怪兽」：返回那个绑定名；不是这种写法返回 None。"""
    anyof = (ap.get("affects") or {}).get("any") or []
    if len(anyof) == 2 and is_ref(anyof[0]):
        same = [f["original_name"]["same_as"] for f in anyof[1].get("filter", []) if "original_name" in f]
        if same and same[0] == anyof[0]:
            return anyof[0]["ref"]
    return None
