import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsPixmapItem, QFileDialog, QComboBox, QLabel, QSizePolicy

from PyQt5.QtGui import QPixmap, QPainter, QFontMetrics
from PyQt5.QtCore import Qt, QRect, QRectF, QSize
from customComponents import CropDialog, ToggleButton, RoundedPixmapItem, OutputSettingDialogSimple
from PIL import Image
from config import FCConfig
from utils import pillow_img_to_pixmap, qpixmap_to_pillow, decrypt_image_qpixmap, decrypt_image_pillow, rpath, runtime_resource_exists

import json
import numpy as np
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import YuGiOhApp


class FCWidget(QWidget):
    def __init__(self, parent: 'YuGiOhApp' = None):
        super().__init__()
        self.parent_app = parent
        self.fc_layout = QVBoxLayout()

        with open(rpath('config/fc_config.json'), 'r', encoding='utf-8') as config_file:
            config_dict = json.load(config_file)
        self.config = FCConfig(**config_dict)

        font = self.font()
        metric = QFontMetrics(font)

        self.mode_hbox = QHBoxLayout()
        self.mode_label = QLabel('模式', self)
        self.mode_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.mode_selector = QComboBox(self)
        self.mode_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.mode_selector.addItems(['经典', '全图', '卡背'])
        self.mode_selector.currentIndexChanged.connect(self.mode_changed)
        self.mode_hbox.addWidget(self.mode_label)
        self.mode_hbox.addWidget(self.mode_selector)

        self.back_hbox = QHBoxLayout()
        self.back_label = QLabel('背景', self)
        self.back_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.back_selector = QComboBox(self)
        self.back_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.back_selector.addItems(self.config.back_list)
        self.back_selector.currentIndexChanged.connect(self.back_changed)
        self.back_hbox.addWidget(self.back_label)
        self.back_hbox.addWidget(self.back_selector)

        self.center_hbox = QHBoxLayout()
        self.center_label = QLabel('中心图', self)
        self.center_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

        self.center_selector = QComboBox(self)
        self.center_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.center_selector.addItems(self.config.center_list_classic)
        self.center_selector.currentIndexChanged.connect(self.center_changed)

        self.center_back_selector = QComboBox(self)
        self.center_back_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.center_back_selector.addItems(self.config.center_list_back)
        self.center_back_selector.currentIndexChanged.connect(self.center_back_changed)

        self.center_full_selector = QComboBox(self)
        self.center_full_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.center_full_selector.addItems(self.config.center_list_full)
        self.center_full_selector.currentIndexChanged.connect(self.center_full_changed)

        self.center_back_selector.setVisible(False)
        self.center_full_selector.setVisible(False)

        self.upload_btn = QPushButton('自定义中心图', self)
        self.upload_btn.clicked.connect(self.load_image)
        self.center_hbox.addWidget(self.center_label)
        self.center_hbox.addWidget(self.center_selector)
        self.center_hbox.addWidget(self.upload_btn)
        self.center_hbox.setStretch(1, 1)
        self.center_hbox.setStretch(2, 1)

        self.border_hbox = QHBoxLayout()
        self.border_label = QLabel('边框', self)
        self.border_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.border_selector = QComboBox(self)
        self.border_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.border_selector.addItems(self.config.border_list)
        self.border_selector.currentIndexChanged.connect(self.border_changed)
        self.border_selector.setEnabled(False)
        self.border_hbox.addWidget(self.border_label)
        self.border_hbox.addWidget(self.border_selector)

        self.text_hbox = QHBoxLayout()
        self.text_label = QLabel('文字', self)
        self.text_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.text_selector = QComboBox(self)
        self.text_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.text_selector.addItems(self.config.text_list)
        self.text_selector.currentIndexChanged.connect(self.text_changed)
        self.text_hbox.addWidget(self.text_label)
        self.text_hbox.addWidget(self.text_selector)

        self.title_icon_hbox = QHBoxLayout()

        self.title_hbox = QHBoxLayout()
        self.title_label = QLabel('场地标题', self)
        self.title_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.title_selector = QComboBox()
        self.title_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.title_selector.addItems(['小', '大'])
        self.title_selector.currentIndexChanged.connect(self.title_change)
        self.title_hbox.addWidget(self.title_label)
        self.title_hbox.addWidget(self.title_selector)

        self.icon_hbox = QHBoxLayout()
        self.icon_label = QLabel('场地图标', self)
        self.icon_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.icon_selector = QComboBox()
        self.icon_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.icon_selector.addItems(['小', '大'])
        self.icon_selector.currentIndexChanged.connect(self.icon_change)
        self.icon_hbox.addWidget(self.icon_label)
        self.icon_hbox.addWidget(self.icon_selector)

        self.title_icon_hbox.addLayout(self.title_hbox)
        self.title_icon_hbox.addStretch(1)
        self.title_icon_hbox.addLayout(self.icon_hbox)
        self.title_icon_hbox.setStretch(0, 42)
        self.title_icon_hbox.setStretch(2, 42)

        self.logo_hbox = QHBoxLayout()
        self.logo_label = QLabel('卡背LOGO', self)
        self.logo_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.logo_selector = QComboBox(self)
        self.logo_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.logo_selector.addItems(['样式一', '样式二'])
        self.logo_selector.currentIndexChanged.connect(self.logo_changed)
        self.logo_label.setEnabled(False)
        self.logo_selector.setEnabled(False)
        self.logo_hbox.addWidget(self.logo_label)
        self.logo_hbox.addWidget(self.logo_selector)

        self.save_hbox = QHBoxLayout()
        self.save_image_button = QPushButton('导出图片', self)
        self.save_image_button.clicked.connect(self.save_img)
        self.setting_btn = QPushButton('导出设置', self)
        self.setting_btn.clicked.connect(self.on_output_setting)
        self.setting_btn.setFixedWidth(120)
        self.label2 = QLabel('圆角')

        label_width = metric.width('圆角')
        self.label2.setFixedWidth(label_width)
        self.toggle_round = ToggleButton(height=20, width=45, check=False)
        self.toggle_round.toggled.connect(self.on_toggle_round)
        self.save_hbox.addWidget(self.save_image_button)
        self.save_hbox.addWidget(self.setting_btn)
        self.save_hbox.addWidget(self.label2)
        self.save_hbox.addWidget(self.toggle_round)

        self.fc_layout.addLayout(self.mode_hbox)
        self.fc_layout.addLayout(self.back_hbox)
        self.fc_layout.addLayout(self.center_hbox)
        self.fc_layout.addLayout(self.border_hbox)
        self.fc_layout.addLayout(self.text_hbox)
        self.fc_layout.addLayout(self.title_icon_hbox)
        self.fc_layout.addLayout(self.logo_hbox)
        self.fc_layout.addStretch(1)
        self.fc_layout.addLayout(self.save_hbox)
        self.fc_layout.setContentsMargins(0, 5, 0, 0)
        self.setLayout(self.fc_layout)
        pass

    def init_vis(self):
        if not self.check_resource():
            self.parent_app.show_warning_message(mess='场地中心卡')
            return
        self.output_format = 0
        self.save_dir = os.getcwd()
        self.upload_dir = ''

        self.base_item = RoundedPixmapItem(None, radius=28)
        self.parent_app.fc_scene.addItem(self.base_item)

        self.card_rect = QRectF(QRect(0, 0, self.config.card_w, self.config.card_h))
        self.center_size = QSize(self.config.center_w, self.config.center_h)
        self.center_full_size = QSize(self.config.center_full_w, self.config.center_full_h)
        self.center_img = None
        self.center_full_img = None
        self.center_display = None
        self.center_full_display = None

        self.center_item = QGraphicsPixmapItem(None)
        self.center_item.setPos(self.config.center_x, self.config.center_y)
        self.full_center_item = RoundedPixmapItem(None)
        self.back_center_item = QGraphicsPixmapItem(None)
        self.parent_app.fc_scene.addItem(self.center_item)
        self.parent_app.fc_scene.addItem(self.full_center_item)
        self.parent_app.fc_scene.addItem(self.back_center_item)
        self.full_center_item.setVisible(False)
        self.back_center_item.setVisible(False)

        self.border_item = QGraphicsPixmapItem(None)
        self.parent_app.fc_scene.addItem(self.border_item)

        self.arrow_item = QGraphicsPixmapItem(decrypt_image_qpixmap(self.config.arrow_img))
        self.parent_app.fc_scene.addItem(self.arrow_item)

        self.text_item = QGraphicsPixmapItem(decrypt_image_qpixmap(self.config.text_imgs[0]))
        self.parent_app.fc_scene.addItem(self.text_item)

        self.title_item = QGraphicsPixmapItem(decrypt_image_qpixmap(self.config.title_imgs[0]))
        self.parent_app.fc_scene.addItem(self.title_item)
        self.icon_item = QGraphicsPixmapItem(decrypt_image_qpixmap(self.config.icon_imgs[0]))
        self.parent_app.fc_scene.addItem(self.icon_item)

        self.magic_item = QGraphicsPixmapItem(decrypt_image_qpixmap(self.config.magic_img))
        self.parent_app.fc_scene.addItem(self.magic_item)
        self.magic_item.setVisible(False)

        self.logo_item = QGraphicsPixmapItem(decrypt_image_qpixmap(self.config.logo_imgs[0]))
        self.parent_app.fc_scene.addItem(self.logo_item)
        self.logo_item.setVisible(False)

        self.current_center = 0
        self.current_full_center = 20
        self.current_back_center = 1
        self.current_full_border = 1

        self.load_demo()
        self.parent_app.FC_init = True
        pass

    def check_resource(self) -> bool:
        # 资源也可能只在打包目录（sys._MEIPASS）里
        for file in self.config.resource:
            if not runtime_resource_exists(file):
                return False
        return True

    def mode_changed(self, index: int):
        self.logo_selector.setEnabled(index == 2)
        self.logo_label.setEnabled(index == 2)
        self.upload_btn.setDisabled(index == 2)
        if index == 0:
            self.center_item.setVisible(True)
            self.full_center_item.setVisible(False)
            self.back_center_item.setVisible(False)
            if self.center_back_selector.parent():
                self.center_hbox.removeWidget(self.center_back_selector)
                self.center_back_selector.setVisible(False)
            if self.center_full_selector.parent():
                self.center_hbox.removeWidget(self.center_full_selector)
                self.center_full_selector.setVisible(False)
            self.center_hbox.insertWidget(1, self.center_selector)
            self.center_selector.setVisible(True)
            self.center_selector.setCurrentIndex(self.current_center)
        elif index == 1:
            self.center_item.setVisible(False)
            self.full_center_item.setVisible(True)
            self.back_center_item.setVisible(False)
            if self.center_selector.parent():
                self.center_hbox.removeWidget(self.center_selector)
                self.center_selector.setVisible(False)
            if self.center_back_selector.parent():
                self.center_hbox.removeWidget(self.center_back_selector)
                self.center_back_selector.setVisible(False)
            self.center_hbox.insertWidget(1, self.center_full_selector)
            self.center_full_selector.setVisible(True)
            self.center_full_selector.setCurrentIndex(self.current_full_center)
        else:
            self.center_item.setVisible(False)
            self.full_center_item.setVisible(False)
            self.back_center_item.setVisible(True)
            if self.center_selector.parent():
                self.center_hbox.removeWidget(self.center_selector)
                self.center_selector.setVisible(False)
            if self.center_full_selector.parent():
                self.center_hbox.removeWidget(self.center_full_selector)
                self.center_full_selector.setVisible(False)
            self.center_hbox.insertWidget(1, self.center_back_selector)
            self.center_back_selector.setVisible(True)
            self.center_back_selector.setCurrentIndex(self.current_back_center)
        self.center_hbox.setStretch(1, 1)
        self.center_hbox.setStretch(2, 1)

        if index == 1:
            self.border_selector.setEnabled(True)
            self.border_selector.setCurrentIndex(self.current_full_border)
        else:
            self.border_selector.setEnabled(False)
            self.border_selector.setCurrentIndex(0)

        if index == 2:
            self.arrow_item.setVisible(False)
            self.text_item.setVisible(False)
            self.text_selector.setEnabled(False)
            self.title_item.setVisible(False)
            self.icon_item.setVisible(False)
            self.title_selector.setEnabled(False)
            self.icon_selector.setEnabled(False)
            self.magic_item.setVisible(True)
            self.logo_item.setVisible(True)
        else:
            self.arrow_item.setVisible(True)
            self.text_item.setVisible(True)
            self.text_selector.setEnabled(True)
            self.title_item.setVisible(True)
            self.icon_item.setVisible(True)
            self.title_selector.setEnabled(True)
            self.icon_selector.setEnabled(True)
            self.magic_item.setVisible(False)
            self.logo_item.setVisible(False)


    def back_changed(self, index):
        self.base_item.setPixmap(decrypt_image_qpixmap(self.config.back_imgs[index]))
        pass

    def center_changed(self, index):
        self.current_center = index
        self.center_item.setPixmap(decrypt_image_qpixmap(self.config.center_imgs + f'{index}.enc'))

    def center_back_changed(self, index: int):
        self.current_back_center = index
        crop_img = self.crop_center_back(self.config.back_imgs[index], self.config.back_center_stand)
        crop_img = pillow_img_to_pixmap(crop_img)
        self.back_center_item.setPixmap(crop_img)

    def center_full_changed(self, index: int):
        self.current_full_center = index
        self.full_center_item.setPixmap(decrypt_image_qpixmap(self.config.full_center_imgs + f'{index}.enc'))

    def load_image(self):
        file_name, _ = QFileDialog.getOpenFileName(self, '选择本地图片', self.upload_dir, 'Image Files (*.png *.jpg *.bmp)')
        self.upload_dir = os.path.dirname(file_name)
        if file_name:
            if self.mode_selector.currentIndex() == 0:
                self.set_center_img(file_name)
            else:
                self.set_center_img_full(file_name)
        pass

    def set_center_img(self, img_path):
        pil_image = Image.open(img_path).convert('RGBA')
        pixmap = pillow_img_to_pixmap(pil_image)
        crop_dialog = CropDialog(pixmap, self, mode='Center')
        if crop_dialog.exec_():
            pixmap = crop_dialog.get_cropped_pixmap()
            self.center_img = qpixmap_to_pillow(pixmap)
            self.transform_normal_img()
        pass

    def set_center_img_full(self, img_path):
        pil_image = Image.open(img_path).convert('RGBA')
        pixmap = pillow_img_to_pixmap(pil_image)
        crop_dialog = CropDialog(pixmap, self, mode='Center_full')
        if crop_dialog.exec_():
            pixmap = crop_dialog.get_cropped_pixmap()
            self.center_full_img = qpixmap_to_pillow(pixmap)
            self.transform_normal_img_full()
        pass

    def transform_normal_img(self):
        card_img_size = self.center_size
        self.center_display = self.center_img.resize((card_img_size.width(), card_img_size.height()), Image.LANCZOS)
        self.center_display = self.crop_center(self.center_display, self.config.center_stand)
        self.center_display = pillow_img_to_pixmap(self.center_display)
        self.center_item.setPixmap(self.center_display)

    def transform_normal_img_full(self):
        card_img_size = self.center_full_size
        self.center_full_display = self.center_full_img.resize((card_img_size.width(), card_img_size.height()), Image.LANCZOS)
        self.center_full_display = pillow_img_to_pixmap(self.center_full_display)
        self.full_center_item.setPixmap(self.center_full_display)

    def border_changed(self, index: int):
        if self.mode_selector.currentIndex() == 1:
            self.current_full_border = index
        self.border_item.setPixmap(decrypt_image_qpixmap(self.config.border_imgs[index]))

    def text_changed(self, index: int):
        self.text_item.setPixmap(decrypt_image_qpixmap(self.config.text_imgs[index]))

    def title_change(self, index: int):
        self.title_item.setPixmap(decrypt_image_qpixmap(self.config.title_imgs[index]))

    def icon_change(self, index: int):
        self.icon_item.setPixmap(decrypt_image_qpixmap(self.config.icon_imgs[index]))

    def logo_changed(self, index: int):
        self.logo_item.setPixmap(decrypt_image_qpixmap(self.config.logo_imgs[index]))

    def on_toggle_round(self, checked: bool):
        self.base_item.set_rounded(checked)
        self.full_center_item.set_rounded(checked)

    def on_output_setting(self):
        dialog = OutputSettingDialogSimple(format=self.output_format, parent=self)
        if dialog.exec_():
            self.output_format = dialog.format
        pass

    def save_img(self):
        card_name = '场地中心卡背' if self.mode_selector.currentIndex() == 2 else '场地中心卡'
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
        self.parent_app.fc_scene.render(painter, QRectF(image.rect()), self.parent_app.fc_scene.sceneRect())
        painter.end()
        if self.output_format == 0:
            image.save(file_name, format='PNG')
        else:
            image.save(file_name, format='JPG')
        pass
        pass

    def load_demo(self):
        self.back_selector.setCurrentIndex(self.config.demo_back)
        self.center_selector.setCurrentIndex(self.config.demo_center)
        self.center_item.setPixmap(decrypt_image_qpixmap(self.config.center_imgs + '0.enc'))
        self.border_item.setPixmap(decrypt_image_qpixmap(self.config.border_imgs[0]))

    def crop_center_back(self, in_img: str, stand_img: str):
        image_a = decrypt_image_pillow(stand_img)
        image_b = decrypt_image_pillow(in_img)
        image_a = image_a.convert('RGBA')
        image_b = image_b.convert('RGBA')
        alpha_a = np.array(image_a.getchannel('A'))
        alpha_b = np.array(image_b.getchannel('A'))
        merged_alpha = np.minimum(alpha_a, alpha_b)
        image_b.putalpha(Image.fromarray(merged_alpha))
        return image_b

    def crop_center(self, image_b: Image.Image, stand_img: str):
        image_a = decrypt_image_pillow(stand_img)
        image_a = image_a.convert('RGBA')
        image_b = image_b.convert('RGBA')
        alpha_a = np.array(image_a.getchannel('A'))
        alpha_b = np.array(image_b.getchannel('A'))
        merged_alpha = np.minimum(alpha_a, alpha_b)
        image_b.putalpha(Image.fromarray(merged_alpha))
        return image_b
    pass
