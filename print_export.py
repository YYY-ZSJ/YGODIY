"""按卡高 86 mm 等比导出，出血与标记位于成品之外。"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter, QPen

import app_preferences

CARD_HEIGHT_MM = 86
BLEED_MM = 3


def print_image(source):
    image = source.toImage() if hasattr(source, "toImage") else source
    if image.isNull():
        return image
    w, h = image.width(), image.height()
    pixels_per_mm = h / CARD_HEIGHT_MM
    x = y = max(1, round(BLEED_MM * pixels_per_mm))
    fmt = image.format() if image.format() in (QImage.Format_ARGB32_Premultiplied, QImage.Format_ARGB32,
                                               QImage.Format_RGB32, QImage.Format_RGB888) else QImage.Format_ARGB32
    result = QImage(w + 2*x, h + 2*y, fmt)
    result.fill(Qt.white)
    result.setDotsPerMeterX(round(pixels_per_mm * 1000))
    result.setDotsPerMeterY(round(pixels_per_mm * 1000))
    painter = QPainter(result)
    # 镜像展开边缘，中心的卡面像素保持在原尺寸。
    for dx, sx, sw, flip_x in ((0, 0, x, True), (x, 0, w, False), (x+w, w-x, x, True)):
        for dy, sy, sh, flip_y in ((0, 0, y, True), (y, 0, h, False), (y+h, h-y, y, True)):
            if flip_x or flip_y:
                painter.drawImage(dx, dy, image.copy(sx, sy, sw, sh).mirrored(flip_x, flip_y))
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawImage(x, y, image)
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
    for color, width in ((Qt.white, 0.35), (Qt.black, 0.15)):
        painter.setPen(QPen(color, max(1, round(width * pixels_per_mm))))
        for cx, sign_x in ((x, -1), (x+w, 1)):
            for cy, sign_y in ((y, -1), (y+h, 1)):
                painter.drawLine(cx + sign_x*x, cy, cx + sign_x*max(1, x//3), cy)
                painter.drawLine(cx, cy + sign_y*y, cx, cy + sign_y*max(1, y//3))
    painter.end()
    return result


def save_image(image, path, fmt, quality=-1):
    if app_preferences.get("print_bleed", False):
        image = print_image(image)
    return image.save(path, fmt, quality)
