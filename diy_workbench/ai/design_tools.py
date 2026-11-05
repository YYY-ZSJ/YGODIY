"""效果文本的设计稿、书写规范检查和与积木读回的对比；不判断规则是否真的成立。"""

import difflib
import re

from sandbox.test_data import intent_text
from sandbox.test_templates import NUMBERED, effect_texts

WORDS = {"手牌": "手卡", "怪物": "怪兽", "坟场": "墓地", "牌组": "卡组", "牌库": "卡组", "对手": "对方", "敌方": "对方", "我方": "自己",
         "血量": "基本分", "生命值": "基本分", "技能": "效果", "抽牌": "抽卡", "从游戏中除外": "除外", "除外区": "除外状态",
         "原来的": "原本的", "出场": "召唤或特殊召唤"}
CHINESE_COUNT = re.compile(r"[一二两三四五六七八九十]+(?=张|只|回合|次|个|星)")


def _issue(level, message, suggestion=""):
    return {"level": level, "message": message, "suggestion": suggestion}


def _numbers(text):
    return [NUMBERED.index(mark) + 1 for mark in re.findall("[" + NUMBERED + "](?=\\s*[:：])", text)]


def check_text(text):
    """→ 问题列表。level：错误=写法不成立，建议=不符合官方习惯，确认=会影响规则含义，要玩家决定。"""
    issues = []
    for word, better in WORDS.items():
        if word in text:
            issues.append(_issue("建议", "「%s」不是官方用语" % word, "写成「%s」" % better))
    for m in CHINESE_COUNT.finditer(text):
        issues.append(_issue("建议", "数量「%s」要用阿拉伯数字" % m.group(), "例如「1张」「1回合」"))
    if re.search(r"[,;:()]", text):
        issues.append(_issue("建议", "有半角标点", "全部用全角标点（，；：（））"))
    if text.count("「") != text.count("」"):
        issues.append(_issue("错误", "「」没有配对"))
    numbers = _numbers(text)
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        issues.append(_issue("错误", "效果编号不连续", "从①开始按顺序编号"))
    cited = {NUMBERED.index(mark) + 1 for line in text.splitlines() if "这个卡名" in line and not _numbers(line)
             for mark in re.findall("[" + NUMBERED + "]", line)}
    if cited - set(numbers):
        issues.append(_issue("错误", "次数限制提到了不存在的效果编号"))
    for line in filter(None, (line.strip() for line in text.splitlines())):
        if line[-1] not in "。）」":
            issues.append(_issue("建议", "这一句没有用句号结束：%s" % line[-12:]))
    if re.search(r"[^。\n]那之后", text):
        issues.append(_issue("确认", "「那之后」前面不是句号", "「。那之后，」和「，」的处理时点不同，改动前请玩家确认"))
    if "选择" in text:
        issues.append(_issue("建议", "不要用「选择」", "取对象写「以……为对象」，不取对象写「选」"))
    if re.search(r"才能发动，", text):
        issues.append(_issue("建议", "「才能发动」后面要用句号", "发动条件、代价写完用句号，再写效果处理"))
    if re.search(r"[\[【][^\]】]*[\]】]", text.replace("【灵摆效果】", "").replace("【怪兽效果】", "")):
        issues.append(_issue("建议", "字段和卡名要用「」", "不要用 [ ] 或【】"))
    if re.search(r"[①-⑳]、", text):
        issues.append(_issue("建议", "编号之间不用顿号", "写成「①②」"))
    if re.search(r"只要这张卡在场上存在", text):
        issues.append(_issue("建议", "永续效果要写明区域", "写「怪兽区域」或「魔法与陷阱区域」，不写「场上」"))
    if re.search(r"(?<![自己方])(从|以)墓地|(?<![自己方的])墓地[1-9]", text):
        issues.append(_issue("确认", "没写是谁的墓地", "不写就是双方的墓地都可以，只想用自己的要写「自己墓地」"))
    if "时才能发动" in text:
        issues.append(_issue("确认", "「时」加「才能发动」可能错过时点", "如果不想被卡时点，改成「场合」"))
    if re.search(r"可以发动|发动后", text):
        issues.append(_issue("确认", "出现「可以发动」或「发动后」", "官方写法是「才能发动」或「发动」，两者含义不同"))
    if re.search(r"(支付|丢弃|解放|除外|送去墓地)[^。]*(然后|再)", text):
        issues.append(_issue("确认", "代价和处理的分界不清楚", "代价写在「才能发动」前面，处理写在句号之后"))
    if "各能使用1次" in text and "其中" in text:
        issues.append(_issue("确认", "同时出现「各能使用1次」和「其中」", "前者每个效果分别计次，后者共用次数"))
    return issues


def _parts(text):
    rows = effect_texts(text)
    header = rows[0][2].strip() if rows else ""
    return header, {number: body.strip() for number, body, _ in rows}


def _squash(text):
    return re.sub(r"\s+", "", text or "")


def _differences(left, right):
    matcher = difflib.SequenceMatcher(None, left, right, autojunk=False)
    return [{"design": left[a:b], "reading": right[c:d]} for tag, a, b, c, d in matcher.get_opcodes() if tag != "equal"][:12]


def compare_text(design, reading):
    """逐个编号对比设计稿和积木读回；文字相同不等于效果相同，文字不同也不一定是错。"""
    head_a, left = _parts(design)
    head_b, right = _parts(reading)
    rows = []
    if _squash(head_a) != _squash(head_b):
        rows.append({"effect": 0, "same": False, "differences": _differences(_squash(head_a), _squash(head_b))})
    for number in sorted(set(left) | set(right)):
        a, b = _squash(left.get(number)), _squash(right.get(number))
        row = {"effect": number, "same": a == b}
        if not row["same"]:
            row["missing"] = "积木" if not b else "设计稿" if not a else ""
            row["differences"] = _differences(a, b)
        rows.append(row)
    return {"same": all(row["same"] for row in rows), "effects": rows,
            "note": "只比较文字；效果是否真的这样运行要看沙盒测试。"}


class DesignTools:
    def __init__(self, operations):
        self.operations = operations

    def _document(self, card_uid=None):
        plan = self.operations.changes.current
        if plan is not None:
            return plan.working_document(card_uid or plan.target)
        tab = self.operations._find(card_uid)[2]
        return dict(tab, data=self.operations.changes.project.data(tab))

    def check(self, text=None, card_uid=None):
        text = text if text is not None else intent_text(self._document(card_uid))
        if not text.strip():
            raise ValueError("这张卡还没有设计稿或效果文字。")
        issues = check_text(text)
        return {"issues": issues, "clean": not issues, "note": "只检查书写习惯，不判断规则是否成立。"}

    def compare(self, card_uid=None):
        from .change_plan import block_feedback
        document = self._document(card_uid)
        text = intent_text(document)
        if not text.strip():
            raise ValueError("这张卡还没有设计稿或效果文字。")
        feedback = block_feedback(document)
        if not feedback["reading"]:
            raise ValueError("积木还读不出文字：%s" % "；".join(row["message"] for row in feedback["warnings"]))
        return compare_text(text, feedback["reading"])
