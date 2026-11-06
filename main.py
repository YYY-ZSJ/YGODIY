import sys
import os
from runtime_paths import prepare_runtime, rpath
from sandbox import WORKER_ARGUMENT


if __name__ == "__main__" and sys.argv[1:2] == [WORKER_ARGUMENT]:
    from sandbox.worker import main as sandbox_main

    sandbox_main(sys.argv[2], sys.argv[3])
    raise SystemExit(0)


def _preload_translation_model():
    """内置神经翻译模型（llama.cpp）必须在任何 PyQt5 模块导入之前载入，否则会访问违例、模型不可用
    （见 ygo_translator/neural.py 的 preload），所以放在 main 模块最前面。失败不影响程序，
    翻译自动退回实例模型；没载入的原因由 main() 记到日志。"""
    try:
        import ygo_translator

        if ygo_translator.USE_NEURAL:
            ygo_translator.neural.preload()
    except Exception:
        pass


_preload_translation_model()

import applog  # noqa: E402  以下的导入都在翻译模型预载之后
import startup
from OTCG_widget import OTCGWidget
from RD_widget import RDWidget
from FC_widget import FCWidget
from PyQt5 import QtCore
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGraphicsView, QGraphicsScene, QComboBox, \
    QLabel, QStackedWidget, QMessageBox, QScrollArea
from PyQt5.QtGui import QFont, QIcon, QMovie, QBrush, QGuiApplication, QPixmapCache
from PyQt5.QtCore import Qt
from CardBack_widget import CardBackWidget
from Past_widget import PastWidget
import traceback

import app_window
import diagnostics

# 平台的新模块（diy_workbench、effect_model、ygopack、sandbox）是包，而启动器的查找器只从源码目录加载顶层模块：
# 把源码目录加到搜索路径末尾，包就能按常规方式导入（顶层模块仍由查找器优先加载，不受影响）
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.append(_SRC_DIR)
import diy_workbench.workbench as diy_workbench  # noqa: E402
import language_switch
import manga
import mode_styles
import overframe
import rd_frame
from common import _install_symbol_bar, _safe_call, _schedule_preview_update_restore, _tab_log


def clean_filename(filename: str):
    forbidden_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
    for char in forbidden_chars:
        filename = filename.replace(char, '')
    return filename

class YuGiOhApp(QWidget):
    def __init__(self):
        super().__init__()
        # 到处都是 QPixmap(rpath(...)) 直接读图，Qt 按文件名自带缓存，但默认上限 10 MB，
        # 一张 1626x2370 的卡面图就有 15 MB，永远放不进去。放大到 256 MB。
        # （必须在 QApplication 建好之后设置，否则会被重置）
        if QPixmapCache.cacheLimit() < 256 * 1024:
            QPixmapCache.setCacheLimit(256 * 1024)

        self.init_ui()

        # 程序图标；窗口不超出屏幕
        app_window._apply_application_icon(self)
        QtCore.QTimer.singleShot(0, lambda window=self: app_window._apply_application_icon(window))
        output_path = os.environ.get("YGODIY_RD_DIAGNOSTIC")
        if output_path:
            QtCore.QTimer.singleShot(2500, lambda: diagnostics._export_rd_diagnostic(self, output_path))
        QtCore.QTimer.singleShot(0, lambda window=self: app_window._fit_main_window_to_screen(window))
        QtCore.QTimer.singleShot(300, lambda window=self: app_window._fit_main_window_to_screen(window))

        # 漫画卡模式：模式下拉的最后一项，选项条、版式下拉和独立右栏
        try:
            self._manga_mode_index = self.combo_box.count()
            self.combo_box.addItem(manga._MANGA_MODE_LABEL)
            manga._manga_install_bar(self)
            manga._manga_install_detail_combo(self)
        except Exception:
            self._manga_mode_index = -1
            _tab_log("安装漫画卡模式失败:\n" + traceback.format_exc())
        try:
            manga._manga_panel_build(self)
        except Exception:
            _tab_log("创建漫画卡面板失败:\n" + traceback.format_exc())
        # DIY 工作台：模式下拉里排在漫画卡后面，给卡写效果、看规范文本与 Lua、导出卡包
        try:
            diy_workbench.install(self)
        except Exception:
            self._workbench_mode_index = -1
            _tab_log("安装 DIY 工作台失败:\n" + traceback.format_exc())

        # OCG/TCG、RD、漫画卡各自的显示设置（mode_styles），RD 另有语言下拉
        self._style_mode_key = "ocg"
        try:
            language_switch._install_rd_language_bar(self)
        except Exception:
            _tab_log("安装 RD 语言下拉失败:\n" + traceback.format_exc())
        # 各模式语言旁的「AI翻译」开关
        try:
            language_switch._ai_install_toggles(self)
        except Exception:
            _tab_log("安装 AI翻译开关失败:\n" + traceback.format_exc())
        try:
            _install_symbol_bar(getattr(self, "_manga_panel", None), "effect_edit", ())
        except Exception:
            _tab_log("安装漫画卡特殊符号按钮失败:\n" + traceback.format_exc())
        from diy_workbench.ai.dock import install
        install(self)

    def init_ui(self):

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setStyleSheet('border: none; background-color: rgba(0, 0, 0, 0);')
        self.rd_scene = QGraphicsScene(self)
        self.fc_scene = QGraphicsScene(self)
        self.back_scene = QGraphicsScene(self)
        self.past_scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QBrush(Qt.transparent))
        self.rd_scene.setBackgroundBrush(QBrush(Qt.transparent))
        self.fc_scene.setBackgroundBrush(QBrush(Qt.transparent))
        self.back_scene.setBackgroundBrush(QBrush(Qt.transparent))
        self.past_scene.setBackgroundBrush(QBrush(Qt.transparent))

        self.RD_init = False
        self.Back_init = False
        self.FC_init = False
        self.Past_init = False

        self.loading_label = QLabel(self.view)
        self.loading_label.setFixedSize(50, 50)
        self.loading_label.hide()
        self.loading_movie = QMovie(rpath('mold/loading.gif'))
        self.loading_label.setMovie(self.loading_movie)

        self.combo_box = QComboBox(self)
        self.combo_box.setEditable(True)
        self.ledit = self.combo_box.lineEdit()
        self.ledit.setAlignment(Qt.AlignCenter)
        self.ledit.setReadOnly(True)
        self.combo_box.addItems(['OCG/TCG', '超速决斗(Rush Duel)', '场地中心卡(Field Center)', '游戏王卡背', '游戏王旧版卡'])
        self.combo_box.currentIndexChanged.connect(self.switch_mode)
        self.clickable(self.combo_box).connect(self.combo_box.showPopup)
        self.clickable(self.ledit).connect(self.combo_box.showPopup)

        self.right_layout = QVBoxLayout()
        self.right_layout.addWidget(self.combo_box)
        self.stacked_widget = QStackedWidget(self)
        self.current_mode = 0

        self.otcg_widget = OTCGWidget(self)
        self.rd_widget = RDWidget(self)
        self.fc_widget = FCWidget(self)
        self.back_widget = CardBackWidget(self)
        self.past_widget = PastWidget(self)

        self.stacked_widget.addWidget(self.otcg_widget)
        self.stacked_widget.addWidget(self.rd_widget)
        self.stacked_widget.addWidget(self.fc_widget)
        self.stacked_widget.addWidget(self.back_widget)
        self.stacked_widget.addWidget(self.past_widget)
        self.stacked_widget.setSizePolicy(13, 5)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidget(self.stacked_widget)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)



        self.right_layout.addWidget(self.scroll_area)
        self.right_widget = QWidget(self)
        self.right_widget.setLayout(self.right_layout)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(0)

        self.hbox = QHBoxLayout()
        self.hbox.addWidget(self.view)
        self.hbox.addWidget(self.right_widget)
        self.hbox.setStretch(0, 1)
        self.hbox.setStretch(1, 1)

        from diy_workbench.ai.dock import make_shell
        make_shell(self)
        self.setWindowTitle('YGODIY 2.0.0')
        self.setWindowIcon(QIcon(rpath('mold/YGODIY.ico')))

        screen_height = QGuiApplication.primaryScreen().geometry().height()
        screen_width = QGuiApplication.primaryScreen().geometry().width()
        if screen_height > 1250:
            self.resize(1490, 1080)
        else:
            self.resize(int(0.85 * screen_width), int(0.8 * screen_height))
        self.center()



    def show_loading_gif(self):
        view_width = self.view.width()
        view_height = self.view.height()
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

    def show_warning_message(self, mess: str):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setText(f'{mess}资源缺失，下载补充包或检查存储路径是否正确')
        msg.setWindowTitle('警告')
        msg.exec_()

    def center(self):
        qr = self.frameGeometry()
        cp = QApplication.desktop().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def resizeEvent(self, event):

        super().resizeEvent(event)
        if self.current_mode in (0, getattr(self, '_workbench_mode_index', -2)):  # DIY 工作台显示的是 OCG 卡面
            self.view.fitInView(self.otcg_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
            self.otcg_widget.update_mix_param()
            self.otcg_widget.update_card_name()
        elif self.current_mode == 1:
            if self.RD_init:
                self.view.fitInView(self.rd_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
                self.rd_widget.update_mix_param()
                self.rd_widget.update_card_name()
        elif self.current_mode == 2:
            self.view.fitInView(self.fc_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
        elif self.current_mode == 3:
            self.view.fitInView(self.back_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
        else:
            if self.Past_init:
                self.view.fitInView(self.past_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
                self.past_widget.update_mix_param()
                self.past_widget.update_card_name()
        pass


    def showEvent(self, event):
        # 漫画卡模式的序号不在 0~3，按漫画卡卡面适配（否则会被当成旧版卡）
        manga_index = getattr(self, '_manga_mode_index', -1)
        manga_item = getattr(self, 'manga_item', None)
        if manga_index >= 0 and self.current_mode == manga_index and manga_item is not None:
            try:
                self.view.fitInView(manga_item.boundingRect(), Qt.KeepAspectRatio)
            except Exception:
                pass
            super().showEvent(event)
            return
        try:
            if self.current_mode in (0, getattr(self, '_workbench_mode_index', -2)):
                self.view.fitInView(self.otcg_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
            elif self.current_mode == 1:
                if self.RD_init:
                    self.view.fitInView(self.rd_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
            elif self.current_mode == 2:
                self.view.fitInView(self.fc_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
            elif self.current_mode == 3:
                self.view.fitInView(self.back_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
            else:
                self.view.fitInView(self.past_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
        except AttributeError:
            pass  # 对应模式的卡面还没建好（没有 base_item）：跳过适配，窗口照常显示
        super().showEvent(event)

    def switch_mode(self, index: int):
        """模式下拉的入口。由外到内：超框图层在模式间同步、补装 AI 翻译开关、切换后保持当前语言（language_switch）、
        各模式自己的显示设置（mode_styles）、漫画卡模式（manga）、RD 卡框跟随 OCG（rd_frame），
        最里层 _switch_mode_base 是各编辑器本身的切换。"""
        if getattr(self, '_of_last_mode', None) is None and self.current_mode in overframe._OF_SYNC_MODES:
            self._of_last_mode = self.current_mode
        result = language_switch._switch_mode_keeping_language(self, index, self._switch_mode_styled)
        try:
            language_switch._ai_install_toggles(self)  # 某个面板若是切过去才建好的，这时补上（已有的不会重复加）
        except Exception:
            _tab_log("补装 AI翻译开关失败:\n" + traceback.format_exc())
        try:
            overframe._of_sync_on_mode_switch(self)
        except Exception:
            _tab_log("切换模式时同步超框卡图失败:\n" + traceback.format_exc())
        host = getattr(self, '_ai_dock', None)
        if host is not None:
            host.context_changed()
        return result

    def _switch_mode_styled(self, index: int):
        try:
            return mode_styles._mode_style_switch(self, index, YuGiOhApp._switch_mode_manga)
        except Exception:
            _tab_log("切换模式显示设置失败:\n" + traceback.format_exc())
            return None

    def _switch_mode_manga(self, index: int):
        workbench_index = getattr(self, '_workbench_mode_index', -1)
        if index == workbench_index and workbench_index >= 0:
            manga._manga_leave(self)
            try:
                diy_workbench.enter(self, YuGiOhApp._switch_mode_frame)
            except Exception:
                _tab_log("切换到 DIY 工作台失败:\n" + traceback.format_exc())
            return None
        diy_workbench.leave(self)
        manga_index = getattr(self, '_manga_mode_index', -1)
        if index == manga_index and manga_index >= 0:
            try:
                manga._manga_enter(self, YuGiOhApp._switch_mode_frame)
            except Exception:
                _tab_log("切换到漫画卡模式失败:\n" + traceback.format_exc())
            return None
        manga._manga_leave(self)
        return self._switch_mode_frame(index)

    def _switch_mode_frame(self, index: int):
        try:
            if index == 1:
                return rd_frame._switch_to_rd_frame_only(self)
            rd_frame._set_rd_only_editor_controls(self, False)
            result = self._switch_mode_base(index)
            _safe_call(getattr(getattr(self, 'otcg_widget', None), 'switch_base_image', None))
            return result
        finally:
            _schedule_preview_update_restore(self)

    def _switch_mode_base(self, index: int):
        if index == 0:
            self.view.setScene(self.scene)
            self.view.fitInView(self.otcg_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
            self.stacked_widget.setCurrentIndex(index)
            self.current_mode = index

        elif index == 1:

            if not self.RD_init:
                self.rd_widget.init_vis()
            if self.RD_init:
                self.view.setScene(self.rd_scene)
                self.view.fitInView(self.rd_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
                self.stacked_widget.setCurrentIndex(0)
                self.current_mode = index
            else:
                self.combo_box.setCurrentIndex(self.current_mode)
        elif index == 2:

            if not self.FC_init:
                self.fc_widget.init_vis()
            if self.FC_init:
                self.view.setScene(self.fc_scene)
                self.view.fitInView(self.fc_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
                self.stacked_widget.setCurrentIndex(index)
                self.current_mode = index
            else:
                self.combo_box.setCurrentIndex(self.current_mode)
        elif index == 3:

            if not self.Back_init:
                self.back_widget.init_vis()
            if self.Back_init:
                self.view.setScene(self.back_scene)
                self.view.fitInView(self.back_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
                self.stacked_widget.setCurrentIndex(index)
                self.current_mode = index
            else:
                self.combo_box.setCurrentIndex(self.current_mode)
        else:
            if not self.Past_init:
                self.past_widget.init_vis()
            if self.Past_init:
                self.view.setScene(self.past_scene)
                self.view.fitInView(self.past_widget.base_item.boundingRect(), Qt.KeepAspectRatio)
                self.stacked_widget.setCurrentIndex(index)
                self.current_mode = index
            else:
                self.combo_box.setCurrentIndex(self.current_mode)
            pass
        pass

    def clickable(self, widget: QWidget):
        class Filter(QtCore.QObject):
            clicked = QtCore.pyqtSignal()
            def eventFilter(self, obj, event):
                if obj == widget:
                    if event.type() == QtCore.QEvent.MouseButtonRelease:
                        if obj.rect().contains(event.pos()):
                            self.clicked.emit()

                            return True
                return False
        filter = Filter(widget)
        widget.installEventFilter(filter)
        return filter.clicked

def main():
    prepare_runtime()
    app_window._install_application_identity()
    language_switch._preload_translation_model()  # 翻译模型没载入时把原因记到日志
    applog.install_crash_guard()
    if not startup.single_instance_guard():
        startup.notify_already_running()
        return
    qt_plugins = os.path.join(os.path.dirname(QtCore.__file__), "Qt5", "plugins")
    QtCore.QCoreApplication.addLibraryPath(qt_plugins)
    app = QApplication(sys.argv)
    app.setFont(QFont('Microsoft YaHei', 10))
    yugioh = startup.build_with_splash(YuGiOhApp)
    yugioh.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
