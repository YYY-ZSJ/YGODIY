"""环境变量开启的诊断输出（性能、RD 卡面 / 控件）。

由补丁分片 p09、p10、p15 整理而来。
"""

import json
import os
import sys
import time
import traceback

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtWidgets import QApplication

from common import (
    _RD_IMAGE_RENDER_CACHE,
    _safe_call,
    _set_combo_text,
    _set_line_text,
    _set_plain_text,
    _tab_log,
    _toggle_checked,
)


def _export_performance_diagnostic(app, editor, output_path):
    try:
        results = {
            "input_debounce_count": len(
                getattr(editor, "_input_debounce_timers", ()) or ()
            ),
            "ignored_stale_fetches": int(
                getattr(editor, "_ignored_stale_fetches", 0)
            ),
            "fetch_race_guard_installed": bool(
                getattr(editor, "_fetch_race_guard_installed", False)
            ),
            "state_bytes": (
                os.path.getsize(_card_tabs_state_path())
                if os.path.exists(_card_tabs_state_path())
                else 0
            ),
            "methods_ms": {},
        }
        for method_name in (
            "update_card_name",
            "update_text",
            "update_ATK",
            "update_DEF",
            "update_card_pack",
            "transform_normal_img",
        ):
            method = getattr(editor, method_name, None)
            if method is None:
                continue
            samples = []
            for _ in range(3):
                started = time.perf_counter()
                method()
                samples.append((time.perf_counter() - started) * 1000)
            results["methods_ms"][method_name] = {
                "average": round(sum(samples) / len(samples), 3),
                "maximum": round(max(samples), 3),
            }

        manager = getattr(app, "card_tab_manager", None)
        if manager is not None and manager._current_tab() is not None:
            profile_started = {}
            profile_stats = {}

            def profiler(frame, event, arg):
                filename = str(frame.f_code.co_filename)
                if "OTCG_widget" not in filename and "customComponents" not in filename:
                    return
                frame_id = id(frame)
                if event == "call":
                    profile_started[frame_id] = time.perf_counter()
                elif event in {"return", "exception"}:
                    method_started = profile_started.pop(frame_id, None)
                    if method_started is None:
                        return
                    elapsed = (time.perf_counter() - method_started) * 1000
                    method_name = frame.f_code.co_name
                    total, count, maximum = profile_stats.get(
                        method_name,
                        (0.0, 0, 0.0),
                    )
                    profile_stats[method_name] = (
                        total + elapsed,
                        count + 1,
                        max(maximum, elapsed),
                    )

            started = time.perf_counter()
            sys.setprofile(profiler)
            try:
                manager._apply_editor_data(manager._current_tab()["data"])
            finally:
                sys.setprofile(None)
            results["apply_current_tab_ms"] = round(
                (time.perf_counter() - started) * 1000,
                3,
            )
            results["apply_profile"] = [
                {
                    "method": method_name,
                    "total": round(total, 3),
                    "count": count,
                    "maximum": round(maximum, 3),
                }
                for method_name, (total, count, maximum) in sorted(
                    profile_stats.items(),
                    key=lambda item: item[1][0],
                    reverse=True,
                )[:25]
            ]

            if getattr(app, "rd_widget", None) is not None:
                _switch_to_rd_frame_only(app)
                rd_editor = app.rd_widget
                results["rd_switch_image_commits"] = int(
                    getattr(app, "_rd_switch_image_commits", 0)
                )
                results["rd_demo_image_suppressed"] = bool(
                    getattr(app, "_rd_demo_image_suppressed", False)
                )
                results["rd_transition_cover_shown"] = bool(
                    getattr(app, "_rd_transition_cover_shown", False)
                )
                results["rd_transition_full_repaint"] = bool(
                    getattr(app, "_rd_transition_full_repaint", False)
                )
                _RD_IMAGE_RENDER_CACHE.clear()
                rd_editor._rd_sync_values = {}
                rd_editor._rd_synced_image_token = None
                started = time.perf_counter()
                _sync_rd_frame_from_otcg(app)
                results["rd_cold_sync_ms"] = round(
                    (time.perf_counter() - started) * 1000,
                    3,
                )
                started = time.perf_counter()
                _sync_rd_frame_from_otcg(app)
                results["rd_cached_sync_ms"] = round(
                    (time.perf_counter() - started) * 1000,
                    3,
                )
                started = time.perf_counter()
                manager._apply_editor_data(manager._current_tab()["data"])
                results["rd_apply_current_tab_ms"] = round(
                    (time.perf_counter() - started) * 1000,
                    3,
                )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump(results, output, ensure_ascii=False, indent=2)
    except Exception:
        _tab_log("导出性能诊断失败:\n" + traceback.format_exc())
    finally:
        _safe_call(getattr(QApplication.instance(), "quit", None))


def _export_rd_diagnostic(app, output_path):
    try:
        from PyQt5.QtCore import QRectF

        mode = os.environ.get("YGODIY_RD_DIAGNOSTIC_MODE", "").lower()
        editor = getattr(app, "otcg_widget", None)
        if editor is not None and mode == "link":
            _set_combo_text(getattr(editor, "info_selector_left", None), "连接")
            arrow_bits = os.environ.get("YGODIY_RD_DIAGNOSTIC_ARROWS", "11111000")
            arrow_bits = arrow_bits[:8].ljust(8, "0")
            editor.arrow_status_list = [value == "1" for value in arrow_bits]
        elif editor is not None and mode == "pendulum":
            _set_combo_text(getattr(editor, "info_selector_left", None), "效果")
            _set_combo_text(getattr(editor, "info_selector_mid", None), "灵摆")
            _set_plain_text(
                getattr(editor, "LB_text_edit", None),
                "①：这张卡在灵摆区域存在的场合才能发动。"
                "从自己的卡组把1只怪兽加入手卡。",
            )
            _set_line_text(getattr(editor, "LB_level_edit", None), "9")

        _switch_to_rd_frame_only(app)
        rd_editor = getattr(app, "rd_widget", None)
        scene = getattr(app, "rd_scene", None)
        if rd_editor is None or scene is None:
            raise RuntimeError("RD editor or scene is unavailable")

        width = int(getattr(rd_editor.config, "card_w", 1626))
        height = int(getattr(rd_editor.config, "card_h", 2370))
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        scene.render(painter, QRectF(0, 0, width, height), QRectF(0, 0, width, height))
        painter.end()
        if not pixmap.save(output_path, "PNG"):
            raise RuntimeError("Could not save RD diagnostic image")
    except Exception:
        _tab_log("导出RD诊断图失败:\n" + traceback.format_exc())


def _export_rd_control_diagnostic(app, output_path):
    try:
        _switch_to_rd_frame_only(app)
        editor = getattr(app, "otcg_widget", None)

        def snapshot():
            selector = getattr(editor, "info_selector_left", None)

            def explicitly_visible(name):
                widget = getattr(editor, name, None)
                if widget is None:
                    return None
                try:
                    return not bool(widget.isHidden())
                except Exception:
                    return None

            toggle = getattr(editor, "LB_Zack_toggle", None)

            def color_tuple(value):
                try:
                    return [int(value.red()), int(value.green()), int(value.blue())]
                except Exception:
                    return None

            rd_editor = getattr(app, "rd_widget", None)
            card_name_item = getattr(rd_editor, "card_name_item", None)
            mix_name_item = getattr(rd_editor, "mix_name_item", None)
            try:
                rendered_title_color = card_name_item.defaultTextColor()
            except Exception:
                rendered_title_color = None
            try:
                rendered_detail_color = rd_editor.detail_text_item.defaultTextColor()
            except Exception:
                rendered_detail_color = None

            def item_visible(item):
                try:
                    return bool(item.isVisible())
                except Exception:
                    return None

            return {
                "call_way_items": [
                    str(selector.itemText(index)) for index in range(selector.count())
                ],
                "zack_label_visible": explicitly_visible("LB_Zack_label"),
                "zack_toggle_visible": explicitly_visible("LB_Zack_toggle"),
                "zack_checked": bool(getattr(toggle, "is_checked", False)),
                "advanced_toggle_checked": _toggle_checked(
                    getattr(editor, "color_advanced_btn", None)
                ),
                "otcg_mix_mode_flag": bool(getattr(editor, "mix_mode_flag", False)),
                "rd_mix_mode_flag": bool(getattr(rd_editor, "mix_mode_flag", False)),
                "normal_name_visible": item_visible(card_name_item),
                "mix_name_visible": item_visible(mix_name_item),
                "rd_title_color": color_tuple(getattr(rd_editor, "title_color", None)),
                "rendered_title_color": color_tuple(rendered_title_color),
                "rendered_detail_color": color_tuple(rendered_detail_color),
            }

        def click_button(button):
            if button is None:
                return
            try:
                class MouseEvent:
                    def button(self):
                        return Qt.LeftButton

                    def pos(self):
                        width = getattr(button, "width", 2)
                        height = getattr(button, "height", 2)
                        width = width() if callable(width) else width
                        height = height() if callable(height) else height
                        return QPoint(max(1, int(width) // 2), max(1, int(height) // 2))

                    def ignore(self):
                        pass

                button.mousePressEvent(MouseEvent())
            except Exception:
                _safe_call(getattr(button, "click", None))
            _safe_call(getattr(QApplication, "processEvents", None))

        def click_button_text(buttons, text):
            for button in buttons or ():
                try:
                    button_text = getattr(button, "text", "")
                    if callable(button_text):
                        button_text = button_text()
                    if button_text == text:
                        click_button(button)
                        return True
                except Exception:
                    pass
            return False

        if _toggle_checked(getattr(editor, "color_advanced_btn", None)):
            click_button(getattr(editor, "color_advanced_btn", None))
        snapshots = {"initial": snapshot()}
        click_button(getattr(editor, "color_advanced_btn", None))
        snapshots["advanced_enabled"] = snapshot()
        click_button_text(getattr(editor, "color_advanced_list", ()), "青字")
        snapshots["advanced_blue"] = snapshot()
        click_button(getattr(editor, "color_advanced_btn", None))
        snapshots["advanced_disabled"] = snapshot()
        click_button_text(getattr(editor, "color_btn_list", ()), "金色")
        snapshots["normal_gold"] = snapshot()

        def render_preview(path):
            from PyQt5.QtCore import QRectF

            rd_editor = getattr(app, "rd_widget", None)
            scene = getattr(app, "rd_scene", None)
            width = int(getattr(rd_editor.config, "card_w", 1626))
            height = int(getattr(rd_editor.config, "card_h", 2370))
            pixmap = QPixmap(width, height)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            scene.render(
                painter,
                QRectF(0, 0, width, height),
                QRectF(0, 0, width, height),
            )
            painter.end()
            pixmap.save(path, "PNG")

        _set_combo_text(getattr(editor, "info_selector_left", None), "超量")
        _safe_call(getattr(QApplication, "processEvents", None))
        snapshots["xyz"] = snapshot()
        render_preview(os.path.splitext(output_path)[0] + "-xyz.png")
        _set_combo_text(getattr(editor, "info_selector_left", None), "效果")
        _safe_call(getattr(QApplication, "processEvents", None))
        snapshots["effect_after_xyz"] = snapshot()
        rd_state = snapshots["effect_after_xyz"]
        try:
            render_preview(os.path.splitext(output_path)[0] + ".png")
        except Exception:
            _tab_log("导出RD控件诊断预览失败:\n" + traceback.format_exc())
        _set_rd_only_editor_controls(app, False)
        data = {
            "current_mode": getattr(app, "current_mode", None),
            "rd": rd_state,
            "color_mode_snapshots": snapshots,
            "restored_ocg_tcg": snapshot(),
        }
        with open(output_path, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
    except Exception:
        _tab_log("导出RD控件诊断失败:\n" + traceback.format_exc())
    finally:
        _safe_call(getattr(QApplication.instance(), "quit", None))


# 子系统之间互相引用：放在模块末尾导入（此时本模块的定义都已就绪），循环导入也能成立。
from card_tabs import _card_tabs_state_path
from rd_frame import _set_rd_only_editor_controls, _switch_to_rd_frame_only, _sync_rd_frame_from_otcg
