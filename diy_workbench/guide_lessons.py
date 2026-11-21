"""分节阅读本机教程，按标题和正文找章节，图和文字一起离线加载。"""
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from .guide_art import GuideReader


def chapters(path):
    source = path.read_text(encoding="utf-8").removeprefix("## ")
    return [(title, body.strip(), path.parent) for section in source.split("\n## ")
            for title, _, body in [section.partition("\n")]]


class LessonPage(QWidget):
    def __init__(self, lessons):
        super().__init__()
        self.lessons = lessons
        layout = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setAccessibleName("搜索课程标题或正文")
        self.query.setPlaceholderText("查本栏课程，例如 输入「代价」或「连锁」")
        self.query.setClearButtonEnabled(True)
        layout.addWidget(self.query)
        nav = QHBoxLayout()
        nav.addWidget(QLabel("章节"))
        self.chapters = QComboBox()
        self.chapters.setAccessibleName("选择章节")
        self.chapters.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.chapters.setMinimumContentsLength(9)
        nav.addWidget(self.chapters, 1)
        layout.addLayout(nav)
        self.reader = GuideReader()
        self.reader.setAccessibleName("课程正文与配图")
        layout.addWidget(self.reader, 1)
        bottom = QHBoxLayout()
        self.previous, self.next_button = QPushButton("上一节"), QPushButton("下一节")
        self.previous.clicked.connect(lambda: self.chapters.setCurrentIndex(self.chapters.currentIndex()-1))
        self.next_button.clicked.connect(lambda: self.chapters.setCurrentIndex(self.chapters.currentIndex()+1))
        bottom.addWidget(self.previous)
        bottom.addWidget(self.next_button)
        self.picture = QPushButton("查看配图原图")
        self.picture.clicked.connect(self.reader.show_original)
        bottom.addWidget(self.picture)
        bottom.addStretch()
        layout.addLayout(bottom)
        self.chapters.currentIndexChanged.connect(self._display)
        self.query.textChanged.connect(self._find)
        self._find("")

    def _find(self, text):
        words = text.casefold().split()
        old = self.chapters.currentData()
        self.chapters.blockSignals(True)
        self.chapters.clear()
        for i, (title, body, _) in enumerate(self.lessons):
            if all(w in (title+" "+body).casefold() for w in words):
                self.chapters.addItem(f"{i+1}. {title}", i)
        if old is not None and self.chapters.findData(old) >= 0:
            self.chapters.setCurrentIndex(self.chapters.findData(old))
        self.chapters.blockSignals(False)
        self._display(self.chapters.currentIndex())

    def _display(self, index):
        self.previous.setEnabled(index > 0)
        self.next_button.setEnabled(0 <= index < self.chapters.count()-1)
        if index < 0:
            self.reader.lesson("没有找到这一项。清空输入可以恢复目录，也可换一个更短的词，例如「召唤」。", self.lessons[0][2])
        else:
            _, body, folder = self.lessons[self.chapters.itemData(index)]
            self.reader.lesson(body, folder)
        self.picture.setVisible(bool(self.reader.images))
