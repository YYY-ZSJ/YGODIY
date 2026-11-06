# -*- coding: utf-8 -*-
"""日文注音：给汉字加上 YGODIY 使用的注音标记「[漢字(よみ)]」。

- 卡名：用离线卡库的读音（jp_ruby）按「汉字段 / 假名段」对齐，对不上就整体注音。
- 效果文本：按游戏王日文文本的常用词表做最长匹配；读音用「|」分到每个汉字上，
  与官方卡面逐字注音的样子一致。词表外的汉字不注音。
"""

import re

# 词 -> 读音（用 | 按汉字分开；分不开的整体注音）
_WORDS = """
発動 はつ|どう
自分 じ|ぶん
効果 こう|か
相手 あい|て
特殊 とく|しゅ
召喚 しょう|かん
場合 ば|あい
墓地 ぼ|ち
手札 て|ふだ
対象 たい|しょう
破壊 は|かい
存在 そん|ざい
使用 し|よう
攻撃 こう|げき
攻撃力 こう|げき|りょく
守備 しゅ|び
守備力 しゅ|び|りょく
戦闘 せん|とう
除外 じょ|がい
魔法 ま|ほう
魔法使 ま|ほう|つか
表側 おもて|がわ
裏側 うら|がわ
表示 ひょう|じ
以外 い|がい
以下 い|か
以上 い|じょう
素材 そ|ざい
終了 しゅう|りょう
装備 そう|び
無効 む|こう
無効化 む|こう|か
元々 もと|もと
融合 ゆう|ごう
選択 せん|たく
状態 じょう|たい
通常 つう|じょう
適用 てき|よう
機械 き|かい
属性 ぞく|せい
光属性 ひかり|ぞく|せい
闇属性 やみ|ぞく|せい
水属性 みず|ぞく|せい
炎属性 ほのお|ぞく|せい
地属性 ち|ぞく|せい
風属性 かぜ|ぞく|せい
神属性 かみ|ぞく|せい
方法 ほう|ほう
同名 どう|めい
合計 ごう|けい
儀式 ぎ|しき
宣言 せん|げん
直接 ちょく|せつ
自身 じ|しん
植物 しょく|ぶつ
悪魔 あく|ま
種族 しゅ|ぞく
回復 かい|ふく
半分 はん|ぶん
種類 しゅ|るい
任意 にん|い
昆虫 こん|ちゅう
一番 いち|ばん
一番上 いち|ばん|うえ
一番下 いち|ばん|した
一番高 いち|ばん|たか
一番低 いち|ばん|ひく
確認 かく|にん
反転 はん|てん
形式 けい|しき
計算 けい|さん
変更 へん|こう
開始 かい|し
発生 はっ|せい
魔力 ま|りょく
数値 すう|ち
天使 てん|し
永続 えい|ぞく
爬虫類 は|ちゅう|るい
恐竜 きょう|りゅう
降臨 こう|りん
戦士 せん|し
獣戦士 じゅう|せん|し
鳥獣 ちょう|じゅう
魚族 ぎょ|ぞく
雷族 いかずち|ぞく
水族 みず|ぞく
炎族 ほのお|ぞく
獣族 じゅう|ぞく
処理 しょ|り
同一 どう|いつ
無視 む|し
条件 じょう|けん
縦列 じゅう|れつ
上記 じょう|き
岩石 がん|せき
順番 じゅん|ばん
可能 か|のう
速攻 そっ|こう
最大 さい|だい
幻竜 げん|りゅう
海竜 かい|りゅう
移動 い|どう
必要 ひつ|よう
片方 かた|ほう
相互 そう|ご
幻想 げん|そう
幻想魔 げん|そう|ま
幻神獣 げん|しん|じゅう
創造神 そう|ぞう|しん
位置 い|ち
裏表 うら|おもて
成功 せい|こう
正面 しょう|めん
公開 こう|かい
指定 し|てい
一組 ひと|くみ
枚数 まい|すう
勝利 しょう|り
同士 どう|し
中央 ちゅう|おう
制限 せい|げん
同時 どう|じ
代用 だい|よう
封印 ふう|いん
奇数 き|すう
偶数 ぐう|すう
倍数 ばい|すう
以降 い|こう
両方 りょう|ほう
未満 み|まん
回数 かい|すう
能力 のう|りょく
複数 ふく|すう
戦闘破壊 せん|とう|は|かい
効果名 こう|か|めい
連続 れん|ぞく
決定 けっ|てい
発動条件 はつ|どう|じょう|けん
所持 しょ|じ
数字 すう|じ
原本 げん|ぽん
変化 へん|か
一度 いち|ど
一体 いっ|たい
以後 い|ご
異 こと
元 もと
"""

# 汉字单独出现（后面跟假名或在词首）时的读音
_SINGLE = """
選 えら
加 くわ
送 おく
戻 もど
限 かぎ
数 かず
行 おこな
与 あた
除 のぞ
他 ほか
上 うえ
事 こと
取 と
同 おな
置 お
捨 す
互 たが
受 う
中 なか
持 も
見 み
離 はな
得 え
代 か
払 はら
次 つぎ
赤 あか
青 あお
守 まも
含 ふく
及 およ
記 しる
先 さき
星 ほし
分 ぶん
表 おもて
裏 うら
間 あいだ
下 した
高 たか
重 かさ
倍 ばい
回 かい
残 のこ
目 め
際 さい
対 たい
好 す
低 ひく
替 か
多 おお
続 つづ
移 うつ
主 おも
毎 ごと
違 ちが
入 い
者 もの
差 さ
失 うしな
当 あ
大 おお
少 すく
無 な
言 い
振 ふ
使 つか
全 すべ
後 ご
時 とき
名 めい
体 たい
枚 まい
度 ど
族 ぞく
扱 あつか
罠 わな
光 ひかり
闇 やみ
炎 ほのお
水 みず
風 かぜ
地 ち
神 かみ
内 ない
組 くみ
戦 たたか
破 やぶ
相 あい
付 つ
変 か
決 き
半 はん
"""

# 汉字出现在汉字串中间/末尾（作为后缀）时改用音读
_SUFFIX = {
    "時": "じ", "後": "ご", "分": "ぶん", "名": "めい", "体": "たい", "枚": "まい", "族": "ぞく",
    "度": "ど", "数": "すう", "回": "かい", "内": "ない", "中": "ちゅう", "上": "じょう", "扱": "あつか",
    "際": "さい", "毎": "ごと", "間": "かん", "者": "しゃ", "目": "め", "下": "か", "化": "か",
}


def _parse(block):
    table = {}
    for line in block.strip().splitlines():
        parts = line.split()
        if len(parts) == 2:
            table.setdefault(parts[0], parts[1])
    return table


WORDS = _parse(_WORDS)
SINGLE = _parse(_SINGLE)
_MAX_WORD = max(len(word) for word in WORDS)

_KANJI_RE = re.compile(r"[㐀-鿿豈-﫿々]+")
_RUBY_RE = re.compile(r"\[[^\[\]]*?\([^()]*?\)\]")


def _is_kanji(char):
    return bool(_KANJI_RE.match(char))


def _ruby(word, reading):
    pieces = reading.split("|")
    if len(pieces) == len(word):
        return "".join("[%s(%s)]" % (char, piece) for char, piece in zip(word, pieces))
    return "[%s(%s)]" % (word, reading.replace("|", ""))


def _segment(run, previous_char):
    """把一串汉字按词表切开并注音。"""
    out = []
    index = 0
    while index < len(run):
        for size in range(min(_MAX_WORD, len(run) - index), 1, -1):
            word = run[index : index + size]
            if word in WORDS:
                out.append(_ruby(word, WORDS[word]))
                index += size
                break
        else:
            char = run[index]
            reading = None
            if index > 0 or _is_katakana(previous_char):
                reading = _SUFFIX.get(char)
            if reading is None:
                reading = SINGLE.get(char)
            out.append("[%s(%s)]" % (char, reading) if reading else char)
            index += 1
    return "".join(out)


def _is_katakana(char):
    return bool(char) and ("゠" <= char <= "ヿ" or char in "ＥＸＰＬＶ")


def _to_hiragana(text):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def name_ruby(name, reading):
    """卡名 + 整体读音 -> 带注音标记的卡名。"""
    if not reading or not _KANJI_RE.search(name):
        return name
    parts = re.findall(r"[㐀-鿿豈-﫿々]+|[^㐀-鿿豈-﫿々]+", name)
    pattern = ""
    for part in parts:
        if _is_kanji(part[0]):
            pattern += "(.+?)"
        else:
            pattern += re.escape(_to_hiragana(part).replace("・", "")).replace("\\ ", "\\s*")
    match = re.fullmatch(pattern, _to_hiragana(reading).replace("・", ""))
    if match:
        out = []
        groups = iter(match.groups())
        hira = _to_hiragana(reading).replace("・", "")
        for part in parts:
            if _is_kanji(part[0]):
                group = next(groups)
                # 读音按原文的假名种类输出
                start = hira.find(group)
                plain = reading.replace("・", "")
                out.append("[%s(%s)]" % (part, plain[start : start + len(group)] if start >= 0 else group))
            else:
                out.append(part)
        return "".join(out)
    return "[%s(%s)]" % (name, reading)


def add_furigana(text, names=(), name_reading=None):
    """给日文文本加注音。已有注音标记的部分保持不变。

    names: 需要按卡名处理的名字（例如本卡卡名）；
    name_reading: 卡名 -> 读音 的查询函数（离线卡库的 jp_ruby）。
    """
    if not text:
        return text
    name_reading = name_reading or (lambda _name: None)
    protected = []

    def keep(fragment):
        protected.append(fragment)
        return "\x00%d\x00" % (len(protected) - 1)

    # 已有的注音标记原样保留
    work = _RUBY_RE.sub(lambda m: keep(m.group(0)), text)

    # 「卡名」与本卡卡名优先用卡名读音
    def quoted(match):
        inner = match.group(1)
        reading = name_reading(inner)
        if reading:
            return "「" + keep(name_ruby(inner, reading)) + "」"
        return match.group(0)

    work = re.sub(r"「([^「」\x00]+)」", quoted, work)
    for name in names:
        if name and name in work:
            reading = name_reading(name)
            if reading:
                work = work.replace(name, keep(name_ruby(name, reading)))

    out = []
    position = 0
    for match in _KANJI_RE.finditer(work):
        out.append(work[position : match.start()])
        previous = work[match.start() - 1] if match.start() > 0 else ""
        out.append(_segment(match.group(0), previous))
        position = match.end()
    out.append(work[position:])
    result = "".join(out)
    return re.sub("\x00(\\d+)\x00", lambda m: protected[int(m.group(1))], result)
