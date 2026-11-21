"""从现有桌面资源生成移动端卡框与位置表。解密密钥仅在构建机上使用。"""
import ast
import hashlib
import io
import json
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from PIL import Image, ImageOps


def prepare(root, output):
    images = output / "frames"
    images.mkdir(exist_ok=True)
    cipher = Fernet((root / "mold/secret.key").read_bytes())

    @lru_cache(maxsize=None)
    def asset(relative):
        source = root / relative
        name = hashlib.sha256(relative.encode()).hexdigest()[:16] + ".webp"
        dest = images / name
        content = source.read_bytes()
        if source.suffix == ".enc":
            content = cipher.decrypt(content)
        with Image.open(io.BytesIO(content)) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGBA")
            image.thumbnail((1084, 1580), Image.Resampling.LANCZOS)
            image.save(dest, "WEBP", quality=85, method=4)
        return "frames/" + name

    def mapping(paths):
        return {name: asset(path) for name, path in paths.items() if (root / path).is_file()}

    def config(filename):
        return json.loads((root / "config" / filename).read_text("utf-8"))

    card, rd = config("config.json"), config("rd_config.json")
    old, field = config("past_config.json"), config("fc_config.json")
    old_styles = {}
    for i, series in enumerate(("1", "2", "3", "7", "8", "9", "10")):
        keys = ("card_x", "card_y", "card_img_size_w", "card_img_size_h", "rect_pos_monster_y", "rect_pos_mt_y", "level_y")
        old_styles[series] = {k: old[k][i] for k in keys}
        old_styles[series]["frames"] = mapping(old["base_images"][i])
    field_names = field.get("back_list", [])
    field_frames = {field_names[i] if i < len(field_names) else str(i + 1): asset(p)
                    for i, p in enumerate(field["back_imgs"])}
    attributes = {k: f"mold/attribute/cn/attribute-{v}.png" for k, v in
                  zip("光暗炎水地风神魔陷", "light dark fire water earth wind divine spell trap".split())}
    support_path = Path(__file__).resolve().parents[2] / "diy_workbench/support_dialog.py"
    support = next(ast.literal_eval(n.value) for n in ast.parse(support_path.read_text("utf-8")).body
                   if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "LINKS" for t in n.targets))
    data = dict(support=support, new=mapping(card["base_images"]), ocg=mapping(card["base_images_official"]), rd=mapping(rd["base_imgs"]),
                past=old_styles, field=field_frames, back=mapping(config("back_config.json")["type_path"]),
                attr=mapping(attributes), rdAttr=mapping(rd["attribute_imgs"]),
                star=asset("mold/star/level_hd.png"), rank=asset("mold/star/rank_hd.png"),
                demo="frames/demo.webp", races=card["race_list"])
    sample = Path(__file__).resolve().parents[1] / "sample" / "blue-eyes.jpg"
    with Image.open(sample) as picture:
        picture.thumbnail((1084, 1084), Image.Resampling.LANCZOS)
        picture.save(images / "demo.webp", "WEBP", quality=90)
    (output / "art.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")
