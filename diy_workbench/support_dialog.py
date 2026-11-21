"""模式下拉最后一项「支持作者」：弹出窗口，不是一个模式，选它不切换模式。"""

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

LABEL = "支持作者"
LINKS = (("GitHub 项目", "https://github.com/YYY-ZSJ/YGODIY"),
         ("爱发电", "https://afdian.com/a/yyyzsj"),
         ("QQ群", "https://qm.qq.com/q/DizNf9MKIM"),
         ("B站", "https://b23.tv/mHcFxl5"),
         ("小红书", "https://xhslink.cn/o/7FEbH6Atabf"),
         ("贴吧", "https://tieba.baidu.com/home/main?id=tb.1.65fbb898.75snxi1ZsyqXl_rdFIe5Kw&fr=personalize_page"))


class SupportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(LABEL)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(10)
        note = QLabel("感谢使用 YGODIY！点击下面的按钮，在浏览器里打开。")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.buttons = []
        for name, url in LINKS:
            button = QPushButton(name)
            button.setMinimumHeight(36)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(url)
            button.clicked.connect(lambda _, link=url: QDesktopServices.openUrl(QUrl(link)))
            self.buttons.append(button)
            layout.addWidget(button)


def install(app):
    app._support_index = app.combo_box.count()
    app.combo_box.addItem(LABEL)


def open_from_combo(app):
    """下拉框退回当前模式再弹窗：这里不发信号，其他模式的切换逻辑都不会运行。"""
    app.combo_box.blockSignals(True)
    app.combo_box.setCurrentIndex(app.current_mode)
    app.combo_box.blockSignals(False)
    SupportDialog(app).exec_()
