"""顶部「积木入门」模式，课程、图鉴与练习桌共用一个页面。"""
from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QTabWidget, QVBoxLayout, QWidget

from .guide_catalog import CatalogPage, FOLDER
from .guide_lessons import LessonPage, chapters


class BlockGuide(QWidget):
    return_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        basics = chapters(Path(__file__).with_name("积木编程入门.md"))
        coaching = chapters(FOLDER / "编程与排错.md")
        rules = [chapter for name in ("规则-基础", "规则-召唤", "规则-判定")
                 for chapter in chapters(FOLDER / (name + ".md"))]
        self.lessons = LessonPage([coaching[0], *basics[:2], *coaching[1:3], *basics[2:], *coaching[3:]])
        self.rules = LessonPage(rules)
        self.catalog = CatalogPage()
        self.tabs.addTab(self.lessons, "入门练习")
        self.tabs.addTab(self.rules, "决斗规则")
        self.tabs.addTab(self.catalog, "积木图鉴")
        self.practice_host = QWidget()
        self.practice_layout = QVBoxLayout(self.practice_host)
        self.practice_layout.setContentsMargins(0, 0, 0, 0)
        self.practice = None
        self.tabs.addTab(self.practice_host, "练习桌")
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)
        bar = QHBoxLayout()
        bar.addStretch()
        back = QPushButton("返回 DIY 工作台")
        back.clicked.connect(self.return_requested.emit)
        bar.addWidget(back)
        layout.addLayout(bar)

    def _tab_changed(self, _):
        if self.tabs.currentWidget() is self.practice_host and self.practice is None:
            from .guide_practice import PracticePage
            self.practice = PracticePage()
            self.practice_layout.addWidget(self.practice)

    def show_block(self, key):
        self.tabs.setCurrentWidget(self.catalog)
        self.catalog.show_block(key)
