"""秘密水印在灵摆卡上向上延伸。

由补丁分片 p16 整理而来。
"""

import traceback

from PIL import Image
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPixmap

from common import _call_original, _tab_log
from utils import rpath, runtime_resource_path


# ---------------------------------------------------------------------------
# Extend the secret watermark upward for Pendulum cards only.
# Also self-heals timing cases where the pendulum extension was skipped while
# card fields were still being loaded (watermark applied before detail_extra1
# became "灵摆"), or where the watermark was never rebuilt because signals were
# blocked during import.
# ---------------------------------------------------------------------------

def _secret_watermark_is_pendulum(self):
    try:
        return (
            getattr(self, "card_type", "") == "怪兽卡"
            and getattr(self, "detail_extra1", "") == "灵摆"
        )
    except Exception:
        _tab_log("secret watermark pendulum check error:\n" + traceback.format_exc())
        return False


# The six decorative squares on the pendulum text frame.
_SECRET_SQUARE_BOXES = (
    (100, 1475, 32, 32),
    (1494, 1475, 32, 32),
    (100, 1748, 32, 34),
    (1494, 1748, 32, 34),
    (100, 2200, 32, 40),
    (1494, 2200, 32, 40),
)
# Pixels just outside the black fill (the anti-aliased seam between the
# parchment and the frame border) are decided per pixel.
_SECRET_EDGE_OUTSIDE = 6
# Parchment (even its shaded rim) has a minimum channel above HIGH; the
# frame border, the squares and the teal card frame stay below LOW.
_SECRET_PARCHMENT_LOW = 100
_SECRET_PARCHMENT_HIGH = 140


def _qimage_rgba_array(image):
    import numpy as np

    image = image.convertToFormat(QImage.Format_RGBA8888)
    pointer = image.constBits()
    pointer.setsize(image.byteCount())
    rows = np.frombuffer(pointer, dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
    return rows[:, : image.width() * 4].reshape(image.height(), image.width(), 4).copy()


def _secret_mask_frame_edges(extended, base_pixmap, inner_rect):
    """Black out the light parchment the plain rectangle fill misses.

    Just outside the fill and in the six square boxes, every non-text
    pixel becomes black with an alpha taken from how light the card frame
    is there: parchment -> opaque, frame border / squares -> transparent,
    and their anti-aliased seam -> partial. The rest of the fill stays
    opaque, so borders and squares are the only frame parts left visible.
    """
    import numpy as np

    if base_pixmap.size() != extended.size():
        return extended
    left, top, right, bottom = inner_rect
    out = _SECRET_EDGE_OUTSIDE
    # Only the frame area is touched; work on that sub-image alone.
    x0 = max(0, min([left - out] + [box[0] for box in _SECRET_SQUARE_BOXES]))
    y0 = max(0, min([top - out] + [box[1] for box in _SECRET_SQUARE_BOXES]))
    x1 = min(extended.width(), max([right + out] + [box[0] + box[2] for box in _SECRET_SQUARE_BOXES]))
    y1 = min(extended.height(), max([bottom + out] + [box[1] + box[3] for box in _SECRET_SQUARE_BOXES]))
    if x1 <= x0 or y1 <= y0:
        return extended
    overlay = _qimage_rgba_array(extended.copy(x0, y0, x1 - x0, y1 - y0).toImage())
    base = _qimage_rgba_array(base_pixmap.copy(x0, y0, x1 - x0, y1 - y0).toImage())
    height, width = overlay.shape[:2]

    region = np.zeros((height, width), dtype=bool)
    region[max(0, top - out - y0):bottom + out - y0, max(0, left - out - x0):right + out - x0] = True
    region[top - y0:bottom - y0, left - x0:right - x0] = False
    for x, y, w, h in _SECRET_SQUARE_BOXES:
        region[y - y0:y - y0 + h, x - x0:x - x0 + w] = True

    # Keep the watermark lettering (anything brighter than the black fill).
    is_text = (overlay[:, :, 3] > 0) & (overlay[:, :, :3].max(axis=2) > 60)
    region &= ~is_text

    lightness = base[:, :, :3].min(axis=2).astype(np.float32)
    span = float(_SECRET_PARCHMENT_HIGH - _SECRET_PARCHMENT_LOW)
    alpha = np.clip((lightness - _SECRET_PARCHMENT_LOW) * (255.0 / span), 0, 255)
    overlay[region, :3] = 0
    overlay[region, 3] = alpha[region].astype(np.uint8)

    patch = QImage(overlay.tobytes(), width, height, width * 4, QImage.Format_RGBA8888).copy()
    result = QPixmap(extended)
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawImage(x0, y0, patch)
    painter.end()
    return result


# The extended pixmap only depends on the watermark file, the pendulum
# text position and the card frame underneath, but it is requested several
# times per card switch. Keep the last few results.
_SECRET_EXTENDED_CACHE = {}
_SECRET_EXTENDED_CACHE_LIMIT = 8
_SECRET_SOURCE_CACHE = {}


def _secret_source(path):
    """Watermark pixmap and the bounding box of its opaque part (cached)."""
    cached = _SECRET_SOURCE_CACHE.get(path)
    if cached is not None:
        return cached
    source = QPixmap(rpath(path))
    if source.isNull():
        return source, None
    alpha_box = None
    try:
        with Image.open(runtime_resource_path(path)) as image:
            alpha_box = image.convert("RGBA").getchannel("A").getbbox()
    except Exception:
        pass
    _SECRET_SOURCE_CACHE[path] = (source, alpha_box)
    return source, alpha_box


def _extend_secret_watermark_for_pendulum(self):
    """Rebuild the secret watermark pixmap extended over the pendulum area.

    Idempotent: keeps the six decorative squares and the text frame
    borders visible (see _secret_mask_frame_edges). Geometry is unchanged
    from the original patch.
    """
    watermark_paths = getattr(self.config, "watermark_img", {}).get("secret")
    if not isinstance(watermark_paths, (list, tuple)) or len(watermark_paths) < 2:
        return
    path = watermark_paths[1]
    base_item = getattr(self, "base_item", None)
    base_pixmap = base_item.pixmap() if base_item is not None else QPixmap()
    has_base = base_pixmap is not None and not base_pixmap.isNull()
    cache_key = (
        path,
        int(getattr(self.config, "lb_text_y", 1500)),
        base_pixmap.cacheKey() if has_base else None,
    )
    cached = _SECRET_EXTENDED_CACHE.get(cache_key)
    if cached is not None:
        self.watermark_item.setPixmap(cached)
        self.watermark_item.setZValue(1000.0)
        self.watermark_item.setVisible(True)
        return
    source, alpha_box = _secret_source(path)
    if source.isNull():
        return
    source_top = 1771
    source_bottom = 2229
    source_left = 110
    source_right = 1514
    if alpha_box:
        source_left = int(alpha_box[0])
        source_top = int(alpha_box[1])
        source_right = max(source_left + 1, int(alpha_box[2]) - 1)
        source_bottom = max(source_top + 1, int(alpha_box[3]) - 1)
    inner_left = max(0, source_left + 1)
    inner_right = min(source.width() - 1, source_right - 1)
    inner_top = max(0, int(getattr(self.config, "lb_text_y", 1500)) - 9)
    inner_bottom = min(source.height() - 1, source_bottom - 1)
    inner_width = max(1, inner_right - inner_left)
    inner_height = max(1, inner_bottom - inner_top)
    source_width = max(1, source_right - source_left)
    source_height = max(1, source_bottom - source_top)
    scale_x = float(inner_width) / float(source_width)
    scale_y = float(inner_height) / float(source_height)
    extended = QPixmap(source.size())
    extended.fill(Qt.transparent)
    painter = QPainter(extended)
    # Cover the complete inner area, including the middle bar.
    painter.fillRect(inner_left, inner_top, inner_width, inner_height, QColor(0, 0, 0, 255))
    painter.save()
    painter.setClipRect(inner_left, inner_top, inner_width, inner_height)
    painter.translate(float(inner_left), float(inner_bottom))
    painter.scale(float(scale_x), float(scale_y))
    painter.translate(-float(source_left), -float(source_bottom))
    painter.drawPixmap(0, 0, source)
    painter.restore()
    painter.end()
    if has_base:
        try:
            extended = _secret_mask_frame_edges(
                extended,
                base_pixmap,
                (inner_left, inner_top, inner_left + inner_width, inner_top + inner_height),
            )
        except Exception:
            _tab_log("secret watermark edge mask error:\n" + traceback.format_exc())
    _SECRET_EXTENDED_CACHE[cache_key] = extended
    while len(_SECRET_EXTENDED_CACHE) > _SECRET_EXTENDED_CACHE_LIMIT:
        _SECRET_EXTENDED_CACHE.pop(next(iter(_SECRET_EXTENDED_CACHE)))
    self.watermark_item.setPixmap(extended)
    self.watermark_item.setZValue(1000.0)
    self.watermark_item.setVisible(True)


def _secret_watermark_recheck(self):
    """Re-evaluate the secret watermark against the final card state.

    Called deferred after load chains finish, so pendulum cards whose
    fields were not yet populated at watermark time still get the extended
    coverage, and non-pendulum cards fall back to the plain watermark.
    """
    try:
        selector = getattr(self, "water_selector", None)
        item = getattr(self, "watermark_item", None)
        if selector is None or item is None:
            return
        if selector.currentText() != "secret":
            return
        if _secret_watermark_is_pendulum(self):
            _extend_secret_watermark_for_pendulum(self)
        else:
            self._standard_watermark_change()
            item.setZValue(0.0)
    except Exception:
        _tab_log("secret watermark recheck error:\n" + traceback.format_exc())


def _schedule_secret_watermark_recheck(self):
    """Defer a recheck to the next event-loop turn (idempotent, re-entry safe)."""
    try:
        if getattr(self, "_secret_wm_recheck_pending", False):
            return
        self._secret_wm_recheck_pending = True

        def _run():
            try:
                self._secret_wm_recheck_pending = False
            except Exception:
                pass
            _secret_watermark_recheck(self)

        try:
            QTimer.singleShot(0, _run)
        except Exception:
            self._secret_wm_recheck_pending = False
            _secret_watermark_recheck(self)
    except Exception:
        _tab_log("secret watermark recheck schedule error:\n" + traceback.format_exc())


def _watermark_change_with_pendulum(self):
    self._standard_watermark_change()
    try:
        current_text = self.water_selector.currentText()
        if current_text != "secret":
            return
        if not _secret_watermark_is_pendulum(self):
            try:
                self.watermark_item.setZValue(0.0)
            except Exception:
                pass
            # During load chains the pendulum subtype may be populated
            # after this call; re-check once the chain settles.
            _schedule_secret_watermark_recheck(self)
            return
        _extend_secret_watermark_for_pendulum(self)
    except Exception:
        _tab_log("secret watermark pendulum extend error:\n" + traceback.format_exc())


def _recheck_secret_watermark_after(method):
    """宿主方法的装饰器：方法执行完后，在下一轮事件循环按最终的卡片状态重查一次秘密水印。

    用于打开卡片、换卡种 / 灵摆比例 / Zack、查卡完成、随机一卡这些会改变「是不是灵摆卡」的入口。
    """
    def wrapped(self, *args, **kwargs):
        # Qt 信号可能多传参数（如 clicked -> bool），按原方法签名裁掉，否则槽函数里的 TypeError 会让程序退出
        result = _call_original(method, self, args, kwargs)
        try:
            _schedule_secret_watermark_recheck(self)
        except Exception:
            _tab_log("secret watermark wrap %s error:\n" % method.__name__ + traceback.format_exc())
        return result

    wrapped.__name__, wrapped.__qualname__, wrapped.__doc__ = method.__name__, method.__qualname__, method.__doc__
    wrapped.__wrapped__ = method
    return wrapped
