"""验证发布用的中文读法与桌面样例一致，并阻止脚本类积木进入离线目录。"""
import json
import sys
import unittest
from pathlib import Path

ANDROID = Path(__file__).resolve().parents[1]
ROOT = ANDROID.parent
sys.path[:0] = [str(ANDROID / "build/assets"), str(ROOT)]
from blocks import read
from blocks.catalog import BLOCKS
from reader import render_text


class MobileReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = json.loads((ANDROID / "build/assets/library.json").read_text("utf-8"))

    def test_catalog_and_illustrations(self):
        catalog = self.library["blocks"]
        self.assertEqual(set(catalog), {k for k in BLOCKS if not k.startswith("ls_") and k not in ("raw", "custom_effect")})
        for key, block in catalog.items():
            self.assertTrue(block["help"], key)
        for chapter in self.library["chapters"]:
            for part in chapter["body"]:
                if "image" in part:
                    self.assertTrue((ANDROID / "build/assets" / part["image"]).is_file())

    def test_desktop_examples(self):
        checked = 0
        for path in sorted((ROOT / "blocks/samples").glob("*.json")):
            model = json.loads(path.read_text("utf-8"))
            effects = model.get("effects", [])
            nodes = [node for effect in effects for node in read.walk_nodes(effect)]
            if not effects or not all(n["block"] in self.library["blocks"] for n in nodes) or model.get("summon"):
                continue
            with self.subTest(path=path.name):
                name = model.get("card", {}).get("name", "")
                result = json.loads(render_text(json.dumps([effects, name, {}])))
                self.assertEqual(result, list(read.read_full(model)))
            checked += 1
        self.assertGreater(checked, 10)


if __name__ == "__main__":
    unittest.main()
