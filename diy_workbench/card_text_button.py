"""顶栏的「复制文字」：OCG、RD 模式用，点击复制当前卡的文字，下拉导出 txt。只读编辑器，不改卡片数据。"""

import re

from PyQt5.QtWidgets import QApplication, QFileDialog, QMenu, QMessageBox, QToolButton, QToolTip

from diy_workbench.ai import card_context
from . import card_text

TEXT_MODES = ("ocg", "rd")


class CardTextButton(QToolButton):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setText("复制文字")
        self.setToolTip("复制当前卡片的文字信息")
        self.setPopupMode(QToolButton.MenuButtonPopup)
        menu = QMenu(self)
        menu.addAction("导出 txt…", self.export)
        self.setMenu(menu)
        self.clicked.connect(self.copy)
        app.combo_box.currentIndexChanged.connect(self.refresh)
        self.refresh(app.combo_box.currentIndex())

    def refresh(self, index):
        self.setVisible(any(row["index"] == index and row["id"] in TEXT_MODES for row in card_context.modes(self.app)))

    def text_now(self):
        fields = card_context.snapshot(self.app)["fields"]
        return card_text.editor_text(fields) if fields else ""

    def copy(self):
        text = self.text_now()
        if text:
            QApplication.clipboard().setText(text)
        QToolTip.showText(self.mapToGlobal(self.rect().bottomLeft()), "已复制" if text else "现在没有卡片", self)

    def export(self):
        text = self.text_now()
        if not text:
            return
        name = re.sub(r'[\\/:*?"<>|]', "_", text.splitlines()[0])
        path, _ = QFileDialog.getSaveFileName(self.app, "导出卡片文字", name + ".txt", "文本文件 (*.txt)")
        if not path:
            return
        try:
            card_text.write(path, text)
        except OSError as error:
            QMessageBox.warning(self.app, "导出失败", "文件写不进去：%s" % error)
