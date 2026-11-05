"""超框卡图：可拖动的超框图元、图层叠放顺序、RD / OCG 多图层与模式间同步。

由补丁分片 p13、p14、p15、p46、p47 整理而来。
"""

import base64
import io
import time
import traceback

from PIL import Image
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGraphicsPixmapItem,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
)

from common import (
    _RARE_FRONT_Z,
    _attach_editor_button,
    _bounded_cache_get,
    _bounded_cache_put,
    _call_original,
    _pixmap_from_pillow,
    _safe_call,
    _set_item_visible,
    _set_toggle_checked_silent,
    _tab_log,
    _widget_scene,
)


# ---------------------------------------------------------------------------
# 超框卡图拖动（对应 YGOLD 的 OverFramePixmapItem + on_overframe_position_changed）
# ---------------------------------------------------------------------------
_OVERFRAME_DRAG_LIMIT_X = 1626
_OVERFRAME_DRAG_LIMIT_Y = 2370
# 超框图层的出框方式：半出框只能在卡片底边之上，全出框不受限。
_RD_OVERFRAME_MODE_HALF = "half"
_RD_OVERFRAME_MODE_FULL = "full"
_RD_OVERFRAME_MODE_LABELS = (
    (_RD_OVERFRAME_MODE_HALF, "半出框"),
    (_RD_OVERFRAME_MODE_FULL, "全出框"),
)
_RD_OVERFRAME_MODE_NAMES = {value: label for value, label in _RD_OVERFRAME_MODE_LABELS}
_RD_OVERFRAME_MAX_LAYERS = 32
_OVERFRAME_ITEM_CLASS = None
# 滚轮缩放超框卡图：每格倍率与上下限（上下限同设置对话框「卡图尺寸」滑块 10%~300%）
_OVERFRAME_WHEEL_STEP = 1.05
_OVERFRAME_WHEEL_MIN_SCALE = 0.1
_OVERFRAME_WHEEL_MAX_SCALE = 3.0

# 点中超框卡图时沿图像轮廓（按透明度）发光，方便确认正在操作哪一层。
# 只画在屏幕上的预览里：导出走 scene.render()，那时 paint 收到的 widget 是 None，不画。
_OVERFRAME_GLOW_RGB = (0, 229, 255)
_OVERFRAME_GLOW_RADIUS = 6.0          # 发光主体宽度（屏幕像素）
_OVERFRAME_GLOW_PAD = 3.0             # 光晕外缘 = 半径 × 3（屏幕像素）
_OVERFRAME_GLOW_HOLD = 1.2            # 最后一次点击 / 拖动 / 滚轮之后保持全亮的秒数
_OVERFRAME_GLOW_FADE_STEP = 0.1       # 每次刷新（30ms）减弱的亮度，约 0.3 秒淡出
_OVERFRAME_GLOW_MAX_SIDE = 512        # 光晕图最大边长；更大时按比例生成后放大
_OVERFRAME_GLOW_SIZE_BUCKET = 1.15    # 屏幕上的尺寸变化超过 15% 才重新生成光晕图
_OVERFRAME_GLOW_WHEEL_SETTLE = 0.25   # 滚轮停下这么久之后才按新尺寸重新生成光晕图
_OVERFRAME_GLOW_STATE = {"item": None, "level": 0.0, "hold_until": 0.0, "timer": None}


def _overframe_glow_mask(pixmap):
    """图像的发光色剪影（最大边 _OVERFRAME_GLOW_MAX_SIDE），每张图只做一次。"""
    from PyQt5.QtGui import QColor, QImage, QPainter

    ratio = min(1.0, _OVERFRAME_GLOW_MAX_SIDE / float(max(1, pixmap.width(), pixmap.height())))
    small = pixmap.toImage().convertToFormat(QImage.Format_ARGB32_Premultiplied).scaled(
        max(1, int(pixmap.width() * ratio)), max(1, int(pixmap.height() * ratio)),
        Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
    )
    tinted = QImage(small.size(), QImage.Format_ARGB32_Premultiplied)
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.drawImage(0, 0, small)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(*_OVERFRAME_GLOW_RGB))
    painter.end()
    return tinted


def _overframe_glow_image(mask, out_w, out_h, radius):
    """把剪影缩到 out 尺寸，向外扩出一圈发光，返回 (QImage, 外扩像素)。"""
    import math

    from PyQt5.QtCore import QPointF
    from PyQt5.QtGui import QImage, QPainter

    tinted = mask.scaled(out_w, out_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    pad = int(math.ceil(radius * _OVERFRAME_GLOW_PAD)) + 1
    canvas = QImage(out_w + 2 * pad, out_h + 2 * pad, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    # 由外到内：外圈淡、内圈实，叠成由亮到暗的光晕
    for distance, opacity in ((radius * 2.6, 0.18), (radius * 1.8, 0.35), (radius, 0.75), (radius * 0.5, 1.0)):
        painter.setOpacity(opacity)
        for step in range(12):
            angle = step * math.pi / 6
            painter.drawImage(
                QPointF(pad + math.cos(angle) * distance, pad + math.sin(angle) * distance), tinted
            )
    painter.end()
    # 缩小再放大一遍，把一圈圈的偏移糊成柔和的光
    soft = canvas.scaled(
        max(1, canvas.width() // 3), max(1, canvas.height() // 3), Qt.IgnoreAspectRatio, Qt.SmoothTransformation
    ).scaled(canvas.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    painter = QPainter(soft)
    painter.drawImage(0, 0, canvas)
    painter.end()
    return soft, pad


def _overframe_glow_device_scale(item):
    """图层的一个本地单位在屏幕上占多少像素（含视图缩放与图层自身的 scale）。"""
    try:
        scene = item.scene()
        views = scene.views() if scene is not None else []
        view_scale = abs(views[0].transform().m11()) if views else 1.0
    except Exception:
        view_scale = 1.0
    return max(1e-4, view_scale * (item.scale() or 1.0))


def _overframe_glow_set_margin(item):
    """发光会画到图像外面，边界矩形要随之放大（否则外圈刷不出来）。"""
    margin = (_OVERFRAME_GLOW_RADIUS * _OVERFRAME_GLOW_PAD + 2) / _overframe_glow_device_scale(item)
    if abs(getattr(item, "_glow_margin", 0.0) - margin) > 1e-3:
        item.prepareGeometryChange()
        item._glow_margin = margin


def _overframe_glow_clear(item):
    try:
        if getattr(item, "_glow_margin", 0.0):
            item.prepareGeometryChange()
            item._glow_margin = 0.0
        item.update()
    except RuntimeError:
        pass  # 图层已被删除


def _overframe_glow_tick():
    state = _OVERFRAME_GLOW_STATE
    item = state["item"]
    if item is None:
        if state["timer"] is not None:
            state["timer"].stop()
        return
    if time.monotonic() < state["hold_until"]:
        state["level"] = 1.0
    else:
        state["level"] -= _OVERFRAME_GLOW_FADE_STEP
    if state["level"] <= 0.0:
        state["item"], state["level"] = None, 0.0
        _overframe_glow_clear(item)
        if state["timer"] is not None:
            state["timer"].stop()
        return
    try:
        item.update()
    except RuntimeError:
        state["item"] = None


def _overframe_glow_touch(item):
    """点击 / 拖动 / 滚轮：让这一层发光（同时只有一层发光），停手后保持一会儿再淡出。"""
    state = _OVERFRAME_GLOW_STATE
    previous = state["item"]
    if previous is not None and previous is not item:
        _overframe_glow_clear(previous)
    state["item"], state["level"] = item, 1.0
    state["hold_until"] = time.monotonic() + _OVERFRAME_GLOW_HOLD
    _overframe_glow_set_margin(item)
    item.update()
    if state["timer"] is None:
        state["timer"] = QTimer()
        state["timer"].setInterval(30)
        state["timer"].timeout.connect(_overframe_glow_tick)
    if not state["timer"].isActive():
        state["timer"].start()


def _overframe_item_class():
    """构建可拖动的超框图形项类（首次调用时创建）。"""
    global _OVERFRAME_ITEM_CLASS
    if _OVERFRAME_ITEM_CLASS is not None:
        return _OVERFRAME_ITEM_CLASS
    from PyQt5.QtCore import QPointF, QRectF
    from PyQt5.QtGui import QPainter, QPainterPath, QPixmap
    from PyQt5.QtWidgets import QGraphicsItem, QGraphicsPixmapItem

    class _OverFramePixmapItem(QGraphicsPixmapItem):
        def __init__(self, pixmap=None, radius=28):
            super().__init__(pixmap if pixmap is not None else QPixmap())
            self.radius = radius
            self.rounded = False
            self.setFlag(QGraphicsItem.ItemIsMovable, True)
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            self.min_x = -_OVERFRAME_DRAG_LIMIT_X
            self.max_x = _OVERFRAME_DRAG_LIMIT_X
            self.min_y = -_OVERFRAME_DRAG_LIMIT_Y
            self.max_y = _OVERFRAME_DRAG_LIMIT_Y
            self.mode = _RD_OVERFRAME_MODE_FULL
            # 半出框的下边界（默认整卡下缘，实际由卡图区底边决定，见 p14 的同步）。
            self.bottom_limit = _OVERFRAME_DRAG_LIMIT_Y
            self.position_changed_callback = None
            # 滚轮改尺寸后回调 (scale × 1000)，由各模式写回自己的图层数据
            self.scale_changed_callback = None
            self._drag_scene_start = None
            self._drag_item_start = None
            # 发光轮廓：外扩边距（本地单位，0 = 不发光）与光晕图缓存
            self._glow_margin = 0.0
            self._glow_cache = None
            # 删除这一层（Del 键 / 右键菜单）时调用，由各模式删掉自己图层列表里的对应项
            self.delete_callback = None
            # 点中后取得场景焦点，Del 才会发到这一层；焦点回到文本框时 Del 照常删字
            self.setFlag(QGraphicsItem.ItemIsFocusable, True)
            self.setAcceptedMouseButtons(Qt.LeftButton)

        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                self._drag_scene_start = event.scenePos()
                self._drag_item_start = self.pos()
                self.setFocus(Qt.MouseFocusReason)
                _overframe_glow_touch(self)
                event.accept()
                return
            super().mousePressEvent(event)

        def _delete_layer(self):
            callback = getattr(self, "delete_callback", None)
            if callback is None:
                return False
            state = _OVERFRAME_GLOW_STATE
            if state["item"] is self:
                state["item"], state["level"] = None, 0.0
            _overframe_glow_clear(self)
            self.clearFocus()
            try:
                callback()
            except Exception:
                _tab_log("删除超框卡图图层失败:\n" + traceback.format_exc())
                return False
            return True

        def keyPressEvent(self, event):
            if event.key() == Qt.Key_Delete and getattr(self, "delete_callback", None) is not None:
                self._delete_layer()
                event.accept()
                return
            super().keyPressEvent(event)

        def contextMenuEvent(self, event):
            if getattr(self, "delete_callback", None) is None:
                event.ignore()
                return
            from PyQt5.QtWidgets import QMenu

            self.setFocus(Qt.PopupFocusReason)
            _overframe_glow_touch(self)  # 菜单弹出时也亮着，确认是哪一层
            menu = QMenu()
            delete_action = menu.addAction("删除")
            delete_action.setShortcut(Qt.Key_Delete)
            chosen = menu.exec_(event.screenPos())
            if chosen is delete_action:
                self._delete_layer()
            else:
                _overframe_glow_touch(self)  # 取消菜单后从此刻起再亮一会儿
            event.accept()

        def mouseMoveEvent(self, event):
            if (
                self._drag_scene_start is not None
                and self._drag_item_start is not None
                and event.buttons() & Qt.LeftButton
            ):
                delta = event.scenePos() - self._drag_scene_start
                self.setPos(self._drag_item_start + delta)
                _overframe_glow_touch(self)
                event.accept()
                return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.LeftButton:
                self._drag_scene_start = None
                self._drag_item_start = None
                _overframe_glow_touch(self)  # 从松手起再亮一会儿
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def boundingRect(self):
            rect = super().boundingRect()
            margin = getattr(self, "_glow_margin", 0.0)
            return rect.adjusted(-margin, -margin, margin, margin) if margin else rect

        def _paint_glow(self, painter, pixmap):
            state = _OVERFRAME_GLOW_STATE
            if state["item"] is not self or state["level"] <= 0.0:
                return
            import math

            transform = painter.worldTransform()
            device_scale = math.sqrt(abs(transform.determinant())) or 1.0
            screen_w = pixmap.width() * device_scale
            screen_h = pixmap.height() * device_scale
            ratio = min(1.0, _OVERFRAME_GLOW_MAX_SIDE / max(1.0, screen_w, screen_h))
            out_w, out_h = max(1, int(screen_w * ratio)), max(1, int(screen_h * ratio))
            bucket = int(round(math.log(max(1.0, screen_w)) / math.log(_OVERFRAME_GLOW_SIZE_BUCKET)))
            key = (pixmap.cacheKey(), bucket)
            cache = self._glow_cache
            # 滚轮缩放过程中沿用旧的光晕图（跟着图像一起拉伸），停手后再按新尺寸重做，
            # 免得每滚几格就重新生成一次光晕而卡顿。
            wheeling = time.monotonic() - getattr(self, "_glow_wheel_time", 0.0) < _OVERFRAME_GLOW_WHEEL_SETTLE
            if cache is None or (cache[0] != key and not (wheeling and cache[0][0] == key[0])):
                mask = getattr(self, "_glow_mask", None)
                if mask is None or mask[0] != key[0]:
                    mask = self._glow_mask = (key[0], _overframe_glow_mask(pixmap))
                image, pad = _overframe_glow_image(
                    mask[1], out_w, out_h, max(1.5, _OVERFRAME_GLOW_RADIUS * ratio)
                )
                cache = self._glow_cache = (key, image, pad, out_w)
            _key, image, pad, cached_w = cache
            pad_local = pad * pixmap.width() / float(cached_w)
            target = QRectF(
                -pad_local, -pad_local, pixmap.width() + 2 * pad_local, pixmap.height() + 2 * pad_local
            )
            painter.save()
            try:
                if self.mode == _RD_OVERFRAME_MODE_HALF:
                    # 半出框：插画区下边缘以下被遮住的部分不发光
                    local_bottom = (self.bottom_limit - self.pos().y()) / (self.scale() or 1.0)
                    painter.setClipRect(
                        QRectF(target.left(), target.top(), target.width(), max(0.0, local_bottom - target.top()))
                    )
                painter.setOpacity(state["level"])
                painter.drawImage(target, image)
            finally:
                painter.restore()

        def wheelEvent(self, event):
            """滚轮调整尺寸：每格 ±5%，范围与设置对话框的「卡图尺寸」一致（10%~300%），
            以鼠标所在点为中心缩放（光标下的那一点不动）。"""
            try:
                steps = event.delta() / 120.0
            except Exception:
                steps = 0.0
            if not steps:
                super().wheelEvent(event)
                return
            old_scale = self.scale() or 1.0
            new_scale = max(
                _OVERFRAME_WHEEL_MIN_SCALE,
                min(_OVERFRAME_WHEEL_MAX_SCALE, old_scale * (_OVERFRAME_WHEEL_STEP ** steps)),
            )
            if abs(new_scale - old_scale) > 1e-6:
                anchor = event.pos()
                before = self.mapToScene(anchor)
                self.setScale(new_scale)
                after = self.mapToScene(anchor)
                # setPos 会经 itemChange 触发 position_changed_callback，位置一并写回
                self.setPos(self.pos() + (before - after))
                callback = getattr(self, "scale_changed_callback", None)
                if callback is not None:
                    try:
                        callback(int(round(new_scale * 1000)))
                    except Exception:
                        pass
            self._glow_wheel_time = time.monotonic()
            _overframe_glow_touch(self)
            event.accept()

        def set_rounded(self, rounded):
            self.rounded = bool(rounded)
            self.update()

        def paint(self, painter, option, widget=None):
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            pixmap = self.pixmap()
            if pixmap is None or pixmap.isNull():
                return
            if widget is not None:  # 只在屏幕预览里发光；导出用的 scene.render() 不传 widget
                try:
                    self._paint_glow(painter, pixmap)
                except Exception:
                    pass
            # 必须把这层裁剪限制在自己的绘制里，否则会溢出到同一场景里
            # 其它元素上（实测会把卡名、攻守、效果文本一起裁掉）。
            painter.save()
            try:
                path = QPainterPath()
                if self.rounded:
                    path.addRoundedRect(QRectF(pixmap.rect()), self.radius, self.radius)
                else:
                    path.addRect(QRectF(pixmap.rect()))
                if self.mode == _RD_OVERFRAME_MODE_HALF:
                    # 半出框：图照旧可以拖到卡图下边缘以下，但超出卡图（插画区）
                    # 底边的部分不显示 —— 是遮挡，不是拖不动。
                    scale = self.scale() or 1.0
                    local_bottom = max(0.0, (self.bottom_limit - self.pos().y()) / scale)
                    clip = QPainterPath()
                    clip.addRect(QRectF(0, 0, float(pixmap.width()), local_bottom))
                    path = path.intersected(clip)
                painter.setClipPath(path)
                painter.drawPixmap(0, 0, pixmap)
            finally:
                painter.restore()

        def itemChange(self, change, value):
            if change == QGraphicsItem.ItemPositionChange:
                pos = value
                x = max(self.min_x, min(pos.x(), self.max_x))
                y = max(self.min_y, min(pos.y(), self.max_y))
                return QPointF(x, y)
            if change == QGraphicsItem.ItemPositionHasChanged:
                callback = getattr(self, "position_changed_callback", None)
                if callback is not None:
                    try:
                        pos = self.pos()
                        callback(round(pos.x()), round(pos.y()))
                    except Exception:
                        pass
            return super().itemChange(change, value)

    _OVERFRAME_ITEM_CLASS = _OverFramePixmapItem
    return _OVERFRAME_ITEM_CLASS


def _on_overframe_moved(editor, x, y):
    """拖动超框卡图后同步坐标字段与设置对话框控件。"""
    try:
        editor.overframe_posx = x
        editor.overframe_posy = y
    except Exception:
        return
    dialog = getattr(editor, "overframe_dialog", None)
    if dialog is None:
        return
    try:
        from PyQt5.QtCore import QSignalBlocker

        for axis, value in (("posx", x), ("posy", y)):
            slider = getattr(dialog, axis + "_slider", None)
            if slider is not None:
                with QSignalBlocker(slider):
                    slider.setValue(int(round(value)))
            label = getattr(dialog, axis + "_num_label", None)
            if label is not None:
                label.setText(str(value))
    except Exception:
        pass


def _prev_ensure_overframe_drag(editor):
    """把编辑器的超框图形项换成可拖动版本（幂等）。"""
    try:
        item = getattr(editor, "overframe_item", None)
        if item is None:
            return
        item_class = _overframe_item_class()

        def callback(x, y, target=editor):
            _on_overframe_moved(target, x, y)

        if isinstance(item, item_class):
            item.position_changed_callback = callback
            return
        scene = item.scene()
        if scene is None:
            return
        replacement = item_class(item.pixmap(), getattr(item, "radius", 28))
        replacement.setPos(item.pos())
        replacement.setZValue(item.zValue())
        replacement.setOpacity(item.opacity())
        replacement.setVisible(item.isVisible())
        replacement.setTransform(item.transform())
        replacement.rounded = bool(getattr(item, "rounded", False))
        replacement.position_changed_callback = callback
        scene.addItem(replacement)
        scene.removeItem(item)
        editor.overframe_item = replacement
    except Exception:
        pass


# ---------------------------------------------------------------------------
# RD 超框卡图（对应 YGOLD 的 RD_front/logo/corner_item 与 overframe_top/bot_item）
# ---------------------------------------------------------------------------
_RD_FRONT_IMGS = {
    "通常": "Rush_Duel/frame/front_TC.enc",
    "效果": "Rush_Duel/frame/front_XG.enc",
    "融合": "Rush_Duel/frame/front_RH.enc",
    "仪式": "Rush_Duel/frame/front_YS.enc",
    "同调": "Rush_Duel/frame/front_TD.enc",
    "超量": "Rush_Duel/frame/front_CL.enc",
    "连接": "Rush_Duel/frame/front_LJ.enc",
    "衍生物": "Rush_Duel/frame/front_YSW.enc",
    "魔法卡": "Rush_Duel/frame/front_Magic.enc",
    "陷阱卡": "Rush_Duel/frame/front_Trap.enc",
    "通常灵摆": "Rush_Duel/frame/front_LB.enc",
    "效果灵摆": "Rush_Duel/frame/front_LB.enc",
    "融合灵摆": "Rush_Duel/frame/front_LB.enc",
    "仪式灵摆": "Rush_Duel/frame/front_LB.enc",
    "同调灵摆": "Rush_Duel/frame/front_LB.enc",
    "超量灵摆": "Rush_Duel/frame/front_LB.enc",
}
_RD_LOGO_IMGS = {
    "通常": "Rush_Duel/frame/logo_TC.enc",
    "效果": "Rush_Duel/frame/logo_XG.enc",
    "融合": "Rush_Duel/frame/logo_RH.enc",
    "仪式": "Rush_Duel/frame/logo_YS.enc",
    "同调": "Rush_Duel/frame/logo_TD.enc",
    "超量": "Rush_Duel/frame/logo_CL.enc",
    "连接": "Rush_Duel/frame/logo_LJ.enc",
    "衍生物": "Rush_Duel/frame/logo_YSW.enc",
    "魔法卡": "Rush_Duel/frame/logo_Magic.enc",
    "陷阱卡": "Rush_Duel/frame/logo_Trap.enc",
    "通常灵摆": "Rush_Duel/frame/logo_LB.enc",
    "效果灵摆": "Rush_Duel/frame/logo_LB.enc",
    "融合灵摆": "Rush_Duel/frame/logo_LB.enc",
    "仪式灵摆": "Rush_Duel/frame/logo_LB.enc",
    "同调灵摆": "Rush_Duel/frame/logo_LB.enc",
    "超量灵摆": "Rush_Duel/frame/logo_LB.enc",
}


def _rd_base_key(rd_widget):
    """复刻 RDWidget.switch_base_image 里的卡框键计算。"""
    card_type = str(getattr(rd_widget, "card_type", "") or "")
    if card_type == "怪兽卡":
        selector = getattr(rd_widget, "call_way_selector", None)
        if selector is not None:
            try:
                return str(selector.currentText())
            except Exception:
                return ""
        return ""
    return card_type


def _rd_overframe_callback(rd_widget, which):
    """拖动 RD 超框卡图后同步坐标。"""

    def callback(x, y):
        try:
            setattr(rd_widget, "overframe_" + which + "_posx", int(x))
            setattr(rd_widget, "overframe_" + which + "_posy", int(y))
            dialog = getattr(rd_widget, "_rd_overframe_dialog", None)
            if dialog is not None:
                dialog.sync_position(which, x, y)
        except Exception:
            pass

    return callback


def _add_rd_overframe_button(rd_widget):
    if getattr(rd_widget, "_rd_overframe_button", None) is not None:
        return
    try:
        from PyQt5.QtWidgets import QPushButton

        button = QPushButton("超框卡图", rd_widget)
        button.setObjectName("rd_overframe_button")
        button.clicked.connect(
            lambda _=False, target=rd_widget: _open_rd_overframe_dialog(target)
        )
        rd_widget._rd_overframe_button = button
        placed = _attach_editor_button(
            rd_widget, button, ("overframe_img_button", "color_black_btn", "color_defined_btn")
        )
        if not placed:
            _tab_log("RD 超框卡图按钮未能进入布局，已作为浮动按钮放置。")
    except Exception:
        _tab_log("创建 RD 超框卡图按钮失败:\n" + traceback.format_exc())


_RD_LAYER_Z = {
    "card_img_item": -1000.0,
    "base_item": -990.0,
    "mask_item": -980.0,
    "rare_item": -900.0,
    # 超框前层只该垫在卡图之上、卡框之下；放高了会盖住灵摆框的菱形刻度箭头。
    "RD_front_item": -985.0,
    # 超框卡图现在是动态图层，z 值由 _rd_sync_overframe_items 按顺序分配。
    "RD_logo_item": -300.0,
    "rare_front_item": _RARE_FRONT_Z,
}


def _rd_fixed_item_class(rd_widget):
    try:
        import customComponents

        item_class = getattr(customComponents, "RoundedPixmapItem", None)
        if item_class is not None:
            return item_class
    except Exception:
        pass
    reference = getattr(rd_widget, "rare_item", None)
    return type(reference) if reference is not None else QGraphicsPixmapItem


def _configure_rd_layer_stack(rd_widget):
    if rd_widget is None:
        return
    for name, z_value in _RD_LAYER_Z.items():
        item = getattr(rd_widget, name, None)
        if item is not None:
            try:
                item.setZValue(z_value)
            except Exception:
                pass


def _rd_overframe_layers_fixed(rd_widget):
    # 这里没有 corner 层：卡框资源（Rush_Duel/*.enc）右上角本来就画好了那个角，
    # 早先再叠一层 corner_*.enc，会在斜切角外多出一块并带出一条白线
    # （实测 17 种卡框在 corner 区域的实心像素都占 92% 以上，属于纯重复）。
    return (
        ("RD_front_item", _RD_FRONT_IMGS),
        ("RD_logo_item", _RD_LOGO_IMGS),
    )


# 超框图层的 z 区间：都在卡框(-990)之上、文字(0)之下。
_RD_OVERFRAME_Z_BASE = -800.0
_RD_OVERFRAME_Z_STEP = 20.0
# 上限：再多的图层也不能压到卡名/攻守/效果这些文字（它们的 z 是 0）。
_RD_OVERFRAME_Z_MAX = -100.0
_RD_OVERFRAME_KEYS = ("image", "enabled", "mode", "scale", "sizex", "sizey", "posx", "posy")


def _rd_overframe_layers(rd_widget):
    """取（必要时初始化）RD 超框图层列表。

    列表顺序就是图层顺序：靠前的在下层。每项是一个 dict，见 _RD_OVERFRAME_KEYS。
    """
    layers = getattr(rd_widget, "_rd_overframe_layers", None)
    if not isinstance(layers, list):
        layers = _rd_overframe_layers_from_legacy(rd_widget)
        rd_widget._rd_overframe_layers = layers
    return layers


def _rd_overframe_layers_from_legacy(rd_widget):
    """把旧的 bot/rect/top 三个固定槽转成图层列表（老卡片数据兼容）。"""
    legacy = (
        ("bot", _RD_OVERFRAME_MODE_HALF),
        ("rect", _RD_OVERFRAME_MODE_HALF),
        ("top", _RD_OVERFRAME_MODE_FULL),
    )
    layers = []
    for which, mode in legacy:
        image = str(getattr(rd_widget, "overframe_" + which + "_image", "") or "")
        if not image:
            continue
        layers.append(
            {
                "image": image,
                "enabled": bool(getattr(rd_widget, "overframe_" + which + "_enabled", False)),
                "mode": mode,
                "scale": int(getattr(rd_widget, "overframe_" + which + "_scale", 1000) or 1000),
                "sizex": int(getattr(rd_widget, "overframe_" + which + "_sizex", 1626) or 1626),
                "sizey": int(getattr(rd_widget, "overframe_" + which + "_sizey", 1626) or 1626),
                "posx": int(getattr(rd_widget, "overframe_" + which + "_posx", 0) or 0),
                "posy": int(getattr(rd_widget, "overframe_" + which + "_posy", 0) or 0),
            }
        )
    return layers


def _rd_overframe_layer_callback(rd_widget, index):
    """拖动某一层后把坐标写回数据。"""

    def callback(x, y):
        layers = _rd_overframe_layers(rd_widget)
        if 0 <= index < len(layers):
            layers[index]["posx"] = int(x)
            layers[index]["posy"] = int(y)

    return callback


def _rd_overframe_layer_scale_callback(rd_widget, index):
    """滚轮调整某一层尺寸后把 scale 写回数据。"""

    def callback(scale):
        layers = _rd_overframe_layers(rd_widget)
        if 0 <= index < len(layers):
            layers[index]["scale"] = int(scale)

    return callback


def _rd_overframe_layer_delete_callback(rd_widget, index):
    """Del 键 / 右键「删除」：删掉 RD 的这一层并重绘。"""

    def callback():
        layers = _rd_overframe_layers(rd_widget)
        if 0 <= index < len(layers):
            del layers[index]
            _rd_apply_overframe_image(rd_widget)
            toggle = getattr(rd_widget, "_rd_overframe_toggle", None)
            if toggle is not None:
                _set_toggle_checked_silent(toggle, any(bool(layer.get("enabled")) for layer in layers))

    return callback


def _rd_apply_overframe_layer(rd_widget, item, layer, index, bottom_limit):
    """把一层的数据贴到对应的图形项上。"""
    encoded = str(layer.get("image") or "")
    if not encoded or not bool(layer.get("enabled", True)):
        _set_item_visible(item, False)
        return
    try:
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as source:
            pil_image = source.convert("RGBA")
        pixmap = _pixmap_from_pillow(pil_image)
        sizex = int(layer.get("sizex") or 1626)
        sizey = int(layer.get("sizey") or 1626)
        pixmap = pixmap.scaled(sizex, sizey, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        item.setPixmap(pixmap)
        item.setScale(max(0.05, min(20.0, float(layer.get("scale") or 1000) / 1000.0)))
        item.mode = str(layer.get("mode") or _RD_OVERFRAME_MODE_FULL)
        item.bottom_limit = bottom_limit
        item.setPos(int(layer.get("posx") or 0), int(layer.get("posy") or 0))
        item.position_changed_callback = _rd_overframe_layer_callback(rd_widget, index)
        item.scale_changed_callback = _rd_overframe_layer_scale_callback(rd_widget, index)
        item.delete_callback = _rd_overframe_layer_delete_callback(rd_widget, index)
        item.setZValue(
            min(_RD_OVERFRAME_Z_BASE + index * _RD_OVERFRAME_Z_STEP, _RD_OVERFRAME_Z_MAX)
        )
        _set_item_visible(item, True)
    except Exception:
        _set_item_visible(item, False)


def _rd_sync_overframe_items(rd_widget):
    """按图层列表同步场景里的超框图形项（多了补、少了藏），并排好 z。"""
    if rd_widget is None:
        return
    scene = getattr(getattr(rd_widget, "parent_app", None), "rd_scene", None)
    if scene is None:
        scene = _widget_scene(rd_widget)
    if scene is None:
        return
    items = getattr(rd_widget, "_rd_overframe_items", None)
    if not isinstance(items, list):
        items = []
        rd_widget._rd_overframe_items = items
    layers = _rd_overframe_layers(rd_widget)[:_RD_OVERFRAME_MAX_LAYERS]
    draggable = _overframe_item_class()
    while len(items) < len(layers):
        try:
            item = draggable(None, 28)
            item.setVisible(False)
            scene.addItem(item)
            items.append(item)
        except Exception:
            break
    # 半出框的下边界是「卡图（插画区）的下边缘」，不是整卡下缘。
    config = getattr(rd_widget, "config", None)
    img_y = int(getattr(config, "card_img_y", 234) or 234)
    img_h = int(getattr(config, "card_img_h", 1468) or 1468)
    bottom_limit = img_y + img_h
    for index, item in enumerate(items):
        if index >= len(layers):
            _set_item_visible(item, False)
            continue
        _rd_apply_overframe_layer(rd_widget, item, layers[index], index, bottom_limit)


def _prev_ensure_rd_overframe(rd_widget):
    """Create/reuse the RD overframe layers in the correct visual stack."""
    if rd_widget is None:
        return
    scene = getattr(getattr(rd_widget, "parent_app", None), "rd_scene", None)
    if scene is None:
        scene = _widget_scene(rd_widget)
    if scene is None:
        return
    draggable = _overframe_item_class()
    fixed_class = _rd_fixed_item_class(rd_widget)
    # 超框卡图改成按图层列表动态创建（见 _rd_sync_overframe_items），
    # 这里只剩固定在卡框里的前层与 logo。
    # 不再创建 RD_corner_item：卡框资源已包含右上角的角，见 _rd_overframe_layers_fixed。
    specs = (
        ("RD_front_item", False, None),
        ("RD_logo_item", False, None),
    )
    for attr, is_draggable, which in specs:
        item = getattr(rd_widget, attr, None)
        if item is None or item.scene() is not scene:
            try:
                if is_draggable:
                    item = draggable(None, 28)
                    item.position_changed_callback = _rd_overframe_callback(rd_widget, which)
                else:
                    item = fixed_class(QPixmap(), 28)
                item.setVisible(False)
                scene.addItem(item)
                setattr(rd_widget, attr, item)
            except Exception:
                continue
        if is_draggable:
            try:
                from PyQt5.QtWidgets import QGraphicsItem

                item.setFlag(QGraphicsItem.ItemIsMovable, True)
                item.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
                item.position_changed_callback = _rd_overframe_callback(rd_widget, which)
            except Exception:
                pass
        else:
            if hasattr(item, "set_rounded"):
                try:
                    item.set_rounded(False)
                except Exception:
                    pass
    _rd_overframe_layers(rd_widget)
    _rd_sync_overframe_items(rd_widget)
    _ensure_rare_front_layer(rd_widget)
    _configure_rd_layer_stack(rd_widget)
    rd_widget._rd_overframe_installed = True


def _apply_rd_overframe_layers(rd_widget):
    """Load the fixed RD frame/front/corner/logo layers for the card type."""
    if rd_widget is None:
        return
    try:
        module = __import__("RD_widget")
        decrypt = getattr(module, "decrypt_image_qpixmap", None)
    except Exception:
        return
    if decrypt is None:
        return
    base_key = _rd_base_key(rd_widget)
    if not base_key:
        return
    for attr, mapping in _rd_overframe_layers_fixed(rd_widget):
        if mapping is None:
            continue
        item = getattr(rd_widget, attr, None)
        if item is None:
            continue
        path = mapping.get(base_key)
        if not path:
            # 该卡种没有对应资源（例如灵摆没有独立的 corner）：清空并隐藏，
            # 否则会残留上一个卡种的图层。
            try:
                item.setPixmap(QPixmap())
                item.setVisible(False)
            except Exception:
                pass
            continue
        try:
            pixmap = decrypt(path)
            if pixmap is None or pixmap.isNull():
                continue
            item.setPixmap(pixmap)
            item.setVisible(True)
        except Exception:
            continue
    _configure_rd_layer_stack(rd_widget)


def _rd_apply_overframe_image(rd_widget, which=None):
    """刷新 RD 超框。

    超框现在是任意多层的列表，which 参数只为兼容旧调用点保留。
    """
    _rd_sync_overframe_items(rd_widget)
    _configure_rd_layer_stack(rd_widget)


def _rd_add_overframe_layer(rd_widget):
    """选一张图片，作为新的超框图层追加到列表末尾（也就是最上层）。"""
    if rd_widget is None:
        return False
    layers = _rd_overframe_layers(rd_widget)
    if len(layers) >= _RD_OVERFRAME_MAX_LAYERS:
        return False
    try:
        path, _selected = QFileDialog.getOpenFileName(
            rd_widget, "选择超框卡图", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
    except Exception:
        return False
    if not path:
        return False
    try:
        with Image.open(path) as source:
            pil_image = source.convert("RGBA")
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        layers.append(
            {
                "image": base64.b64encode(buffer.getvalue()).decode("ascii"),
                "enabled": True,
                "mode": _RD_OVERFRAME_MODE_HALF,
                "scale": 1000,
                "sizex": 1626,
                "sizey": 1626,
                "posx": 0,
                "posy": 0,
            }
        )
        _rd_sync_overframe_items(rd_widget)
    except Exception:
        return False
    return True


def _apply_rd_overframe_data(rd_widget, data):
    if rd_widget is None or not isinstance(data, dict):
        return
    _ensure_rd_overframe(rd_widget)
    layers = data.get("rd_overframe_layers")
    if isinstance(layers, list):
        cleaned = []
        for entry in layers[:_RD_OVERFRAME_MAX_LAYERS]:
            if isinstance(entry, dict):
                cleaned.append({key: entry.get(key) for key in _RD_OVERFRAME_KEYS})
        rd_widget._rd_overframe_layers = cleaned
    else:
        # 老卡片数据：先把旧的固定槽字段装回 widget，再迁移成图层列表。
        for which in ("bot", "rect", "top"):
            for key in ("image", "enabled", "posx", "posy", "scale", "sizex", "sizey"):
                name = "overframe_" + which + "_" + key
                if name in data:
                    try:
                        setattr(rd_widget, name, data.get(name))
                    except Exception:
                        pass
        rd_widget._rd_overframe_layers = _rd_overframe_layers_from_legacy(rd_widget)
    _rd_sync_overframe_items(rd_widget)


_OTCG_LAYER_Z = {
    "card_img_item": -1000.0,
    "base_item": -990.0,
    "rare_item": -980.0,
    "overframe_item": -970.0,
    "overframe_inner": -960.0,
    "overframe_mask": -950.0,
    "rare_front_item": _RARE_FRONT_Z,
}


def _configure_otcg_layer_stack(editor):
    if editor is None:
        return
    for name, z_value in _OTCG_LAYER_Z.items():
        item = getattr(editor, name, None)
        if item is not None:
            try:
                item.setZValue(z_value)
            except Exception:
                pass


def _ensure_overframe_drag(editor):
    _prev_ensure_overframe_drag(editor)
    _configure_otcg_layer_stack(editor)


def _ensure_rd_overframe(rd_widget):
    _prev_ensure_rd_overframe(rd_widget)
    _install_rd_reference_buttons(rd_widget)
    _configure_rd_layer_stack(rd_widget)
    _apply_rd_text_styles(rd_widget)


def _open_rd_overframe_dialog(rd_widget):
    """RD 的超框卡图设置。"""
    return _open_overframe_layers_dialog(
        rd_widget,
        _rd_overframe_layers(rd_widget),
        lambda: _rd_apply_overframe_image(rd_widget),
        lambda: _rd_add_overframe_layer(rd_widget),
    )


def _open_overframe_layers_dialog(parent, layers, apply_layers, add_layer, pos_range=(1626, 1626)):
    """超框卡图设置：任意多图层，可增删、排序、逐层设置出框方式与参数。

    RD 与 OCG/TCG 共用：layers 是该编辑器的图层列表（就地修改），
    apply_layers() 按列表重绘，add_layer() 选图追加一层、成功返回 True。
    pos_range 是横 / 纵位置滑块的范围（卡面宽、高）。"""
    from PyQt5.QtWidgets import QListWidget

    dialog = QDialog(parent)
    dialog.setWindowTitle("超框卡图设置")
    dialog.setMinimumWidth(420)
    root = QVBoxLayout(dialog)

    layer_list = QListWidget(dialog)
    layer_list.setMinimumHeight(140)
    root.addWidget(layer_list)

    buttons = QHBoxLayout()
    add_button = QPushButton("添加图片", dialog)
    remove_button = QPushButton("删除", dialog)
    up_button = QPushButton("上移", dialog)
    down_button = QPushButton("下移", dialog)
    for button in (add_button, remove_button, up_button, down_button):
        buttons.addWidget(button)
    root.addLayout(buttons)

    hint = QLabel("列表从上到下 = 图层从下到上（越靠下越显示在前面）", dialog)
    root.addWidget(hint)

    mode_line = QHBoxLayout()
    mode_line.addWidget(QLabel("出框方式: ", dialog))
    mode_box = QComboBox(dialog)
    for value, label in _RD_OVERFRAME_MODE_LABELS:
        mode_box.addItem(label, value)
    mode_line.addWidget(mode_box, 1)
    root.addLayout(mode_line)

    sliders = {}
    for key, title in (("scale", "卡图尺寸"), ("posx", "横向位置"), ("posy", "纵向位置")):
        line = QHBoxLayout()
        line.addWidget(QLabel(title + ": ", dialog))
        slider = QSlider(Qt.Horizontal, dialog)
        number = QLabel("0", dialog)
        if key == "scale":
            slider.setRange(10, 300)
        else:
            limit = int(pos_range[0] if key == "posx" else pos_range[1])
            slider.setRange(-limit, limit)
        line.addWidget(slider, 1)
        line.addWidget(number)
        root.addLayout(line)
        sliders[key] = (slider, number)

    close_button = QPushButton("关闭", dialog)
    close_button.clicked.connect(dialog.accept)
    root.addWidget(close_button)

    state = {"syncing": False}

    def current():
        row = layer_list.currentRow()
        if 0 <= row < len(layers):
            return row, layers[row]
        return -1, None

    def sync_controls():
        _row, layer = current()
        usable = layer is not None
        mode_box.setEnabled(usable)
        for slider, _number in sliders.values():
            slider.setEnabled(usable)
        if not usable:
            return
        state["syncing"] = True
        try:
            value = str(layer.get("mode") or _RD_OVERFRAME_MODE_FULL)
            index = mode_box.findData(value)
            mode_box.setCurrentIndex(index if index >= 0 else 0)
            values = {
                "scale": int(round(float(layer.get("scale") or 1000) / 10.0)),
                "posx": int(layer.get("posx") or 0),
                "posy": int(layer.get("posy") or 0),
            }
            for key, (slider, number) in sliders.items():
                slider.setValue(values[key])
                number.setText(
                    str(values[key]) + "%" if key == "scale" else str(values[key])
                )
        finally:
            state["syncing"] = False

    def refresh(row=0):
        state["syncing"] = True
        try:
            layer_list.clear()
            for index, layer in enumerate(layers):
                mode_name = _RD_OVERFRAME_MODE_NAMES.get(
                    str(layer.get("mode")), "全出框"
                )
                suffix = "" if layer.get("enabled", True) else "（已关闭）"
                layer_list.addItem("图层 %d（%s）%s" % (index + 1, mode_name, suffix))
            if layers:
                layer_list.setCurrentRow(max(0, min(row, len(layers) - 1)))
        finally:
            state["syncing"] = False
        sync_controls()

    def on_select(_row=None):
        if state["syncing"]:
            return
        sync_controls()

    def on_mode(_index=None):
        if state["syncing"]:
            return
        row, layer = current()
        if layer is None:
            return
        layer["mode"] = str(mode_box.currentData())
        apply_layers()
        refresh(row)

    def on_slider(value, key, number):
        if state["syncing"]:
            return
        _row, layer = current()
        if layer is None:
            return
        if key == "scale":
            layer["scale"] = int(value) * 10
            number.setText(str(value) + "%")
        else:
            layer[key] = int(value)
            number.setText(str(value))
        apply_layers()

    def on_add():
        if add_layer():
            refresh(len(layers) - 1)

    def on_remove():
        row, layer = current()
        if layer is None:
            return
        del layers[row]
        apply_layers()
        refresh(row - 1)

    def on_move(delta):
        row, layer = current()
        if layer is None:
            return
        target = row + delta
        if not 0 <= target < len(layers):
            return
        layers[row], layers[target] = layers[target], layers[row]
        apply_layers()
        refresh(target)

    layer_list.currentRowChanged.connect(on_select)
    mode_box.currentIndexChanged.connect(on_mode)
    add_button.clicked.connect(on_add)
    remove_button.clicked.connect(on_remove)
    up_button.clicked.connect(lambda _=False: on_move(-1))
    down_button.clicked.connect(lambda _=False: on_move(1))
    for key, (slider, number) in sliders.items():
        slider.valueChanged.connect(
            lambda value, k=key, lbl=number: on_slider(value, k, lbl)
        )

    refresh(0)
    dialog.exec_()


_OCG_OF_DATA_KEY = "ocg_overframe_layers"
# 在卡框(-990)、罕贵闪(-980)之上，文字(0)之下；与 RD 一样逐层递增、封顶。
_OCG_OF_Z_BASE = -960.0
_OCG_OF_Z_STEP = 20.0
_OCG_OF_Z_MAX = -100.0
_OCG_OF_DEFAULT_SIZE = 1626
_OCG_OF_PIXMAP_CACHE = {}
_OCG_OF_PIXMAP_CACHE_LIMIT = 24


def _ocg_of_layers(editor):
    layers = getattr(editor, "_ocg_overframe_layers", None)
    if not isinstance(layers, list):
        layers = editor._ocg_overframe_layers = []
    return layers


def _ocg_of_pos_range(editor):
    config = getattr(editor, "config", None)
    return (
        int(getattr(config, "card_rect_w", 1626) or 1626),
        int(getattr(config, "card_rect_h", 2370) or 2370),
    )


def _ocg_of_pixmap(encoded, sizex, sizey):
    key = (len(encoded), hash(encoded), sizex, sizey)
    pixmap = _bounded_cache_get(_OCG_OF_PIXMAP_CACHE, key)
    if pixmap is None:
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as source:
            pil_image = source.convert("RGBA")
        pixmap = _pixmap_from_pillow(pil_image).scaled(
            sizex, sizey, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        _bounded_cache_put(_OCG_OF_PIXMAP_CACHE, key, pixmap, _OCG_OF_PIXMAP_CACHE_LIMIT)
    return pixmap


def _ocg_of_hide_host(editor):
    for name in ("overframe_item", "overframe_mask"):
        _set_item_visible(getattr(editor, name, None), False)
    button = getattr(editor, "overframe_upload_btn", None)
    if button is not None:
        _safe_call(getattr(button, "setVisible", None), False)


def _ocg_of_allowed(editor):
    """卡模不支持超框时（宿主 switch_template 会禁用开关），所有图层都不显示。"""
    toggle = getattr(editor, "overframe_toggle", None)
    try:
        return toggle is None or bool(toggle.isEnabled())
    except Exception:
        return True


def _ocg_of_bottom_limit(editor):
    """半出框的下边界：卡图（插画区）的下边缘。灵摆卡的插画区不同，直接取卡图项的实际范围。"""
    item = getattr(editor, "card_img_item", None)
    try:
        if item is not None and not item.pixmap().isNull():
            return float(item.sceneBoundingRect().bottom())
    except Exception:
        pass
    config = getattr(editor, "config", None)
    return float(getattr(config, "card_y", 436) or 436) + float(getattr(config, "card_img_size_h", 1230) or 1230)


def _ocg_of_callback(editor, index):
    def callback(x, y):
        layers = _ocg_of_layers(editor)
        if 0 <= index < len(layers):
            layers[index]["posx"] = int(x)
            layers[index]["posy"] = int(y)

    return callback


def _ocg_of_scale_callback(editor, index):
    """滚轮调整某一层尺寸后把 scale 写回数据。"""

    def callback(scale):
        layers = _ocg_of_layers(editor)
        if 0 <= index < len(layers):
            layers[index]["scale"] = int(scale)

    return callback


def _ocg_of_delete_callback(editor, index):
    """Del 键 / 右键「删除」：删掉 OCG 的这一层并重绘。"""

    def callback():
        layers = _ocg_of_layers(editor)
        if 0 <= index < len(layers):
            del layers[index]
            _ocg_of_sync(editor)
            _ocg_of_show_toggle(editor)

    return callback


def _ocg_of_sync(editor):
    """按图层列表同步场景里的超框图形项（多了补、少了藏），并排好 z。"""
    if editor is None:
        return
    _ocg_of_hide_host(editor)
    scene = getattr(getattr(editor, "parent_app", None), "scene", None)
    reference = getattr(editor, "base_item", None)
    if reference is not None and reference.scene() is not None:
        scene = reference.scene()
    if scene is None:
        return
    items = getattr(editor, "_ocg_overframe_items", None)
    if not isinstance(items, list):
        items = editor._ocg_overframe_items = []
    layers = _ocg_of_layers(editor)[:_RD_OVERFRAME_MAX_LAYERS]
    draggable = _overframe_item_class()
    while len(items) < len(layers):
        try:
            item = draggable(None, 28)
            item.setVisible(False)
            scene.addItem(item)
            items.append(item)
        except Exception:
            break
    allowed = _ocg_of_allowed(editor)
    bottom_limit = _ocg_of_bottom_limit(editor)
    for index, item in enumerate(items):
        layer = layers[index] if index < len(layers) else None
        encoded = str((layer or {}).get("image") or "")
        if layer is None or not allowed or not encoded or not bool(layer.get("enabled", True)):
            _set_item_visible(item, False)
            continue
        try:
            sizex = int(layer.get("sizex") or _OCG_OF_DEFAULT_SIZE)
            sizey = int(layer.get("sizey") or _OCG_OF_DEFAULT_SIZE)
            item.setPixmap(_ocg_of_pixmap(encoded, sizex, sizey))
            item.setScale(max(0.05, min(20.0, float(layer.get("scale") or 1000) / 1000.0)))
            item.mode = str(layer.get("mode") or _RD_OVERFRAME_MODE_FULL)
            item.bottom_limit = bottom_limit
            # 先清掉回调再定位，免得 setPos 把旧坐标写回别的图层
            item.position_changed_callback = None
            item.setPos(int(layer.get("posx") or 0), int(layer.get("posy") or 0))
            item.position_changed_callback = _ocg_of_callback(editor, index)
            item.scale_changed_callback = _ocg_of_scale_callback(editor, index)
            item.delete_callback = _ocg_of_delete_callback(editor, index)
            item.setZValue(min(_OCG_OF_Z_BASE + index * _OCG_OF_Z_STEP, _OCG_OF_Z_MAX))
            item.update()
            _set_item_visible(item, True)
        except Exception:
            _set_item_visible(item, False)


def _ocg_of_show_toggle(editor):
    """开关显示成「是否有启用的图层」（与 RD 一致）；卡模禁用超框时保持宿主的关闭状态。"""
    toggle = getattr(editor, "overframe_toggle", None)
    if toggle is None or not _ocg_of_allowed(editor):
        return
    checked = any(bool(layer.get("enabled")) for layer in _ocg_of_layers(editor))
    if bool(getattr(toggle, "is_checked", False)) != checked:
        _set_toggle_checked_silent(toggle, checked)


def _ocg_of_add_layer(editor):
    """选一张图片，作为新的超框图层追加到列表末尾（也就是最上层）。"""
    layers = _ocg_of_layers(editor)
    if len(layers) >= _RD_OVERFRAME_MAX_LAYERS:
        return False
    try:
        path, _selected = QFileDialog.getOpenFileName(
            editor, "选择超框卡图", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
    except Exception:
        return False
    if not path:
        return False
    try:
        with Image.open(path) as source:
            pil_image = source.convert("RGBA")
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
    except Exception:
        _tab_log("读取超框卡图失败:\n" + traceback.format_exc())
        return False
    layers.append(
        {
            "image": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "enabled": True,
            "mode": _RD_OVERFRAME_MODE_HALF,
            "scale": 1000,
            "sizex": _OCG_OF_DEFAULT_SIZE,
            "sizey": _OCG_OF_DEFAULT_SIZE,
            "posx": 0,
            "posy": 0,
        }
    )
    _ocg_of_sync(editor)
    _ocg_of_show_toggle(editor)
    return True


def _ocg_of_open_dialog(editor):
    def apply_layers():
        _ocg_of_sync(editor)
        _ocg_of_show_toggle(editor)

    _open_overframe_layers_dialog(
        editor,
        _ocg_of_layers(editor),
        apply_layers,
        lambda: _ocg_of_add_layer(editor),
        _ocg_of_pos_range(editor),
    )


def _ocg_of_layers_from_data(data):
    layers = data.get(_OCG_OF_DATA_KEY)
    if isinstance(layers, list):
        cleaned = []
        for entry in layers[:_RD_OVERFRAME_MAX_LAYERS]:
            if isinstance(entry, dict) and entry.get("image"):
                cleaned.append({key: entry.get(key) for key in _RD_OVERFRAME_KEYS})
        return cleaned
    # 旧卡片：宿主的单张超框图迁移成一个半出框图层（宿主是按 尺寸×缩放 缩放后贴在 pos 处）
    encoded = data.get("overframe_image")
    if isinstance(encoded, str) and encoded:
        return [
            {
                "image": encoded,
                "enabled": bool(data.get("overframe")),
                "mode": _RD_OVERFRAME_MODE_HALF,
                "scale": int(data.get("overframe_scale") or 1000),
                "sizex": int(data.get("overframe_sizex") or _OCG_OF_DEFAULT_SIZE),
                "sizey": int(data.get("overframe_sizey") or _OCG_OF_DEFAULT_SIZE),
                "posx": int(data.get("overframe_posx") or 0),
                "posy": int(data.get("overframe_posy") or 0),
            }
        ]
    return []


def _ocg_of_apply_data(editor, data):
    editor._ocg_overframe_layers = _ocg_of_layers_from_data(data)
    # 宿主的单张超框图已迁移进图层，不再由宿主导出（p29 会把「开着但没有图」当作关闭）
    editor.overframe_img = None
    _ocg_of_sync(editor)
    _ocg_of_show_toggle(editor)


def _ocg_of_inject(editor, data):
    data[_OCG_OF_DATA_KEY] = [dict(layer) for layer in _ocg_of_layers(editor)]
    return data


def _ocg_of_setup_buttons(editor):
    """「超框设置」改开图层对话框；「上传超框卡图」隐藏（在对话框里添加）。"""
    if getattr(editor, "_ocg_of_buttons_ready", False):
        return
    button = getattr(editor, "overframe_setting_btn", None)
    if button is None:
        return
    try:
        button.clicked.disconnect()
    except Exception:
        pass
    button.clicked.connect(lambda _=False, target=editor: _ocg_of_open_dialog(target))
    _ocg_of_hide_host(editor)
    editor._ocg_of_buttons_ready = True


def _ocg_of_after_init(editor, where):
    """OTCGWidget.__init__ / init_vis 末尾：换上多图层的「超框设置」按钮并显示图层。"""
    try:
        _ocg_of_setup_buttons(editor)
        _ocg_of_sync(editor)
    except Exception:
        _tab_log("OCG 超框图层（%s）失败:\n" % where + traceback.format_exc())


def _ocg_of_after_toggle(editor, checked):
    """OTCGWidget.overframe_toggle_change 末尾：宿主会显示自己的超框图与遮罩、按开关启停「超框设置」，这里都改回来。"""
    try:
        if not getattr(editor, "_ocg_of_importing", False):
            for layer in _ocg_of_layers(editor):
                layer["enabled"] = bool(checked)
        button = getattr(editor, "overframe_setting_btn", None)
        if button is not None:
            button.setEnabled(_ocg_of_allowed(editor))
        _ocg_of_sync(editor)
    except Exception:
        _tab_log("OCG 超框图层（%s）失败:\n" % "overframe_toggle_change" + traceback.format_exc())


def _ocg_of_after_layout_change(editor):
    """OTCGWidget.switch_template 末尾：换卡模后重排图层、刷新开关显示。"""
    try:
        _ocg_of_sync(editor)
        _ocg_of_show_toggle(editor)
    except Exception:
        _tab_log("OCG 超框图层（%s）失败:\n" % "switch_template" + traceback.format_exc())


def _sync_ocg_layers_after(method):
    """OTCGWidget 方法的装饰器：卡图 / 卡框变了（灵摆与普通插画区不同）之后重算半出框的下边界。"""
    def wrapped(self, *args, **kwargs):
        result = _call_original(method, self, args, kwargs)
        try:
            _ocg_of_sync(self)
        except Exception:
            _tab_log("OCG 超框图层（%s）失败:\n" % method.__name__ + traceback.format_exc())
        return result

    wrapped.__name__, wrapped.__qualname__, wrapped.__doc__ = method.__name__, method.__qualname__, method.__doc__
    wrapped.__wrapped__ = method
    return wrapped


_OF_SYNC_MODES = (0, 1)  # 0 = OCG/TCG，1 = RD


def _of_sync_editors(app):
    ocg = getattr(app, "otcg_widget", None)
    rd = getattr(app, "rd_widget", None) if getattr(app, "RD_init", False) else None
    return ocg, rd


def _of_art_rect(editor, kind):
    """插画区 (左, 上, 宽)：优先取卡图项的实际范围（灵摆插画区不同），否则用配置。"""
    item = getattr(editor, "card_img_item", None)
    try:
        if item is not None and not item.pixmap().isNull():
            rect = item.sceneBoundingRect()
            if rect.width() > 1:
                return float(rect.x()), float(rect.y()), float(rect.width())
    except Exception:
        pass
    config = getattr(editor, "config", None)
    if kind == "rd":
        return (
            float(getattr(config, "card_img_x", 81) or 81),
            float(getattr(config, "card_img_y", 234) or 234),
            float(getattr(config, "card_img_w", 1463) or 1463),
        )
    return (
        float(getattr(config, "card_x", 199) or 199),
        float(getattr(config, "card_y", 436) or 436),
        float(getattr(config, "card_img_size_w", 1230) or 1230),
    )


def _of_convert_layers(layers, source_rect, target_rect):
    sx, sy, sw = source_rect
    tx, ty, tw = target_rect
    ratio = tw / sw if sw > 0 else 1.0
    converted = []
    for layer in layers or ():
        if not isinstance(layer, dict):
            continue
        item = dict(layer)
        item["posx"] = int(round(tx + (float(layer.get("posx") or 0) - sx) * ratio))
        item["posy"] = int(round(ty + (float(layer.get("posy") or 0) - sy) * ratio))
        item["scale"] = max(10, int(round(float(layer.get("scale") or 1000) * ratio)))
        converted.append(item)
    return converted


def _of_layers_of(editor, kind):
    return _rd_overframe_layers(editor) if kind == "rd" else _ocg_of_layers(editor)


def _of_converted(app, source_kind, target_kind):
    """source 模式的图层换算到 target 模式；任一编辑器还没建好时返回 None。"""
    ocg, rd = _of_sync_editors(app)
    editors = {"ocg": ocg, "rd": rd}
    source, target = editors[source_kind], editors[target_kind]
    if source is None or target is None:
        return None
    return _of_convert_layers(
        _of_layers_of(source, source_kind),
        _of_art_rect(source, source_kind),
        _of_art_rect(target, target_kind),
    )


def _of_show_layers(app, kind, layers):
    """把图层装进某个模式的编辑器并重绘、刷新开关显示。"""
    ocg, rd = _of_sync_editors(app)
    if kind == "rd" and rd is not None:
        rd._rd_overframe_layers = layers
        _rd_apply_overframe_image(rd)
        toggle = getattr(rd, "_rd_overframe_toggle", None)
        if toggle is not None:
            _set_toggle_checked_silent(toggle, any(bool(layer.get("enabled")) for layer in layers))
    elif kind == "ocg" and ocg is not None:
        ocg._ocg_overframe_layers = layers
        _ocg_of_sync(ocg)
        _ocg_of_show_toggle(ocg)


def _of_kind(mode):
    return "rd" if mode == 1 else "ocg"


def _of_sync_on_mode_switch(app):
    current = getattr(app, "current_mode", None)
    if current not in _OF_SYNC_MODES:
        return  # 漫画卡等模式不编辑超框，保持「上一个编辑超框的模式」不变
    last = getattr(app, "_of_last_mode", None)
    app._of_last_mode = current
    if last is None or last == current:
        return
    layers = _of_converted(app, _of_kind(last), _of_kind(current))
    if layers is not None:
        _of_show_layers(app, _of_kind(current), layers)


def _of_sync_after_apply(manager, data):
    """标签页套用卡片数据之后：只有一边有超框图层、另一边的字段根本不存在（旧卡）时，从有的一边补。"""
    try:
        app = getattr(manager, "app", None)
        ocg, rd = _of_sync_editors(app)
        if isinstance(data, dict) and ocg is not None and rd is not None:
            ocg_layers, rd_layers = _ocg_of_layers(ocg), _rd_overframe_layers(rd)
            if ocg_layers and not rd_layers and "rd_overframe_layers" not in data:
                _of_show_layers(app, "rd", _of_converted(app, "ocg", "rd") or [])
            elif rd_layers and not ocg_layers and _OCG_OF_DATA_KEY not in data and not data.get("overframe_image"):
                _of_show_layers(app, "ocg", _of_converted(app, "rd", "ocg") or [])
    except Exception:
        _tab_log("载入卡片时同步超框卡图失败:\n" + traceback.format_exc())


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from rd_panel import _install_rd_reference_buttons
from rd_style import _apply_rd_text_styles
from rarity import _ensure_rare_front_layer
