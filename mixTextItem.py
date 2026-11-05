import sys
from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout, QGraphicsView, QGraphicsScene, QGraphicsTextItem, \
    QGraphicsDropShadowEffect
from PyQt5.QtGui import QFont, QFontDatabase, QColor, QTextOption, QTextCursor, QPen, QTextCharFormat, \
    QLinearGradient
from PyQt5.QtCore import Qt, QObject, QSignalBlocker
import PyQt5.QtWidgets

import rd_ruby


class OutlinedGraphicsTextItem(QGraphicsTextItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.outlineFormat = QTextCharFormat()
        self.outlineFormat.setTextOutline(QPen(
            Qt.GlobalColor.red, 5,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin
        ))
        self.dummyFormat = QTextCharFormat()
        self.dummyFormat.setTextOutline(QPen(Qt.GlobalColor.transparent))

        children = self.findChildren(QObject)
        if not children:
            super().setPlainText('')
            children = self.findChildren(QObject)
        if self.toPlainText():

            self.setPlainText(self.toPlainText())

        for obj in children:
            if obj.metaObject().className() == 'QWidgetTextControl':
                self.textControl = obj
                break

    def setPlainText(self, text):
        super().setPlainText(text)
        if text:
            format = QTextCharFormat()

            cursor = QTextCursor(self.document())
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.mergeCharFormat(format)

    def paint(self, painter, option, widget):
        with QSignalBlocker(self.textControl):
            cursor = QTextCursor(self.document())
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.mergeCharFormat(self.outlineFormat)
            super().paint(painter, option, widget)
            cursor.mergeCharFormat(self.dummyFormat)
            super().paint(painter, option, widget)


class MixTextItem(QGraphicsTextItem):
    def __init__(self, text='', outline_enabled=False, outline_color=Qt.GlobalColor.black, outline_thickness: float = 2,
                 gradient_flag=False, duplicate=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setPlainText(text)
        self.document().setDocumentMargin(0)

        self.outline_enabled = outline_enabled
        self.outline_color = outline_color
        self.outline_thickness = outline_thickness
        self.outlineFormat = QTextCharFormat()
        self.updateOutlineFormat()
        self.dummyFormat = QTextCharFormat()
        self.dummyFormat.setTextOutline(QPen(Qt.GlobalColor.transparent))

        self.paint_font = QFont('Arial', 12)
        self.offset_flag = False
        self.offset_ver = 12.5

        self.single_color = Qt.black
        self.gradient_flag = gradient_flag
        self.gradient_process = [[True, 0, QColor(255, 0, 0)], [True, 0.21, QColor(255, 255, 255)],
                                 [True, 0.42, QColor(217, 217, 217)], [True, 0.52, QColor(141, 141, 141)],
                                 [True, 0.66, QColor(161, 161, 161)], [True, 1, QColor(255, 255, 255)]]
        self.gradient_edge_top = 114
        self.gradient_edge_bottom = 193

        self.duplicate = duplicate

        children = self.findChildren(QObject)
        if not children:
            super().setPlainText('')
            children = self.findChildren(QObject)
        if self.toPlainText():
            self.setPlainText(self.toPlainText())

        for obj in children:
            if obj.metaObject().className() == 'QWidgetTextControl':
                self.textControl = obj
                break

    def updateOutlineFormat(self):
        if self.outline_enabled:
            self.outlineFormat.setTextOutline(QPen(self.outline_color, self.outline_thickness,
                                                   Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        else:
            self.outlineFormat.setTextOutline(QPen(Qt.GlobalColor.transparent))

    def enableOutline(self, enabled: bool):
        self.outline_enabled = enabled
        self.updateOutlineFormat()
        self.update()

    def setOutlineStyle(self, color=None, thickness=None):
        if color is not None:
            self.outline_color = color
        if thickness is not None:
            self.outline_thickness = thickness
        self.updateOutlineFormat()
        self.update()

    def enableGradient(self, enabled: bool):
        self.gradient_flag = enabled
        self.update()

    def setSingleColor(self, color: QColor):
        self.single_color = color

    def setGradientProcess(self, gradient_process: list):
        self.gradient_process = gradient_process
        self.update()

    def setGradientEdge(self, top: int, bottom: int):
        self.gradient_edge_top = top
        self.gradient_edge_bottom = bottom
        self.update()

    def setOffsetFlag(self, flag: bool):
        self.offset_flag = flag

    def setOffsetVer(self, value: float):
        self.offset_ver = value

    def setPlainText(self, text):
        # 日文注音「[汉字(读音)]」：正文去掉标记，读音以小字画在汉字上方（rd_ruby）
        rd_ruby._set_plain_text_with_ruby(self, text, super().setPlainText)

    def setFont(self, font: QFont) -> None:
        self.paint_font = font
        super().setFont(font)
        rd_ruby._relayout_ruby_after_font(self)

    def paint(self, painter, option, widget=None):
        rd_ruby._relayout_ruby_if_stale(self)
        with QSignalBlocker(self.textControl):
            cursor = QTextCursor(self.document())
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.mergeCharFormat(self.outlineFormat)
            super().paint(painter, option, widget)
            cursor.mergeCharFormat(self.dummyFormat)
            if self.duplicate:
                super().paint(painter, option, widget)

            text = self.toPlainText()










            if self.gradient_flag:
                rect = self.boundingRect()
                gradient = QLinearGradient(0, self.gradient_edge_top, 0, self.gradient_edge_bottom)
                for flag, pos, color in self.gradient_process:
                    if flag:
                        gradient.setColorAt(pos, color)
                pen = QPen()
                pen.setBrush(gradient)
                painter.setPen(pen)

                painter.setFont(self.paint_font)
                text_option = QTextOption()
                text_option.setAlignment(Qt.AlignCenter)
                rect = self.boundingRect()

                if self.offset_flag:
                    painter.drawText(rect.adjusted(0, -self.offset_ver, 0, -self.offset_ver), text, text_option)
                else:
                    painter.drawText(rect, text, text_option)


class YuGiOhApp(QWidget):
    def __init__(self):
        super().__init__()
        self.hbox = QHBoxLayout()
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)

        font_id = QFontDatabase.addApplicationFont('mold/font/en_name.ttf')
        font_families = QFontDatabase.applicationFontFamilies(font_id)
        custom_font = QFont(font_families[0])
        custom_font.setPixelSize(158)

        zwsp = '​'
        self.text_item = MixTextItem('Text Pghdt')
        self.text_item = MixTextItem(zwsp + 'TextPreview' + zwsp)
        self.text_item.setDefaultTextColor(Qt.black)
        self.text_item.document().setDocumentMargin(50)
        self.text_item.enableGradient(True)
        self.text_item.setGradientEdge(135, 233)
        self.text_item.setOffsetFlag(True)





        self.text_item.setGradientProcess([[True, 0, QColor(255, 220, 0)], [True, 0.23, QColor(255, 255, 255)],
                                           [True, 0.42, QColor(255, 220, 0)], [True, 0.52, QColor(181, 129, 0)],
                                           [True, 0.73, QColor(255, 220, 0)], [True, 1, QColor(255, 220, 0)]])
        self.scene.addItem(self.text_item)

        self.text_item.setFont(custom_font)

        self.hbox.addWidget(self.view)
        self.setLayout(self.hbox)
        self.setWindowTitle('游戏王')
        self.resize(800, 500)

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont('Microsoft YaHei', 10))
    yugioh = YuGiOhApp()
    yugioh.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
