from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QLabel, QSizePolicy, QGraphicsPixmapItem, QFileDialog

from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtCore import Qt, QSize, QRectF
from customComponents import RoundedPixmapItem, ToggleButton, OutputSettingDialogSimple
import json
from config import BackConfig
import os
from utils import decrypt_image_qpixmap, rpath, runtime_resource_exists
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import YuGiOhApp


class CardBackWidget(QWidget):
    def __init__(self, parent: 'YuGiOhApp' = None):
        super().__init__()
        self.parent_app = parent
        self.back_layout = QVBoxLayout()

        with open(rpath('config/back_config.json'), 'r', encoding='utf-8') as config_file:
            config_dict = json.load(config_file)
        self.config = BackConfig(**config_dict)

        self.save_dir = os.getcwd()

        self.type_hbox = QHBoxLayout()
        self.type_label = QLabel('类型: ', self)
        self.type_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.type_selector = QComboBox(self)
        self.type_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.type_selector.addItems(['普通', '巨神兵', '天空龙', '翼神龙', 'Zexal'])
        self.type_selector.setCurrentText('普通')
        self.type_selector.currentIndexChanged.connect(self.type_changed)
        self.type_hbox.addWidget(self.type_label)
        self.type_hbox.addWidget(self.type_selector)

        self.logo_hbox = QHBoxLayout()
        self.logo_label = QLabel('标志: ', self)
        self.logo_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.logo_selector = QComboBox(self)
        self.logo_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.logo_selector.addItems(['无', 'OCG', 'TCG', 'RD'])
        self.logo_selector.setCurrentText('OCG')
        self.logo_selector.currentIndexChanged.connect(self.logo_changed)
        self.logo_hbox.addWidget(self.logo_label)
        self.logo_hbox.addWidget(self.logo_selector)

        self.toggle_hbox = QHBoxLayout()
        self.label1 = QLabel('K标')
        self.toggle_konmai = ToggleButton(height=20, width=45)
        self.toggle_konmai.toggled.connect(self.on_toggle_konami)
        self.label2 = QLabel('R标')
        self.toggle_rsymbol = ToggleButton(height=20, width=45)
        self.toggle_rsymbol.toggled.connect(self.on_toggle_rsymbol)
        self.label3 = QLabel('圆角')
        self.toggle_round = ToggleButton(height=20, width=45, check=False)
        self.toggle_round.toggled.connect(self.on_toggle_round)
        self.toggle_hbox.addWidget(self.label1)
        self.toggle_hbox.addWidget(self.toggle_konmai)
        self.toggle_hbox.addStretch(0)
        self.toggle_hbox.addWidget(self.label2)
        self.toggle_hbox.addWidget(self.toggle_rsymbol)
        self.toggle_hbox.addStretch(0)
        self.toggle_hbox.addWidget(self.label3)
        self.toggle_hbox.addWidget(self.toggle_round)

        self.save_hbox = QHBoxLayout()
        self.save_image_button = QPushButton('导出图片', self)
        self.save_image_button.clicked.connect(self.save_img)
        self.setting_btn = QPushButton('导出设置', self)
        self.setting_btn.clicked.connect(self.on_output_setting)
        self.setting_btn.setFixedWidth(120)
        self.save_hbox.addWidget(self.save_image_button)
        self.save_hbox.addWidget(self.setting_btn)

        self.back_layout.addLayout(self.type_hbox)
        self.back_layout.addLayout(self.logo_hbox)
        self.back_layout.addLayout(self.toggle_hbox)
        self.back_layout.addStretch(1)
        self.back_layout.addLayout(self.save_hbox)
        self.back_layout.setContentsMargins(0, 5, 0, 0)
        self.setLayout(self.back_layout)

        pass

    def init_vis(self):
        if not self.check_resource():
            self.parent_app.show_warning_message(mess='卡背')
            return
        self.base_item = RoundedPixmapItem(decrypt_image_qpixmap('CardBack/back.enc'), radius=28)
        self.parent_app.back_scene.addItem(self.base_item)
        self.logo_item = QGraphicsPixmapItem(decrypt_image_qpixmap('CardBack/ocg.enc'))
        self.parent_app.back_scene.addItem(self.logo_item)
        self.konami_item = QGraphicsPixmapItem(decrypt_image_qpixmap('CardBack/konami.enc'))
        self.parent_app.back_scene.addItem(self.konami_item)
        self.rsymbol_item = QGraphicsPixmapItem(decrypt_image_qpixmap('CardBack/rsymbol.enc'))
        self.parent_app.back_scene.addItem(self.rsymbol_item)

        self.output_format = 0
        self.parent_app.Back_init = True

    def check_resource(self) -> bool:
        # 资源也可能只在打包目录（sys._MEIPASS）里
        for file in self.config.resource:
            if not runtime_resource_exists(file):
                return False
        return True

    def type_changed(self):
        self.base_item.setPixmap(decrypt_image_qpixmap(self.config.type_path[self.type_selector.currentText()]))

    def logo_changed(self):
        if self.logo_selector.currentIndex() == 0:
            self.logo_item.setVisible(False)
        else:
            self.logo_item.setVisible(True)
            self.logo_item.setPixmap(decrypt_image_qpixmap(self.config.logo_path[self.logo_selector.currentText()]))
        pass

    def on_toggle_konami(self, checked: bool):
        self.konami_item.setVisible(checked)

    def on_toggle_rsymbol(self, checked: bool):
        self.rsymbol_item.setVisible(checked)

    def on_toggle_round(self, checked: bool):
        self.base_item.set_rounded(checked)

    def on_output_setting(self):
        dialog = OutputSettingDialogSimple(format=self.output_format, parent=self)
        if dialog.exec_():
            self.output_format = dialog.format
        pass

    def save_img(self):
        card_name = '卡背'
        if self.output_format == 0:
            file_name, _ = QFileDialog.getSaveFileName(self, '保存结果', os.path.join(self.save_dir, card_name),
                                                       'Image Files (*.png)')
        else:
            file_name, _ = QFileDialog.getSaveFileName(self, '保存结果', os.path.join(self.save_dir, card_name),
                                                       'Image Files (*.jpg)')
        if not file_name:
            return
        self.save_dir = os.path.dirname(file_name)
        card_size = QSize(self.config.card_w, self.config.card_h)
        image = QPixmap(card_size)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self.parent_app.back_scene.render(painter, QRectF(image.rect()), self.parent_app.back_scene.sceneRect())
        painter.end()
        if self.output_format == 0:
            image.save(file_name, format='PNG')
        else:
            image.save(file_name, format='JPG')
        pass

    pass
