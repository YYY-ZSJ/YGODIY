import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsPixmapItem, QFileDialog, QColorDialog, QComboBox, QLabel, QSizePolicy, QSpacerItem, QGraphicsDropShadowEffect, QToolTip


from PyQt5.QtGui import QPixmap, QFont, QColor, QPainter, QTextOption, QTextCursor, QTextBlockFormat, QFontMetricsF, QRegularExpressionValidator, QFontMetrics, QTransform

from PyQt5.QtCore import Qt, QRect, QRectF, QRegularExpression, QSize, QThreadPool, QPoint
from customComponents import Worker, AttributeButton, StarButton, CloseButton, ColorButton, QLineEdit, QTextEdit, CropDialog, ToggleButton, RoundedButton, ColorAdvancedDialog, RoundedPixmapItem, OutputSettingDialog


from infoFetcher import RDFetcher
from mixTextItem import MixTextItem
from PyQt5.QtSvg import QGraphicsSvgItem, QSvgRenderer
from PIL import Image
from config import RDConfig
from utils import pillow_img_to_pixmap, qpixmap_to_pillow, clean_filename, remove_leading_zeros, decrypt_image_pillow, decrypt_image_qpixmap, decrypt_font, decrypt_svg, rpath, runtime_resource_exists


import json
import numpy as np
import requests
import io
import traceback

import customization
import overframe
import rarity
import rd_frame
import rd_panel
import rd_style
from common import _RD_RANK_RESOURCE_PREFIX, _tab_log

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import YuGiOhApp


ATTRIBUTE_DICT = {
    0: '光', 1: '暗', 2: '风', 3: '水', 4: '炎', 5: '地', 6: '神'}



class RDWidget(QWidget):
    def __init__(self, parent: 'YuGiOhApp' = None):
        super().__init__()
        with open(rpath('config/rd_config.json'), 'r', encoding='utf-8') as config_file:
            config_dict = json.load(config_file)
        self.config = RDConfig(**config_dict)
        self.parent_app = parent

        self.rd_layout = QVBoxLayout()


        self.name_type_hbox = QHBoxLayout()
        card_name_hbox = QHBoxLayout()
        self.card_name_label = QLabel('卡名', self)
        self.card_name_edit = QLineEdit()
        self.card_name_edit.setPlaceholderText('输入卡名')
        self.card_name_edit.setMaxLength(50)
        self.card_name_edit.textChanged.connect(self.update_card_name)
        card_name_hbox.addWidget(self.card_name_label)
        card_name_hbox.addWidget(self.card_name_edit)
        card_type_hbox = QHBoxLayout()
        self.card_type_label = QLabel('类型', self)
        self.card_type_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.type_selector = QComboBox(self)
        self.type_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.type_selector.addItems(['怪兽卡', '魔法卡', '陷阱卡'])
        self.type_selector.currentIndexChanged.connect(self.switch_card_type)
        card_type_hbox.addWidget(self.card_type_label)
        card_type_hbox.addWidget(self.type_selector)
        self.name_type_hbox.addLayout(card_name_hbox)
        self.name_type_hbox.addStretch(1)
        self.name_type_hbox.addLayout(card_type_hbox)
        self.name_type_hbox.setStretch(0, 4)
        self.name_type_hbox.setStretch(2, 4)


        self.color_vbox = QVBoxLayout()

        self.color_label_hbox = QHBoxLayout()
        self.color_label = QLabel('卡名颜色：')
        self.color_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.color_advanced_label = QLabel('高级选项 ')
        self.color_advanced_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        spacer = QSpacerItem(40, 20, QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.color_advanced_btn = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.color_advanced_btn.toggled.connect(self.change_color_mode)

        self.color_label_hbox.addWidget(self.color_label)
        self.color_label_hbox.addItem(spacer)
        self.color_label_hbox.addWidget(self.color_advanced_label)
        self.color_label_hbox.addWidget(self.color_advanced_btn)

        self.color_option = 0
        self.mix_option = 0
        self.color_btn_hbox = QHBoxLayout()
        self.color_black_btn = ColorButton(circle_color=QColor(0, 0, 0), text='黑色', parent=self)
        self.color_black_btn.toggled.connect(self.color_btn_clicked)
        self.color_white_btn = ColorButton(circle_color=QColor(255, 255, 255), text='白色', parent=self)
        self.color_white_btn.toggled.connect(self.color_btn_clicked)
        self.color_gold_btn = ColorButton(circle_color=QColor(251, 215, 5), text='金色', parent=self)
        self.color_gold_btn.toggled.connect(self.color_btn_clicked)
        self.color_red_btn = ColorButton(circle_color=QColor(255, 0, 0), text='红色', parent=self)
        self.color_red_btn.toggled.connect(self.color_btn_clicked)
        self.color_custom_btn = ColorButton(circle_color=QColor(255, 255, 255), text='其他', parent=self)
        self.color_custom_btn.toggled.connect(self.color_btn_clicked)
        self.color_btn_hbox.addWidget(self.color_black_btn)
        self.color_btn_hbox.addStretch(1)
        self.color_btn_hbox.addWidget(self.color_white_btn)
        self.color_btn_hbox.addStretch(1)
        self.color_btn_hbox.addWidget(self.color_gold_btn)
        self.color_btn_hbox.addStretch(1)
        self.color_btn_hbox.addWidget(self.color_red_btn)
        self.color_btn_hbox.addStretch(1)
        self.color_btn_hbox.addWidget(self.color_custom_btn)
        self.color_vbox.addLayout(self.color_label_hbox)
        self.color_vbox.addLayout(self.color_btn_hbox)
        self.color_btn_list = [self.color_black_btn, self.color_white_btn, self.color_gold_btn, self.color_red_btn, self.color_custom_btn]

        self.color_advanced_hbox = QHBoxLayout()
        self.color_silver_btn = ColorButton(text='银字', parent=self, half=True, top_color=QColor(255, 255, 255), bottom_color=QColor(161, 161, 161))
        self.color_silver_btn.toggled.connect(self.advanced_btn_clicked)
        self.color_golden_btn = ColorButton(text='金字', parent=self, half=True, top_color=QColor(255, 220, 0), bottom_color=QColor(181, 129, 0))
        self.color_golden_btn.toggled.connect(self.advanced_btn_clicked)
        self.color_blue_btn = ColorButton(text='青字', parent=self, half=True, top_color=QColor(76, 255, 190), bottom_color=QColor(0, 153, 163))
        self.color_blue_btn.toggled.connect(self.advanced_btn_clicked)
        self.color_scarlet_btn = ColorButton(text='红字', parent=self, half=True, top_color=QColor(255, 0, 0), bottom_color=QColor(0, 0, 0))
        self.color_scarlet_btn.toggled.connect(self.advanced_btn_clicked)
        self.color_defined_btn = ColorButton(text='自定义', parent=self, half=True, top_color=QColor(255, 255, 255), bottom_color=QColor(0, 0, 0))
        self.color_defined_btn.toggled.connect(self.advanced_btn_clicked)
        self.color_advanced_hbox.addWidget(self.color_silver_btn)
        self.color_advanced_hbox.addStretch(1)
        self.color_advanced_hbox.addWidget(self.color_golden_btn)
        self.color_advanced_hbox.addStretch(1)
        self.color_advanced_hbox.addWidget(self.color_blue_btn)
        self.color_advanced_hbox.addStretch(1)
        self.color_advanced_hbox.addWidget(self.color_scarlet_btn)
        self.color_advanced_hbox.addStretch(1)
        self.color_advanced_hbox.addWidget(self.color_defined_btn)
        self.color_advanced_list = [self.color_silver_btn, self.color_golden_btn, self.color_blue_btn, self.color_scarlet_btn, self.color_defined_btn]
        for btn in self.color_advanced_list:
            btn.setVisible(False)


        self.upload_btn_hbox = QHBoxLayout()
        self.load_image_button_nocrop = QPushButton('上传卡图(不裁剪)', self)
        self.load_image_button_nocrop.clicked.connect(self.load_image_nocrop)
        self.load_image_button_crop = QPushButton('上传卡图(裁剪)', self)
        self.load_image_button_crop.clicked.connect(self.load_image_crop)
        self.upload_btn_hbox.addWidget(self.load_image_button_nocrop)
        self.upload_btn_hbox.addWidget(self.load_image_button_crop)


        self.race = ''
        self.call_way = ''
        self.extra_info = ''
        self.detail_info_hbox = QHBoxLayout()
        self.detail_info_label = QLabel('详细', self)
        self.detail_info_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.race_selector = QComboBox(self)
        self.race_selector.addItems(self.config.race_list)
        self.race_selector.currentIndexChanged.connect(self.switch_info)
        self.race_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.call_way_selector = QComboBox(self)
        self.call_way_selector.addItems(self.config.call_way_list)
        self.call_way_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.call_way_selector.setCurrentText('效果')
        self.call_way_selector.currentIndexChanged.connect(self.switch_info)
        self.extra_info_selector = QComboBox(self)
        self.extra_info_selector.addItems(['通常', '效果'])
        self.extra_info_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.extra_info_selector.setCurrentIndex(1)
        self.extra_info_selector.currentIndexChanged.connect(self.switch_info)
        self.detail_info_hbox.addWidget(self.detail_info_label)
        self.detail_info_hbox.addWidget(self.race_selector)
        self.detail_info_hbox.addWidget(self.call_way_selector)
        self.detail_info_hbox.addWidget(self.extra_info_selector)

        self.MT_type_hbox = QHBoxLayout()
        self.MT_type_label = QLabel('类型', self)
        self.MT_type_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.MT_type_selector = QComboBox(self)
        self.MT_type_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.MT_type_selector.addItems(['通常', '永续', '装备', '仪式', '场地', '反击', '速攻'])
        self.MT_type_selector.currentIndexChanged.connect(self.update_MT_type)
        self.MT_type_hbox.addWidget(self.MT_type_label)
        self.MT_type_hbox.addWidget(self.MT_type_selector)
        self.MT_type_label.setVisible(False)
        self.MT_type_selector.setVisible(False)


        self.attribute_on_colors = {'光': '#ffd700', '暗': '#785ba2', '风': '#72bb53', '水': '#11abe5',
            '炎': '#ff0000', '地': '#000000', '神': '#7c6439'}
        self.attribute_off_colors = {'光': '#f9edac', '暗': '#d0c7dd', '风': '#cee4c5', '水': '#b1e0f1',
            '炎': '#f9acac', '地': '#acacac', '神': '#d1cabd'}

        self.attribute_hbox = QHBoxLayout()
        self.attribute_label = QLabel('属性：', self)
        self.attribute_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.attribute_hbox.addWidget(self.attribute_label)

        self.light_btn = AttributeButton('光', 40, 25, color=self.attribute_off_colors['光'])
        self.dark_btn = AttributeButton('暗', 40, 25, color=self.attribute_on_colors['暗'])
        self.wind_btn = AttributeButton('风', 40, 25, color=self.attribute_off_colors['风'])
        self.water_btn = AttributeButton('水', 40, 25, color=self.attribute_off_colors['水'])
        self.fire_btn = AttributeButton('炎', 40, 25, color=self.attribute_off_colors['炎'])
        self.ground_btn = AttributeButton('地', 40, 25, color=self.attribute_off_colors['地'])
        self.god_btn = AttributeButton('神', 40, 25, color=self.attribute_off_colors['神'])
        self.attribute_hbox.addWidget(self.light_btn)
        self.attribute_hbox.addStretch(1)
        self.attribute_hbox.addWidget(self.dark_btn)
        self.attribute_hbox.addStretch(1)
        self.attribute_hbox.addWidget(self.wind_btn)
        self.attribute_hbox.addStretch(1)
        self.attribute_hbox.addWidget(self.water_btn)
        self.attribute_hbox.addStretch(1)
        self.attribute_hbox.addWidget(self.fire_btn)
        self.attribute_hbox.addStretch(1)
        self.attribute_hbox.addWidget(self.ground_btn)
        self.attribute_hbox.addStretch(1)
        self.attribute_hbox.addWidget(self.god_btn)

        self.attribute_btn_dict = {'光': self.light_btn, '暗': self.dark_btn, '风': self.wind_btn, '水': self.water_btn,
            '炎': self.fire_btn, '地': self.ground_btn, '神': self.god_btn}

        self.light_btn.clicked.connect(self.attribute_clicked)
        self.dark_btn.clicked.connect(self.attribute_clicked)
        self.wind_btn.clicked.connect(self.attribute_clicked)
        self.water_btn.clicked.connect(self.attribute_clicked)
        self.fire_btn.clicked.connect(self.attribute_clicked)
        self.ground_btn.clicked.connect(self.attribute_clicked)
        self.god_btn.clicked.connect(self.attribute_clicked)


        self.star_level_color = '#f7d60a'
        self.level_bg_color = '#f14724'
        self.star_rank_color = '#ffdd33'
        self.rank_bg_color = '#2e3234'
        self.star_undo_color = '#ffffff'
        self.bg_undo_color = '#595959'
        self.level_box = QHBoxLayout()

        font = self.font()
        metric = QFontMetrics(font)
        level_label_width = metric.width('等级 10 ')
        self.level_label = QLabel('等级 2 ', self)
        self.level_label.setFixedWidth(level_label_width)
        self.level_box.addWidget(self.level_label)
        self.level_zero_btn = CloseButton(width=20, height=20)
        self.level_zero_btn.clicked.connect(self.star_zero_clicked)
        self.level_star_btn_list = [StarButton(radius=10) for _ in range(13)]
        self.level_box.addWidget(self.level_zero_btn)
        for btn in self.level_star_btn_list:
            btn.clicked.connect(self.star_clicked)
            self.level_box.addStretch(0)
            self.level_box.addWidget(btn)






        self.ATK_DEF_hbox = QHBoxLayout()

        self.ATK_hbox = QHBoxLayout()
        self.ATK_label = QLabel('攻击', self)
        self.ATK_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.ATK_edit = QLineEdit()
        self.ATK_edit.setPlaceholderText('ATK')
        self.ATK_edit.setMaxLength(4)
        self.ATK_edit.textChanged.connect(self.update_ATK)
        self.ATK_hbox.addWidget(self.ATK_label)
        self.ATK_hbox.addWidget(self.ATK_edit)

        self.DEF_hbox = QHBoxLayout()
        self.DEF_label = QLabel('防御', self)
        self.DEF_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.DEF_edit = QLineEdit()
        self.DEF_edit.setPlaceholderText('DEF')
        self.DEF_edit.setMaxLength(4)
        self.DEF_edit.textChanged.connect(self.update_DEF)
        self.DEF_hbox.addWidget(self.DEF_label)
        self.DEF_hbox.addWidget(self.DEF_edit)

        regular_exp = QRegularExpression('[0-9?]*')
        validator = QRegularExpressionValidator(regular_exp, self.ATK_edit)
        self.ATK_edit.setValidator(validator)
        self.DEF_edit.setValidator(validator)

        self.Max_ATK_hbox = QHBoxLayout()
        self.Max_ATK_label = QLabel('极限攻击')
        self.Max_ATK_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.Max_ATK_toggle = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.Max_ATK_toggle.toggled.connect(self.on_toggle_Max_ATK)
        self.Max_ATK_edit = QLineEdit()
        self.Max_ATK_edit.setPlaceholderText('Max ATK')
        self.Max_ATK_edit.setMaxLength(4)
        self.Max_ATK_edit.setText('3000')
        self.Max_ATK_edit.setDisabled(True)
        self.Max_ATK_edit.setValidator(validator)
        self.Max_ATK_edit.textChanged.connect(self.update_Max)
        self.Max_ATK_hbox.addWidget(self.Max_ATK_label)
        self.Max_ATK_hbox.addWidget(self.Max_ATK_toggle)
        self.Max_ATK_hbox.addWidget(self.Max_ATK_edit)

        self.ATK_DEF_hbox.addLayout(self.ATK_hbox)
        self.ATK_DEF_hbox.addStretch(5)
        self.ATK_DEF_hbox.addLayout(self.DEF_hbox)
        self.ATK_DEF_hbox.addStretch(5)
        self.ATK_DEF_hbox.addLayout(self.Max_ATK_hbox)
        self.ATK_DEF_hbox.setStretch(0, 25)
        self.ATK_DEF_hbox.setStretch(2, 25)
        self.ATK_DEF_hbox.setStretch(4, 40)


        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText('效果')
        self.text_input.textChanged.connect(self.update_text)


        self.card_info_hbox = QHBoxLayout()
        card_pass_hbox = QHBoxLayout()
        self.card_pass_label = QLabel('卡密')
        self.card_pass_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.card_pass_edit = QLineEdit()
        self.card_pass_edit.setMaxLength(9)
        regular_exp = QRegularExpression('[0-9]*')
        validator = QRegularExpressionValidator(regular_exp, self.card_pass_edit)
        self.card_pass_edit.setValidator(validator)

        self.card_pass_btn = RoundedButton(text='检索', width=60, height=25)
        self.card_pass_btn.clicked.connect(self.on_pass_btn_clicked)
        card_pass_hbox.addWidget(self.card_pass_label)
        card_pass_hbox.addWidget(self.card_pass_edit)
        card_pass_hbox.addWidget(self.card_pass_btn)
        card_pack_hbox = QHBoxLayout()
        self.card_pack_label = QLabel('卡包')
        self.card_pack_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.card_pack_edit = QLineEdit()
        self.card_pack_edit.setMaxLength(13)
        self.card_pack_edit.setText('RD/KP19-JP024')
        regular_exp = QRegularExpression('[A-Za-z0-9/-]*')
        validator = QRegularExpressionValidator(regular_exp, self.card_pack_edit)
        self.card_pack_edit.setValidator(validator)
        self.card_pack_edit.textChanged.connect(self.update_card_pack)
        self.random_btn = RoundedButton(text='随机一卡', width=80, height=25)
        self.random_btn.clicked.connect(self.random_card)
        card_pack_hbox.addWidget(self.card_pack_label)
        card_pack_hbox.addWidget(self.card_pack_edit)
        card_pack_hbox.addWidget(self.random_btn)
        self.card_info_hbox.addLayout(card_pass_hbox)
        self.card_info_hbox.addStretch(1)
        self.card_info_hbox.addLayout(card_pack_hbox)
        self.card_info_hbox.setStretch(0, 4)
        self.card_info_hbox.setStretch(2, 4)


        self.holo_copyright_hbox = QHBoxLayout()

        self.holo_hbox = QHBoxLayout()
        self.holo_label = QLabel('防伪标志', self)
        self.holo_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.holo_selector = QComboBox()
        self.holo_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.holo_selector.addItems(['样式一', '样式二', '样式三'])
        self.holo_selector.setCurrentText('样式一')
        self.holo_selector.currentIndexChanged.connect(self.holo_change)
        self.holo_hbox.addWidget(self.holo_label)
        self.holo_hbox.addWidget(self.holo_selector)

        self.copyright_hbox = QHBoxLayout()
        self.copyright_label = QLabel('版权文字', self)
        self.copyright_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.copyright_selector = QComboBox()
        self.copyright_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.copyright_selector.addItems(['样式一', '样式二', '样式三'])
        self.copyright_selector.setCurrentText('样式一')
        self.copyright_selector.currentIndexChanged.connect(self.copyright_change)
        self.copyright_hbox.addWidget(self.copyright_label)
        self.copyright_hbox.addWidget(self.copyright_selector)

        self.holo_copyright_hbox.addLayout(self.holo_hbox)
        self.holo_copyright_hbox.addStretch(1)
        self.holo_copyright_hbox.addLayout(self.copyright_hbox)
        self.holo_copyright_hbox.setStretch(0, 4)
        self.holo_copyright_hbox.setStretch(2, 4)

        self.rare_water_hbox = QHBoxLayout()

        rare_list = ['N', 'SR', 'RR', 'PSER']
        self.rare_hbox = QHBoxLayout()
        self.rare_label = QLabel('罕贵', self)
        self.rare_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.rare_selector = QComboBox()
        self.rare_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.rare_selector.addItems(rare_list)
        self.rare_selector.currentIndexChanged.connect(self.rare_change)
        self.rare_hbox.addWidget(self.rare_label)
        self.rare_hbox.addWidget(self.rare_selector)

        water_list = ['无', 'sample']
        self.water_hbox = QHBoxLayout()
        self.water_label = QLabel('水印', self)
        self.water_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.water_selector = QComboBox()
        self.water_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.water_selector.addItems(water_list)
        self.water_selector.currentIndexChanged.connect(self.watermark_change)
        self.water_hbox.addWidget(self.water_label)
        self.water_hbox.addWidget(self.water_selector)

        self.rare_water_hbox.addLayout(self.rare_hbox)
        self.rare_water_hbox.addStretch(1)
        self.rare_water_hbox.addLayout(self.water_hbox)
        self.rare_water_hbox.setStretch(0, 4)
        self.rare_water_hbox.setStretch(2, 4)


        self.toggle_hbox = QHBoxLayout()
        self.label1 = QLabel('卡包')
        self.toggle_pack = ToggleButton(height=20, width=45)
        self.toggle_pack.toggled.connect(self.on_toggle_pack)
        self.label2 = QLabel('防伪标志')
        self.toggle_holo = ToggleButton(height=20, width=45)
        self.toggle_holo.toggled.connect(self.on_toggle_holo)
        self.label3 = QLabel('版权文字')
        self.toggle_copy = ToggleButton(height=20, width=45)
        self.toggle_copy.toggled.connect(self.on_toggle_copy)
        self.label4 = QLabel('传说')
        self.toggle_legend = ToggleButton(height=20, width=45, check=False)
        self.toggle_legend.toggled.connect(self.on_toggle_legend)
        self.label5 = QLabel('圆角')
        self.toggle_corner = ToggleButton(check=False, height=20, width=45)
        self.toggle_corner.toggled.connect(self.on_toggle_corner)
        self.toggle_hbox.addWidget(self.label1)
        self.toggle_hbox.addWidget(self.toggle_pack)
        self.toggle_hbox.addStretch(0)
        self.toggle_hbox.addWidget(self.label2)
        self.toggle_hbox.addWidget(self.toggle_holo)
        self.toggle_hbox.addStretch(0)
        self.toggle_hbox.addWidget(self.label3)
        self.toggle_hbox.addWidget(self.toggle_copy)
        self.toggle_hbox.addStretch(0)
        self.toggle_hbox.addWidget(self.label4)
        self.toggle_hbox.addWidget(self.toggle_legend)
        self.toggle_hbox.addStretch(0)
        self.toggle_hbox.addWidget(self.label5)
        self.toggle_hbox.addWidget(self.toggle_corner)


        self.save_hbox = QHBoxLayout()
        self.save_image_button = QPushButton('导出图片', self)
        self.save_image_button.clicked.connect(self.on_save_image)
        self.setting_btn = QPushButton('导出设置', self)
        self.setting_btn.clicked.connect(self.on_output_setting)
        self.setting_btn.setFixedWidth(120)
        self.save_hbox.addWidget(self.save_image_button)
        self.save_hbox.addWidget(self.setting_btn)


        self.rd_btn = QPushButton('导出图片')
        self.rd_layout.addLayout(self.name_type_hbox)
        self.rd_layout.addLayout(self.color_vbox)
        self.rd_layout.addLayout(self.upload_btn_hbox)
        self.rd_layout.addLayout(self.detail_info_hbox)
        self.rd_layout.addLayout(self.attribute_hbox)
        self.rd_layout.addLayout(self.level_box)
        self.rd_layout.addLayout(self.ATK_DEF_hbox)
        self.rd_layout.addWidget(self.text_input)
        self.rd_layout.addLayout(self.card_info_hbox)
        self.rd_layout.addLayout(self.holo_copyright_hbox)
        self.rd_layout.addLayout(self.rare_water_hbox)
        self.rd_layout.addLayout(self.toggle_hbox)
        self.rd_layout.addLayout(self.save_hbox)
        self.rd_layout.setContentsMargins(0, 5, 0, 0)
        self.setLayout(self.rd_layout)
        rarity._add_extra_rarity_grades(self, ('ORR',))
        rd_panel._add_rd_text_color_button(self)
        overframe._add_rd_overframe_button(self)
        rarity._install_rarity_popup_position(getattr(self, 'rare_selector', None))
        customization._install_customization_controls(self)

    def init_vis(self):
        if self.check_resource():
            self._init_vis_items()
        else:
            self.parent_app.show_warning_message(mess='RD')
        # 超框卡图图层与前层
        overframe._ensure_rd_overframe(self)
        overframe._apply_rd_overframe_layers(self)
        overframe._rd_apply_overframe_image(self, "top")
        overframe._rd_apply_overframe_image(self, "bot")
        # 右栏按 OCG/TCG 的版式重排、补齐控件
        rd_panel._schedule_rd_layout(self)
        rd_panel._complete_rd_panel(self)

    def _init_vis_items(self):
        self.card_type = '怪兽卡'

        self.mix_mode_flag = False
        self.shadow_vis_ratio = 1.0
        self.outline_enabled = True
        self.outline_color = QColor(0, 0, 0)
        self.outline_thickess = 2
        self.shadow_flag = True
        self.shadow_color = QColor(0, 0, 0)
        self.shadow_blur_size = 5
        self.shadow_x_offset = 2
        self.shadow_y_offset = 2
        self.gradient_flag = True
        self.gradient_process = [[True, 0, QColor(222, 0, 0)], [False, 0.2, QColor(0, 0, 0)], [False, 0.6, QColor(0, 200, 0)],
            [False, 0.7, QColor(251, 121, 32)], [False, 0.8, QColor(0, 145, 101)], [True, 1, QColor(0, 222, 0)]]
        self.single_color = QColor(0, 0, 0)

        self.outline_enabled_c = True
        self.outline_color_c = QColor(0, 0, 0)
        self.outline_thickess_c = 3
        self.shadow_flag_c = True
        self.shadow_color_c = QColor(0, 0, 0)
        self.shadow_blur_size_c = 5
        self.shadow_x_offset_c = 2
        self.shadow_y_offset_c = 2
        self.gradient_flag_c = True
        self.gradient_process_c = [[True, 0, QColor(222, 0, 0)], [False, 0.2, QColor(0, 0, 0)], [False, 0.6, QColor(0, 200, 0)],
            [False, 0.7, QColor(251, 121, 32)], [False, 0.8, QColor(0, 145, 101)], [True, 1, QColor(0, 0, 0)]]
        self.single_color_c = QColor(240, 0, 0)

        self.threadpool = QThreadPool()
        self.info_fetcher = RDFetcher()
        self.card_pass_list = None

        self.base_item = RoundedPixmapItem(None, radius=28)
        self.parent_app.rd_scene.addItem(self.base_item)

        self.card_rect = QRectF(QRect(0, 0, self.config.card_w, self.config.card_h))
        self.card_img_size = QSize(self.config.card_img_w, self.config.card_img_h)
        self.card_img = None
        self.display_img = None
        self.card_img_item = QGraphicsPixmapItem(None)
        self.card_img_item.setPos(self.config.card_img_x, self.config.card_img_y)
        self.parent_app.rd_scene.addItem(self.card_img_item)

        self.mask_item = QGraphicsPixmapItem(None)
        self.parent_app.rd_scene.addItem(self.mask_item)
        self.mask_item.setPos(self.config.mask_pos_x, self.config.mask_pos_y)

        self.current_attribute = ''
        self.attribute_item = QGraphicsPixmapItem(None)
        self.parent_app.rd_scene.addItem(self.attribute_item)

        self.legend_item = QGraphicsPixmapItem(decrypt_image_qpixmap(self.config.legend_img))
        self.parent_app.rd_scene.addItem(self.legend_item)
        self.legend_item.setVisible(False)

        self.ATK_DEF_item = QGraphicsPixmapItem(decrypt_image_qpixmap(self.config.ATK_DEF_img))
        self.parent_app.rd_scene.addItem(self.ATK_DEF_item)

        self.Max_ATK_flag = False
        self.Max_ATK_item = QGraphicsPixmapItem(decrypt_image_qpixmap(self.config.MAX_ATK_img))
        self.parent_app.rd_scene.addItem(self.Max_ATK_item)
        self.Max_ATK_item.setVisible(False)

        self.current_level = 4
        self.level_item = QGraphicsPixmapItem(None)
        self.parent_app.rd_scene.addItem(self.level_item)

        self.icon_item = QGraphicsPixmapItem(None)
        self.parent_app.rd_scene.addItem(self.icon_item)
        self.icon_item.setPos(self.config.icon_x, self.config.icon_y)
        self.icon_item.setVisible(False)

        self.title_color = QColor(Qt.black)
        self.card_name_item = MixTextItem('', duplicate=True)
        self.card_name_item.setDefaultTextColor(Qt.black)
        font = decrypt_font(self.config.name_font)
        font.setPixelSize(self.config.card_name_size)
        self.card_name_item.setFont(font)
        self.card_name_item.setPos(self.config.card_name_posx, self.config.card_name_posy)
        self.card_name_item.document().setDocumentMargin(self.config.card_name_margin)
        self.parent_app.rd_scene.addItem(self.card_name_item)

        self.card_name_list = [MixTextItem('', duplicate=True) for _ in range(self.config.NAME_LIST_LEN)]
        for i in range(self.config.NAME_LIST_LEN):
            self.card_name_list[i].setVisible(False)
            self.card_name_list[i].setDefaultTextColor(Qt.black)
            self.card_name_list[i].document().setDocumentMargin(self.config.card_name_margin)
            self.parent_app.rd_scene.addItem(self.card_name_list[i])

        self.mix_name_item = MixTextItem(duplicate=True)
        self.mix_name_item.setDefaultTextColor(Qt.transparent)
        font = decrypt_font(self.config.name_font)
        font.setPixelSize(self.config.card_name_size)
        self.mix_name_item.setFont(font)
        self.mix_name_item.setPos(self.config.card_name_posx, self.config.card_name_posy)
        self.mix_name_item.document().setDocumentMargin(self.config.card_name_margin)
        self.parent_app.rd_scene.addItem(self.mix_name_item)
        self.mix_name_item.setVisible(False)

        self.mix_name_list = [MixTextItem(duplicate=True) for _ in range(self.config.NAME_LIST_LEN)]
        for i in range(self.config.NAME_LIST_LEN):
            self.mix_name_list[i].setVisible(False)
            self.mix_name_list[i].setDefaultTextColor(Qt.transparent)
            self.mix_name_list[i].document().setDocumentMargin(self.config.card_name_margin)
            self.parent_app.rd_scene.addItem(self.mix_name_list[i])

        self.shadow_effect = QGraphicsDropShadowEffect()
        self.shadow_effect.setColor(self.shadow_color)
        self.shadow_effect.setBlurRadius(self.shadow_blur_size)
        self.shadow_effect.setXOffset(self.shadow_x_offset)
        self.shadow_effect.setYOffset(self.shadow_y_offset)
        self.shadow_list = [QGraphicsDropShadowEffect() for _ in range(self.config.NAME_LIST_LEN)]
        for i in range(self.config.NAME_LIST_LEN):
            self.shadow_list[i].setColor(self.shadow_color)
            self.shadow_list[i].setBlurRadius(self.shadow_blur_size)
            self.shadow_list[i].setXOffset(self.shadow_x_offset)
            self.shadow_list[i].setYOffset(self.shadow_y_offset)

        detail_font = decrypt_font(self.config.detail_font)
        detail_font.setPixelSize(self.config.detail_text_size)
        self.detail_text_item = MixTextItem('')
        self.detail_text_item.setDefaultTextColor(Qt.black)
        self.detail_text_item.setFont(detail_font)
        self.detail_text_item.document().setDocumentMargin(0)
        self.detail_text_item.setPos(self.config.detail_pos_x, self.config.detail_pos_y)
        self.parent_app.rd_scene.addItem(self.detail_text_item)

        self.MT_text_item = MixTextItem('')
        self.MT_text_item.setDefaultTextColor(Qt.black)
        self.MT_text_item.setFont(detail_font)
        self.MT_text_item.document().setDocumentMargin(0)
        self.MT_text_item.setPos(self.config.detail_pos_x, self.config.detail_pos_y)
        self.parent_app.rd_scene.addItem(self.MT_text_item)
        self.MT_text_item.setVisible(False)


        ATK_DEF_number_font = decrypt_font(self.config.ATK_DEF_font)
        ATK_DEF_number_font.setPixelSize(self.config.ATK_DEF_number_size)
        ATK_DEF_number_font.setLetterSpacing(QFont.AbsoluteSpacing, -5)
        self.ATK_number_item = MixTextItem('', duplicate=True)
        self.ATK_number_item.setDefaultTextColor(Qt.white)
        self.ATK_number_item.setFont(ATK_DEF_number_font)
        self.ATK_number_item.document().setDocumentMargin(0)
        self.ATK_number_item.setPos(self.config.ATK_number_x, self.config.ATK_number_y)
        self.ATK_number_item.setTextWidth(self.config.ATK_DEF_number_width)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.ATK_number_item.document().setDefaultTextOption(text_option)
        self.ATK_number_item.enableOutline(True)
        self.ATK_number_item.setOutlineStyle(color=QColor(0, 0, 0), thickness=6)
        self.parent_app.rd_scene.addItem(self.ATK_number_item)

        self.DEF_number_item = MixTextItem('', duplicate=True)
        self.DEF_number_item.setDefaultTextColor(Qt.white)
        self.DEF_number_item.setFont(ATK_DEF_number_font)
        self.DEF_number_item.document().setDocumentMargin(0)
        self.DEF_number_item.setPos(self.config.DEF_number_x, self.config.DEF_number_y)
        self.DEF_number_item.setTextWidth(self.config.ATK_DEF_number_width)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.DEF_number_item.document().setDefaultTextOption(text_option)
        self.DEF_number_item.enableOutline(True)
        self.DEF_number_item.setOutlineStyle(color=QColor(0, 0, 0), thickness=6)
        self.parent_app.rd_scene.addItem(self.DEF_number_item)

        self.Max_number_item = MixTextItem('', duplicate=True)
        self.Max_number_item.setDefaultTextColor(Qt.white)
        self.Max_number_item.setFont(ATK_DEF_number_font)
        self.Max_number_item.document().setDocumentMargin(0)
        self.Max_number_item.setPos(self.config.Max_number_x, self.config.Max_number_y)
        self.Max_number_item.setTextWidth(self.config.ATK_DEF_number_width)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.Max_number_item.document().setDefaultTextOption(text_option)
        self.Max_number_item.enableOutline(True)
        self.Max_number_item.setOutlineStyle(color=QColor(0, 0, 0), thickness=6)
        self.parent_app.rd_scene.addItem(self.Max_number_item)

        renderer = QSvgRenderer(decrypt_svg(self.config.copyright_svgs[0]))
        self.copyright_item = QGraphicsSvgItem()
        self.copyright_item.setSharedRenderer(renderer)
        self.copyright_item.setPos(self.config.copyright_x, self.config.copyright_y)
        self.copyright_item.setScale(self.config.copyright_scale[0])
        scale_x = self.config.transform_scale[0]
        scale_y = 1.0
        transform = QTransform()
        transform.scale(scale_x, scale_y)
        self.copyright_item.setTransform(transform)
        self.parent_app.rd_scene.addItem(self.copyright_item)

        pack_font = decrypt_font(self.config.tip_font)
        pack_font.setPixelSize(self.config.pack_font_size)
        pack_font.setStretch(self.config.pack_stretch)
        self.card_pack_item = MixTextItem('RD/KP19-JP024')
        self.card_pack_item.setDefaultTextColor(Qt.white)
        self.card_pack_item.document().setDocumentMargin(0)
        self.card_pack_item.setFont(pack_font)
        self.card_pack_item.setPos(self.config.card_pack_x, self.config.card_pack_y)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.card_pack_item.document().setDefaultTextOption(text_option)
        self.card_pack_item.setTextWidth(self.config.card_pack_width)
        self.parent_app.rd_scene.addItem(self.card_pack_item)


        self.text_item = MixTextItem('')
        self.text_item.setDefaultTextColor(Qt.black)
        self.text_item.document().setDocumentMargin(self.config.text_margin)
        font = decrypt_font(self.config.text_font)
        font.setPixelSize(self.config.text_size)
        self.text_item.setFont(font)

        self.rect_width = self.config.rect_width + 2 * self.config.text_margin
        self.rect_height = self.config.rect_height + 2 * self.config.text_margin
        self.rect_pos = (self.config.rect_pos_x - self.config.text_margin, self.config.rect_pos_y - self.config.text_margin)
        self.text_display_rect = QRectF(self.rect_pos[0], self.rect_pos[1],
            self.rect_width, self.rect_height)

        self.text_item.setTextWidth(self.rect_width)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignJustify)
        self.text_item.document().setDefaultTextOption(text_option)
        self.text_item.setPos(self.rect_pos[0], self.rect_pos[1])
        self.parent_app.rd_scene.addItem(self.text_item)


        self.holo_item = QGraphicsPixmapItem(decrypt_image_qpixmap(self.config.holo_imgs[0]))
        self.holo_item.setPos(self.config.holo_x, self.config.holo_y)
        self.parent_app.rd_scene.addItem(self.holo_item)

        self.water_item = QGraphicsPixmapItem(None)
        self.parent_app.rd_scene.addItem(self.water_item)
        self.water_item.setVisible(False)

        self.rare_item = RoundedPixmapItem(None, radius=28)
        self.parent_app.rd_scene.addItem(self.rare_item)
        self.rare_item.setVisible(False)

        self.output_format = 0
        self.output_name = 0
        self.upload_dir = ''
        self.save_dir = os.getcwd()

        self.load_demo()
        self.parent_app.rd_scene.setSceneRect(self.card_rect)
        self.parent_app.RD_init = True
        pass

    def check_resource(self) -> bool:
        # 资源也可能只在打包目录（sys._MEIPASS）里
        for file in self.config.resource:
            if not runtime_resource_exists(file):
                return False
        return True

    def switch_card_type(self):
        selected_key = self.type_selector.currentText()
        self.card_type = selected_key
        self.switch_base_image()
        if self.card_type == '怪兽卡':
            self.rd_layout.removeItem(self.MT_type_hbox)
            self.MT_type_label.setVisible(False)
            self.MT_type_selector.setVisible(False)
            self.MT_text_item.setVisible(False)
            self.icon_item.setVisible(False)
            self.reappear_monster_items()
            self.attribute_item.setPixmap(decrypt_image_qpixmap(self.config.attribute_imgs[self.current_attribute]))
        else:
            self.hide_monster_items()
            if not self.MT_type_hbox.parent():
                self.rd_layout.insertLayout(3, self.MT_type_hbox)
                self.MT_type_label.setVisible(True)
                self.MT_type_selector.setVisible(True)
                self.MT_text_item.setVisible(True)
            if self.card_type == '魔法卡':
                self.attribute_item.setPixmap(decrypt_image_qpixmap(self.config.attribute_imgs['魔']))
            else:
                self.attribute_item.setPixmap(decrypt_image_qpixmap(self.config.attribute_imgs['罠']))
            self.update_MT_type()
        rd_style._apply_rd_text_colors(self)

    def switch_info(self):
        self.switch_base_image()
        self.race = self.race_selector.currentText()
        self.call_way = self.call_way_selector.currentText()
        self.extra_info = self.extra_info_selector.currentText()

        if self.call_way == '通常':
            self.call_way, self.extra_info = ('通常', '')
        else:
            if self.call_way == '效果':
                self.extra_info = ''

            elif self.extra_info == '通常':
                self.extra_info = ''
            pass
        detail_text = '【' + self.race
        if not self.call_way == '':
            detail_text = detail_text + '/' + self.call_way
        if not self.extra_info == '':
            detail_text = detail_text + '/' + self.extra_info
        detail_text = detail_text + '】'
        self.detail_text_item.setPlainText(detail_text)
        rd_style._apply_rd_text_colors(self)

    def switch_base_image(self):
        rd_frame._with_rd_frame_key(self, self._apply_base_image)

    def _apply_base_image(self):
        base_key = ''
        if self.card_type == '怪兽卡':
            base_key = self.call_way_selector.currentText()
        else:
            base_key = self.card_type
        self.base_item.setPixmap(decrypt_image_qpixmap(self.config.base_imgs[base_key]))
        self.mask_item.setPixmap(decrypt_image_qpixmap(self.config.mask_imgs[base_key]))
        self.parent_app.view.fitInView(self.base_item.boundingRect(), Qt.KeepAspectRatio)
        overframe._ensure_rd_overframe(self)
        overframe._apply_rd_overframe_layers(self)

    def hide_monster_items(self):
        self.rd_layout.removeItem(self.detail_info_hbox)
        self.rd_layout.removeItem(self.attribute_hbox)
        self.rd_layout.removeItem(self.level_box)
        self.rd_layout.removeItem(self.ATK_DEF_hbox)
        self.detail_info_label.setVisible(False)
        self.race_selector.setVisible(False)
        self.call_way_selector.setVisible(False)
        for _, btn in self.attribute_btn_dict.items():
            btn.setVisible(False)
        for btn in self.level_star_btn_list:
            btn.setVisible(False)
        self.ATK_label.setVisible(False)
        self.ATK_edit.setVisible(False)
        self.DEF_label.setVisible(False)
        self.DEF_edit.setVisible(False)
        self.Max_ATK_label.setVisible(False)
        self.Max_ATK_edit.setVisible(False)

        self.ATK_DEF_item.setVisible(False)
        self.level_item.setVisible(False)
        self.Max_ATK_item.setVisible(False)
        self.ATK_number_item.setVisible(False)
        self.DEF_number_item.setVisible(False)
        self.Max_number_item.setVisible(False)
        self.detail_text_item.setVisible(False)

    def reappear_monster_items(self):
        self.rd_layout.insertLayout(3, self.detail_info_hbox)
        self.rd_layout.insertLayout(4, self.attribute_hbox)
        self.rd_layout.insertLayout(5, self.level_box)
        self.rd_layout.insertLayout(6, self.ATK_DEF_hbox)
        self.detail_info_label.setVisible(True)
        self.race_selector.setVisible(True)
        self.call_way_selector.setVisible(True)
        for _, btn in self.attribute_btn_dict.items():
            btn.setVisible(True)
        for btn in self.level_star_btn_list:
            btn.setVisible(True)
        self.ATK_label.setVisible(True)
        self.ATK_edit.setVisible(True)
        self.DEF_label.setVisible(True)
        self.DEF_edit.setVisible(True)
        self.Max_ATK_label.setVisible(True)
        self.Max_ATK_edit.setVisible(True)

        self.ATK_DEF_item.setVisible(True)
        self.level_item.setVisible(True)
        self.Max_ATK_item.setVisible(self.Max_ATK_flag)
        self.ATK_number_item.setVisible(True)
        self.DEF_number_item.setVisible(True)
        self.Max_number_item.setVisible(self.Max_ATK_flag)
        self.detail_text_item.setVisible(True)
        rd_style._apply_rd_text_colors(self)

    def attribute_clicked(self):
        button = self.sender()
        btn_text = button.text()
        self.current_attribute = btn_text
        self.attribute_item.setPixmap(decrypt_image_qpixmap(self.config.attribute_imgs[btn_text]))
        for k, btn in self.attribute_btn_dict.items():
            if k == btn_text:
                btn.setColor(self.attribute_on_colors[k])
            else:
                btn.setColor(self.attribute_off_colors[k])
        pass

    def star_clicked(self):
        button = self.sender()
        flag = True
        for i, btn in enumerate(self.level_star_btn_list):
            if flag:
                btn.setStarColor(self.star_level_color)
                btn.setCircleColor(self.level_bg_color)
            else:
                btn.setStarColor(self.star_undo_color)
                btn.setCircleColor(self.bg_undo_color)
            if btn is button:
                self.current_level = i + 1
                flag = False
        self.update_level_label()
        self.update_level_img()
        if rd_frame._rd_is_xyz(self):
            # 超量：右栏点出的阶级写回 OCG 的 current_rank，之后的同步与存卡都以它为准
            try:
                rd_frame._rd_push_rank_to_otcg(self)
            except Exception:
                _tab_log("RD 阶级写回 OCG 失败:\n" + traceback.format_exc())

    def update_level_label(self):
        self.level_label.setText(f'等级 {self.current_level}')
        if rd_frame._rd_is_xyz(self):
            self.level_label.setText(f"阶级 {getattr(self, 'current_level', 0)}")

    def update_level_img(self):
        if rd_frame._rd_is_xyz(self):
            # 超量怪兽（含超量灵摆）贴阶级图标
            item = getattr(self, 'level_item', None)
            if item is not None:
                item.setPixmap(
                    decrypt_image_qpixmap(f'{_RD_RANK_RESOURCE_PREFIX}{rd_frame._rd_clamped_level(self)}.enc'))
            return
        self.level_item.setPixmap(decrypt_image_qpixmap(self.config.level_img + f'{self.current_level}.enc'))

    def star_zero_clicked(self):
        self.current_level = 0
        for btn in self.level_star_btn_list:
            btn.setStarColor(self.star_undo_color)
            btn.setCircleColor(self.bg_undo_color)
        self.update_level_label()
        self.update_level_img()
        if rd_frame._rd_is_xyz(self):
            # 超量：右栏点出的阶级写回 OCG 的 current_rank，之后的同步与存卡都以它为准
            try:
                rd_frame._rd_push_rank_to_otcg(self)
            except Exception:
                _tab_log("RD 阶级写回 OCG 失败:\n" + traceback.format_exc())

    def on_toggle_Max_ATK(self, checked: bool):
        self.Max_ATK_flag = checked
        self.Max_ATK_edit.setEnabled(checked)
        self.Max_ATK_item.setVisible(checked)
        self.Max_number_item.setVisible(checked)
        self.update_Max()

    def update_MT_type(self):
        text = self.MT_type_selector.currentText()
        if text == '通常':
            self.icon_item.setVisible(False)
        else:
            self.icon_item.setVisible(True)
            self.icon_item.setPixmap(decrypt_image_qpixmap(self.config.icon_imgs[text]))
        self.update_MT_text()
        pass

    def update_MT_text(self):
        mt_text = ''
        if self.MT_type_selector.currentText() == '通常':
            mt_text = f'【{self.card_type}】'
        else:
            mt_text = f'【{self.card_type}/{self.MT_type_selector.currentText()}      】'
        self.MT_text_item.setPlainText(mt_text)
        rd_style._apply_rd_text_colors(self)

    def watermark_change(self):
        text = self.water_selector.currentText()
        if text == '无':
            self.water_item.setVisible(False)
        else:
            self.water_item.setVisible(True)
            self.water_item.setPixmap(decrypt_image_qpixmap(self.config.sample))
        pass

    def rare_change(self):
        # 罕贵度分底图和前景两层，前景压在卡面最上层（rarity）
        rarity._apply_rd_rarity(self)

    def on_toggle_legend(self, checked: bool):
        self.legend_item.setVisible(checked)

    def on_toggle_corner(self, checked: bool):
        self.base_item.set_rounded(checked)
        self.rare_item.set_rounded(checked)

    def update_card_name(self):
        name_item = self.mix_name_item if self.mix_mode_flag else self.card_name_item
        name_list = self.mix_name_list if self.mix_mode_flag else self.card_name_list

        for i in range(self.config.NAME_LIST_LEN):
            name_list[i].setPlainText('')
            name_list[i].setVisible(False)

        card_name_posy = self.config.card_name_posy
        name_item.setPos(self.config.card_name_posx, card_name_posy)

        text = self.card_name_edit.text()
        name_len = len(text)
        if not self.check_name_len(text):
            name_item.setTextWidth(self.config.NAME_WIDTH)
            name_item.setPlainText(text)
            fontWid = 100
            while self.count_name_line() > 1:
                fontWid -= 1
                font = name_item.font()
                font.setStretch(fontWid)
                name_item.setFont(font)
                name_item.setPlainText(text)

            name_item.setVisible(False)
            font = name_item.font()
            metrics = QFontMetricsF(font)
            text_width = metrics.width(text)
            remain_space = self.config.NAME_WIDTH - text_width
            extra_spacing = remain_space / (name_len - 1)
            x_pos = self.config.card_name_posx
            for i, char in enumerate(text):
                name_list[i].setFont(font)
                name_list[i].setPos(x_pos, card_name_posy)
                x_pos += metrics.width(char) + extra_spacing
                name_list[i].setPlainText(char)
                name_list[i].setVisible(True)
                if not self.mix_mode_flag:
                    name_list[i].setDefaultTextColor(self.title_color)
                else:
                    color = Qt.transparent if self.gradient_flag else self.single_color
                    name_list[i].setDefaultTextColor(color)
                    if self.shadow_flag:
                        name_list[i].setGraphicsEffect(self.shadow_list[i])
                    else:
                        name_list[i].setGraphicsEffect(None)
        else:
            name_item.setVisible(True)
            if not self.mix_mode_flag:
                name_item.setDefaultTextColor(self.title_color)
            else:
                color = Qt.transparent if self.gradient_flag else self.single_color
                name_item.setDefaultTextColor(color)
                if self.shadow_flag:
                    name_item.setGraphicsEffect(self.shadow_effect)
                else:
                    name_item.setGraphicsEffect(None)

        self.card_name_item.update()
        rd_style._apply_rd_text_colors(self)

    def check_name_len(self, text):
        name_item = self.mix_name_item if self.mix_mode_flag else self.card_name_item
        font = name_item.font()
        font.setStretch(100)
        name_item.setFont(font)
        name_item.setTextWidth(-1)
        name_item.setPlainText(text)
        name_item.setVisible(True)
        return name_item.boundingRect().width() <= self.config.NAME_WIDTH + 2 * self.config.card_name_margin

    def count_name_line(self):
        name_item = self.mix_name_item if self.mix_mode_flag else self.card_name_item
        document = name_item.document()
        layout = document.documentLayout()
        visual_lines = 0
        font_metrics = QFontMetrics(name_item.font())
        line_height = font_metrics.lineSpacing()

        for block_num in range(document.blockCount()):
            block = document.findBlockByNumber(block_num)
            block_rect = layout.blockBoundingRect(block)
            block_height = block_rect.height()

            visual_lines += int(block_height // line_height)
        return visual_lines

    def color_btn_clicked(self):
        button = self.sender()
        btn_text = button.text
        other_close_flag = False
        color = QColor(255, 0, 0)
        if btn_text == '黑色':
            self.color_option = 0
            color = QColor(0, 0, 0)
        elif btn_text == '白色':
            self.color_option = 1
            color = QColor(255, 255, 255)
        elif btn_text == '金色':
            self.color_option = 2
            color = QColor(251, 215, 5)
        elif btn_text == '红色':
            self.color_option = 3
            color = QColor(255, 0, 0)
        else:
            custom_color = QColorDialog.getColor(self.title_color, self)
            if not custom_color.isValid():
                other_close_flag = True
            else:
                self.color_option = 4
                color = custom_color

        if other_close_flag:
            return

        self.mix_mode_flag = False
        self.title_color = color
        self.mix_name_item.setVisible(False)
        for i in range(self.config.NAME_LIST_LEN):
            self.mix_name_list[i].setVisible(False)
        self.update_card_name()

        for btn in self.color_btn_list:
            if btn is button:
                btn.display_ring()
            else:
                btn.hide_ring()
        for btn in self.color_advanced_list:
            btn.hide_ring()
        pass

    def change_color_mode(self, checked: bool):
        if checked:
            if self.color_btn_hbox.parent():
                self.color_vbox.removeItem(self.color_btn_hbox)
            for btn in self.color_btn_list:
                btn.setVisible(False)
            if self.color_advanced_hbox.parent() is None:
                self.color_vbox.addLayout(self.color_advanced_hbox)
            for btn in self.color_advanced_list:
                btn.setVisible(True)
        else:
            if self.color_advanced_hbox.parent():
                self.color_vbox.removeItem(self.color_advanced_hbox)
            for btn in self.color_advanced_list:
                btn.setVisible(False)
            if self.color_btn_hbox.parent() is None:
                self.color_vbox.addLayout(self.color_btn_hbox)
            for btn in self.color_btn_list:
                btn.setVisible(True)
        pass

    def advanced_btn_clicked(self):
        button = self.sender()
        btn_text = button.text
        other_close_flag = False
        if btn_text == '银字':
            self.mix_option = 0
            self.outline_enabled = True
            self.outline_color = QColor(0, 0, 0)
            self.outline_thickess = 5
            self.shadow_flag = True
            self.shadow_color = QColor(0, 0, 0)
            self.shadow_blur_size = 5
            self.shadow_x_offset = 1.2
            self.shadow_y_offset = 2
            self.gradient_flag = True
            self.gradient_process = [[True, 0, QColor(222, 222, 222)], [True, 0.21, QColor(255, 255, 255)],
                [True, 0.42, QColor(217, 217, 217)], [True, 0.52, QColor(141, 141, 141)],
                [True, 0.66, QColor(161, 161, 161)], [True, 1, QColor(255, 255, 255)]]
            self.single_color = QColor(0, 0, 0)
        elif btn_text == '金字':
            self.mix_option = 1
            self.outline_enabled = True
            self.outline_color = QColor(0, 0, 0)
            self.outline_thickess = 5
            self.shadow_flag = True
            self.shadow_color = QColor(0, 0, 0)
            self.shadow_blur_size = 5
            self.shadow_x_offset = 1.2
            self.shadow_y_offset = 2
            self.gradient_flag = True
            self.gradient_process = [[True, 0, QColor(255, 220, 0)], [True, 0.23, QColor(255, 255, 255)],
                [True, 0.42, QColor(255, 220, 0)], [True, 0.52, QColor(181, 129, 0)],
                [True, 0.73, QColor(255, 220, 0)], [True, 1, QColor(255, 220, 0)]]
            self.single_color = QColor(0, 0, 0)
        elif btn_text == '青字':
            self.mix_option = 2
            self.outline_enabled = True
            self.outline_color = QColor(0, 0, 0)
            self.outline_thickess = 5
            self.shadow_flag = True
            self.shadow_color = QColor(0, 0, 0)
            self.shadow_blur_size = 5
            self.shadow_x_offset = 1.2
            self.shadow_y_offset = 2
            self.gradient_flag = True
            self.gradient_process = [[True, 0, QColor(76, 255, 190)], [True, 0.23, QColor(255, 255, 255)],
                [True, 0.42, QColor(0, 255, 174)], [True, 0.54, QColor(0, 153, 163)],
                [True, 0.73, QColor(0, 255, 174)], [True, 1, QColor(76, 244, 255)]]
            self.single_color = QColor(0, 0, 0)
        elif btn_text == '红字':
            self.mix_option = 3
            self.outline_enabled = True
            self.outline_color = QColor(0, 0, 0)
            self.outline_thickess = 5
            self.shadow_flag = True
            self.shadow_color = QColor(0, 0, 0)
            self.shadow_blur_size = 5
            self.shadow_x_offset = 1.2
            self.shadow_y_offset = 2
            self.gradient_flag = False
            self.gradient_process = [[True, 0, QColor(222, 222, 222)], [True, 0.21, QColor(255, 255, 255)],
                [True, 0.42, QColor(217, 217, 217)], [True, 0.52, QColor(141, 141, 141)],
                [True, 0.66, QColor(161, 161, 161)], [True, 1, QColor(255, 255, 255)]]
            self.single_color = QColor(230, 0, 0)
        else:
            dialog = ColorAdvancedDialog(self.outline_enabled_c, self.outline_color_c, self.outline_thickess_c,
                self.shadow_flag_c, self.shadow_color_c, self.shadow_blur_size_c, self.shadow_x_offset_c,
                self.shadow_y_offset_c, self.gradient_flag_c, self.gradient_process_c, self.single_color_c, self)
            if dialog.exec_():
                self.mix_option = 4
                self.outline_enabled = self.outline_enabled_c = dialog.outline_enabled
                self.outline_color = self.outline_color_c = dialog.outline_color
                self.outline_thickess = self.outline_thickess_c = dialog.outline_thickess
                self.shadow_flag = self.shadow_flag_c = dialog.shadow_flag
                self.shadow_color = self.shadow_color_c = dialog.shadow_color
                self.shadow_blur_size = self.shadow_blur_size_c = dialog.shadow_blur_size
                self.shadow_x_offset = self.shadow_x_offset_c = dialog.shadow_x_offset
                self.shadow_y_offset = self.shadow_y_offset_c = dialog.shadow_y_offset
                self.gradient_flag = self.gradient_flag_c = dialog.gradient_flag
                self.gradient_process = self.gradient_process_c = dialog.gradient_process
                self.single_color = self.single_color_c = dialog.single_color
            else:
                other_close_flag = True
            pass

        if other_close_flag:
            return
        self.mix_mode_flag = True
        self.update_mix_param()
        self.card_name_item.setVisible(False)
        for i in range(self.config.NAME_LIST_LEN):
            self.card_name_list[i].setVisible(False)
        self.update_card_name()

        for btn in self.color_advanced_list:
            if btn is button:
                btn.display_ring()
            else:
                btn.hide_ring()
        for btn in self.color_btn_list:
            btn.hide_ring()
        pass

    def update_shadow_ratio(self):
        W, H = self.config.card_w, self.config.card_h
        card_hw_ratio = 1.0 * H / W
        view_width = self.parent_app.view.width()
        view_height = self.parent_app.view.height()
        view_hw_ratio = 1.0 * view_height / view_width
        if view_hw_ratio >= card_hw_ratio:
            self.shadow_vis_ratio = 1.0 * view_width / W
        else:
            self.shadow_vis_ratio = 1.0 * view_height / H
        pass

    def update_mix_param(self):
        self.mix_name_item.enableOutline(self.outline_enabled)
        self.mix_name_item.setOutlineStyle(self.outline_color, self.outline_thickess)
        self.mix_name_item.enableGradient(self.gradient_flag)
        self.mix_name_item.setSingleColor(self.single_color)
        self.mix_name_item.setGradientProcess(self.gradient_process)
        edge_points = self.config.gradient_edge_points
        self.mix_name_item.setGradientEdge(edge_points[0], edge_points[1])

        self.update_shadow_ratio()
        self.shadow_effect = QGraphicsDropShadowEffect()
        self.shadow_effect.setColor(self.shadow_color)
        self.shadow_effect.setBlurRadius(self.shadow_blur_size * self.shadow_vis_ratio)
        self.shadow_effect.setXOffset(self.shadow_x_offset * self.shadow_vis_ratio)
        self.shadow_effect.setYOffset(self.shadow_y_offset * self.shadow_vis_ratio)

        for i in range(self.config.NAME_LIST_LEN):
            self.mix_name_list[i].enableOutline(self.outline_enabled)
            self.mix_name_list[i].setOutlineStyle(self.outline_color, self.outline_thickess)
            self.mix_name_list[i].enableGradient(self.gradient_flag)
            self.mix_name_list[i].setSingleColor(self.single_color)
            self.mix_name_list[i].setGradientProcess(self.gradient_process)
            edge_points = self.config.gradient_edge_points
            self.mix_name_list[i].setGradientEdge(edge_points[0], edge_points[1])

            self.shadow_list[i] = QGraphicsDropShadowEffect()
            self.shadow_list[i].setColor(self.shadow_color)
            self.shadow_list[i].setBlurRadius(self.shadow_blur_size * self.shadow_vis_ratio)
            self.shadow_list[i].setXOffset(self.shadow_x_offset * self.shadow_vis_ratio)
            self.shadow_list[i].setYOffset(self.shadow_y_offset * self.shadow_vis_ratio)
        pass

    def update_ATK(self):
        text = self.ATK_edit.text()
        self.ATK_number_item.setPlainText(text)

    def update_DEF(self):
        text = self.DEF_edit.text()
        self.DEF_number_item.setPlainText(text)

    def update_Max(self):
        text = self.Max_ATK_edit.text()
        self.Max_number_item.setPlainText(text)

    def update_text(self):
        text = self.text_input.toPlainText()
        self.set_line_height((self.rect_height - 2 * self.config.text_margin) / self.config.text_line_num)
        if not self.check_fit_in(text):
            fontWid = 100
            while fontWid > 25 and self.text_item.boundingRect().height() > self.text_display_rect.height():
                fontWid -= 1
                font = self.text_item.font()
                font.setStretch(fontWid)
                self.text_item.setFont(font)
                self.text_item.setPlainText(text)
                self.set_line_height((self.rect_height - 2 * self.config.text_margin) / self.config.text_line_num)
        rd_style._apply_rd_text_colors(self)
        # 效果文字仿 OCG 排版：先横向压窄，仍放不下再缩小字号
        try:
            rd_frame._rd_refit_effect_text(self)
        except Exception:
            _tab_log("RD 效果文字按字号排版失败:\n" + traceback.format_exc())

    def check_fit_in(self, text):
        font = self.text_item.font()
        font.setStretch(100)
        self.text_item.setFont(font)
        self.text_item.setPlainText(text)
        self.set_line_height((self.rect_height - 2 * self.config.text_margin) / self.config.text_line_num)
        return self.text_item.boundingRect().height() <= self.text_display_rect.height()

    def set_line_height(self, line_height):
        cursor = self.text_item.textCursor()
        cursor.select(QTextCursor.Document)
        block_format = QTextBlockFormat()
        block_format.setLineHeight(line_height, QTextBlockFormat.FixedHeight)
        cursor.setBlockFormat(block_format)

    def update_card_pack(self):
        text = self.card_pack_edit.text()
        self.card_pack_item.setPlainText(text)

    def copyright_change(self, *_args):
        # 版权下拉里有可增删的自定义项：推迟到下一轮事件循环，由 customization 判断选的是自定义项还是标准样式
        customization._defer_custom_combo_change(self, 'copyright', RDWidget._standard_copyright_change)

    def _standard_copyright_change(self, index: int):
        self.copyright_item.renderer().load(decrypt_svg(self.config.copyright_svgs[index]))
        self.copyright_item.setScale(self.config.copyright_scale[index])
        scale_x = self.config.transform_scale[index]
        scale_y = 1.0
        transform = QTransform()
        transform.scale(scale_x, scale_y)
        self.copyright_item.setTransform(transform)
        self.copyright_item.update()

    def holo_change(self, *_args):
        # 防伪下拉里有可增删的自定义项：推迟到下一轮事件循环，由 customization 判断选的是自定义项还是标准样式
        customization._defer_custom_combo_change(self, 'holo', RDWidget._standard_holo_change)

    def _standard_holo_change(self, index: int):
        self.holo_item.setPixmap(decrypt_image_qpixmap(self.config.holo_imgs[index]))

    def on_toggle_pack(self, checked: bool):
        self.card_pack_item.setVisible(checked)

    def on_toggle_copy(self, checked: bool):
        self.copyright_item.setVisible(checked)

    def on_toggle_holo(self, checked: bool):
        self.holo_item.setVisible(checked)

    def on_output_setting(self):
        dialog = OutputSettingDialog(HD_img=0, format=self.output_format, name=self.output_name, RD=True, parent=self)
        if dialog.exec_():
            self.output_format = dialog.format
            self.output_name = dialog.name
        pass

    def load_image_nocrop(self):
        file_name, _ = QFileDialog.getOpenFileName(self, '选择本地图片', self.upload_dir, 'Image Files (*.png *.jpg *.bmp)')
        self.upload_dir = os.path.dirname(file_name)
        if file_name:
            self.set_card_img_nocrop(file_name)
        pass

    def load_image_crop(self):
        file_name, _ = QFileDialog.getOpenFileName(self, '选择本地图片', self.upload_dir, 'Image Files (*.png *.jpg *.bmp)')
        self.upload_dir = os.path.dirname(file_name)
        if file_name:
            self.set_card_img_crop(file_name)
        pass

    def set_card_img_nocrop(self, img_path):
        self.card_img = Image.open(img_path).convert('RGBA')
        self.transform_normal_img()

    def set_card_img_crop(self, img_path):
        pil_image = Image.open(img_path).convert('RGBA')
        pixmap = pillow_img_to_pixmap(pil_image)
        crop_dialog = CropDialog(pixmap, self, mode='RD')
        if crop_dialog.exec_():
            pixmap = crop_dialog.get_cropped_pixmap()
            self.card_img = qpixmap_to_pillow(pixmap)
            self.transform_normal_img()
        pass

    def transform_normal_img(self):
        card_img_size = self.card_img_size
        self.display_img = self.card_img.resize((card_img_size.width(), card_img_size.height()), Image.LANCZOS)
        self.display_img = pillow_img_to_pixmap(self.display_img)
        self.card_img_item.setPixmap(self.display_img)

    def on_pass_btn_clicked(self):
        self.on_cardpass_return()

    def on_cardpass_return(self):
        worker = Worker(self.fetch_info)
        worker.signals.finished.connect(self.after_info_fetch)
        self.parent_app.show_loading_gif()
        self.threadpool.start(worker)
        pass

    def fetch_info(self):
        card_pass = self.card_pass_edit.text()
        if len(card_pass) < 9:
            card_pass = card_pass.zfill(9)
        self.card_pass_edit.setText(card_pass)
        self.info_fetcher.set_card_pass(card_pass)

    def after_info_fetch(self):
        if not self.info_fetcher.valid:
            self.parent_app.hide_loading_gif()
            QToolTip.showText(self.card_pass_edit.mapToGlobal(self.card_pass_edit.rect().topLeft()) + QPoint(-3, -40),
                '无效卡密', self.card_pass_edit)
            return

        if self.info_fetcher.card_img is not None:
            self.card_img = self.info_fetcher.card_img
            self.transform_normal_img()
        if self.info_fetcher.card_info is None:
            return
        card_info = self.info_fetcher.card_info
        self.card_pack_edit.setText(card_info[0])
        self.card_name_edit.setText(card_info[1])
        self.type_selector.setCurrentIndex(card_info[2])
        self.text_input.setText(card_info[13])
        self.toggle_legend.is_checked = card_info[12]
        self.toggle_legend.animate_circle()
        self.on_toggle_legend(self.toggle_legend.is_checked)
        self.current_attribute = ATTRIBUTE_DICT[card_info[3]]
        if self.card_type == '怪兽卡':
            for k, btn in self.attribute_btn_dict.items():
                if k == self.current_attribute:
                    btn.setColor(self.attribute_on_colors[k])
                else:
                    btn.setColor(self.attribute_off_colors[k])
            self.attribute_item.setPixmap(decrypt_image_qpixmap(self.config.attribute_imgs[self.current_attribute]))

            self.current_level = card_info[4]
            self.display_level_btn()
            self.update_level_label()
            self.update_level_img()
            self.race_selector.setCurrentIndex(card_info[5])
            self.call_way_selector.setCurrentIndex(card_info[6])
            self.extra_info_selector.setCurrentIndex(card_info[7])
            self.ATK_edit.setText(card_info[9])
            self.DEF_edit.setText(card_info[10])
            if not card_info[11] == '':
                self.Max_ATK_toggle.is_checked = True
                self.Max_ATK_toggle.animate_circle()
                self.on_toggle_Max_ATK(self.Max_ATK_toggle.is_checked)
                self.Max_ATK_edit.setText(card_info[11])
            else:
                self.Max_ATK_toggle.is_checked = False
                self.Max_ATK_toggle.animate_circle()
                self.on_toggle_Max_ATK(self.Max_ATK_toggle.is_checked)
        else:
            self.MT_type_selector.setCurrentIndex(card_info[8])

        self.parent_app.hide_loading_gif()

    def random_card(self):
        url = 'https://gitee.com/scutlzl/game-king-card-maker/raw/master/data/CSJD_pass_list.npy'
        if self.card_pass_list is None:
            try:
                response = requests.get(url, timeout=5)
                file_content = io.BytesIO(response.content)
                self.card_pass_list = np.load(file_content)
            except Exception as e:
                return
        if self.card_pass_list is not None:
            random_pass = np.random.choice(self.card_pass_list)
            cardpass = str(random_pass).zfill(9)
            self.card_pass_edit.setText(cardpass)
            self.on_cardpass_return()
        pass

    def on_save_image(self):
        if self.output_name == 0:
            card_name = clean_filename(self.card_name_edit.text())
        else:
            card_name = remove_leading_zeros(self.card_pass_edit.text())
        if self.output_format == 0:
            file_name, _ = QFileDialog.getSaveFileName(self, '保存结果', os.path.join(self.save_dir, card_name),
                'Image Files (*.png)')
        else:
            file_name, _ = QFileDialog.getSaveFileName(self, '保存结果', os.path.join(self.save_dir, card_name),
                'Image Files (*.jpg)')
        if file_name:
            self.save_dir = os.path.dirname(file_name)
            self.save_image(file_name)
        pass

    def save_image(self, file_name=''):
        if not file_name:
            return
        if self.mix_mode_flag and self.shadow_flag:
            self.shadow_effect = QGraphicsDropShadowEffect()
            self.shadow_effect.setColor(self.shadow_color)
            self.shadow_effect.setBlurRadius(self.shadow_blur_size)
            self.shadow_effect.setXOffset(self.shadow_x_offset)
            self.shadow_effect.setYOffset(self.shadow_y_offset)

            for i in range(self.config.NAME_LIST_LEN):
                self.shadow_list[i] = QGraphicsDropShadowEffect()
                self.shadow_list[i].setColor(self.shadow_color)
                self.shadow_list[i].setBlurRadius(self.shadow_blur_size)
                self.shadow_list[i].setXOffset(self.shadow_x_offset)
                self.shadow_list[i].setYOffset(self.shadow_y_offset)
            pass
            self.update_card_name()
        card_size = QSize(self.config.card_w, self.config.card_h)
        image = QPixmap(card_size)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self.parent_app.rd_scene.render(painter, QRectF(image.rect()), self.parent_app.rd_scene.sceneRect())
        painter.end()
        if self.output_format == 0:
            image.save(file_name, format='PNG')
        else:
            image.save(file_name, format='JPG')
        self.update_mix_param()
        self.update_card_name()

    def display_level_btn(self):
        for i, btn in enumerate(self.level_star_btn_list):
            if i + 1 <= self.current_level:
                btn.setStarColor(self.star_level_color)
                btn.setCircleColor(self.level_bg_color)
            else:
                btn.setStarColor(self.star_undo_color)
                btn.setCircleColor(self.bg_undo_color)
        pass

    def load_demo(self):
        self.card_name_edit.setText(self.config.demo_card_name)

        self.current_level = self.config.demo_card_level
        self.display_level_btn()
        self.update_level_label()
        self.update_level_img()

        self.current_attribute = self.config.demo_attribute
        for k, btn in self.attribute_btn_dict.items():
            if k == self.current_attribute:
                btn.setColor(self.attribute_on_colors[k])
            else:
                btn.setColor(self.attribute_off_colors[k])
        self.attribute_item.setPixmap(decrypt_image_qpixmap(self.config.attribute_imgs[self.current_attribute]))

        self.call_way_selector.setCurrentText('通常')
        self.race_selector.setCurrentText('战士族')
        self.ATK_edit.setText('1200')
        self.DEF_edit.setText('500')
        self.text_input.setText(self.config.demo_card_text)
        self.card_pass_edit.setText(self.config.demo_card_pass)
        self.card_pack_edit.setText(self.config.demo_card_pack)

        self.card_img = decrypt_image_pillow(self.config.demo_show_img)
        self.transform_normal_img()
        pass
    pass
