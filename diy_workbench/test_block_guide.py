"""教学资料与实际编辑器的一致性，使用发行版已有的 Python、PyQt5 和 unittest。"""
import re
import unittest

from blocks import SCHEMA, build
from blocks.catalog import BLOCKS
from .guide_catalog import FOLDER, article, read_notes, slot_options
from .guide_practice import exercises


class BlockGuideTest(unittest.TestCase):
    def test_every_block_has_a_lesson_and_usable_slot_links(self):
        notes = read_notes()
        self.assertEqual(set(notes), set(BLOCKS))
        for key, block in BLOCKS.items():
            with self.subTest(block=key):
                self.assertTrue(all(notes[key]))
                self.assertIn(block.label, article(key, notes, expanded=True))
                for i, (_, _, kind, _, only) in enumerate(block.slots):
                    compatible = slot_options(block, i)
                    self.assertTrue(compatible)
                    self.assertTrue(all(BLOCKS[item].kind == kind for item in compatible))
                    if only:
                        self.assertEqual(set(compatible), set(only))

    def test_course_illustrations_are_shipped(self):
        lessons = [FOLDER.parent / "积木编程入门.md", *FOLDER.glob("*.md")]
        for lesson in lessons:
            for image in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", lesson.read_text(encoding="utf-8")):
                with self.subTest(lesson=lesson.name, image=image):
                    self.assertTrue((lesson.parent / image).is_file())

    def test_practice_solutions_compile(self):
        for title, kind, _, effect in exercises():
            with self.subTest(practice=title):
                data = {"code": 100098100, "name": title, "kind": kind}
                result = build({"schema": SCHEMA, "card": data, "effects": [effect]})
                self.assertEqual(result["issues"], [])
                self.assertTrue(result["lua"])


if __name__ == "__main__":
    unittest.main()
