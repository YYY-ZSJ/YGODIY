from PyQt5.QtWidgets import QWidget, QPushButton, QApplication, QVBoxLayout, QTextEdit, QLineEdit, QDialog, QGraphicsScene, QGraphicsRectItem, QGraphicsView, QGraphicsPixmapItem, QLabel, QComboBox, QGraphicsItem, QHBoxLayout, QColorDialog, QSlider, QCheckBox, QGraphicsDropShadowEffect, QToolTip, QFileDialog, QProgressBar, QGraphicsTextItem, QSizePolicy, QProxyStyle, QStyle, QStyleOptionSlider, QScrollArea, QSpinBox, QDoubleSpinBox, QGraphicsItemGroup




from PyQt5.QtCore import Qt, QPropertyAnimation, pyqtSignal, QRect, QRectF, QPointF, QSize, QPoint, QSizeF, pyqtProperty, QRectF, QRunnable, pyqtSlot, pyqtSignal, QObject, QThreadPool, QSignalBlocker, QEvent, QTimer

from PyQt5.QtGui import QColor, QPainter, QBrush, QCursor, QPen, QColor, QPolygonF, QFont, QIcon, QFontMetricsF, QFontMetrics, QFontDatabase, QPixmap, QPainterPath, QMovie, QIntValidator, QGuiApplication, QTransform


import math
import os
import applog
import sys
from mixTextItem import MixTextItem
from collections import defaultdict
from infoFetcher import CardNameFetcher
from PIL import Image
from utils import pillow_img_to_pixmap
from CompressText import MixText, TextItem
from typing import TYPE_CHECKING, List

import card_search

if TYPE_CHECKING:
    from OTCG_widget import OTCGWidget


def filter_strings(string_list: list[str]):
    filtered_list = [
        s for s in string_list
        if s.isdigit() and len(s) <= 8]

    return filtered_list

def clean_filename(filename: str):
    forbidden_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
    for char in forbidden_chars:
        filename = filename.replace(char, '')
    return filename

def remove_leading_zeros(s: str):
    return s.lstrip('0') or '0'


SYMBOL_BUTTON_TEXTS = ('「」', '①', '②', '③', '④', '⑤', '●')


class SymbolBarWatcher(QObject):
    """跟踪面板里最近获得焦点的文本框，并让符号按钮条随效果文本框显示 / 隐藏。"""

    def __init__(self, bar, effect, targets):
        super().__init__(bar)
        self.bar = bar
        self.effect = effect
        self.last = effect
        for target in targets:
            target.installEventFilter(self)

    def eventFilter(self, obj, event):
        try:
            kind = event.type()
            if kind == QEvent.FocusIn:
                self.last = obj
            elif obj is self.effect and kind in (QEvent.ShowToParent, QEvent.HideToParent):
                self.bar.setVisible(kind == QEvent.ShowToParent)
        except Exception:
            pass
        return False

    def insert(self, symbol):
        """在光标处插入符号，等同于用户亲手输入（卡面照常刷新）。
        「」会把光标放在括号中间；选中了文字时把选中的文字括起来。"""
        target = self.last
        if target is None or not target.isVisible():
            target = self.effect
        cursor = target.textCursor()
        if symbol == '「」':
            selected = cursor.selectedText()
            cursor.insertText('「' + selected + '」')
            if not selected:
                cursor.movePosition(cursor.Left)
        else:
            cursor.insertText(symbol)
        target.setTextCursor(cursor)
        target.setFocus()


def make_symbol_bar(parent, effect, extra_targets=()):
    """效果文本框上方的一排特殊符号快捷按钮：「」 ① ② ③ ④ ⑤ ●。
    插入目标是这个面板里最近获得焦点的文本框：一般是效果文本，刚编辑过灵摆效果就插到灵摆效果里。
    返回 (按钮条, 跟踪器)。"""
    bar = QWidget(parent)
    row = QHBoxLayout(bar)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    watcher = SymbolBarWatcher(bar, effect, [effect] + [w for w in extra_targets if w is not None])
    for symbol in SYMBOL_BUTTON_TEXTS:
        button = QPushButton(symbol, bar)
        button.setFixedSize(36, 24)
        button.setFocusPolicy(Qt.NoFocus)  # 点按钮不抢走文本框的焦点和光标
        button.setToolTip('插入 ' + symbol)
        button.clicked.connect(lambda _=False, s=symbol: watcher.insert(s))
        row.addWidget(button)
    row.addStretch(1)
    # 效果文本框还没放进面板（没有父控件）时 isHidden() 恒为真，不能据此隐藏按钮条
    if effect.parentWidget() is not None and effect.isHidden():
        bar.setVisible(False)
    return bar, watcher


class WorkerSignals(QObject):
    finished = pyqtSignal()

class Worker(QRunnable):
    def __init__(self, func):
        super(Worker, self).__init__()
        self.func = func
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        # 查卡出错（联网超时/连接被重置/SSL 错误、卡片数据异常）时，异常不能从 Qt 调用的 run() 里抛出——
        # PyQt 会直接 qFatal 结束程序，而且 finished 发不出去，按钮会一直禁用。
        # 这里记日志并按「无效卡密」处理，照常发出 finished，让 after_info_fetch 走失败分支。
        try:
            self.func()
        except Exception:
            applog.log_exception("后台查卡失败（已拦截，按无效卡密处理）:")
            owner = getattr(self.func, "__self__", None)
            fetcher = getattr(owner, "info_fetcher", None)
            if fetcher is not None:
                try:
                    fetcher.valid = False
                except Exception:
                    pass
        try:
            self.signals.finished.emit()
        except Exception:
            pass


def rpath(relative_path):
    ' Get absolute path to resource, works for dev and for PyInstaller '
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


class ToggleButton(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None, check=True, on_color=QColor(0, 150, 0), off_color=QColor(150, 150, 150),
        disable_color=QColor(200, 200, 200), width=50, height=25):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.is_checked = check
        self.on_color = on_color
        self.off_color = off_color
        self.disable_color = disable_color
        self.circle_color = QColor(255, 255, 255)
        self.setCursor(Qt.PointingHandCursor)

        self._circle_x_pos = 0 if not self.is_checked else self.width() - self.height()
        self.animation = QPropertyAnimation(self, b'circle_x_pos')
        self.animation.setDuration(80)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_checked = not self.is_checked
            self.animate_circle()
            self.toggled.emit(self.is_checked)

    def animate_circle(self):

        start_value = self.circle_x_pos
        end_value = self.width() - self.height() if self.is_checked else 0
        self.animation.setStartValue(start_value)
        self.animation.setEndValue(end_value)
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)


        if not self.isEnabled():
            bg_color = self.disable_color
        else:
            bg_color = self.on_color if self.is_checked else self.off_color

        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), self.height() / 2, self.height() / 2)


        circle_scale = 0.8
        circle_diameter = self.height() * circle_scale
        offset = (self.height() - circle_diameter) / 2


        circle_rect = QRect(int(self.circle_x_pos + offset), int(offset), int(circle_diameter), int(circle_diameter))

        painter.setBrush(QBrush(self.circle_color))
        painter.drawEllipse(circle_rect)

    def sizeHint(self):
        return QSize(60, 30)


    @pyqtProperty(float)
    def circle_x_pos(self):
        return self._circle_x_pos

    @circle_x_pos.setter
    def circle_x_pos(self, value):
        self._circle_x_pos = value
        self.update()


class AttributeButton(QPushButton):
    def __init__(self, text, width=100, height=50, color='gray', parent=None):
        super().__init__(text, parent)


        self.setFixedSize(width, height)


        self.setStyleSheet(f'color: white; border: none; background-color: {color};')

        self.setCursor(QCursor(Qt.PointingHandCursor))

    def setColor(self, color):
        '设置按钮的背景颜色'
        self.setStyleSheet(f'color: white; border: none; background-color: {color};')


class StarButton(QPushButton):
    def __init__(self, circle_color='#595959', star_color='#ffffff', radius=50, star_size_ratio=0.85, parent=None):
        super().__init__(parent)
        self.circle_color = QColor(circle_color)
        self.star_color = QColor(star_color)
        self.radius = radius
        self.star_size_ratio = star_size_ratio
        self.setFixedSize(2 * radius, 2 * radius)
        self.setStyleSheet('border: none;')
        self.setMouseTracking(True)

    def setCircleColor(self, color):
        self.circle_color = QColor(color)
        self.update()

    def setStarColor(self, color):
        self.star_color = QColor(color)
        self.update()

    def setStarSizeRatio(self, ratio):
        self.star_size_ratio = ratio
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)


        painter.setBrush(QBrush(self.circle_color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, self.width(), self.height())


        star_points = self.calculate_star_points(self.radius, self.radius, self.radius * 0.5)
        painter.setBrush(QBrush(self.star_color))
        painter.drawPolygon(QPolygonF(star_points))

    def calculate_star_points(self, cx, cy, inner_radius):
        '计算五角星的五个顶点'
        points = []
        outer_radius = self.radius * self.star_size_ratio
        inner_radius = self.radius * 0.28
        for i in range(5):
            outer_angle = i * 2 * math.pi / 5 - math.pi / 2
            inner_angle = (i + 0.5) * 2 * math.pi / 5 - math.pi / 2

            outer_point = QPointF(
                cx + outer_radius * math.cos(outer_angle),
                cy + outer_radius * math.sin(outer_angle))

            inner_point = QPointF(
                cx + inner_radius * math.cos(inner_angle),
                cy + inner_radius * math.sin(inner_angle))

            points.append(outer_point)
            points.append(inner_point)
        return points

    def hitButton(self, pos):
        '检查鼠标点击是否在圆形内'
        dist = math.sqrt((pos.x() - self.radius) ** 2 + (pos.y() - self.radius) ** 2)
        return dist <= self.radius

    def mouseMoveEvent(self, event):
        '鼠标移动时触发'
        if self.hitButton(event.pos()):
            self.setCursor(QCursor(Qt.PointingHandCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        '鼠标离开按钮时触发'
        self.setCursor(QCursor(Qt.ArrowCursor))
        super().leaveEvent(event)


class CloseButton(QPushButton):
    def __init__(self, width=30, height=30, parent=None):
        super().__init__(parent)
        self.width = width
        self.height = height
        self.bg_color = QColor('#D3D3D3')
        self.cross_color = QColor('white')
        self.hover_bg_color = QColor('#909090')
        self.setFixedSize(self.width, self.height)
        self.setStyleSheet('border: none;')
        self.setCursor(QCursor(Qt.PointingHandCursor))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)


        painter.setBrush(QBrush(self.bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRect(0, 0, self.width, self.height)


        pen = QPen(self.cross_color, 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)


        side_length = int(min(self.width, self.height) * 0.5)
        offset_x = int((self.width - side_length) / 2)
        offset_y = int((self.height - side_length) / 2)

        x1, y1 = offset_x, offset_y
        x2, y2 = offset_x + side_length, offset_y + side_length

        painter.drawLine(x1, y1, x2, y2)
        painter.drawLine(x1, y2, x2, y1)

    def enterEvent(self, event):
        '鼠标进入按钮时触发'
        self.bg_color = self.hover_bg_color
        self.update()

    def leaveEvent(self, event):
        '鼠标离开按钮时触发'
        self.bg_color = QColor('#D3D3D3')
        self.update()

    def sizeHint(self):
        return QSize(self.width, self.height)


class LinkButton(QPushButton):
    def __init__(self, size=38, hand=True, parent=None):
        super().__init__(parent)
        self.size = size
        self.outer_color = QColor('#dddddd')
        self.inner_color = QColor('#bbbbbb')
        self.hover_color = QColor('#bbbbbb')
        self.setFixedSize(self.size, self.size)
        self.setStyleSheet('border: none;')
        self.setCursor(QCursor(Qt.ArrowCursor))
        self.radius_corner = self.size * 0.12
        self.hand = hand

    def setOuterColor(self, color):
        '设置大正方形的背景颜色'
        self.outer_color = QColor(color)
        self.update()

    def setInnerColor(self, color):
        '设置小正方形的背景颜色'
        self.inner_color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)


        painter.setBrush(QBrush(self.outer_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.size, self.size, self.radius_corner, self.radius_corner)


        inner_size = int(self.size * 0.75)
        offset = int((self.size - inner_size) / 2)
        painter.setBrush(QBrush(self.inner_color))
        painter.drawRect(offset, offset, inner_size, inner_size)

    def enterEvent(self, event):
        '鼠标进入按钮区域时触发'
        if self.hand:
            self.setCursor(QCursor(Qt.PointingHandCursor))
            self.outer_color = self.hover_color
            self.update()

    def leaveEvent(self, event):
        '鼠标离开按钮区域时触发'
        self.setCursor(QCursor(Qt.ArrowCursor))
        self.outer_color = QColor('#dddddd')
        self.update()

    def sizeHint(self):
        return QSize(self.size, self.size)


class ColorButton(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, text='Button', circle_color=QColor(255, 255, 255),
        width=68, height=23, half=False, top_color=QColor(255, 255, 255),
        bottom_color=QColor(255, 255, 255), parent=None):
        super().__init__(parent)
        self.width = width
        self.height = height
        self.padding = 2
        self.ring_thickness = 3
        self.show_ring = False
        self.setFixedSize(self.width + self.padding * 2, self.height + self.padding * 2)
        self.is_checked = False
        self.bg_color = QColor(190, 190, 190)
        self.circle_color = circle_color
        self.text = text
        self.half = half
        self.top_color = top_color
        self.bottom_color = bottom_color
        self.setMouseTracking(True)

    def setSize(self, width, height):
        '设置按钮的宽度和高度'
        self.width = width
        self.height = height
        self.setFixedSize(self.width + self.padding * 2, self.height + self.padding * 2)
        self.update()

    def calculate_font_size(self):
        '根据按钮高度动态计算合适的字体大小'
        return max(6, int(self.height * 0.4))

    def is_in_button_area(self, mouse_pos):
        '判断鼠标是否在左侧圆形、右侧圆角或矩形区域'
        circle_radius = self.height // 2
        circle_center_left = QPoint(self.padding + circle_radius, self.padding + circle_radius)
        circle_center_right = QPoint(self.padding + self.width - circle_radius, self.padding + circle_radius)


        distance_to_left_circle = ((mouse_pos.x() - circle_center_left.x()) ** 2 + (mouse_pos.y() - circle_center_left.y()) ** 2) ** 0.5
        distance_to_right_circle = ((mouse_pos.x() - circle_center_right.x()) ** 2 + (mouse_pos.y() - circle_center_right.y()) ** 2) ** 0.5


        if distance_to_left_circle <= circle_radius:
            return True


        if distance_to_right_circle <= circle_radius and mouse_pos.x() >= self.padding + self.width - circle_radius:
            return True


        if self.padding + circle_radius < mouse_pos.x() < self.padding + self.width - circle_radius:
            return True

        return False

    def mousePressEvent(self, event):
        '仅当鼠标在按钮区域内时触发点击事件'
        if event.button() == Qt.LeftButton:
            if self.is_in_button_area(event.pos()):
                self.is_checked = not self.is_checked
                self.update()
                self.toggled.emit(self.is_checked)
            else:
                event.ignore()

    def mouseMoveEvent(self, event):
        '动态检测鼠标是否在圆形区域或按钮的左右圆角区域，改变样式'
        if self.is_in_button_area(event.pos()):
            self.setCursor(QCursor(Qt.PointingHandCursor))
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)


        circle_diameter = self.height
        circle_radius = circle_diameter // 2


        painter.setBrush(QBrush(self.bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRect(self.padding, self.padding, self.width, self.height), circle_radius, circle_radius)


        if self.half:

            painter.setBrush(QBrush(self.top_color))
            painter.setPen(Qt.NoPen)
            painter.drawPie(QRect(self.padding, self.padding, circle_diameter, circle_diameter), 0, 2880)


            painter.setBrush(QBrush(self.bottom_color))
            painter.setPen(Qt.NoPen)
            painter.drawPie(QRect(self.padding, self.padding, circle_diameter, circle_diameter), 2880, 2880)
        else:

            painter.setBrush(QBrush(self.circle_color))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRect(self.padding, self.padding, circle_diameter, circle_diameter))


        font_size = self.calculate_font_size()
        font = QFont('Microsoft YaHei', font_size)
        painter.setFont(font)


        text_rect = QRect(circle_diameter + self.padding * 2, self.padding, self.width - circle_diameter - self.padding * 2, self.height)
        font_metrics = QFontMetricsF(font)
        text_width = font_metrics.boundingRect(self.text).width()

        while text_width > text_rect.width() and font_size > 8:
            font_size -= 1
            font.setPointSize(font_size)
            painter.setFont(font)
            font_metrics = QFontMetricsF(font)
            text_width = font_metrics.boundingRect(self.text).width()


        painter.setPen(Qt.black)
        painter.drawText(text_rect, Qt.AlignCenter, self.text)


        if self.show_ring:
            pen = QPen(QColor(0, 200, 0), self.ring_thickness)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)


            painter.drawEllipse(QRect(self.padding, self.padding, circle_diameter, circle_diameter))

    def display_ring(self):
        '显示绿色圆环'
        self.show_ring = True
        self.update()

    def hide_ring(self):
        '隐藏绿色圆环'
        self.show_ring = False
        self.update()

    def setText(self, text):
        '设置按钮的文本'
        self.text = text
        self.update()

    def setCircleColor(self, color):
        '设置圆形的颜色'
        self.circle_color = color
        self.update()

    def sizeHint(self):
        return self.size()


class CustomTextEdit(QTextEdit):
    def __init__(self):
        super().__init__()
        self.textChanged.connect(self.on_text_changed)
        self.is_programmatic_change = False
        self.has_user_type = False

    def setText(self, text):
        self.is_programmatic_change = True
        super().setText(text)
        self.is_programmatic_change = False

    def on_text_changed(self):
        if not self.is_programmatic_change:
            self.has_user_type = True


class CustomLineEdit(QLineEdit):
    def __init__(self):
        super().__init__()
        self.textChanged.connect(self.on_text_changed)
        self.is_programmatic_change = False
        self.has_user_type = False

    def setText(self, text):
        self.is_programmatic_change = True
        super().setText(text)
        self.is_programmatic_change = False

    def on_text_changed(self):
        if not self.is_programmatic_change:
            self.has_user_type = True


class ResizableRectItem(QGraphicsRectItem):
    def __init__(self, *args, boundary_rect: QRectF = None, keep_square=True, fixed_ratio=None, parent_dialog=None):
        super().__init__(*args)
        self.setFlag(QGraphicsRectItem.ItemIsMovable)
        self.setFlag(QGraphicsRectItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsRectItem.ItemIsFocusable, True)
        self.setFocus()
        self.setPen(QPen(QColor(255, 0, 0), 2))
        self.boundary_rect = boundary_rect
        self.keep_square = keep_square
        self.fixed_ratio = fixed_ratio
        self.resizing = False
        self.drag_start_pos = None
        self.resize_direction = None
        self.min_size = 20
        self.parent_dialog = parent_dialog

    def hoverMoveEvent(self, event):
        '鼠标悬停时改变鼠标光标'
        cursor_pos = event.pos()
        rect = self.rect()
        margin = 10

        if abs(cursor_pos.x() - rect.right()) < margin and abs(cursor_pos.y() - rect.bottom()) < margin:
            if self.keep_square == False and not self.fixed_ratio is not None:
                self.setCursor(QCursor(Qt.SizeFDiagCursor))
                self.resize_direction = 'bottom_right'; return
        if abs(cursor_pos.x() - rect.right()) < margin:
            self.setCursor(QCursor(Qt.SizeHorCursor))
            self.resize_direction = 'right'
        elif abs(cursor_pos.y() - rect.bottom()) < margin:
            self.setCursor(QCursor(Qt.SizeVerCursor))
            self.resize_direction = 'bottom'
        else:
            self.setCursor(QCursor(Qt.ArrowCursor))
            self.resize_direction = None

    def mousePressEvent(self, event):
        '记录开始拖拽的位置'
        if self.resize_direction:
            self.resizing = True
            self.drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        '根据鼠标拖动调整大小或移动裁剪框'
        rect = self.rect()

        if self.resizing and self.resize_direction:
            diff = event.pos() - self.drag_start_pos
            new_rect = QRectF(rect)

            scene_rect = self.mapRectToScene(new_rect)

            if self.keep_square:

                new_size = 0
                if self.resize_direction == 'right':
                    size_change = diff.x()
                    new_size = max(self.min_size, rect.width() + size_change)
                    max_size = min(self.boundary_rect.width() - scene_rect.left(),
                        self.boundary_rect.height() - scene_rect.top())
                    new_size = min(new_size, max_size)
                elif self.resize_direction == 'bottom':
                    size_change = diff.y()
                    new_size = max(self.min_size, rect.width() + size_change)
                    max_size = min(self.boundary_rect.width() - scene_rect.left(),
                        self.boundary_rect.height() - scene_rect.top())
                    new_size = min(new_size, max_size)
                new_rect.setWidth(new_size)
                new_rect.setHeight(new_size)
            elif self.fixed_ratio:

                ratio_width = self.fixed_ratio
                ratio_height = 1
                new_width, new_height = (0, 0)
                if self.resize_direction == 'right':
                    width_change = diff.x()
                    new_width = max(self.min_size, rect.width() + width_change)
                    new_height = new_width / ratio_width * ratio_height

                    if scene_rect.left() + new_width > self.boundary_rect.right():
                        new_width = self.boundary_rect.right() - scene_rect.left()
                        new_height = new_width / ratio_width * ratio_height

                    if scene_rect.top() + new_height > self.boundary_rect.bottom():
                        new_height = self.boundary_rect.bottom() - scene_rect.top()
                        new_width = new_height * ratio_width / ratio_height
                elif self.resize_direction == 'bottom':

                    height_change = diff.y()
                    new_height = max(self.min_size, rect.height() + height_change)
                    new_width = new_height * ratio_width / ratio_height

                    if scene_rect.top() + new_height > self.boundary_rect.bottom():
                        new_height = self.boundary_rect.bottom() - scene_rect.top()
                        new_width = new_height * ratio_width / ratio_height

                    if scene_rect.left() + new_width > self.boundary_rect.right():
                        new_width = self.boundary_rect.right() - scene_rect.left()
                        new_height = new_width / ratio_width * ratio_height
                new_rect.setHeight(new_height)
                new_rect.setWidth(new_width)


            elif self.resize_direction == 'bottom_right':
                width_change = diff.x()
                new_width = max(self.min_size, rect.width() + width_change)
                if scene_rect.left() + new_width > self.boundary_rect.right():
                    new_width = self.boundary_rect.right() - scene_rect.left()
                height_change = diff.y()
                new_height = max(self.min_size, rect.height() + height_change)
                if scene_rect.top() + new_height > self.boundary_rect.bottom():
                    new_height = self.boundary_rect.bottom() - scene_rect.top()
                new_rect.setWidth(new_width)
                new_rect.setHeight(new_height)
            elif self.resize_direction == 'right':
                width_change = diff.x()
                new_width = max(self.min_size, rect.width() + width_change)
                if scene_rect.left() + new_width > self.boundary_rect.right():
                    new_width = self.boundary_rect.right() - scene_rect.left()
                new_rect.setWidth(new_width)
            elif self.resize_direction == 'bottom':
                height_change = diff.y()
                new_height = max(self.min_size, rect.height() + height_change)
                if scene_rect.top() + new_height > self.boundary_rect.bottom():
                    new_height = self.boundary_rect.bottom() - scene_rect.top()
                new_rect.setHeight(new_height)

            self.setRect(new_rect)
            self.drag_start_pos = event.pos()
        else:


            super().mouseMoveEvent(event)
            self.limit_within_boundary()

        if self.parent_dialog:
            self.parent_dialog.update_mask()

    def mouseReleaseEvent(self, event):
        '停止调整大小并确保裁剪框在 boundary_rect 内'
        self.resizing = False
        super().mouseReleaseEvent(event)
        self.limit_within_boundary()

        if self.parent_dialog:
            self.parent_dialog.update_mask()

    def keyPressEvent(self, event):
        '键盘方向键控制裁剪框移动'
        step = 1
        if event.key() == Qt.Key_Left:
            self.moveBy(-step, 0)
        elif event.key() == Qt.Key_Right:
            self.moveBy(step, 0)
        elif event.key() == Qt.Key_Up:
            self.moveBy(0, -step)
        elif event.key() == Qt.Key_Down:
            self.moveBy(0, step)


        self.limit_within_boundary()


        if self.parent_dialog:
            self.parent_dialog.update_mask()


        event.accept()

    def limit_within_boundary(self):
        '确保裁剪框在 boundary_rect 内，不能移出范围'

        scene_rect = self.mapRectToScene(self.rect())


        if scene_rect.left() < self.boundary_rect.left():
            delta = self.boundary_rect.left() - scene_rect.left()
            self.moveBy(delta, 0)
        if scene_rect.top() < self.boundary_rect.top():
            delta = self.boundary_rect.top() - scene_rect.top()
            self.moveBy(0, delta)
        if scene_rect.right() > self.boundary_rect.right():
            delta = scene_rect.right() - self.boundary_rect.right()
            self.moveBy(-delta, 0)
        if scene_rect.bottom() > self.boundary_rect.bottom():
            delta = scene_rect.bottom() - self.boundary_rect.bottom()
            self.moveBy(0, -delta)


class CropDialog(QDialog):
    def __init__(self, pixmap: QPixmap, parent=None, mode='OTCG'):
        super().__init__(parent)

        self.setWindowTitle('裁剪图像')
        screen_height = QGuiApplication.primaryScreen().geometry().height()
        min_size = int(0.74 * screen_height)
        self.setMinimumSize(min_size, min_size)


        self.original_pixmap = pixmap
        self.original_width = pixmap.width()
        self.original_height = pixmap.height()


        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)


        self.view.setRenderHint(QPainter.SmoothPixmapTransform)


        self.pixmap_item = QGraphicsPixmapItem(self.original_pixmap)
        self.scene.addItem(self.pixmap_item)


        self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)


        self.displayed_width = self.pixmap_item.boundingRect().width()
        self.displayed_height = self.pixmap_item.boundingRect().height()

        init_frame_size = 2 * min(self.displayed_width, self.displayed_height) // 3

        self.boundary_rect = QRectF(0, 0, self.displayed_width, self.displayed_height)


        self.crop_rect = ResizableRectItem(0, 0, init_frame_size, init_frame_size, keep_square=True, boundary_rect=self.boundary_rect, parent_dialog=self)
        self.scene.addItem(self.crop_rect)


        self.mask_items = []
        self.update_mask()


        item_dict = {
            'OTCG': ['正方形卡图', '灵摆卡图', '任意矩形'],
            'OverFrame': ['任意矩形', '卡面矩形'],
            'RD': ['正方形卡图', '任意矩形'],
            'Center': ['场地中心图'],
            'Center_full': ['场地中心图(全图)']}

        self.mode_selector = QComboBox(self)
        self.mode_selector.addItems(item_dict[mode])
        self.mode_selector.currentIndexChanged.connect(self.change_mode)


        self.confirm_button = QPushButton('确认')
        self.confirm_button.clicked.connect(self.crop_and_show_preview)


        layout = QVBoxLayout(self)
        layout.addWidget(self.mode_selector)
        layout.addWidget(self.view)
        layout.addWidget(self.confirm_button)
        self.setLayout(layout)

        self.change_mode()

        self.view.setFocusPolicy(Qt.StrongFocus)

    def update_mask(self):
        '更新半透明的遮罩覆盖裁剪框外的区域'

        for item in self.mask_items:
            self.scene.removeItem(item)
        self.mask_items.clear()

        crop_rect = self.crop_rect.mapRectToScene(self.crop_rect.rect())


        top_rect = QRectF(0, 0, self.displayed_width, crop_rect.top())
        bottom_rect = QRectF(0, crop_rect.bottom(), self.displayed_width, self.displayed_height - crop_rect.bottom())
        left_rect = QRectF(0, crop_rect.top(), crop_rect.left(), crop_rect.height())
        right_rect = QRectF(crop_rect.right(), crop_rect.top(), self.displayed_width - crop_rect.right(), crop_rect.height())


        mask_color = QColor(0, 0, 0, 128)
        for rect in (top_rect, bottom_rect, left_rect, right_rect):
            mask_item = QGraphicsRectItem(rect)
            mask_item.setBrush(mask_color)
            mask_item.setPen(QPen(Qt.NoPen))
            self.scene.addItem(mask_item)
            self.mask_items.append(mask_item)


    def resizeEvent(self, event):
        '当窗口调整大小时，重新调整图像显示大小'
        super().resizeEvent(event)
        self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)


        self.displayed_width = self.pixmap_item.boundingRect().width()
        self.displayed_height = self.pixmap_item.boundingRect().height()


        self.boundary_rect.setRect(0, 0, self.displayed_width, self.displayed_height)


        self.update_mask()


    def mouseMoveEvent(self, event):
        '根据鼠标拖动调整裁剪框时，更新遮罩'
        super().mouseMoveEvent(event)
        self.update_mask()

    def change_mode(self):
        '根据用户选择的模式，切换裁剪框'
        if self.mode_selector.currentText() == '正方形卡图':
            self.crop_rect.keep_square = True
            self.crop_rect.fixed_ratio = None
            self.adjust_to_square()
        elif self.mode_selector.currentText() == '灵摆卡图':
            self.crop_rect.keep_square = False
            self.crop_rect.fixed_ratio = 0.7837988826815643
            self.adjust_to_ratio(1403, 1790)
        elif self.mode_selector.currentText() == '场地中心图':
            self.crop_rect.keep_square = False
            self.crop_rect.fixed_ratio = 0.6831084225221034
            self.adjust_to_ratio(1468, 2149)
        elif self.mode_selector.currentText() == '场地中心图(全图)':
            self.crop_rect.keep_square = False
            self.crop_rect.fixed_ratio = 0.7156118143459915
            self.adjust_to_ratio(1696, 2370)
        elif self.mode_selector.currentText() == '卡面矩形':
            self.crop_rect.keep_square = False
            self.crop_rect.fixed_ratio = 0.6860759493670886
            self.adjust_to_ratio(1626, 2370)
        else:
            self.crop_rect.keep_square = False
            self.crop_rect.fixed_ratio = None


        self.update_mask()

    def adjust_to_square(self):
        '将裁剪框立即调整为正方形'
        rect = self.crop_rect.rect()


        side_length = min(rect.width(), rect.height())


        new_rect = QRectF(rect.topLeft(), QSizeF(side_length, side_length))
        self.crop_rect.setRect(new_rect)

    def adjust_to_ratio(self, width_ratio, height_ratio):
        '将裁剪框立即调整为指定比例的矩形'
        rect = self.crop_rect.rect()


        new_width = rect.width()
        new_height = new_width * height_ratio / width_ratio


        if rect.top() + new_height > self.boundary_rect.bottom():
            new_height = self.boundary_rect.bottom() - rect.top()
            new_width = new_height * width_ratio / height_ratio


        new_rect = QRectF(rect.topLeft(), QSizeF(new_width, new_height))
        self.crop_rect.setRect(new_rect)

    def crop_and_show_preview(self):

        rect = self.crop_rect.rect()


        scale_x = self.original_width / self.displayed_width
        scale_y = self.original_height / self.displayed_height


        scene_rect = self.crop_rect.mapRectToScene(rect)


        crop_rect = (QRectF(
            scene_rect.x() * scale_x,
            scene_rect.y() * scale_y,
            scene_rect.width() * scale_x,
            scene_rect.height() * scale_y)
            .toRect)()


        crop_rect = crop_rect.intersected(QRectF(0, 0, self.original_width, self.original_height).toRect())


        cropped_image = self.original_pixmap.copy(crop_rect)
        self.cropped_pixmap = cropped_image
        self.done(1)

    def get_cropped_pixmap(self):
        return getattr(self, 'cropped_pixmap', None)

    def showEvent(self, event):

        self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        super().showEvent(event)


class RoundedButton(QPushButton):
    def __init__(self, text='', width=None, height=None, radius=5, btn_color=QColor(0, 0, 0),
        press_color=QColor(60, 60, 60), text_color=QColor(255, 255, 255), parent=None):
        super().__init__(text, parent)
        self.radius = radius
        self.default_bg_color = btn_color
        self.pressed_bg_color = press_color
        self.text_color = text_color
        self.icon_size = 16

        if not (width is None or height is None):
            self.setFixedSize(width, height)

        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet('border: none;')
        self.setFocusPolicy(Qt.NoFocus)
        self.is_pressed = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)


        rect = self.rect()
        brush = QBrush(self.default_bg_color if not self.is_pressed else self.pressed_bg_color)
        painter.setBrush(brush)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, self.radius, self.radius)


        icon = self.icon()
        if not icon.isNull():
            icon_rect = QRect((self.width() - self.icon_size) // 2,
                (self.height() - self.icon_size) // 2,
                self.icon_size, self.icon_size)
            icon.paint(painter, icon_rect, Qt.AlignCenter)


        if self.text():
            painter.setPen(self.text_color)
            painter.drawText(rect, Qt.AlignCenter, self.text())

    def setIconSize(self, size):
        '设置图标大小'
        self.icon_size = size

    def mousePressEvent(self, event):
        self.is_pressed = True
        self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.is_pressed = False
        self.update()
        super().mouseReleaseEvent(event)


class ColorSquare(QPushButton):
    def __init__(self, parent=None, size=50):
        super(ColorSquare, self).__init__(parent)
        self.color = QColor(100, 100, 100)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)

    def setColor(self, color: QColor):
        self.color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.isEnabled():

            painter.setBrush(self.color)
        else:

            painter.setBrush(QColor(160, 160, 160))

        painter.setPen(Qt.NoPen)
        radius = int(self.width() * 0.15)
        painter.drawRoundedRect(QRect(0, 0, self.width(), self.height()), radius, radius)

        if self.isEnabled():

            arrow_pen = QPen(Qt.white, 2, Qt.SolidLine)
            painter.setPen(arrow_pen)


            center_x = self.width() // 2
            center_y = self.height() // 2
            arrow_size = int(min(self.width(), self.height()) * 0.4)


            painter.drawLine(int(center_x - arrow_size // 2), int(center_y - arrow_size // 4),
                int(center_x), int(center_y + arrow_size // 4))
            painter.drawLine(int(center_x), int(center_y + arrow_size // 4),
                int(center_x + arrow_size // 2), int(center_y - arrow_size // 4))










class ColorSlider(QSlider):
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setCursor(Qt.PointingHandCursor)

        self.setStyleSheet('\n            QSlider::handle:horizontal {\n                background-color: black;\n                width: 10px;\n                height: 20px;\n                border-radius: 5px;\n            }\n            QSlider::handle:horizontal:disabled {\n                background-color: gray;\n                width: 10px;\n                height: 20px;\n                border-radius: 5px;\n            }\n        ')















class ColorAdvancedDialog(QDialog):
    def __init__(self, outline_enabled, outline_color, outline_thickness, shadow_flag, shadow_color, shadow_blur_size, shadow_x_offset, shadow_y_offset, gradient_flag, gradient_process, single_color,

        parent=None):
        super().__init__(parent)
        self.setWindowTitle('卡名样式自定义')
        self.setFixedWidth(550)
        screen_height = QGuiApplication.primaryScreen().geometry().height()
        if screen_height > 1050:
            self.resize(550, 820)
        else:
            self.resize(550, int(0.7 * screen_height))
        font = self.font()
        bold_font = self.font()
        bold_font.setBold(True)
        font_metrics = QFontMetrics(font)
        self.cn_font = QFont(QFontDatabase.applicationFontFamilies(
            QFontDatabase.addApplicationFont(rpath('mold/font/cn.ttf')))[0])
        self.en_font = QFont(QFontDatabase.applicationFontFamilies(
            QFontDatabase.addApplicationFont(rpath('mold/font/en_name.ttf')))[0])

        self.outline_enabled = outline_enabled
        self.outline_color = outline_color
        self.outline_thickess = outline_thickness

        self.shadow_flag = shadow_flag
        self.shadow_color = shadow_color
        self.shadow_blur_size = shadow_blur_size
        self.shadow_x_offset = shadow_x_offset
        self.shadow_y_offset = shadow_y_offset
        self.shadow_vis_ratio = 0.7663817663817664

        self.gradient_flag = gradient_flag
        self.gradient_process = gradient_process
        self.single_color = single_color

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setStyleSheet('border: none; background-color: rgba(0, 0, 0, 0);')
        self.scene.setBackgroundBrush(QBrush(Qt.transparent))

        self.text_item1 = MixTextItem('效果预览', duplicate=True)
        self.text_item1.document().setDocumentMargin(15)
        self.cn_font.setPixelSize(130)
        self.text_item1.setFont(self.cn_font)
        self.text_item1.setGradientEdge(34, 125)

        zwsp = '\u200b'
        self.text_item2 = MixTextItem(zwsp + 'TextPreview' + zwsp, duplicate=True)
        self.text_item2.document().setDocumentMargin(15)
        self.text_item2.setOffsetFlag(True)
        self.en_font.setPixelSize(135)
        self.text_item2.setFont(self.en_font)
        self.text_item2.setGradientEdge(79, 160)

        self.scene.addItem(self.text_item1)
        self.scene.addItem(self.text_item2)
        self.scene.update()
        rect1 = self.text_item1.boundingRect()
        rect2 = self.text_item2.boundingRect()
        view_rect = self.view.rect()
        self.scene.setSceneRect(QRectF(view_rect))
        scene_width = view_rect.width()
        scene_height = view_rect.height()
        x1 = (scene_width - rect1.width()) / 2
        x2 = (scene_width - rect2.width()) / 2
        y1 = scene_height / 2 - rect1.height() + 10
        y2 = scene_height / 2 - 30
        self.text_item1.setPos(x1, y1)
        self.text_item2.setPos(x2, y2)

        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)


        self.shadow1 = QGraphicsDropShadowEffect()
        self.shadow2 = QGraphicsDropShadowEffect()
        if self.gradient_flag:
            self.text_item1.setDefaultTextColor(Qt.transparent)
            self.text_item2.setDefaultTextColor(Qt.transparent)
            self.text_item1.enableGradient(True)
            self.text_item2.enableGradient(True)
            self.text_item1.setGradientProcess(self.gradient_process)
            self.text_item2.setGradientProcess(self.gradient_process)
        else:
            self.text_item1.enableGradient(False)
            self.text_item2.enableGradient(False)
            self.text_item1.setDefaultTextColor(self.single_color)
            self.text_item2.setDefaultTextColor(self.single_color)

        if self.outline_enabled:
            self.text_item1.enableOutline(True)
            self.text_item2.enableOutline(True)
            self.text_item1.setOutlineStyle(self.outline_color, self.outline_thickess)
            self.text_item2.setOutlineStyle(self.outline_color, self.outline_thickess)
        else:
            self.text_item1.enableOutline(False)
            self.text_item2.enableOutline(False)
        if self.shadow_flag:
            self.shadow1.setColor(self.shadow_color)
            self.shadow1.setBlurRadius(self.shadow_blur_size * self.shadow_vis_ratio)
            self.shadow1.setXOffset(self.shadow_x_offset * self.shadow_vis_ratio)
            self.shadow1.setYOffset(self.shadow_y_offset * self.shadow_vis_ratio)
            self.shadow2.setColor(self.shadow_color)
            self.shadow2.setBlurRadius(self.shadow_blur_size * self.shadow_vis_ratio)
            self.shadow2.setXOffset(self.shadow_x_offset * self.shadow_vis_ratio)
            self.shadow2.setYOffset(self.shadow_y_offset * self.shadow_vis_ratio)
            self.text_item1.setGraphicsEffect(self.shadow1)
            self.text_item2.setGraphicsEffect(self.shadow2)


        self.preview_vbox = QVBoxLayout()
        self.preview_hbox = QHBoxLayout()
        font = self.font()
        font.setBold(True)
        self.preview_label = QLabel('效果预览')
        self.preview_label.setFont(font)
        self.dark_label = QLabel('深色背景 ')
        self.dark_label.setFont(font)
        self.dark_mode_btn = ToggleButton(height=20, width=40, check=False, on_color=QColor(0, 0, 0))
        self.dark_flag = False
        self.dark_mode_btn.toggled.connect(self.dark_btn_clicked)
        self.preview_hbox.addWidget(self.preview_label)
        self.preview_hbox.addStretch(1)
        self.preview_hbox.addWidget(self.dark_label)
        self.preview_hbox.addWidget(self.dark_mode_btn)
        self.preview_vbox.addLayout(self.preview_hbox)
        self.preview_vbox.addWidget(self.view)


        self.outline_hbox1 = QHBoxLayout()
        self.outline_label = QLabel('卡名轮廓 ')
        self.outline_label.setFont(bold_font)
        self.outline_toggle = ToggleButton(height=20, width=40, check=self.outline_enabled)
        self.outline_toggle.toggled.connect(self.outline_toggle_clicked)
        self.outline_hbox1.addWidget(self.outline_label)
        self.outline_hbox1.addWidget(self.outline_toggle)
        self.outline_hbox1.addStretch(1)

        self.outline_hbox2 = QHBoxLayout()
        self.outline_color_label = QLabel('颜色：')
        self.outline_color_btn = ColorSquare(size=25)
        self.outline_color_btn.setColor(self.outline_color)
        self.outline_color_btn.clicked.connect(self.outline_color_cliked)
        self.outline_size_label = QLabel(f'粗细：{self.outline_thickess}')
        self.outline_size_slider = ColorSlider(Qt.Horizontal)
        self.outline_size_slider.setRange(1, 20)
        self.outline_size_slider.valueChanged.connect(self.outline_size_change)
        self.outline_size_slider.setValue(self.outline_thickess)
        self.outline_hbox2.addWidget(self.outline_color_label)
        self.outline_hbox2.addWidget(self.outline_color_btn)
        self.outline_hbox2.addSpacing(20)
        self.outline_hbox2.addWidget(self.outline_size_label)
        self.outline_hbox2.addWidget(self.outline_size_slider)

        self.outline_color_label.setEnabled(self.outline_enabled)
        self.outline_size_label.setEnabled(self.outline_enabled)
        self.outline_color_btn.setEnabled(self.outline_enabled)
        self.outline_size_slider.setEnabled(self.outline_enabled)


        self.shadow_hbox1 = QHBoxLayout()
        self.shadow_label = QLabel('卡名阴影 ')
        self.shadow_label.setFont(bold_font)
        self.shadow_toggle = ToggleButton(height=20, width=40, check=self.shadow_flag)
        self.shadow_toggle.toggled.connect(self.shadow_toggle_clicked)
        self.shadow_hbox1.addWidget(self.shadow_label)
        self.shadow_hbox1.addWidget(self.shadow_toggle)
        self.shadow_hbox1.addStretch(1)

        width = font_metrics.horizontalAdvance('模糊半径：20')
        self.shadow_hbox2 = QHBoxLayout()
        self.shadow_color_hbox = QHBoxLayout()
        self.shadow_color_label = QLabel('颜色：')
        self.shadow_color_btn = ColorSquare(size=25)
        self.shadow_color_btn.setColor(self.shadow_color)
        self.shadow_color_btn.clicked.connect(self.shadow_color_clicked)
        self.shadow_color_hbox.addWidget(self.shadow_color_label)
        self.shadow_color_hbox.addWidget(self.shadow_color_btn)
        self.shadow_color_hbox.addStretch(1)
        self.shadow_blur_hbox = QHBoxLayout()
        self.shadow_blursize_label = QLabel(f'模糊半径：{self.shadow_blur_size}')
        self.shadow_blursize_label.setFixedWidth(width)
        self.shadow_blursize_slider = ColorSlider(Qt.Horizontal)
        self.shadow_blursize_slider.setRange(0, 25)
        self.shadow_blursize_slider.valueChanged.connect(self.shadow_blursize_change)
        self.shadow_blursize_slider.setValue(self.shadow_blur_size)
        self.shadow_blur_hbox.addWidget(self.shadow_blursize_label)
        self.shadow_blur_hbox.addWidget(self.shadow_blursize_slider)
        self.shadow_hbox2.addLayout(self.shadow_color_hbox)
        self.shadow_hbox2.addStretch(10)
        self.shadow_hbox2.addLayout(self.shadow_blur_hbox)
        self.shadow_hbox2.setStretch(0, 45)
        self.shadow_hbox2.setStretch(2, 45)

        self.shadow_hbox3 = QHBoxLayout()
        self.shadow_xoffset_hbox = QHBoxLayout()
        self.shadow_xoffset_label = QLabel(f'X偏移量：{self.shadow_x_offset}')
        self.shadow_xoffset_label.setFixedWidth(width)
        self.shadow_xoffset_slider = ColorSlider(Qt.Horizontal)
        self.shadow_xoffset_slider.setRange(-20, 20)
        self.shadow_xoffset_slider.setValue(self.shadow_x_offset)
        self.shadow_xoffset_slider.valueChanged.connect(self.shadow_xoffset_change)
        self.shadow_xoffset_hbox.addWidget(self.shadow_xoffset_label)
        self.shadow_xoffset_hbox.addWidget(self.shadow_xoffset_slider)
        self.shadow_yoffset_hbox = QHBoxLayout()
        self.shadow_yoffset_label = QLabel(f'Y偏移量：{self.shadow_y_offset}')
        self.shadow_yoffset_label.setFixedWidth(width)
        self.shadow_yoffset_slider = ColorSlider(Qt.Horizontal)
        self.shadow_yoffset_slider.setRange(-20, 20)
        self.shadow_yoffset_slider.setValue(self.shadow_y_offset)
        self.shadow_yoffset_slider.valueChanged.connect(self.shadow_yoffset_change)
        self.shadow_yoffset_hbox.addWidget(self.shadow_yoffset_label)
        self.shadow_yoffset_hbox.addWidget(self.shadow_yoffset_slider)
        self.shadow_hbox3.addLayout(self.shadow_xoffset_hbox)
        self.shadow_hbox3.addStretch(10)
        self.shadow_hbox3.addLayout(self.shadow_yoffset_hbox)
        self.shadow_hbox3.setStretch(0, 45)
        self.shadow_hbox3.setStretch(2, 45)

        self.shadow_color_label.setEnabled(self.shadow_flag)
        self.shadow_color_btn.setEnabled(self.shadow_flag)
        self.shadow_blursize_label.setEnabled(self.shadow_flag)
        self.shadow_blursize_slider.setEnabled(self.shadow_flag)
        self.shadow_xoffset_label.setEnabled(self.shadow_flag)
        self.shadow_xoffset_slider.setEnabled(self.shadow_flag)
        self.shadow_yoffset_label.setEnabled(self.shadow_flag)
        self.shadow_yoffset_slider.setEnabled(self.shadow_flag)


        self.gradient_hbox = QHBoxLayout()
        self.gradient_label = QLabel('渐变颜色 ')
        self.gradient_label.setFont(bold_font)
        self.gradient_toggle = ToggleButton(height=20, width=40, check=self.gradient_flag)
        self.gradient_toggle.toggled.connect(self.gradient_toggle_clicked)
        self.single_color_label = QLabel('单色：')
        self.single_color_label.setFont(font)
        self.single_color_btn = ColorSquare(size=25)
        self.single_color_btn.setColor(self.single_color)
        self.single_color_btn.setEnabled(not self.gradient_flag)
        self.single_color_btn.clicked.connect(self.single_color_clicked)
        self.gradient_hbox.addWidget(self.gradient_label)
        self.gradient_hbox.addWidget(self.gradient_toggle)
        self.gradient_hbox.addSpacing(20)
        self.gradient_hbox.addWidget(self.single_color_label)
        self.gradient_hbox.addWidget(self.single_color_btn)
        self.gradient_hbox.addStretch(1)

        self.gradient_slider_vbox = QVBoxLayout()

        self.gradient_hbox_list = [QHBoxLayout() for _ in range(6)]
        self.checkbox_list = [QCheckBox() for _ in range(6)]
        self.label_list = [QLabel() for _ in range(6)]
        self.color_btn_list = [ColorSquare(size=25) for _ in range(6)]
        self.slider_list = [ColorSlider(Qt.Horizontal) for _ in range(6)]

        width = font_metrics.horizontalAdvance('渐变终点 100')
        self.label_list[0].setText('渐变起点 0')
        self.label_list[5].setText('渐变终点 100')
        for i in range(6):
            checkbox, colorbtn = self.checkbox_list[i], self.color_btn_list[i]
            label, slider = self.label_list[i], self.slider_list[i]
            label.setFixedWidth(width)
            slider.setRange(0, 100)
            checkbox.setChecked(self.gradient_process[i][0])
            colorbtn.setColor(self.gradient_process[i][2])
            slider.setValue(int(self.gradient_process[i][1] * 100))
            if i == 0 or i == 5:
                checkbox.setEnabled(False)
                colorbtn.setEnabled(self.gradient_flag)
                label.setEnabled(self.gradient_flag)
                slider.setEnabled(False)
            else:
                checkbox.setEnabled(self.gradient_flag)
                colorbtn.setEnabled(self.gradient_process[i][0] and self.gradient_flag)
                label.setEnabled(self.gradient_process[i][0] and self.gradient_flag)
                slider.setEnabled(self.gradient_process[i][0] and self.gradient_flag)
                label.setText(f'渐变中点 {int(self.gradient_process[i][1] * 100)}')
            pass

            hbox = self.gradient_hbox_list[i]
            hbox.addWidget(self.checkbox_list[i])
            hbox.addWidget(self.color_btn_list[i])
            hbox.addWidget(self.label_list[i])
            hbox.addWidget(self.slider_list[i])
            self.gradient_slider_vbox.addLayout(hbox)

        for i in range(6):
            checkbox, colorbtn = self.checkbox_list[i], self.color_btn_list[i]
            label, slider = self.label_list[i], self.slider_list[i]
            checkbox.toggled.connect(self.on_gradient_check)
            colorbtn.clicked.connect(self.gradient_color_clicked)
            slider.valueChanged.connect(self.gradient_slider_change)


        self.confirm_btn = QPushButton('确认')
        self.confirm_btn.clicked.connect(self.confirm_clicked)

        self.content_widget = QWidget(self)
        self.vbox = QVBoxLayout(self.content_widget)
        self.vbox.addLayout(self.preview_vbox)
        self.vbox.addSpacing(5)
        self.vbox.addLayout(self.outline_hbox1)
        self.vbox.addSpacing(5)
        self.vbox.addLayout(self.outline_hbox2)
        self.vbox.addSpacing(30)
        self.vbox.addLayout(self.shadow_hbox1)
        self.vbox.addSpacing(5)
        self.vbox.addLayout(self.shadow_hbox2)
        self.vbox.addLayout(self.shadow_hbox3)
        self.vbox.addSpacing(30)
        self.vbox.addLayout(self.gradient_hbox)
        self.vbox.addLayout(self.gradient_slider_vbox)
        self.vbox.addWidget(self.confirm_btn)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidget(self.content_widget)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.view.setMinimumWidth(510)
        self.view.setFixedHeight(309)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.scroll_area)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)


    def dark_btn_clicked(self):
        self.dark_flag = not self.dark_flag
        if self.dark_flag:
            self.scene.setBackgroundBrush(QBrush(Qt.black))
        else:
            self.scene.setBackgroundBrush(QBrush(Qt.transparent))
        pass

    def outline_toggle_clicked(self):
        self.outline_enabled = not self.outline_enabled
        self.text_item1.enableOutline(self.outline_enabled)
        self.text_item2.enableOutline(self.outline_enabled)
        self.outline_color_btn.setEnabled(self.outline_enabled)
        self.outline_size_slider.setEnabled(self.outline_enabled)
        self.outline_color_label.setEnabled(self.outline_enabled)
        self.outline_size_label.setEnabled(self.outline_enabled)

    def outline_color_cliked(self):
        btn = self.sender()
        color = QColorDialog.getColor(btn.color, self)
        if color.isValid():
            btn.color = color
            btn.update()
            self.outline_color = color
            self.text_item1.setOutlineStyle(color, self.outline_thickess)
            self.text_item2.setOutlineStyle(color, self.outline_thickess)
        pass

    def outline_size_change(self, value: int):
        self.outline_size_label.setText(f'粗细 {value}')
        self.outline_thickess = value
        self.text_item1.setOutlineStyle(self.outline_color, value)
        self.text_item2.setOutlineStyle(self.outline_color, value)

    def shadow_toggle_clicked(self):
        self.shadow_flag = not self.shadow_flag
        if self.shadow_flag:
            self.shadow1 = QGraphicsDropShadowEffect()
            self.shadow1.setColor(self.shadow_color)
            self.shadow1.setBlurRadius(self.shadow_blur_size * self.shadow_vis_ratio)
            self.shadow1.setXOffset(self.shadow_x_offset * self.shadow_vis_ratio)
            self.shadow1.setYOffset(self.shadow_y_offset * self.shadow_vis_ratio)
            self.shadow2 = QGraphicsDropShadowEffect()
            self.shadow2.setColor(self.shadow_color)
            self.shadow2.setBlurRadius(self.shadow_blur_size * self.shadow_vis_ratio)
            self.shadow2.setXOffset(self.shadow_x_offset * self.shadow_vis_ratio)
            self.shadow2.setYOffset(self.shadow_y_offset * self.shadow_vis_ratio)
            self.text_item1.setGraphicsEffect(self.shadow1)
            self.text_item2.setGraphicsEffect(self.shadow2)
        else:
            self.text_item1.setGraphicsEffect(None)
            self.text_item2.setGraphicsEffect(None)

        self.shadow_color_btn.setEnabled(self.shadow_flag)
        self.shadow_blursize_slider.setEnabled(self.shadow_flag)
        self.shadow_xoffset_slider.setEnabled(self.shadow_flag)
        self.shadow_yoffset_slider.setEnabled(self.shadow_flag)
        self.shadow_color_label.setEnabled(self.shadow_flag)
        self.shadow_blursize_label.setEnabled(self.shadow_flag)
        self.shadow_xoffset_label.setEnabled(self.shadow_flag)
        self.shadow_yoffset_label.setEnabled(self.shadow_flag)

    def shadow_color_clicked(self):
        btn = self.sender()
        color = QColorDialog.getColor(btn.color, self)
        if color.isValid():
            btn.color = color
            btn.update()
            self.shadow_color = color
            self.shadow1.setColor(color)
            self.shadow2.setColor(color)
        pass

    def shadow_blursize_change(self, value):
        self.shadow_blursize_label.setText(f'模糊半径：{value}')
        self.shadow_blur_size = value
        self.shadow1.setBlurRadius(value * self.shadow_vis_ratio)
        self.shadow2.setBlurRadius(value * self.shadow_vis_ratio)

    def shadow_xoffset_change(self, value: int):
        self.shadow_xoffset_label.setText(f'X偏移量: {value}')
        self.shadow_x_offset = value
        self.shadow1.setXOffset(value * self.shadow_vis_ratio)
        self.shadow2.setXOffset(value * self.shadow_vis_ratio)

    def shadow_yoffset_change(self, value: int):
        self.shadow_yoffset_label.setText(f'Y偏移量: {value}')
        self.shadow_y_offset = value
        self.shadow1.setYOffset(value * self.shadow_vis_ratio)
        self.shadow2.setYOffset(value * self.shadow_vis_ratio)

    def gradient_toggle_clicked(self):
        self.gradient_flag = not self.gradient_flag
        self.text_item1.enableGradient(self.gradient_flag)
        self.text_item2.enableGradient(self.gradient_flag)
        if self.gradient_flag:
            self.text_item1.setDefaultTextColor(Qt.transparent)
            self.text_item2.setDefaultTextColor(Qt.transparent)
            self.text_item1.setGradientProcess(self.gradient_process)
            self.text_item2.setGradientProcess(self.gradient_process)
        else:
            self.text_item1.setDefaultTextColor(self.single_color)
            self.text_item2.setDefaultTextColor(self.single_color)

        self.single_color_btn.setEnabled(not self.gradient_flag)
        self.single_color_label.setEnabled(not self.gradient_flag)
        for i in range(6):
            checkbox, colorbtn = self.checkbox_list[i], self.color_btn_list[i]
            label, slider = self.label_list[i], self.slider_list[i]
            if i == 0 or i == 5:
                colorbtn.setEnabled(self.gradient_flag)
                label.setEnabled(self.gradient_flag)
            else:
                checkbox.setEnabled(self.gradient_flag)
                colorbtn.setEnabled(self.gradient_flag and checkbox.isChecked())
                label.setEnabled(self.gradient_flag and checkbox.isChecked())
                slider.setEnabled(self.gradient_flag and checkbox.isChecked())
            pass

    def single_color_clicked(self):
        btn = self.sender()
        color = QColorDialog.getColor(btn.color, self)
        if color.isValid():
            btn.color = color
            btn.update()
            self.single_color = color
            self.text_item1.setDefaultTextColor(color)
            self.text_item2.setDefaultTextColor(color)
        pass

    def on_gradient_check(self, checked):
        btn = self.sender()
        idx = 1
        for i in range(1, 5):
            if self.checkbox_list[i] is btn:
                idx = i
                break
        self.color_btn_list[idx].setEnabled(checked)
        self.label_list[idx].setEnabled(checked)
        self.slider_list[idx].setEnabled(checked)
        self.gradient_process[idx][0] = checked
        self.text_item1.setGradientProcess(self.gradient_process)
        self.text_item2.setGradientProcess(self.gradient_process)

    def gradient_color_clicked(self):
        btn = self.sender()
        idx = 0
        for i in range(6):
            if self.color_btn_list[i] is btn:
                idx = i
                break
        color = QColorDialog.getColor(btn.color, self)
        if color.isValid():
            btn.color = color
            btn.update()
            self.gradient_process[idx][2] = color
            self.text_item1.setGradientProcess(self.gradient_process)
            self.text_item2.setGradientProcess(self.gradient_process)

    def gradient_slider_change(self, value: int):
        btn = self.sender()
        idx = 1
        for i in range(1, 5):
            if self.slider_list[i] is btn:
                idx = i
                break
        self.label_list[idx].setText(f'渐变中点 {value}')
        self.gradient_process[idx][1] = 1.0 * value / 100
        self.text_item1.setGradientProcess(self.gradient_process)
        self.text_item2.setGradientProcess(self.gradient_process)

    def confirm_clicked(self):
        self.done(1)

    def resizeEvent(self, event):

        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        super().resizeEvent(event)

    def showEvent(self, event):

        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
        super().showEvent(event)
    pass


class FolderLabel(QLabel):
    def __init__(self, *args, **kwargs):
        super(FolderLabel, self).__init__(*args, **kwargs)
        pixmap = QPixmap(rpath('mold/folder.png'))
        pixmap = pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pixmap)
        self.setCursor(Qt.PointingHandCursor)
        self.tool_tip_text = '目前尚未选择卡图来源文件夹'

    def setText(self, s: str):
        self.tool_tip_text = s

    def enterEvent(self, event):

        if self.isEnabled():
            QToolTip.showText(self.mapToGlobal(self.rect().topLeft()) + QPoint(-50, -60),
                '开启后,检索卡片会优先使用本地图片作为卡图(图片须使用卡密作为文件名)\n' + self.tool_tip_text)
        super(FolderLabel, self).enterEvent(event)


class HelpButton(QPushButton):
    def __init__(self, has_border=False, border_color='black', bg_color='rgb(0,0,0)', question_color='white', parent=None):
        super().__init__('?', parent)
        self.setFixedSize(20, 20)
        border_style = f'border: 2px solid {border_color};' if has_border else 'border: none;'
        self.setStyleSheet(f'{border_style} border-radius: 10px; background-color: {bg_color}; color: {question_color};')
        self.setCursor(Qt.PointingHandCursor)
        self.helptext = '开启后，检索卡片时卡图会优先使用本地来源文件夹的图片(图片须使用卡密作为文件名)\n'
        self.extratext = '当前尚未选择本地卡图文件夹'

    def setHelpText(self, s: str):
        self.helptext = s

    def setExtraText(self, s: str):
        self.extratext = s


class RoundedPixmapItem(QGraphicsPixmapItem):
    def __init__(self, pixmap, radius=28):
        super().__init__(pixmap)
        self.radius = radius
        self.rounded = False

    def set_rounded(self, rounded):
        '设置是否启用圆角'
        self.rounded = rounded
        self.update()

    def paint(self, painter, option, widget=None):

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        if self.rounded:

            path = QPainterPath()
            rect = QRectF(0, 0, self.pixmap().width(), self.pixmap().height())
            path.addRoundedRect(rect, self.radius, self.radius)


            painter.setClipPath(path)


        painter.drawPixmap(0, 0, self.pixmap())


class BatchDialog(QDialog):
    def __init__(self, parent: 'OTCGWidget' = None):
        super().__init__(parent)
        self.setWindowTitle('批量制卡')
        self.setFixedSize(400, 500)
        self.parent_app = parent
        self.vbox = QVBoxLayout()

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText('输入YDK（每行一卡密）')
        self.btn = QPushButton('批量导出')
        self.btn.clicked.connect(self.on_btn_clicked)


        self.progress_bar = QProgressBar(self)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)

        self.vbox.addWidget(self.text_edit)
        self.vbox.addWidget(self.progress_bar)
        self.vbox.addWidget(self.btn)
        self.setLayout(self.vbox)

    def on_btn_clicked(self):
        res_path = QFileDialog.getExistingDirectory(self, '选择导出文件夹')
        if not res_path:
            return

        text_content = self.text_edit.toPlainText()
        line_list = text_content.splitlines()
        line_list = filter_strings(line_list)

        total = len(line_list)
        if total == 0:
            return

        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(total)


        self.progress_bar.setFormat(f'0/{total}')


        name_dict = defaultdict(int)
        for i, cardpass in enumerate(line_list):
            self.parent_app.card_pass_edit.setText(cardpass)
            self.parent_app.fetch_info()
            file_name = ''
            file_name = os.path.join(res_path, f'{cardpass}.png')
            if self.parent_app.info_fetcher.valid:
                self.parent_app.after_info_fetch()
                if self.parent_app.output_name == 0:
                    file_name = clean_filename(self.parent_app.card_name_edit.text())
                else:
                    file_name = remove_leading_zeros(self.parent_app.card_pass_edit.text())
                name_dict[file_name] += 1
                if name_dict[file_name] > 1:
                    file_name = file_name + f'({name_dict[file_name] - 1})'

                if self.parent_app.output_format == 0:
                    file_name = os.path.join(res_path, f'{file_name}.png')
                else:
                    file_name = os.path.join(res_path, f'{file_name}.jpg')
                self.parent_app.save_image(file_name)


            self.progress_bar.setValue(i + 1)
            self.progress_bar.setFormat(f'{i + 1}/{total}')

            QApplication.processEvents()
        pass

class OverFrameSettingDialog(QDialog):
    def __init__(self, parent: 'OTCGWidget' = None):
        super().__init__(parent)
        self.setWindowTitle('超框卡图设置')
        self.setFixedSize(400, 220)
        self.vbox = QVBoxLayout()
        self.pwid = parent

        metric = QFontMetrics(self.font())
        label_width = metric.width('99.9%')

        self.size_hbox = QHBoxLayout()
        self.size_label = QLabel('卡图尺寸:', self)
        self.size_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        num_text = '100%' if parent.overframe_scale == 1000 else f'{parent.overframe_scale * 1.0 / 10:.1f}%'
        self.size_num_label = QLabel(num_text)
        self.size_num_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.size_num_label.setFixedWidth(label_width)
        self.size_num_label.setAlignment(Qt.AlignRight)

        self.size_slider = QSlider(Qt.Horizontal, self)
        self.size_slider.setStyle(HollowHandleStyle())
        self.size_slider.setRange(100, 1000)
        self.size_slider.setValue(parent.overframe_scale)
        self.size_slider.valueChanged.connect(self.update_size)

        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(10.0, 100.0)
        self.size_spin.setDecimals(1)
        self.size_spin.setSingleStep(0.1)
        self.size_spin.setValue(parent.overframe_scale * 1.0 / 10)
        self.size_spin.valueChanged.connect(self.update_size_spin)

        self.size_hbox.addWidget(self.size_label)
        self.size_hbox.addWidget(self.size_num_label)
        self.size_hbox.addWidget(self.size_slider)
        self.size_hbox.addWidget(self.size_spin)

        self.posx_hbox = QHBoxLayout()
        self.posx_label = QLabel('横向位置:', self)
        self.posx_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.posx_num_label = QLabel(f'{parent.overframe_posx}')
        self.posx_num_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.posx_num_label.setFixedWidth(label_width)
        self.posx_num_label.setAlignment(Qt.AlignRight)

        self.posx_slider = QSlider(Qt.Horizontal, self)
        self.posx_slider.setStyle(HollowHandleStyle())
        self.posx_slider.setRange(0, 1626)
        self.posx_slider.setValue(parent.overframe_posx)
        self.posx_slider.valueChanged.connect(self.update_posx)

        self.posx_spin = QSpinBox()
        self.posx_spin.setRange(0, 1626)
        self.posx_spin.setValue(parent.overframe_posx)
        self.posx_spin.valueChanged.connect(self.update_posx)

        self.posx_hbox.addWidget(self.posx_label)
        self.posx_hbox.addWidget(self.posx_num_label)
        self.posx_hbox.addWidget(self.posx_slider)
        self.posx_hbox.addWidget(self.posx_spin)

        self.posy_hbox = QHBoxLayout()
        self.posy_label = QLabel('纵向位置:', self)
        self.posy_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.posy_num_label = QLabel(f'{parent.overframe_posy}')
        self.posy_num_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.posy_num_label.setFixedWidth(label_width)
        self.posy_num_label.setAlignment(Qt.AlignRight)

        self.posy_slider = QSlider(Qt.Horizontal, self)
        self.posy_slider.setStyle(HollowHandleStyle())
        self.posy_slider.setRange(0, 2370)
        self.posy_slider.setValue(parent.overframe_posy)
        self.posy_slider.valueChanged.connect(self.update_posy)

        self.posy_spin = QSpinBox()
        self.posy_spin.setRange(0, 2370)
        self.posy_spin.setValue(parent.overframe_posy)
        self.posy_spin.valueChanged.connect(self.update_posy)

        self.posy_hbox.addWidget(self.posy_label)
        self.posy_hbox.addWidget(self.posy_num_label)
        self.posy_hbox.addWidget(self.posy_slider)
        self.posy_hbox.addWidget(self.posy_spin)

        self.confirm_btn = QPushButton('关闭')
        self.confirm_btn.clicked.connect(self.on_confirm)
        self.vbox.addLayout(self.size_hbox)
        self.vbox.addLayout(self.posx_hbox)
        self.vbox.addLayout(self.posy_hbox)
        self.vbox.addStretch(1)
        self.vbox.addWidget(self.confirm_btn)
        self.setLayout(self.vbox)
        pass

    def update_size(self, value: int):
        self.pwid.overframe_scale = value
        num_text = '100%' if value == 1000 else f'{value * 1.0 / 10:.1f}%'
        self.size_num_label.setText(num_text)
        with QSignalBlocker(self.size_spin):
            self.size_spin.setValue(value * 1.0 / 10)
        sizex, sizey = int(self.pwid.overframe_sizex * value * 1.0 / 1000), int(self.pwid.overframe_sizey * value * 1.0 / 1000)
        self.pwid.of_display_img = self.pwid.overframe_img.resize((sizex, sizey), Image.Resampling.LANCZOS)
        self.pwid.of_display_img = pillow_img_to_pixmap(self.pwid.of_display_img)
        self.pwid.overframe_item.setPixmap(self.pwid.of_display_img)
        pass

    def update_size_spin(self, value: float):
        self.pwid.overframe_scale = int(value * 10)
        num_text = '100%' if value >= 100 else f'{value:.1f}%'
        self.size_num_label.setText(num_text)
        with QSignalBlocker(self.size_slider):
            self.size_slider.setValue(self.pwid.overframe_scale)
        sizex, sizey = int(self.pwid.overframe_sizex * value * 1.0 / 100), int(self.pwid.overframe_sizey * value * 1.0 / 100)
        self.pwid.of_display_img = self.pwid.overframe_img.resize((sizex, sizey), Image.Resampling.LANCZOS)
        self.pwid.of_display_img = pillow_img_to_pixmap(self.pwid.of_display_img)
        self.pwid.overframe_item.setPixmap(self.pwid.of_display_img)
        pass

    def update_posx(self, value: int):
        self.pwid.overframe_posx = value
        self.posx_num_label.setText(str(value))
        with QSignalBlocker(self.posx_slider):
            self.posx_slider.setValue(value)
        with QSignalBlocker(self.posx_spin):
            self.posx_spin.setValue(value)
        self.pwid.overframe_item.setPos(self.pwid.overframe_posx, self.pwid.overframe_posy)
        pass

    def update_posy(self, value: int):
        self.pwid.overframe_posy = value
        self.posy_num_label.setText(str(value))
        with QSignalBlocker(self.posy_slider):
            self.posy_slider.setValue(value)
        with QSignalBlocker(self.posy_spin):
            self.posy_spin.setValue(value)
        self.pwid.overframe_item.setPos(self.pwid.overframe_posx, self.pwid.overframe_posy)
        pass

    def on_confirm(self):
        self.done(1)
    pass

class OutputSettingDialog(QDialog):
    def __init__(self, HD_img: int, format: int, name: int, RD=False, parent: 'OTCGWidget' = None):
        super().__init__(parent)
        self.setWindowTitle('导出设置')
        self.setFixedSize(300, 180)
        self.vbox = QVBoxLayout()

        self.HD_img = HD_img
        self.format = format
        self.name = name

        if not RD:
            self.HD_hbox = QHBoxLayout()
            self.HD_label = QLabel('导出尺寸: ', self)
            self.HD_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            self.HD_selector = QComboBox(self)
            self.HD_selector.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
            self.HD_selector.addItems(['标准卡图', '高清卡图'])
            self.HD_selector.currentIndexChanged.connect(self.HD_change)
            self.HD_selector.setCurrentIndex(self.HD_img)
            self.HD_hbox.addWidget(self.HD_label)
            self.HD_hbox.addWidget(self.HD_selector)

        self.format_hbox = QHBoxLayout()
        self.format_label = QLabel('导出格式: ', self)
        self.format_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.format_selector = QComboBox(self)
        self.format_selector.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        self.format_selector.addItems(['PNG', 'JPG'])
        self.format_selector.currentIndexChanged.connect(self.format_change)
        self.format_selector.setCurrentIndex(self.format)
        self.format_hbox.addWidget(self.format_label)
        self.format_hbox.addWidget(self.format_selector)

        self.name_hbox = QHBoxLayout()
        self.name_label = QLabel('文件名称: ', self)
        self.name_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.name_selector = QComboBox(self)
        self.name_selector.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        self.name_selector.addItems(['卡名', '卡密'])
        self.name_selector.currentIndexChanged.connect(self.name_change)
        self.name_selector.setCurrentIndex(self.name)
        self.name_hbox.addWidget(self.name_label)
        self.name_hbox.addWidget(self.name_selector)

        self.confirm_btn = QPushButton('确认')
        self.confirm_btn.clicked.connect(self.on_confirm)
        if not RD:
            self.vbox.addLayout(self.HD_hbox)
        self.vbox.addLayout(self.format_hbox)
        self.vbox.addLayout(self.name_hbox)
        self.vbox.addStretch(1)
        self.vbox.addWidget(self.confirm_btn)
        self.setLayout(self.vbox)

    def HD_change(self, index: int):
        self.HD_img = index

    def format_change(self, index: int):
        self.format = index

    def name_change(self, index: int):
        self.name = index

    def on_confirm(self):
        self.done(1)
    pass


class OutputSettingDialogSimple(QDialog):
    def __init__(self, format: int, parent: 'OTCGWidget' = None):
        super().__init__(parent)
        self.setWindowTitle('导出设置')
        self.setFixedSize(300, 180)
        self.vbox = QVBoxLayout()
        self.format = format

        self.format_hbox = QHBoxLayout()
        self.format_label = QLabel('导出格式: ', self)
        self.format_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.format_selector = QComboBox(self)
        self.format_selector.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        self.format_selector.addItems(['PNG', 'JPG'])
        self.format_selector.currentIndexChanged.connect(self.format_change)
        self.format_selector.setCurrentIndex(self.format)
        self.format_hbox.addWidget(self.format_label)
        self.format_hbox.addWidget(self.format_selector)

        self.confirm_btn = QPushButton('确认')
        self.confirm_btn.clicked.connect(self.on_confirm)
        self.vbox.addLayout(self.format_hbox)
        self.vbox.addStretch(1)
        self.vbox.addWidget(self.confirm_btn)
        self.setLayout(self.vbox)

    def format_change(self, index: int):
        self.format = index

    def on_confirm(self):
        self.done(1)
    pass


class HollowHandleStyle(QProxyStyle):
    def __init__(self, config: dict = None):
        super().__init__()
        self.config = {
            'groove.height': 3,
            'sub-page.color': QColor(0, 0, 0),
            'add-page.color': QColor(255, 255, 255),
            'handle.color': QColor(0, 0, 0),
            'handle.ring-width': 2,
            'handle.hollow-radius': 5,
            'handle.margin': 0}

        config = config if config else {}
        self.config.update(config)

        w = (self.config['handle.margin'] + self.config['handle.ring-width'] +
            self.config['handle.hollow-radius'])
        self.config['handle.size'] = QSize(2 * w, 2 * w)

    def subControlRect(self, cc: QStyle.ComplexControl, opt: QStyleOptionSlider, sc: QStyle.SubControl, widget: QWidget):
        ' 返回子控件所占的矩形区域 '
        if cc != self.CC_Slider or opt.orientation != Qt.Horizontal or sc == self.SC_SliderTickmarks:
            return super().subControlRect(cc, opt, sc, widget)

        rect = opt.rect

        if sc == self.SC_SliderGroove:
            h = self.config['groove.height']
            grooveRect = QRectF(0, (rect.height() - h) // 2, rect.width(), h)
            return grooveRect.toRect()

        if sc == self.SC_SliderHandle:
            size = self.config['handle.size']
            x = self.sliderPositionFromValue(
                opt.minimum, opt.maximum, opt.sliderPosition, rect.width())

            x *= (rect.width() - size.width()) / rect.width()


            y = (rect.height() - size.height()) // 2

            sliderRect = QRectF(x, y, size.width(), size.height())
            return sliderRect.toRect()

    def drawComplexControl(self, cc: QStyle.ComplexControl, opt: QStyleOptionSlider, painter: QPainter, widget: QWidget):
        ' 绘制子控件 '
        if cc != self.CC_Slider or opt.orientation != Qt.Horizontal:
            return super().drawComplexControl(cc, opt, painter, widget)

        grooveRect = self.subControlRect(cc, opt, self.SC_SliderGroove, widget)
        handleRect = self.subControlRect(cc, opt, self.SC_SliderHandle, widget)
        painter.setRenderHints(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)


        painter.save()
        painter.translate(grooveRect.topLeft())


        w = handleRect.x() - grooveRect.x()
        h = self.config['groove.height']
        painter.setBrush(self.config['sub-page.color'])
        painter.drawRect(0, 0, w, h)


        x = w + self.config['handle.size'].width()
        painter.setBrush(self.config['add-page.color'])
        painter.drawRect(x, 0, grooveRect.width() - w, h)
        painter.restore()


        ringWidth = self.config['handle.ring-width']
        hollowRadius = self.config['handle.hollow-radius']
        radius = ringWidth + hollowRadius

        path = QPainterPath()
        path.moveTo(0, 0)
        center = handleRect.center() + QPoint(1, 1)
        path.addEllipse(center, radius, radius)
        path.addEllipse(center, hollowRadius, hollowRadius)

        handleColor = self.config['handle.color']
        handleColor.setAlpha((255 if (opt.activeSubControls !=
            self.SC_SliderHandle) else 153))
        painter.setBrush(handleColor)
        painter.drawPath(path)


        if widget.isSliderDown():
            handleColor.setAlpha(255)
            painter.setBrush(handleColor)
            painter.drawEllipse(handleRect)


class NameSearchDialog(QDialog):
    def __init__(self, text='', parent: 'OTCGWidget' = None):
        super().__init__(parent)
        self.setWindowTitle('卡名搜索')
        self.setFixedSize(550, 600)
        self.parent_app = parent
        self.card_max_num = 5
        self.img_height = 90
        self.img_width = 70

        self.vbox = QVBoxLayout()

        self.name_hbox = QHBoxLayout()
        self.text_edit = QLineEdit(self)
        self.text_edit.setPlaceholderText('卡名')
        self.text_edit.setText(text)
        self.text_edit.returnPressed.connect(self.search_btn_clicked)
        self.btn = RoundedButton(text='搜索', width=60, height=25)
        self.btn.setFixedWidth(60)
        self.btn.clicked.connect(self.search_btn_clicked)
        self.name_hbox.addWidget(self.text_edit)
        self.name_hbox.addWidget(self.btn)

        self.label_hbox = QHBoxLayout()
        self.nothing_label = QLabel('没有找到卡片', self)
        self.label_hbox.addStretch(0)
        self.label_hbox.addWidget(self.nothing_label)
        self.label_hbox.addStretch(0)
        self.nothing_label.setVisible(False)

        self.card_vbox = QVBoxLayout()
        self.text_font = self.font()
        self.text_font.setPixelSize(18)
        self.text_font.setBold(True)

        self.card_box_list = [QHBoxLayout() for _ in range(self.card_max_num)]
        self.text_box_list = [QVBoxLayout() for _ in range(self.card_max_num)]
        self.img_label_list = [QLabel('', self) for _ in range(self.card_max_num)]
        self.name_label_list = [QLabel('', self) for _ in range(self.card_max_num)]
        self.code_label_list = [QLabel('', self) for _ in range(self.card_max_num)]
        self.detail_label_list = [QLabel('', self) for _ in range(self.card_max_num)]
        self.btn_list = [RoundedButton(text='加载', width=60, height=25) for _ in range(self.card_max_num)]

        for i in range(self.card_max_num):
            box, text_box, name, code, detail, img_label, btn = (self.card_box_list[i], self.text_box_list[i], self.name_label_list[i],
                self.code_label_list[i], self.detail_label_list[i], self.img_label_list[i], self.btn_list[i])
            name.setFont(self.text_font)
            text_box.addWidget(name)
            text_box.addWidget(code)
            text_box.addWidget(detail)
            box.addWidget(img_label)
            box.addLayout(text_box)
            box.addWidget(btn)
            self.card_vbox.addLayout(box)
            if i < self.card_max_num - 1:
                self.card_vbox.addSpacing(10)
            img_label.setFixedHeight(self.img_height)
            img_label.setFixedWidth(self.img_width)
            btn.setVisible(False)
            btn.setEnabled(False)
            btn.setFixedWidth(80)
            btn.clicked.connect(self.btn_clicked)
            btn.setFixedWidth(60)

        self.current_page_edit = QLineEdit(self)
        self.current_page_edit.setFixedWidth(26)
        self.current_page_edit.setFixedHeight(16)
        self.current_page_edit.move(240, 579)
        self.current_page_edit.setValidator(QIntValidator())
        self.current_page_edit.returnPressed.connect(self.current_page_return)
        self.total_page_label = QLabel('', self)
        self.total_page_label.setFixedWidth(55)
        self.total_page_label.setFixedHeight(25)
        self.total_page_label.move(272, 576)
        self.total_page_label.setAlignment(Qt.AlignLeft)
        self.last_page_btn = RoundedButton(text='', width=20, height=20, btn_color=Qt.transparent, press_color=Qt.transparent, parent=self)
        self.last_page_btn.setIcon(QIcon(rpath('mold/last.png')))
        self.last_page_btn.setIconSize(15)
        self.last_page_btn.move(200, 579)
        self.last_page_btn.clicked.connect(self.last_page)

        self.next_page_btn = RoundedButton(text='', width=20, height=20, btn_color=Qt.transparent, press_color=Qt.transparent, parent=self)
        self.next_page_btn.setIcon(QIcon(rpath('mold/next.png')))
        self.next_page_btn.setIconSize(15)
        self.next_page_btn.move(335, 579)
        self.next_page_btn.clicked.connect(self.next_page)

        self.vbox.addLayout(self.name_hbox)
        self.vbox.addLayout(self.label_hbox)
        self.vbox.addSpacing(6)
        self.vbox.addLayout(self.card_vbox)
        self.vbox.addStretch(0)
        self.setLayout(self.vbox)
        self.init_vis()
        # 翻页控件放大、换成文字按钮（窗口尺寸定下来后再校正一次）；手动改搜索词时清掉高级搜索条件
        card_search._enhance_search_dialog_pagination(self)
        QTimer.singleShot(0, lambda dialog=self: card_search._enhance_search_dialog_pagination(dialog))
        self.text_edit.textEdited.connect(lambda _: setattr(self.fetcher, "_advanced_filters", None))

    def init_vis(self):
        self.threadpool = QThreadPool()
        self.fetcher = CardNameFetcher(page_size=self.card_max_num, img_height=self.img_height)
        self.total_page = 1
        self.current_page = 1

        self.loading_label = QLabel(self)
        self.loading_label.setFixedSize(50, 50)
        self.loading_label.hide()
        self.loading_movie = QMovie(rpath('mold/loading.gif'))
        self.loading_label.setMovie(self.loading_movie)
        pass

    def show_loading_gif(self):
        view_width = self.width()
        view_height = self.height()
        label_width = self.loading_label.width()
        label_height = self.loading_label.height()
        x = (view_width - label_width) // 2
        y = (view_height - label_height) // 2
        self.loading_label.setGeometry(x, y, label_width, label_height)
        self.loading_label.show()
        self.loading_movie.start()

    def hide_loading_gif(self):
        self.loading_label.hide()
        self.loading_movie.stop()

    def update_display(self, n):
        for i in range(self.card_max_num):
            visible = i < n
            self.name_label_list[i].setVisible(visible)
            self.code_label_list[i].setVisible(visible)
            self.detail_label_list[i].setVisible(visible)
            self.img_label_list[i].setVisible(visible)
            self.btn_list[i].setVisible(visible)
            self.btn_list[i].setEnabled(visible)
        self.nothing_label.setVisible(n == 0)
        self.total_page_label.setVisible(n != 0)
        self.current_page_edit.setVisible(n != 0)
        self.current_page_edit.setEnabled(n != 0)
        self.last_page_btn.setVisible(n != 0)
        self.last_page_btn.setEnabled(n != 0)
        self.next_page_btn.setVisible(n != 0)
        self.next_page_btn.setEnabled(n != 0)
        pass

    def fetch_info(self):
        self.fetcher.search_info(search_text=self.text_edit.text(), current_page=self.current_page)
        pass

    def after_info_fetch(self):
        info_len = self.fetcher.info_len
        for i in range(info_len):
            self.img_label_list[i].setPixmap(self.fetcher.card_img_list[i])
            self.name_label_list[i].setText(self.fetcher.name_list[i])
            self.code_label_list[i].setText(self.fetcher.code_list[i])
            self.detail_label_list[i].setText(self.fetcher.detail_list[i])
        self.btn.setEnabled(True)
        self.text_edit.setEnabled(True)
        self.total_page_label.setVisible(True)
        self.current_page_edit.setVisible(True)
        self.current_page_edit.setEnabled(True)
        self.last_page_btn.setVisible(True)
        self.last_page_btn.setEnabled(True)
        self.next_page_btn.setVisible(True)
        self.next_page_btn.setEnabled(True)
        for i in range(self.card_max_num):
            self.btn_list[i].setEnabled(True)
        self.total_page = math.ceil(self.fetcher.total_len / self.card_max_num)
        self.total_page_label.setText(f'/ {self.total_page} 页')
        self.update_display(info_len)
        self.hide_loading_gif()
        card_search._schedule_search_page_button_style(self)

    def search_btn_clicked(self):
        self.current_page = 1
        self.current_page_edit.setText('1')
        self.total_page_label.setVisible(False)
        self.current_page_edit.setVisible(False)
        self.current_page_edit.setEnabled(False)
        self.last_page_btn.setVisible(False)
        self.last_page_btn.setEnabled(False)
        self.next_page_btn.setVisible(False)
        self.next_page_btn.setEnabled(False)
        self.search_name()
        card_search._schedule_search_page_button_style(self)

    def search_name(self):
        if len(self.text_edit.text()) == 0:
            QToolTip.showText(self.text_edit.mapToGlobal(self.text_edit.rect().topLeft()) + QPoint(-3, -40),
                '无法搜索空名', self.text_edit)
            return
        worker = Worker(self.fetch_info)
        worker.signals.finished.connect(self.after_info_fetch)
        self.show_loading_gif()
        self.btn.setEnabled(False)
        self.text_edit.setEnabled(False)
        for i in range(self.card_max_num):
            self.btn_list[i].setEnabled(False)
        self.threadpool.start(worker)
        pass

    def btn_clicked(self):
        manager = getattr(self, '_card_tab_manager', None)
        if manager is not None:
            # 从标签页的「高级搜索」打开时，选中的卡加成新标签页
            button = self.sender()
            for index, candidate in enumerate(self.btn_list):
                if candidate is button:
                    manager.add_card_tab(self.code_label_list[index].text())
                    return
            return
        button = self.sender()
        for i in range(self.card_max_num):
            if self.btn_list[i] is button:
                self.parent_app.card_pass_edit.setText(self.code_label_list[i].text())
                break
        self.parent_app.on_cardpass_return()
        pass

    def current_page_return(self):
        num = int(self.current_page_edit.text())
        if num < 1:
            num = 1
            self.current_page_edit.setText('1')
        if num > self.total_page:
            num = self.total_page
            self.current_page_edit.setText(str(self.total_page))
        self.current_page = num
        self.current_page_edit.setEnabled(False)
        self.last_page_btn.setEnabled(False)
        self.next_page_btn.setEnabled(False)
        self.search_name()
        card_search._schedule_search_page_button_style(self)

    def last_page(self):
        page_num = int(self.current_page_edit.text()) - 1
        if page_num < 1: page_num = 1
        if page_num > self.total_page: page_num = self.total_page
        self.current_page = page_num
        self.current_page_edit.setText(str(page_num))
        self.current_page_edit.setEnabled(False)
        self.last_page_btn.setEnabled(False)
        self.next_page_btn.setEnabled(False)
        self.search_name()
        card_search._schedule_search_page_button_style(self)

    def next_page(self):
        page_num = int(self.current_page_edit.text()) + 1
        if page_num < 1: page_num = 1
        if page_num > self.total_page: page_num = self.total_page
        self.current_page = page_num
        self.current_page_edit.setText(str(page_num))
        self.current_page_edit.setEnabled(False)
        self.last_page_btn.setEnabled(False)
        self.next_page_btn.setEnabled(False)
        self.search_name()
        card_search._schedule_search_page_button_style(self)


class NotationWord(QGraphicsItem):

    def __init__(self, text: str = '', notation: str = '', x: int = 0, y: int = 0, text_font: QFont = QFont('Arial', 50),
        notation_font: QFont = QFont('Arial', 20)):
        super().__init__()
        self.text = text
        self.notation = notation
        self.text_item = QGraphicsTextItem()
        self.notation_item = MixTextItem()
        self.text_item.setDefaultTextColor(Qt.black)
        self.notation_item.setDefaultTextColor(Qt.black)
        self.text_item.document().setDocumentMargin(0)
        self.notation_item.document().setDocumentMargin(0)
        self.text_font = text_font
        self.notation_font = notation_font
        self.text_item.setFont(self.text_font)
        self.notation_item.setFont(self.notation_font)
        self.text_metric = QFontMetrics(self.text_font)
        self.notation_metric = QFontMetrics(self.notation_font)
        self.posx = x
        self.posy = y
        self.interval = -32
        self.text_x, self.text_y = (0, 0)
        self.notation_x, self.notation_y = (0, 0)
        self.narrow_ctrl = False
        self.narrow_wid_ratio = 0.8
        self.narrow_spacing = -1
        self.fontWid = 100
        self.calculate_pos()

    def boundingRect(self):
        height = self.text_metric.height()
        width = max(self.text_metric.horizontalAdvance(self.text), self.notation_metric.horizontalAdvance(self.notation))
        return QRectF(0, 0, width, height)

    def setFontWid(self, v: int):
        self.fontWid = v
        self.text_font.setStretch(self.fontWid)
        self.notation_font.setStretch(self.fontWid)
        self.text_metric = QFontMetrics(self.text_font)
        self.notation_metric = QFontMetrics(self.notation_font)
        self.text_item.setFont(self.text_font)
        self.notation_item.setFont(self.notation_font)

    def setFont(self, text_font: QFont, notation_font: QFont):
        self.text_font = text_font
        self.notation_font = notation_font
        self.text_item.setFont(self.text_font)
        self.notation_item.setFont(self.notation_font)
        self.text_metric = QFontMetrics(self.text_font)
        self.notation_metric = QFontMetrics(self.notation_font)
        self.calculate_pos()
        self.update()

    def narrowNotation(self):
        self.notation_font.setStretch(int(self.fontWid * self.narrow_wid_ratio))
        self.notation_font.setLetterSpacing(QFont.AbsoluteSpacing, self.narrow_spacing)
        self.notation_item.setFont(self.notation_font)
        self.notation_metric = QFontMetrics(self.notation_font)

    def setText(self, text: str, notation: str):
        self.text = text
        self.notation = notation[:30]
        if self.narrow_ctrl:
            self.notation_font.setStretch(self.fontWid)
            self.notation_font.setLetterSpacing(QFont.AbsoluteSpacing, 0)
            self.notation_metric = QFontMetrics(self.notation_font)
            self.notation_item.setFont(self.notation_font)
            if self.text_metric.horizontalAdvance(self.text) < self.notation_metric.horizontalAdvance(self.notation):
                self.narrowNotation()
        self.calculate_pos()
        self.update()

    def setXy(self, x: int, y: int):
        self.posx = x
        self.posy = y
        self.calculate_pos()
        self.update()

    def setInterval(self, v: int):
        self.interval = v

    def calculate_pos(self):
        if self.text_metric.horizontalAdvance(self.text) >= self.notation_metric.horizontalAdvance(self.notation):
            self.text_x = self.posx
            self.text_y = self.posy
            text_width = self.text_metric.horizontalAdvance(self.text)
            notation_width = self.notation_metric.horizontalAdvance(self.notation)
            self.notation_x = int(self.posx + text_width / 2 - notation_width / 2)
            self.notation_y = int(self.posy - self.interval - self.notation_metric.height())
        else:
            self.notation_x = self.posx
            self.text_y = self.posy
            text_width = self.text_metric.horizontalAdvance(self.text)
            notation_width = self.notation_metric.horizontalAdvance(self.notation)
            self.notation_y = int(self.posy - self.interval - self.notation_metric.height())
            self.text_x = int(self.posx + notation_width / 2 - text_width / 2)
        pass

    def paint(self, painter, option, widget):
        self.text_item.setPlainText(self.text)
        self.notation_item.setPlainText(self.notation)
        self.text_item.setPos(self.text_x, self.text_y)
        self.notation_item.setPos(self.notation_x, self.notation_y)
        self.text_item.setVisible(True)
        self.notation_item.setVisible(True)
    pass


class MixNotationWord(QGraphicsItem):
    def __init__(self, text: str = '', notation: str = '', x: int = 0, y: int = 0, text_font: QFont = QFont('Arial', 50),
        notation_font: QFont = QFont('Arial', 20)):
        super().__init__()
        self.text = text
        self.notation = notation
        self.text_item = MixTextItem()
        self.notation_item = MixTextItem()
        self.text_item.setDefaultTextColor(Qt.black)
        self.notation_item.setDefaultTextColor(Qt.black)
        self.text_item.document().setDocumentMargin(0)
        self.notation_item.document().setDocumentMargin(0)
        self.text_font = text_font
        self.notation_font = notation_font
        self.text_item.setFont(self.text_font)
        self.notation_item.setFont(self.notation_font)
        self.text_metric = QFontMetrics(self.text_font)
        self.notation_metric = QFontMetrics(self.notation_font)
        self.posx = x
        self.posy = y
        self.interval = -32
        self.text_x, self.text_y = (0, 0)
        self.notation_x, self.notation_y = (0, 0)
        self.fontWid = 100
        self.calculate_pos()

    def boundingRect(self):
        height = self.text_metric.height()
        width = max(self.text_metric.horizontalAdvance(self.text), self.notation_metric.horizontalAdvance(self.notation))
        return QRectF(0, 0, width, height)

    def setFontWid(self, v: int):
        self.fontWid = v
        self.text_font.setStretch(self.fontWid)
        self.notation_font.setStretch(self.fontWid)
        self.text_metric = QFontMetrics(self.text_font)
        self.notation_metric = QFontMetrics(self.notation_font)
        self.text_item.setFont(self.text_font)
        self.notation_item.setFont(self.notation_font)

    def setFont(self, text_font: QFont, notation_font: QFont):
        self.text_font = text_font
        self.notation_font = notation_font
        self.text_item.setFont(self.text_font)
        self.notation_item.setFont(self.notation_font)
        self.text_metric = QFontMetrics(self.text_font)
        self.notation_metric = QFontMetrics(self.notation_font)
        self.calculate_pos()
        self.update()

    def setText(self, text: str, notation: str):
        self.text = text
        self.notation = notation[:30]
        self.calculate_pos()
        self.update()

    def setXy(self, x: int, y: int):
        self.posx = x
        self.posy = y
        self.calculate_pos()
        self.update()

    def calculate_pos(self):
        if self.text_metric.horizontalAdvance(self.text) >= self.notation_metric.horizontalAdvance(self.notation):
            self.text_x = self.posx
            self.text_y = self.posy
            text_width = self.text_metric.horizontalAdvance(self.text)
            notation_width = self.notation_metric.horizontalAdvance(self.notation)
            self.notation_x = int(self.posx + text_width / 2 - notation_width / 2)
            self.notation_y = int(self.posy - self.interval - self.notation_metric.height())
        else:
            self.notation_x = self.posx
            self.text_y = self.posy
            text_width = self.text_metric.horizontalAdvance(self.text)
            notation_width = self.notation_metric.horizontalAdvance(self.notation)
            self.notation_y = int(self.posy - self.interval - self.notation_metric.height())
            self.text_x = int(self.posx + notation_width / 2 - text_width / 2)
        pass

    def paint(self, painter, option, widget):
        self.text_item.setPlainText(self.text)
        self.notation_item.setPlainText(self.notation)
        self.text_item.setPos(self.text_x, self.text_y)
        self.notation_item.setPos(self.notation_x, self.notation_y)
        self.text_item.setVisible(True)
        self.notation_item.setVisible(True)
    pass



class TextGroup(QGraphicsItemGroup):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ruby_items = []
        self.rt_items = []
        self.rubyFont = QFont('Arial', 20)
        self.rtFont = QFont('Arial', 20)

    def setRubyFont(self, font: QFont):
        self.rubyFont = font

    def setRubyFontSize(self, size: int):
        self.rubyFont.setPixelSize(size)

    def setRtFont(self, font: QFont):
        self.rtFont = font

    def setRtFontSize(self, size: int):
        self.rtFont.setPixelSize(size)

    def clear(self):
        for item in self.ruby_items:
            self.removeFromGroup(item)
            if item.scene():
                item.scene().removeItem(item)

            del item

        for item in self.rt_items:
            self.removeFromGroup(item)
            if item.scene():
                item.scene().removeItem(item)

            del item
        self.ruby_items.clear()
        self.rt_items.clear()


    def setName(self, itemLists: List[TextItem], enflag: bool, name_color: QColor, rtZoomRatio: float = 1,
        mix_mode_flag=False,
        gradient_flag=False,
        outline_enabled=False,
        outline_color=Qt.black,
        outline_thickess=1,
        gradient_process=[[True, 0, QColor(0, 0, 0)], [True, 1, QColor(255, 255, 255)]],
        edge_points=[0, 1],
        single_color=Qt.black):

        old_pos = self.pos()
        self.setPos(0, 0)
        self.clear()

        ruby_color = name_color
        if mix_mode_flag:
            ruby_color = Qt.transparent if gradient_flag else single_color
        duplicate = True if mix_mode_flag else False
        for item in itemLists:
            ruby, rt = item.ruby, item.rt
            if ruby.line == -1:
                continue
            rubytext = '\u200b' + ruby.text + '\u200b' if enflag else ruby.text
            ruby_item = MixTextItem(rubytext, duplicate=duplicate)
            ruby_item.setFont(self.rubyFont)
            ruby_item.setPos(ruby.x, ruby.y)
            ruby_item.setDefaultTextColor(ruby_color)
            if mix_mode_flag:
                ruby_item.enableOutline(outline_enabled)
                ruby_item.setOutlineStyle(outline_color, outline_thickess)
                ruby_item.setSingleColor(single_color)
                ruby_item.enableGradient(gradient_flag)
                ruby_item.setGradientProcess(gradient_process)
                ruby_item.setGradientEdge(edge_points[0], edge_points[1])
                if enflag:
                    ruby_item.setOffsetFlag(True)


            if ruby.scaleX < 1:
                transform = QTransform()
                transform.scale(ruby.scaleX, 1)
                ruby_item.setTransform(transform)
            self.addToGroup(ruby_item)
            self.ruby_items.append(ruby_item)

            if not (rt.text and ruby.text):
                continue
            rt_item = MixTextItem(rt.text)
            rtFont = QFont(self.rtFont)
            setting_letterspacing = rt.letterSpacing / rtZoomRatio
            rtFont.setLetterSpacing(QFont.AbsoluteSpacing, setting_letterspacing)
            rt_item.setFont(rtFont)
            rt_item.setDefaultTextColor(name_color)
            pos_x = rt.x - rt.letterSpacing / 2
            rtwidth = (rt.width + (len(rt.text) - 1) * rt.letterSpacing) * rt.scaleX

            rt_item.setScale(rtZoomRatio)

            rt_item.setPos(pos_x - rtwidth / 2, rt.y)
            if rt.scaleX < 1:
                transform = QTransform()
                transform.scale(rt.scaleX, 1)
                rt_item.setTransform(transform)
            self.addToGroup(rt_item)
            self.rt_items.append(rt_item)

        self.setPos(old_pos)

    def setTexts(self, itemLists: List[TextItem], fontweight: float = 0, rtZoomRatio: float = 1):
        old_pos = self.pos()
        self.setPos(0, 0)
        self.clear()
        for item in itemLists:
            ruby, rt = item.ruby, item.rt

            if ruby.line == -1:
                continue
            ruby_item = MixTextItem(ruby.text)
            ruby_item.setFont(self.rubyFont)
            ruby_item.setPos(ruby.x, ruby.y)
            if fontweight > 0:
                ruby_item.enableOutline(True)
                ruby_item.setOutlineStyle(color=Qt.black, thickness=fontweight)
            if ruby.scaleX < 1:
                transform = QTransform()
                transform.scale(ruby.scaleX, 1)
                ruby_item.setTransform(transform)
            self.addToGroup(ruby_item)
            self.ruby_items.append(ruby_item)

            if not (rt.text and ruby.text):
                continue
            rt_item = MixTextItem(rt.text)
            rtFont = QFont(self.rtFont)
            setting_letterspacing = rt.letterSpacing / rtZoomRatio
            rtFont.setLetterSpacing(QFont.AbsoluteSpacing, setting_letterspacing)
            rt_item.setFont(rtFont)
            pos_x = rt.x - rt.letterSpacing / 2
            rtwidth = (rt.width + (len(rt.text) - 1) * rt.letterSpacing) * rt.scaleX

            rt_item.setScale(rtZoomRatio)

            rt_item.setPos(pos_x - rtwidth / 2, rt.y)
            if rt.scaleX < 1:
                transform = QTransform()
                transform.scale(rt.scaleX, 1)
                rt_item.setTransform(transform)
            self.addToGroup(rt_item)
            self.rt_items.append(rt_item)

        self.setPos(old_pos)


class NameGroup(QGraphicsItemGroup):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ruby_items = [QGraphicsTextItem() for _ in range(300)]
        self.rt_items = [MixTextItem() for _ in range(300)]
        for ruby in self.ruby_items:
            ruby.document().setDocumentMargin(0)
        for rt in self.rt_items:
            rt.document().setDocumentMargin(0)
        self.rubyFont = QFont('Arial', 20)
        self.rtFont = QFont('Arial', 20)

    def setRubyFont(self, font: QFont):
        self.rubyFont = font

    def setRubyFontSize(self, size: int):
        self.rubyFont.setPixelSize(size)

    def setRtFont(self, font: QFont):
        self.rtFont = font

    def setRtFontSize(self, size: int):
        self.rtFont.setPixelSize(size)

    def clear(self):
        for item in self.ruby_items:
            item.setPlainText('')
            item.setTransform(QTransform())
            item.setScale(1.0)
            self.removeFromGroup(item)

        for item in self.rt_items:
            item.setPlainText('')
            item.setTransform(QTransform())
            item.setScale(1.0)
            self.removeFromGroup(item)

    def setName(self, itemLists: List[TextItem], enflag: bool, rt_color: QColor, name_color: QColor, rtZoomRatio: float = 1):
        old_pos = self.pos()
        self.setPos(0, 0)
        self.clear()

        ruby_color = name_color

        for i, item in enumerate(itemLists):
            ruby, rt = item.ruby, item.rt
            if ruby.line == -1:
                continue
            rubytext = '\u200b' + ruby.text + '\u200b' if enflag else ruby.text
            self.ruby_items[i].setPlainText(rubytext)
            self.ruby_items[i].setFont(self.rubyFont)
            self.ruby_items[i].setPos(ruby.x, ruby.y)
            self.ruby_items[i].setDefaultTextColor(ruby_color)

            if ruby.scaleX < 1:
                transform = QTransform()
                transform.scale(ruby.scaleX, 1)
                self.ruby_items[i].setTransform(transform)
            self.addToGroup(self.ruby_items[i])

            if not (rt.text and ruby.text):
                continue

            self.rt_items[i].setPlainText(rt.text)
            rtFont = QFont(self.rtFont)
            setting_letterspacing = rt.letterSpacing / rtZoomRatio
            rtFont.setLetterSpacing(QFont.AbsoluteSpacing, setting_letterspacing)
            self.rt_items[i].setFont(rtFont)
            self.rt_items[i].setDefaultTextColor(rt_color)
            pos_x = rt.x - rt.letterSpacing / 2
            rtwidth = (rt.width + (len(rt.text) - 1) * rt.letterSpacing) * rt.scaleX

            self.rt_items[i].setScale(rtZoomRatio)

            self.rt_items[i].setPos(pos_x - rtwidth / 2, rt.y)
            if rt.scaleX < 1:
                transform = QTransform()
                transform.scale(rt.scaleX, 1)
                self.rt_items[i].setTransform(transform)
            self.addToGroup(self.rt_items[i])

        self.setPos(old_pos)


class MixNameGroup(QGraphicsItemGroup):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ruby_items = [MixTextItem(duplicate=True) for _ in range(300)]
        self.rt_items = [MixTextItem() for _ in range(300)]
        for rt in self.rt_items:
            rt.document().setDocumentMargin(0)
        self.rubyFont = QFont('Arial', 20)
        self.rtFont = QFont('Arial', 20)

    def setRubyFont(self, font: QFont):
        self.rubyFont = font

    def setRubyFontSize(self, size: int):
        self.rubyFont.setPixelSize(size)

    def setRtFont(self, font: QFont):
        self.rtFont = font

    def setRtFontSize(self, size: int):
        self.rtFont.setPixelSize(size)

    def clear(self):
        for item in self.ruby_items:
            item.setPlainText('')
            item.setTransform(QTransform())
            item.setScale(1.0)
            self.removeFromGroup(item)

        for item in self.rt_items:
            item.setPlainText('')
            item.setTransform(QTransform())
            item.setScale(1.0)
            self.removeFromGroup(item)

    def setName(self, itemLists: List[TextItem], enflag: bool, rt_color: QColor, name_color: QColor, rtZoomRatio: float = 1,
        mix_mode_flag=False,
        gradient_flag=False,
        outline_enabled=False,
        outline_color=Qt.black,
        outline_thickess=1,
        gradient_process=[[True, 0, QColor(0, 0, 0)], [True, 1, QColor(255, 255, 255)]],
        edge_points=[0, 1],
        single_color=Qt.black):

        old_pos = self.pos()
        self.setPos(0, 0)
        self.clear()

        ruby_color = name_color
        if mix_mode_flag:
            ruby_color = Qt.transparent if gradient_flag else single_color

        for i, item in enumerate(itemLists):
            ruby, rt = item.ruby, item.rt
            if ruby.line == -1:
                continue
            rubytext = '\u200b' + ruby.text + '\u200b' if enflag else ruby.text
            self.ruby_items[i].setPlainText(rubytext)
            self.ruby_items[i].setFont(self.rubyFont)
            self.ruby_items[i].setPos(ruby.x, ruby.y)
            self.ruby_items[i].setDefaultTextColor(ruby_color)
            if mix_mode_flag:
                self.ruby_items[i].enableOutline(outline_enabled)
                self.ruby_items[i].setOutlineStyle(outline_color, outline_thickess)
                self.ruby_items[i].setSingleColor(single_color)
                self.ruby_items[i].enableGradient(gradient_flag)
                self.ruby_items[i].setGradientProcess(gradient_process)
                self.ruby_items[i].setGradientEdge(edge_points[0], edge_points[1])
                if enflag:
                    self.ruby_items[i].setOffsetFlag(True)


            if ruby.scaleX < 1:
                transform = QTransform()
                transform.scale(ruby.scaleX, 1)
                self.ruby_items[i].setTransform(transform)
            self.addToGroup(self.ruby_items[i])

            if not (rt.text and ruby.text):
                continue

            self.rt_items[i].setPlainText(rt.text)
            rtFont = QFont(self.rtFont)
            setting_letterspacing = rt.letterSpacing / rtZoomRatio
            rtFont.setLetterSpacing(QFont.AbsoluteSpacing, setting_letterspacing)
            self.rt_items[i].setFont(rtFont)
            self.rt_items[i].setDefaultTextColor(rt_color)
            pos_x = rt.x - rt.letterSpacing / 2
            rtwidth = (rt.width + (len(rt.text) - 1) * rt.letterSpacing) * rt.scaleX

            self.rt_items[i].setScale(rtZoomRatio)

            self.rt_items[i].setPos(pos_x - rtwidth / 2, rt.y)
            if rt.scaleX < 1:
                transform = QTransform()
                transform.scale(rt.scaleX, 1)
                self.rt_items[i].setTransform(transform)
            self.addToGroup(self.rt_items[i])

        self.setPos(old_pos)




if __name__ == '__main__':
    app = QApplication([])

    window = QWidget()
    layout = QVBoxLayout()


    btn = ColorSquare()
    layout.addWidget(btn)

    window.setLayout(layout)
    window.show()
    app.exec_()
