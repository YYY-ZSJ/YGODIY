"""按卡包清单导出 ygopro 扩展包（.ypk）。

卡包清单（JSON）：

    {
      "name": "星光",                       // 包名，也决定文件名 ygodiy-星光.ypk
      "id": "ygodiy-star",                  // 可省略：包内文件名用的 ASCII 名字，默认按包名或第一张卡的卡号
      "author": "某人",
      "ot": 3,                              // 可省略：1 OCG / 2 TCG / 3 两边都能用（默认）
      "setnames": {"0xa01": "星光"},        // 自己的字段，写进 strings.conf
      "cards": [
        {"code": 100001000,                 // 可省略：用卡面的卡号，不能用时报错
         "card": "cards/星光探索者.json",    // YGODIY「导出数据」的 JSON（或标签页里的卡片数据）
         "effect": "effects/星光探索者.json",// Effect Model；通常怪兽可以不写
         "setcodes": ["0xa01"],             // 这张卡属于哪些字段（可写字段名）
         "art": "art/星光探索者.png"}        // 可省略：默认用卡片数据里的卡图
      ]
    }

清单里的相对路径相对清单文件所在的目录。

包内结构（与萌卡超先行卡包相同；包内文件名全用 ASCII）：
    <id>.cdb                      卡片资料与效果提示文字（str1..str16）
    <id>-strings.conf             字段名（标准写法）
    <id>-mdpro3.conf              字段名（MDPro3 兼容写法，见 MDPRO3_COMPAT）
    script/c<卡号>.lua             Effect Model 生成的脚本
    art/<卡号>.jpg                 卡图原画（MDPro3 先找 art/，找不到才从 pics/ 的整张卡面里裁）
    corres_srv.ini                包名、作者

MDPro3 把所有扩展包里的文件放进同一张表、按包内路径索引，同名文件只有一个能被看到，
所以 cdb 与 conf 的文件名都带上这个包自己的 id，不用通行的「strings.conf」。
"""

# MDPro3（2026-09 的版本）读扩展字段名时用 ResourceManager.GetTextsByExtensions(".conf", 排除 "lflist")，
# 但排除条件写反了，而且检查的是文件内容：结果只收「内容里含 lflist」的 conf，任何扩展包的字段名都读不进来。
# 兼容版 conf 带一行含这个词的注释；MDPro3 修好以后（无论按内容还是按文件名排除）标准版照常生效，
# 两份都被读到时同一个字段编号只认第一个，不冲突。文件名不能以 lflist.conf 结尾，否则会被当成禁限卡表。
MDPRO3_COMPAT = ("# MDPro3 兼容：MDPro3 读扩展字段名时只收内容里含「lflist」这个词的 conf（读取条件写反了），"
                 "所以这份字段名多写这一行注释。这不是禁限卡表。")

import io
import json
import os
import re
import zipfile

from . import cardinfo, cdb

STRINGID_LIMIT = 0xFFFFFFFF // 16     # aux.Stringid(id, n) = id*16+n 要放得进 32 位


class PackError(Exception):
    pass


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, card, text):
        self.items.append((level, card, text))

    def error(self, card, text):
        self.add("错误", card, text)

    def warn(self, card, text):
        self.add("提示", card, text)

    @property
    def ok(self):
        return not any(level == "错误" for level, _, _ in self.items)

    def lines(self):
        return ["[%s] %s%s" % (level, (card + "：") if card else "", text) for level, card, text in self.items]


def _load_json(value, base):
    if isinstance(value, dict):
        return value, base
    path = os.path.join(base, value)
    with open(path, encoding="utf-8") as f:
        return json.load(f), os.path.dirname(path)


def _hex(value, setnames):
    if isinstance(value, int):
        return value
    for code, name in setnames.items():
        if value == name:
            return int(code, 16)
    return int(value, 16)


def slug(name):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_")
    return s or "pack"


def pack_id(manifest, codes):
    """包内文件名用的 ASCII 名字：清单里的 id → 包名本身是 ASCII 时用包名 → ygodiy-<最小卡号>。"""
    given = manifest.get("id")
    if given:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", given):
            raise PackError("id 只能用英文字母、数字和 . _ -：%r" % given)
        return given
    name = slug(manifest.get("name") or "")
    if re.fullmatch(r"[A-Za-z0-9._-]+", name):
        return "ygodiy-" + name
    return "ygodiy-%d" % min(codes) if codes else "ygodiy-pack"


def stringids_used(lua):
    return sorted({int(n) for n in re.findall(r"aux\.Stringid\(id,(\d+)\)", lua)})


def limit_codes(code, lua):
    """脚本用到的「1回合1次」计数代码与 flag 代码（id、id+o、id+o*k）。"""
    o = 1 if code < 100000000 else 100
    out = set()
    for m in re.finditer(r"\bid(?:\+o(?:\*(\d+))?)?(?=[,)+])", lua):
        k = int(m.group(1)) if m.group(1) else (1 if "+o" in m.group(0) else 0)
        out.add(code + o * k)
    return out


def build(manifest_path, out_dir=None, assets_dir=None, known_codes=None):
    """导出卡包。返回 (ypk 路径, Report)。有错误时不写文件，路径为 None。

    assets_dir：卡片数据用 _image_ref 引用卡图时，到哪里找图（YGODIY 的「制卡器标签页资源」）。
    known_codes：已经存在的卡号（官方卡、别的扩展包）→ 来源说明，用来查冲突。
    """
    manifest, base = _load_json(os.path.abspath(manifest_path), "")
    out_dir = out_dir or os.path.dirname(os.path.abspath(manifest_path))
    return build_manifest(manifest, base, out_dir, assets_dir, known_codes)


MEDIA = {"closeup": (".png",), "overframe": (".png", ".jpg"), "art2": (".png",), "video": (".mp4",)}


def merge_strings(generated, custom):
    """玩家填的提示文本替换同一格；str1 对应 aux.Stringid(id,0)。"""
    result = list(generated) + [""] * (16 - len(generated))
    for index, text in (custom or {}).items():
        result[int(index)] = text
    while result and not result[-1]:
        result.pop()
    return result


def _media_files(entry, code, label, assets_dir, base, report):
    """MDPro3 按卡号读这些目录（Data/FileGroups.json）：closeup/ overframe/ art2/ video/。"""
    result = []
    for kind, name in (entry.get("media") or {}).items():
        path = os.path.join(assets_dir or base, name)
        ext = os.path.splitext(name)[1].lower()
        folder = "video" if kind == "video" else kind
        if ext not in MEDIA.get(kind, ()):
            report.error(label, "资源 %s 的格式不对：%s" % (kind, name))
        elif not os.path.exists(path):
            report.warn(label, "找不到资源文件，没有放进卡包：%s" % name)
        else:
            result.append((path, "%s/%d%s" % (folder, code, ext)))
    return result


def build_manifest(manifest, base, out_dir, assets_dir=None, known_codes=None):
    """同 build，但清单是内存里的 dict（制卡器的 DIY 工作台用）。base 是清单里相对路径的起点。"""
    from blocks import build as build_blocks, is_blocks, type_bits     # v0.3 积木树（工作台存的）
    from effect_model import build as build_effect
    report = Report()
    name = manifest.get("name") or "DIY"
    setnames = {k.lower(): v for k, v in (manifest.get("setnames") or {}).items()}
    ot = int(manifest.get("ot", 3))
    records, scripts, arts, media = [], {}, {}, []
    for i, entry in enumerate(manifest.get("cards", [])):
        label = "第%d张" % (i + 1)
        try:
            data, card_base = _load_json(entry["card"], base)
            model = None
            if entry.get("effect"):
                model, _ = _load_json(entry["effect"], base)
            has_effects = bool(model and model.get("effects")) or bool(entry.get("script"))
            rec, notes = cardinfo.from_ygodiy(data, has_effects=has_effects)
        except (cardinfo.CardDataError, OSError, ValueError, KeyError) as ex:
            report.error(label, str(ex))
            continue
        label = rec["name"]
        for n in notes:
            report.warn(label, n)
        code = entry.get("code") or str(data.get("cardpass") or "").strip()
        if not str(code).isdigit() or int(code) <= 0:
            report.error(label, "没有卡号：清单里写 code，或在卡面上填卡号")
            continue
        rec["code"] = code = int(code)
        rec["ot"] = ot
        rec["type"] |= type_bits(model)       # 积木的「不能通常召唤」写进 cdb 的 type
        if code > STRINGID_LIMIT:
            report.error(label, "卡号 %d 太大，效果提示文字（aux.Stringid）会溢出；请用 %d 以下的卡号" % (code, STRINGID_LIMIT))
        if known_codes and code in known_codes:
            report.error(label, "卡号 %d 已被 %s 使用" % (code, known_codes[code]))
        try:
            rec["setcodes"] = [_hex(s, setnames) for s in entry.get("setcodes", [])]
        except ValueError as ex:
            report.error(label, "字段写法不对：%s" % ex)
            rec["setcodes"] = []
        for sc in rec["setcodes"]:
            if "0x%x" % (sc & 0xfff) not in setnames:
                report.warn(label, "字段 0x%x 没有在 setnames 里起名字（官方字段可以忽略这条）" % sc)
        desc, pdesc = rec["desc"], rec.get("pdesc", "")
        if model:
            model = dict(model)
            old = model.get("card") or {}
            model["card"] = cardinfo.model_card(rec)
            if old.get("kind") and old["kind"] != model["card"]["kind"]:
                report.warn(label, "Effect Model 里写的卡种是 %s，卡片数据是 %s，以卡片数据为准" % (old["kind"], model["card"]["kind"]))
            model.setdefault("schema", "ygodiy-effect/0.1")
            try:
                result = build_blocks(model) if is_blocks(model) else build_effect(model)
            except Exception as ex:   # 生成器不认识的写法：整张卡导不出来，但不影响别的卡
                report.error(label, "生成脚本失败：%s" % ex)
                continue
            for level, where, msg in result["issues"]:
                (report.error if level == "error" else report.warn)(label, "%s %s" % (where, msg))
            if desc and desc.replace("\r", "") != result["desc"]:
                report.warn(label, "卡面上的效果文字和 Effect Model 生成的规范文本不同，卡包里用生成的（与脚本一致）")
            desc, pdesc = result["desc"], result["pdesc"]
            scripts[code] = result["lua"]
            rec["strings"] = merge_strings(result["strings"], entry.get("strings"))
            for n in stringids_used(result["lua"]):
                if n >= 16 or n >= len(rec["strings"]) or not rec["strings"][n]:
                    report.error(label, "脚本用到 aux.Stringid(id,%d)，但没有对应的提示文字" % n)
        elif not entry.get("script") and (rec["type"] & cardinfo.TYPE_EFFECT or not rec["type"] & cardinfo.TYPE_MONSTER):
            report.warn(label, "没有 Effect Model：这张卡在对局里没有效果")
        if entry.get("script"):             # 手写脚本优先于积木生成的
            from blocks.lua_guard import problems
            for text in problems(entry["script"]):
                report.error(label, "手写脚本：" + text)
            scripts[code] = entry["script"]
            rec["strings"] = merge_strings(rec.get("strings") or [], entry.get("strings"))
            for n in stringids_used(entry["script"]):
                if n >= 16 or n >= len(rec["strings"]) or not rec["strings"][n]:
                    report.error(label, "脚本用到 aux.Stringid(id,%d)，但没有对应的提示文字" % n)
        rec["cdb_desc"] = cardinfo.ygopro_desc(rec, desc, pdesc)
        image = None
        if entry.get("art"):
            with open(os.path.join(base, entry["art"]), "rb") as f:
                image = f.read()
        else:
            image = cardinfo.card_image_bytes(data, assets_dir)
        if image:
            arts[code] = _to_jpg(image)
        else:
            report.warn(label, "没有卡图")
        media += _media_files(entry, code, label, assets_dir, base, report)
        if not model and entry.get("strings"):
            rec["strings"] = merge_strings([], entry["strings"])
        rec["category"] = int(entry.get("category", 0))
        if entry.get("alias"):
            rec["alias"] = int(entry["alias"])
        records.append(rec)
        for token in cardinfo.token_records(model, code, ot):      # DIY 衍生物：卡号接在这张卡后面
            if known_codes and token["code"] in known_codes:
                report.error(label, "衍生物「%s」的卡号 %d 已被 %s 使用" % (token["name"], token["code"],
                                                                     known_codes[token["code"]]))
            records.append(token)

    _check_collisions(records, scripts, report)
    if not report.ok:
        return None, report

    stem = "ygodiy-" + slug(name)
    try:
        inner = pack_id(manifest, [r["code"] for r in records])
    except PackError as ex:
        report.error(None, str(ex))
        return None, report
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, stem + ".ypk")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        cdb_path = os.path.join(tmp, inner + ".cdb")
        cdb.write(cdb_path, records)
        tmp_out = out + ".tmp"
        with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(cdb_path, inner + ".cdb")
            names = ["!setname %s %s" % (k, v) for k, v in setnames.items()]
            head = "#YGODIY 导出：%s" % name
            z.writestr(inner + "-strings.conf", "\n".join([head] + names) + "\n")
            if names:
                z.writestr(inner + "-mdpro3.conf", "\n".join([head, MDPRO3_COMPAT] + names) + "\n")
            for code, lua in sorted(scripts.items()):
                z.writestr("script/c%d.lua" % code, lua)
            for code, jpg in sorted(arts.items()):
                z.writestr("art/%d.jpg" % code, jpg)
            for path, inner_path in media:
                z.write(path, inner_path)
            z.writestr("corres_srv.ini", "[YGOProExpansionPack]\nFileName = %s.ypk\nPackName = %s\nPackAuthor = %s\n"
                       % (stem, name, manifest.get("author", "")))
        os.replace(tmp_out, out)
    return out, report


def mark_unverified(path, reasons):
    """玩家强制导出时在卡包里留下记录；文件名带卡包名，避免 MDPro3 里全局撞名。"""
    stem = os.path.splitext(os.path.basename(path))[0]
    with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ygodiy-verify/%s-unverified.txt" % stem, "未通过验证\n" + "\n".join(reasons) + "\n")


def _check_collisions(records, scripts, report):
    owner = {}
    for rec in records:
        if rec["code"] in owner:
            report.error(rec["name"], "卡号 %d 和「%s」重复" % (rec["code"], owner[rec["code"]]))
        owner[rec["code"]] = rec["name"]
    used = {}
    for rec in records:
        if rec["type"] & cardinfo.TYPE_TOKEN:      # 衍生物没有脚本，卡号和计数代码重了也不会共用次数
            continue
        codes = limit_codes(rec["code"], scripts[rec["code"]]) if rec["code"] in scripts else {rec["code"]}
        for c in codes:
            if c in used and used[c] != rec["name"]:
                report.warn(rec["name"], "「1回合1次」的计数代码 %d 和「%s」撞车，两张卡会共用次数；把卡号拉开 %d 以上" % (
                    c, used[c], 100 if rec["code"] >= 100000000 else 10))
            used[c] = rec["name"]


def _to_jpg(png_bytes):
    from PIL import Image
    img = Image.open(io.BytesIO(png_bytes))
    if img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.convert("RGBA").split()[-1])
        img = bg
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=92)
    return buf.getvalue()


def known_setcodes(expansions, skip_file=None):
    """扩展目录里别的卡包已经用掉的字段：{编号(小写十六进制): (字段名或空, 来源)}。
    名字读 conf 里的「!setname」；没起名字、但卡片已经用上的编号（cdb 的 setcode）也算占用。"""
    import tempfile
    from . import sqlite
    out = {}

    def from_conf(text, source):
        for line in text.splitlines():
            if line.startswith("!setname "):
                code, _, name = line[len("!setname "):].strip().partition(" ")
                try:
                    key = "0x%x" % int(code, 16)
                except ValueError:
                    continue
                if not out.get(key, ("",))[0]:                # 有名字的优先
                    out[key] = (name.split("\t")[0].strip(), source)

    def from_cdb(path, source):
        try:
            con = sqlite.connect(path, readonly=True)
            for (sc,) in con.query("select setcode from datas"):
                sc = int(sc or 0)
                while sc:
                    part = sc & 0xffff
                    if part:
                        out.setdefault("0x%x" % part, ("", source))
                    sc >>= 16
            con.close()
        except Exception:
            pass

    if not expansions or not os.path.isdir(expansions):
        return out
    for f in sorted(os.listdir(expansions)):
        path = os.path.join(expansions, f)
        if skip_file and os.path.normcase(f) == os.path.normcase(skip_file):
            continue
        low = f.lower()
        if low.endswith(".conf"):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    from_conf(fh.read(), "扩展 " + f)
            except OSError:
                pass
        elif low.endswith(".cdb"):
            from_cdb(path, "扩展 " + f)
        elif low.endswith((".ypk", ".zip")):
            try:
                with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory() as tmp:
                    for e in z.namelist():
                        if e.lower().endswith(".conf"):
                            from_conf(z.read(e).decode("utf-8", "replace"), "扩展 " + f)
                        elif e.lower().endswith(".cdb"):
                            from_cdb(z.extract(e, tmp), "扩展 " + f)
            except (zipfile.BadZipFile, OSError):
                pass
    return out


def known_codes(mdpro3_dir, skip_file=None, expansions=None):
    """MDPro3 里已有的卡号：官方卡库 + 扩展目录里的其他扩展。skip_file 是要被替换的旧版本卡包。
    expansions：卡包要装进的扩展目录（用户自定义了 DIY 路径时就是那个目录），默认 MDPro3 自带的 Expansions。"""
    import tempfile
    from . import sqlite
    out = {}

    def read(path, source):
        try:
            con = sqlite.connect(path, readonly=True)
            for (code,) in con.query("select id from datas"):
                out.setdefault(code, source)
            con.close()
        except Exception:
            pass

    if mdpro3_dir:
        read(os.path.join(mdpro3_dir, "Data", "locales", "zh-CN", "cards.cdb"), "官方卡")
    exp = expansions or (os.path.join(mdpro3_dir, "Expansions") if mdpro3_dir else None)
    if exp and os.path.isdir(exp):
        for f in sorted(os.listdir(exp)):
            path = os.path.join(exp, f)
            if skip_file and os.path.normcase(f) == os.path.normcase(skip_file):
                continue
            if f.lower().endswith(".cdb"):
                read(path, "扩展 " + f)
            elif f.lower().endswith((".ypk", ".zip")):
                try:
                    with zipfile.ZipFile(path) as z, tempfile.TemporaryDirectory() as tmp:
                        for e in z.namelist():
                            if e.lower().endswith(".cdb"):
                                read(z.extract(e, tmp), "扩展 " + f)
                except (zipfile.BadZipFile, OSError):
                    pass
    return out
