"""MDPro3 专用的卡片资源：立绘、超框卡图、动态卡图和同名卡。文件复制进标签页资源目录，卡片里只存文件名。"""

import os
import shutil

from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout, QWidget)

KINDS = (("closeup", "怪兽立绘", "PNG 图片 (*.png)", "决斗时怪兽上方的立绘"),
         ("overframe", "超框卡图", "图片 (*.png *.jpg)", "png 是透明卡图，jpg 是完整超框卡图"),
         ("art2", "框内卡图", "PNG 图片 (*.png)", "超框卡的框内插画"),
         ("video", "动态卡图", "MP4 视频 (*.mp4)", "再次导入同一卡号的新视频前，要先删掉 MDPro3 的 Video/Art 里的旧文件"))
MEDIA_FOLDER = "mdpro3"


class MediaDialog(QDialog):
    def __init__(self, tab, assets, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MDPro3 资源")
        self.tab, self.assets = tab, assets
        diy = tab.setdefault("diy", {})
        self.media = dict(diy.get("media") or {})
        self.labels = {}
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for kind, label, pattern, note in KINDS:
            row = QHBoxLayout()
            self.labels[kind] = QLabel()
            self.labels[kind].setToolTip(note)
            choose, clear = QPushButton("选择…"), QPushButton("清除")
            choose.clicked.connect(lambda _, k=kind, p=pattern: self._choose(k, p))
            clear.clicked.connect(lambda _, k=kind: self._clear(k))
            row.addWidget(self.labels[kind], 1)
            row.addWidget(choose)
            row.addWidget(clear)
            holder = QWidget()
            holder.setLayout(row)
            form.addRow(label, holder)
        self.alias = QLineEdit(str(diy.get("alias") or ""))
        self.alias.setValidator(QIntValidator(0, 999999999, self))
        self.alias.setPlaceholderText("不是同名卡就留空")
        self.alias.setToolTip("这张卡在规则上当作哪张卡")
        form.addRow("同名卡的原卡卡号", self.alias)
        self.alias_name = QLineEdit(diy.get("alias_name", ""))
        self.alias_name.setPlaceholderText("写进效果文字，例如：鹰身女郎")
        form.addRow("原卡卡名", self.alias_name)
        self.alias_mode = QComboBox()
        self.alias_mode.addItem("规则上同名，效果不同（用这张卡自己的积木和脚本）", "rule")
        self.alias_mode.addItem("异画，效果完全相同（读原卡脚本，这张卡的积木不导出）", "art")
        self.alias_mode.setCurrentIndex(max(0, self.alias_mode.findData(diy.get("alias_mode", "rule"))))
        form.addRow("同名方式", self.alias_mode)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def _refresh(self):
        for kind, label in self.labels.items():
            label.setText(self.media.get(kind) or "（未设置）")

    def _choose(self, kind, pattern):
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", pattern)
        if path:
            self.media[kind] = store_media(path, self.assets, self.tab.get("_card_uid") or "card", kind)
            self._refresh()

    def _clear(self, kind):
        self.media.pop(kind, None)
        self._refresh()

    def accept(self):
        diy = self.tab.setdefault("diy", {})
        diy["media"] = self.media
        alias = int(self.alias.text() or 0)
        if alias:
            diy.update(alias=alias, alias_name=self.alias_name.text().strip(), alias_mode=self.alias_mode.currentData())
        else:
            for key in ("alias", "alias_name", "alias_mode"):
                diy.pop(key, None)
        super().accept()


def store_media(path, assets, uid, kind):
    """复制进资源目录，返回相对路径；换了文件也不影响已经复制的那份。"""
    name = "%s-%s%s" % (uid, kind, os.path.splitext(path)[1].lower())
    folder = os.path.join(assets, MEDIA_FOLDER)
    os.makedirs(folder, exist_ok=True)
    shutil.copyfile(path, os.path.join(folder, name))
    return MEDIA_FOLDER + "/" + name
