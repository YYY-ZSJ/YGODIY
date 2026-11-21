"""独立手册中的本地插图和按当前积木定义绘制的槽图。"""
from PyQt5.QtCore import QRect, QRectF, Qt, QUrl
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap, QTextCursor, QTextDocument
from PyQt5.QtWidgets import QDialog, QLabel, QPushButton, QScrollArea, QTextBrowser, QVBoxLayout

from .block_editor import KIND_STYLE


def block_picture(block, font):
    names = [("槽", s[1].split("（")[0], KIND_STYLE[s[2]][3]) for s in block.slots]
    if not names:
        names = [("选项", f[1].split("（")[0], "#31536f") for f in block.fields]
    if not names:
        placement = "放在中栏最外层" if block.kind == "hat" else "放入接受这种积木的槽"
        names = [("使用", placement, "#31536f")]
    width, height = 570, 62 + len(names) * 32
    result = QImage(width * 2, height * 2, QImage.Format_ARGB32_Premultiplied)
    result.setDevicePixelRatio(2)
    result.fill(QColor("#f5f8fa"))
    p = QPainter(result)
    p.setRenderHint(QPainter.Antialiasing)
    textfont = QFont(font)
    textfont.setPixelSize(16)
    p.setFont(textfont)
    _, bg, fg, marker = KIND_STYLE[block.kind]
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(bg))
    p.drawRoundedRect(QRectF(12, 8, width-24, 36), 5, 5)
    p.setBrush(QColor(marker))
    p.drawRoundedRect(QRectF(24, 19, 13, 13), 3, 3)
    p.setPen(QColor(fg))
    p.drawText(QRect(48, 8, width-67, 36), Qt.AlignVCenter, block.label)
    for i, (role, name, color) in enumerate(names):
        y = 56 + 32 * i
        p.setPen(QPen(QColor("#8999a6"), 1))
        p.drawLine(31, 43 if i == 0 else y-23, 31, y+8)
        p.drawLine(31, y+8, 50, y+8)
        p.setPen(QPen(QColor(color), 2))
        if role == "槽":
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(52, y+2, 12, 12), 2, 2)
        else:
            p.setBrush(QColor(color))
            p.drawEllipse(QRectF(55, y+5, 6, 6))
        p.setPen(QColor("#243b50"))
        line = role + "　" + name
        p.drawText(QRect(74, y-4, width-90, 27), Qt.AlignVCenter,
                   p.fontMetrics().elidedText(line, Qt.ElideRight, width-90))
    p.end()
    return result


class GuideReader(QTextBrowser):
    def __init__(self):
        super().__init__()
        self.diagram = None
        self.images = []
        self.document().setDocumentMargin(14)
        self.setOpenExternalLinks(True)

    def loadResource(self, kind, url):
        if kind == QTextDocument.ImageResource and url.scheme() == "diagram":
            return self.diagram
        return super().loadResource(kind, url)

    def lesson(self, body, folder):
        self.images = []
        self.document().setBaseUrl(QUrl.fromLocalFile(str(folder) + "/"))
        self.setMarkdown(body)
        self._collect_images()

    def entry(self, html, block):
        self.images = []
        self.diagram = block_picture(block, self.font())
        self.setHtml(html)
        self._collect_images()

    def _collect_images(self):
        doc = self.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                f = it.fragment()
                if f.charFormat().isImageFormat():
                    fmt = f.charFormat().toImageFormat()
                    url = doc.baseUrl().resolved(QUrl(fmt.name()))
                    pic = doc.resource(QTextDocument.ImageResource, url)
                    if hasattr(pic, "width") and pic.width() and pic.height():
                        self.images.append((f.position(), pic))
                it += 1
            block = block.next()
        self._fit_images()
        self.verticalScrollBar().setValue(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_images()

    def _fit_images(self):
        room = max(1, self.viewport().width()-2*self.document().documentMargin()-8)
        for pos, pic in self.images:
            cursor = QTextCursor(self.document())
            cursor.setPosition(pos)
            cursor.setPosition(pos+1, QTextCursor.KeepAnchor)
            fmt = cursor.charFormat().toImageFormat()
            shown = min(pic.width()/pic.devicePixelRatio(), room)
            if fmt.width() != shown:
                fmt.setWidth(shown)
                fmt.setHeight(shown*pic.height()/pic.width())
                cursor.setCharFormat(fmt)

    def show_original(self):
        if not self.images:
            return
        pic = self.images[0][1]
        pixmap = pic if isinstance(pic, QPixmap) else QPixmap.fromImage(pic)
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setWindowTitle("配图原图")
        layout = QVBoxLayout(dialog)
        image = QLabel()
        image.setPixmap(pixmap)
        image.adjustSize()
        scroll = QScrollArea()
        scroll.setAlignment(Qt.AlignCenter)
        scroll.setWidget(image)
        layout.addWidget(scroll, 1)
        close = QPushButton("关闭")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, 0, Qt.AlignRight)
        dialog.resize(min(image.width()+50, self.window().width()), min(image.height()+95, self.window().height()))
        dialog.exec_()
