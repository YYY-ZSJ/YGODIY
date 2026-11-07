import os
import sys
from CompressText import CompressText
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsPixmapItem, QFileDialog, QColorDialog, QComboBox, QToolTip, QLabel, QSizePolicy, QSpacerItem, QGraphicsLineItem, QGraphicsDropShadowEffect, QSlider, QMessageBox, QGraphicsTextItem, QGraphicsRectItem


from PyQt5.QtGui import QPixmap, QFont, QFontDatabase, QColor, QPainter, QTextOption, QIcon, QTextCursor, QTextBlockFormat, QFontMetricsF, QRegularExpressionValidator, QFontMetrics, QPen, QTransform

from PyQt5.QtCore import Qt, QRect, QRectF, QPointF, QRegularExpression, QSize, QThreadPool, QPoint, QUrl
from PyQt5.QtSvg import QGraphicsSvgItem, QSvgRenderer
from customComponents import make_symbol_bar, Worker, AttributeButton, StarButton, CloseButton, LinkButton, ColorButton, CustomTextEdit, CustomLineEdit, CropDialog, ToggleButton, RoundedButton, ColorAdvancedDialog, HelpButton, BatchDialog, RoundedPixmapItem, OutputSettingDialog, HollowHandleStyle, NameSearchDialog, OverFrameSettingDialog, TextGroup, MixNameGroup, NameGroup



from infoFetcher import InfoFetcher
from mixTextItem import MixTextItem
from PIL import Image
from config import Config
import json
import numpy as np
import requests
from opencc import OpenCC
import io
import base64
import traceback
from utils import clean_filename, remove_leading_zeros, pillow_img_to_pixmap, qpixmap_to_pillow, rpath, crop_square_image, apply_fade_to_alpha, remove_annotation, add_application_font

import card_library
import card_tabs
import customization
import editor_setup
import free_text
import language_switch
import manga
import overframe
import rarity
import watermark
from common import _tab_log

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import YuGiOhApp


# ---------------------------------------------------------------------------
# macOS 渲染微调：CoreText 与 Windows 的字形位置、视觉大小有差异，卡名与注音按平台修正。
# Windows 走原始配置，行为不变。
# ---------------------------------------------------------------------------
_MACOS_NAME_Y_OFFSET = 14       # 卡名文本整体下移（像素）
_MACOS_RUBY_SIZE_SCALE = 0.88   # 注音字号缩放比例
_MACOS_RUBY_FONT = 'mold/font/FOT-Rodin Pro.ttf'  # 注音常规字重（rt_font_path 指向的 DB 是粗体）


def _load_rt_font(config):
    """注音字体。macOS 换常规字重的 FOT-Rodin Pro（CoreText 下 DB 偏粗、视觉偏大）。"""
    path = config.rt_font_path
    if sys.platform == 'darwin' and os.path.isfile(rpath(_MACOS_RUBY_FONT)):
        path = _MACOS_RUBY_FONT
    return QFont(QFontDatabase.applicationFontFamilies(add_application_font(rpath(path)))[0])


def _rt_ratio(ratio: float) -> float:
    """注音字号比例：macOS 上略缩小，其他平台原样。"""
    return ratio * _MACOS_RUBY_SIZE_SCALE if sys.platform == 'darwin' else ratio


def _name_pos(config, language):
    """卡名文本位置：macOS 上整体下移少许，其他平台用配置原值。"""
    x = config.card_name_posx[language]
    y = config.card_name_posy[language]
    if sys.platform == 'darwin':
        y += _MACOS_NAME_Y_OFFSET
    return x, y


class OTCGWidget(QWidget):
    def __init__(self, parent: 'YuGiOhApp' = None):
        super().__init__()
        with open(rpath('config/config.json'), 'r', encoding='utf-8') as config_file:
            config_dict = json.load(config_file)
        self.config = Config(**config_dict)

        self.parent_app = parent
        self.otcg_layout = QVBoxLayout()

        self.name_type_hbox = QHBoxLayout()
        card_name_hbox = QHBoxLayout()
        self.card_name_label = QLabel('卡名', self)
        self.card_name_edit = CustomLineEdit()
        self.card_name_edit.setPlaceholderText('请输入卡名')
        self.card_name_edit.setMaxLength(300)
        self.card_name_edit.textChanged.connect(self.update_card_name)
        self.card_name_edit.returnPressed.connect(self.on_name_search)
        self.name_search_btn = RoundedButton(text='', width=30, height=25)
        self.name_search_btn.setIcon(QIcon(rpath('mold/search.png')))
        self.name_search_btn.setIconSize(15)
        self.name_search_btn.clicked.connect(self.on_name_search)
        card_name_hbox.addWidget(self.card_name_label)
        card_name_hbox.addWidget(self.card_name_edit)
        card_name_hbox.addWidget(self.name_search_btn)

        card_type_hbox = QHBoxLayout()
        self.card_type_label = QLabel('类型', self)
        self.card_type_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.type_selector = QComboBox(self)
        self.type_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.type_selector.addItems(['怪兽卡', '魔法卡', '陷阱卡'])
        self.type_selector.currentIndexChanged.connect(self.switch_card_type)

        self.template_label = QLabel('卡模', self)
        self.template_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.template_selector = QComboBox(self)
        self.template_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.template_selector.addItems(['官方', '经典'])
        self.template_selector.currentIndexChanged.connect(self.switch_template)

        card_type_hbox.addWidget(self.card_type_label)
        card_type_hbox.addWidget(self.type_selector)
        card_type_hbox.addWidget(self.template_label)
        card_type_hbox.addWidget(self.template_selector)
        self.name_type_hbox.addLayout(card_name_hbox)
        self.name_type_hbox.addStretch(1)
        self.name_type_hbox.addLayout(card_type_hbox)
        self.name_type_hbox.setStretch(0, 4)
        self.name_type_hbox.setStretch(2, 4)


        self.lan_tran_hbox = QHBoxLayout()

        self.tc_type = 0
        self.lan_hbox = QHBoxLayout()
        self.lan_label = QLabel('语言', self)
        self.lan_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.lan_selector = QComboBox(self)
        self.lan_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.lan_selector.addItems(['简体中文', '繁体中文', '日文', '英文'])
        self.lan_selector.setCurrentText('简体中文')
        self.lan_selector.currentIndexChanged.connect(self.update_language)

        self.tc_type_selector = QComboBox(self)
        self.tc_type_selector.addItems(['类型1', '类型2'])
        self.tc_type_selector.setCurrentIndex(0)
        self.tc_type_selector.currentIndexChanged.connect(self.update_tc_type)
        self.tc_type_selector.setVisible(True)
        self.lan_hbox.addWidget(self.lan_label)
        self.lan_hbox.addWidget(self.lan_selector)
        self.lan_hbox.addWidget(self.tc_type_selector)

        self.translation_hbox = QHBoxLayout()
        self.trans_label = QLabel('中文翻译类型')
        self.trans_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.trans_selector = QComboBox(self)
        self.trans_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.trans_selector.addItems(['YGOPro', '官方简中'])
        self.trans_selector.currentIndexChanged.connect(self.update_trans_type)
        self.translation_hbox.addWidget(self.trans_label)
        self.translation_hbox.addWidget(self.trans_selector)

        self.lan_tran_hbox.addLayout(self.lan_hbox)
        self.lan_tran_hbox.addStretch(1)
        self.lan_tran_hbox.addLayout(self.translation_hbox)
        self.lan_tran_hbox.setStretch(0, 4)
        self.lan_tran_hbox.setStretch(2, 4)


        self.color_vbox = QVBoxLayout()

        self.color_label_hbox = QHBoxLayout()
        # 卡名颜色：高级 [开关] ……——开关紧挨着标题，看得出两者的关系（以前开关在行尾，离标题很远）
        self.color_label = QLabel('卡名颜色：')
        self.color_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.color_advanced_label = QLabel('高级')
        self.color_advanced_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.color_advanced_btn = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.color_advanced_btn.toggled.connect(self.change_color_mode)

        self.color_label_hbox.addWidget(self.color_label)
        self.color_label_hbox.addWidget(self.color_advanced_label)
        self.color_label_hbox.addWidget(self.color_advanced_btn)
        self.color_label_hbox.addStretch(1)

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
        self.upload_left_box = QHBoxLayout()
        self.upload_right_box = QHBoxLayout()

        self.load_image_button_nocrop = QPushButton('上传卡图(不裁剪)', self)
        self.load_image_button_nocrop.clicked.connect(self.load_image_nocrop)
        self.load_image_button_crop = QPushButton('上传卡图(裁剪)', self)
        self.load_image_button_crop.clicked.connect(self.load_image_crop)

        font = self.font()
        metric = QFontMetrics(font)
        label_width = metric.width('超框卡图')
        self.overframe_label = QLabel('超框卡图', self)
        self.overframe_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.overframe_label.setFixedWidth(label_width)
        self.overframe_toggle = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.overframe_toggle.toggled.connect(self.overframe_toggle_change)
        self.overframe_upload_btn = QPushButton('上传超框卡图', self)
        self.overframe_setting_btn = QPushButton('超框设置', self)
        self.overframe_upload_btn.setEnabled(False)
        self.overframe_setting_btn.setEnabled(False)
        self.overframe_upload_btn.clicked.connect(self.on_overframe_upload)
        self.overframe_setting_btn.clicked.connect(self.show_overframe_setting)

        self.upload_left_box.addWidget(self.load_image_button_nocrop)
        self.upload_left_box.addWidget(self.load_image_button_crop)

        self.upload_right_box.addWidget(self.overframe_label)
        self.upload_right_box.addWidget(self.overframe_toggle)
        self.upload_right_box.addWidget(self.overframe_upload_btn)
        self.upload_right_box.addWidget(self.overframe_setting_btn)

        self.upload_btn_hbox.addLayout(self.upload_left_box)
        self.upload_btn_hbox.addLayout(self.upload_right_box)
        self.upload_btn_hbox.setStretch(0, 1)
        self.upload_btn_hbox.setStretch(1, 1)


        self.detail_call_way = ''
        self.detail_extra1 = ''
        self.detail_extra2 = ''

        self.call_way_list = ['通常', '效果', '融合', '仪式', '同调', '超量', '衍生物', '连接', '暗黑同调', '巨神兵', '天空龙', '翼神龙']
        self.extra1_list = ['', '通常', '调整', '二重', '灵魂', '反转', '特殊召唤', '同盟', '卡通', '灵摆']
        self.extra2_list = ['', '通常', '调整', '二重', '灵魂', '反转', '特殊召唤', '同盟', '卡通']
        self.detail_info_hbox = QHBoxLayout()
        self.detail_info_label = QLabel('详细', self)
        self.detail_info_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.race_selector = QComboBox(self)
        self.race_selector.addItems(self.config.race_list)
        self.race_selector.currentIndexChanged.connect(self.switch_info)
        self.race_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.info_selector_left = QComboBox(self)
        self.info_selector_left.addItems(self.call_way_list)
        self.info_selector_left.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.info_selector_left.setCurrentText('效果')
        self.info_selector_left.currentIndexChanged.connect(self.switch_info)
        self.info_selector_mid = QComboBox(self)
        self.info_selector_mid.addItems(self.extra1_list)
        self.info_selector_mid.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.info_selector_mid.currentIndexChanged.connect(self.switch_info)
        self.info_selector_right = QComboBox(self)
        self.info_selector_right.addItems(self.extra2_list)
        self.info_selector_right.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.info_selector_right.currentIndexChanged.connect(self.switch_info)
        self.detail_info_hbox.addWidget(self.detail_info_label)
        self.detail_info_hbox.addWidget(self.race_selector)
        self.detail_info_hbox.addWidget(self.info_selector_left)
        self.detail_info_hbox.addWidget(self.info_selector_mid)
        self.detail_info_hbox.addWidget(self.info_selector_right)

        self.monster_info_hbox = QHBoxLayout()

        self.detail_custom_hbox = QHBoxLayout()
        self.detail_custom_label = QLabel('自定', self)
        self.detail_custom_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.detail_custom_toggle = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.detail_custom_toggle.toggled.connect(self.detail_custom_cliked)
        self.detail_custom_edit = CustomLineEdit()
        self.detail_custom_edit.setEnabled(False)
        self.detail_custom_edit.setPlaceholderText('种族文本')
        self.detail_custom_edit.setText(self.config.demo_detail_text)
        self.detail_custom_edit.textChanged.connect(self.update_detail_text_only)
        self.detail_custom_edit.setMaxLength(100)
        self.detail_custom_hbox.addWidget(self.detail_custom_label)
        self.detail_custom_hbox.addWidget(self.detail_custom_toggle)
        self.detail_custom_hbox.addWidget(self.detail_custom_edit)

















        self.attr_effect_hbox = QHBoxLayout()
        self.attr_hide_label = QLabel('属性显示', self)
        self.attr_hide_toggle = ToggleButton(check=True, on_color=QColor(0, 0, 0), height=20, width=42)
        self.attr_hide_toggle.toggled.connect(self.show_hide_attr)
        self.only_image_label = QLabel('首行压缩', self)
        self.only_img_toggle = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.only_img_toggle.toggled.connect(self.first_line_compress)
        self.full_effect_label = QLabel('效果全栏', self)
        self.full_effect_toggle = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.full_effect_toggle.toggled.connect(self.full_effect_clicked)
        self.attr_effect_hbox.addWidget(self.attr_hide_label)
        self.attr_effect_hbox.addWidget(self.attr_hide_toggle)
        self.attr_effect_hbox.addWidget(self.only_image_label)
        self.attr_effect_hbox.addWidget(self.only_img_toggle)
        self.attr_effect_hbox.addWidget(self.full_effect_label)
        self.attr_effect_hbox.addWidget(self.full_effect_toggle)

        self.monster_info_hbox.addLayout(self.detail_custom_hbox)
        self.monster_info_hbox.addStretch(0)
        self.monster_info_hbox.addLayout(self.attr_effect_hbox)



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

        self.light_btn = AttributeButton('光', 35, 25, color=self.attribute_off_colors['光'])
        self.dark_btn = AttributeButton('暗', 35, 25, color=self.attribute_on_colors['暗'])
        self.wind_btn = AttributeButton('风', 35, 25, color=self.attribute_off_colors['风'])
        self.water_btn = AttributeButton('水', 35, 25, color=self.attribute_off_colors['水'])
        self.fire_btn = AttributeButton('炎', 35, 25, color=self.attribute_off_colors['炎'])
        self.ground_btn = AttributeButton('地', 35, 25, color=self.attribute_off_colors['地'])
        self.god_btn = AttributeButton('神', 35, 25, color=self.attribute_off_colors['神'])
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


        self.link_vbox = QVBoxLayout()

        self.link_first_hbox = QHBoxLayout()
        self.link_lefttop_btn = LinkButton()
        self.link_top_btn = LinkButton()
        self.link_righttop_btn = LinkButton()
        self.link_first_hbox.addStretch(1)
        self.link_first_hbox.addWidget(self.link_lefttop_btn)
        self.link_first_hbox.addWidget(self.link_top_btn)
        self.link_first_hbox.addWidget(self.link_righttop_btn)
        self.link_first_hbox.addStretch(1)

        self.link_second_hbox = QHBoxLayout()
        self.link_left_btn = LinkButton()
        self.link_center_btn = LinkButton(hand=False)
        self.link_right_btn = LinkButton()
        self.link_second_hbox.addStretch(1)
        self.link_second_hbox.addWidget(self.link_left_btn)
        self.link_second_hbox.addWidget(self.link_center_btn)
        self.link_second_hbox.addWidget(self.link_right_btn)
        self.link_second_hbox.addStretch(1)

        self.link_third_hbox = QHBoxLayout()
        self.link_leftdown_btn = LinkButton()
        self.link_down_btn = LinkButton()
        self.link_rightdown_btn = LinkButton()
        self.link_third_hbox.addStretch(1)
        self.link_third_hbox.addWidget(self.link_leftdown_btn)
        self.link_third_hbox.addWidget(self.link_down_btn)
        self.link_third_hbox.addWidget(self.link_rightdown_btn)
        self.link_third_hbox.addStretch(1)

        self.link_btn_on_color = '#fc7848'
        self.link_btn_off_color = '#bbbbbb'
        self.link_btn_list = [self.link_lefttop_btn, self.link_top_btn, self.link_righttop_btn,
            self.link_left_btn, self.link_center_btn, self.link_right_btn,
            self.link_leftdown_btn, self.link_down_btn, self.link_rightdown_btn]
        self.link_control_list = [self.link_lefttop_btn, self.link_top_btn, self.link_righttop_btn,
            self.link_left_btn, self.link_right_btn,
            self.link_leftdown_btn, self.link_down_btn, self.link_rightdown_btn]
        for btn in self.link_control_list:
            btn.clicked.connect(self.link_btn_clicked)
        self.link_vbox.addLayout(self.link_first_hbox)
        self.link_vbox.addLayout(self.link_second_hbox)
        self.link_vbox.addLayout(self.link_third_hbox)


        self.star_level_color = '#f7d60a'
        self.level_bg_color = '#f14724'
        self.star_rank_color = '#ffdd33'
        self.rank_bg_color = '#2e3234'
        self.star_undo_color = '#ffffff'
        self.bg_undo_color = '#595959'
        self.level_box = QHBoxLayout()

        self.level_label = QLabel('等级 2 ', self)
        self.level_label.setFixedWidth(metric.width('等级 10 '))
        self.level_box.addWidget(self.level_label)
        self.level_zero_btn = CloseButton(width=20, height=20)
        self.level_zero_btn.clicked.connect(self.star_zero_clicked)
        self.level_star_btn_list = [StarButton(radius=10) for _ in range(12)]
        self.level_box.addWidget(self.level_zero_btn)
        for btn in self.level_star_btn_list:
            btn.clicked.connect(self.star_clicked)
            self.level_box.addStretch(0)
            self.level_box.addWidget(btn)

        for i in range(self.config.demo_card_level):
            self.level_star_btn_list[i].setCircleColor(self.level_bg_color)
            self.level_star_btn_list[i].setStarColor(self.star_level_color)


        self.rank_box = QHBoxLayout()

        self.rank_label = QLabel('阶级 10 ', self)
        self.rank_label.setFixedWidth(metric.width('等级 10 '))
        self.rank_box.addWidget(self.rank_label)
        self.rank_zero_btn = CloseButton(width=20, height=20)
        self.rank_zero_btn.clicked.connect(self.rank_zero_clicked)
        self.rank_star_btn_list = [StarButton(radius=10) for _ in range(13)]
        self.rank_box.addWidget(self.rank_zero_btn)
        for btn in self.rank_star_btn_list:
            btn.clicked.connect(self.rank_clicked)
            self.rank_box.addStretch(0)
            self.rank_box.addWidget(btn)
        for i in range(self.config.demo_card_level):
            self.rank_star_btn_list[i].setCircleColor(self.rank_bg_color)
            self.rank_star_btn_list[i].setStarColor(self.star_rank_color)

        self.rank_label.setText(f'阶级 {self.config.demo_card_level}')


        self.LB_info_hbox = QHBoxLayout()
        self.LB_level_hbox = QHBoxLayout()
        self.LB_ratio_hbox = QHBoxLayout()
        self.LB_level_label = QLabel('灵摆刻度', self)
        self.LB_level_edit = CustomLineEdit()
        regular_exp = QRegularExpression('^\\d{1,2}$')
        validator = QRegularExpressionValidator(regular_exp, self.LB_level_edit)
        self.LB_level_edit.setValidator(validator)
        self.LB_level_edit.textChanged.connect(self.update_lb_level)
        self.LB_ratio_label = QLabel('灵摆卡图', self)
        self.LB_ratio_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.LB_ratio_selector = QComboBox()
        self.LB_ratio_selector.addItems(['正方形', '灵摆矩形'])
        self.LB_ratio_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.LB_ratio_selector.currentIndexChanged.connect(self.LB_ratio_changed)
        self.LB_Zack_label = QLabel('扎克灵摆', self)
        self.LB_Zack_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.LB_Zack_toggle = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.LB_Zack_toggle.toggled.connect(self.LB_Zack_clicked)

        self.LB_level_hbox.addWidget(self.LB_level_label)
        self.LB_level_hbox.addWidget(self.LB_level_edit)
        self.LB_ratio_hbox.addWidget(self.LB_ratio_label)
        self.LB_ratio_hbox.addWidget(self.LB_ratio_selector)
        self.LB_ratio_hbox.addWidget(self.LB_Zack_label)
        self.LB_ratio_hbox.addWidget(self.LB_Zack_toggle)

        self.LB_info_hbox.addLayout(self.LB_level_hbox)
        self.LB_info_hbox.addStretch(1)
        self.LB_info_hbox.addLayout(self.LB_ratio_hbox)
        self.LB_info_hbox.setStretch(0, 4)
        self.LB_info_hbox.setStretch(2, 4)

        self.LB_text_edit = CustomTextEdit()
        self.LB_text_edit.setPlaceholderText('灵摆效果')
        self.LB_text_edit.setMaximumHeight(120)
        self.LB_text_edit.textChanged.connect(self.update_lb_text)


        self.ATK_DEF_hbox = QHBoxLayout()

        self.ATK_hbox = QHBoxLayout()
        self.ATK_label = QLabel('攻击', self)
        self.ATK_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.ATK_edit = CustomLineEdit()
        self.ATK_edit.setPlaceholderText('ATK')
        self.ATK_edit.setMaxLength(6)
        self.ATK_edit.setText(self.config.demo_atk)
        self.ATK_edit.textChanged.connect(self.update_ATK)
        self.ATK_hbox.addWidget(self.ATK_label)
        self.ATK_hbox.addWidget(self.ATK_edit)

        self.DEF_hbox = QHBoxLayout()
        self.DEF_label = QLabel('防御', self)
        self.DEF_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.DEF_edit = CustomLineEdit()
        self.DEF_edit.setPlaceholderText('DEF')
        self.DEF_edit.setMaxLength(6)
        self.DEF_edit.setText(self.config.demo_def)
        self.DEF_edit.textChanged.connect(self.update_DEF)
        self.DEF_hbox.addWidget(self.DEF_label)
        self.DEF_hbox.addWidget(self.DEF_edit)

        regular_exp = QRegularExpression('[0-9?]*')
        validator = QRegularExpressionValidator(regular_exp, self.ATK_edit)
        self.ATK_edit.setValidator(validator)
        self.DEF_edit.setValidator(validator)

        self.ATK_DEF_ctrl_hbox = QHBoxLayout()
        self.ATK_DEF_type_label = QLabel('中文攻守')
        self.ATK_DEF_type_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.ATK_DEF_type_toggle = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.ATK_DEF_type_toggle.toggled.connect(self.on_toggle_ATK_DEF)
        self.ATK_DEF_ctrl_hbox.addWidget(self.ATK_DEF_type_label)
        self.ATK_DEF_ctrl_hbox.addWidget(self.ATK_DEF_type_toggle)

        self.ATK_DEF_hbox.addLayout(self.ATK_hbox)
        self.ATK_DEF_hbox.addStretch(5)
        self.ATK_DEF_hbox.addLayout(self.DEF_hbox)
        self.ATK_DEF_hbox.addStretch(5)
        self.ATK_DEF_hbox.addLayout(self.ATK_DEF_ctrl_hbox)
        self.ATK_DEF_hbox.setStretch(0, 35)
        self.ATK_DEF_hbox.setStretch(2, 35)


        self.text_input = CustomTextEdit()
        self.text_input.setPlaceholderText('效果')
        self.text_input.textChanged.connect(self.update_text)

        metric = QFontMetrics(self.font())
        label_width = metric.width('字号')

        self.text_ctrl_hbox = QHBoxLayout()

        self.text_sizeable = False
        self.text_size_hbox = QHBoxLayout()
        self.text_ctrl_label = QLabel('字号')
        self.text_ctrl_label.setFixedWidth(label_width)
        self.text_size_label = QLabel('0')
        self.text_size_label.setFixedWidth(metric.width('-15'))
        self.text_size_label.setAlignment(Qt.AlignCenter)
        self.text_adjust_btn = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.text_adjust_btn.toggled.connect(self.text_sizeable_toggle)

        self.text_size_slider = QSlider(Qt.Horizontal, self)
        self.text_size_slider.setStyle(HollowHandleStyle())
        self.text_size_slider.setRange(-15, 20)
        self.text_size_slider.setValue(0)
        self.text_size_slider.valueChanged.connect(self.update_text_size)
        self.text_size_slider.setEnabled(False)
        self.text_size_hbox.addWidget(self.text_ctrl_label)
        self.text_size_hbox.addWidget(self.text_size_label)
        self.text_size_hbox.addWidget(self.text_adjust_btn)
        self.text_size_hbox.addWidget(self.text_size_slider)

        self.text_weightable = False
        self.text_weight_hbox = QHBoxLayout()
        self.text_weight_label = QLabel('字重')
        self.text_weight_label.setFixedWidth(label_width)
        self.text_weightnum_label = QLabel('0')
        self.text_weightnum_label.setFixedWidth(metric.width('-15'))
        self.text_weightnum_label.setAlignment(Qt.AlignCenter)
        self.text_weight_adjust_btn = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.text_weight_adjust_btn.toggled.connect(self.text_weight_switch)
        self.text_weight_slider = QSlider(Qt.Horizontal, self)
        self.text_weight_slider.setStyle(HollowHandleStyle())
        self.text_weight_slider.setRange(0, 15)
        self.text_weight_slider.setValue(0)
        self.text_weight_slider.valueChanged.connect(self.update_text_weight)
        self.text_weight_slider.setEnabled(False)

        self.text_weight_hbox.addWidget(self.text_weight_label)
        self.text_weight_hbox.addWidget(self.text_weightnum_label)
        self.text_weight_hbox.addWidget(self.text_weight_adjust_btn)
        self.text_weight_hbox.addWidget(self.text_weight_slider)

        self.text_ctrl_hbox.addLayout(self.text_size_hbox)
        self.text_ctrl_hbox.addStretch(1)
        self.text_ctrl_hbox.addLayout(self.text_weight_hbox)
        self.text_ctrl_hbox.setStretch(0, 4)
        self.text_ctrl_hbox.setStretch(2, 4)


        self.align_box = QHBoxLayout()

        self.name_align_box = QHBoxLayout()
        self.name_align_label = QLabel('卡名对齐', self)
        self.name_align_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.name_align_selector = QComboBox()
        self.name_align_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.name_align_selector.addItems(['居左', '居中', '居右'])
        self.name_align_selector.currentIndexChanged.connect(self.name_align_change)
        self.name_align_box.addWidget(self.name_align_label)
        self.name_align_box.addWidget(self.name_align_selector)

        self.text_align_box = QHBoxLayout()
        self.text_align_label = QLabel('效果对齐', self)
        self.text_align_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.text_align_selector = QComboBox()
        self.text_align_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.text_align_selector.addItems(['默认', '居中'])
        self.text_align_selector.currentIndexChanged.connect(self.text_align_change)
        self.text_align_box.addWidget(self.text_align_label)
        self.text_align_box.addWidget(self.text_align_selector)

        self.align_box.addLayout(self.name_align_box)
        self.align_box.addStretch(1)
        self.align_box.addLayout(self.text_align_box)
        self.align_box.setStretch(0, 4)
        self.align_box.setStretch(2, 4)


        self.card_info_hbox = QHBoxLayout()
        card_pass_hbox = QHBoxLayout()
        self.card_pass_label = QLabel('卡密')
        self.card_pass_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.card_pass_edit = CustomLineEdit()
        self.card_pass_edit.setMaxLength(9)
        regular_exp = QRegularExpression('[0-9]*')
        validator = QRegularExpressionValidator(regular_exp, self.card_pass_edit)
        self.card_pass_edit.setValidator(validator)
        self.card_pass_edit.textChanged.connect(self.update_card_pass)
        self.card_pass_edit.returnPressed.connect(self.on_pass_btn_clicked)
        self.card_pass_btn = RoundedButton(text='检索', width=60, height=25)
        self.card_pass_btn.clicked.connect(self.on_pass_btn_clicked)
        card_pass_hbox.addWidget(self.card_pass_label)
        card_pass_hbox.addWidget(self.card_pass_edit)
        card_pass_hbox.addWidget(self.card_pass_btn)
        card_pack_hbox = QHBoxLayout()
        self.card_pack_label = QLabel('卡包')
        self.card_pack_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.card_pack_edit = CustomLineEdit()
        self.card_pack_edit.setMaxLength(20)
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


        self.hcrw_hbox = QHBoxLayout()

        self.holo_copyright_hbox = QHBoxLayout()

        self.holo_hbox = QHBoxLayout()
        self.holo_label = QLabel('防伪', self)
        self.holo_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.holo_selector = QComboBox()
        self.holo_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.holo_selector.addItems(['样式一', '样式二', '样式三'])
        self.holo_selector.setCurrentText('样式一')
        self.holo_selector.currentIndexChanged.connect(self.holo_change)
        self.holo_hbox.addWidget(self.holo_label)
        self.holo_hbox.addWidget(self.holo_selector)

        self.copyright_hbox = QHBoxLayout()
        self.copyright_label = QLabel('版权', self)
        self.copyright_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.copyright_selector = QComboBox()
        self.copyright_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.copyright_selector.addItems(['样式一', '样式二', '样式三', '样式四', '样式五'])
        self.copyright_selector.currentIndexChanged.connect(self.copyright_change)
        self.copyright_selector.setCurrentText('样式一')
        self.copyright_hbox.addWidget(self.copyright_label)
        self.copyright_hbox.addWidget(self.copyright_selector)

        self.holo_copyright_hbox.addLayout(self.holo_hbox)
        self.holo_copyright_hbox.addLayout(self.copyright_hbox)


        self.rare_water_hbox = QHBoxLayout()

        rare_list = ['N', 'UR', 'DT', 'GR', 'GSER', 'HR', 'PSER', 'PP', 'SER', 'NPR', 'CR', 'ESR', 'KC', 'MR']
        self.rare_hbox = QHBoxLayout()
        self.rare_label = QLabel('罕贵', self)
        self.rare_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.rare_selector = QComboBox()
        self.rare_selector.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.rare_selector.addItems(rare_list)
        self.rare_selector.currentIndexChanged.connect(self.rare_change)
        self.rare_hbox.addWidget(self.rare_label)
        self.rare_hbox.addWidget(self.rare_selector)

        water_list = ['无', '20th', '25th', 'sample', 'sample2', 'secret', 'star', 'DIY', '10000']
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
        self.rare_water_hbox.addLayout(self.water_hbox)

        self.hcrw_hbox.addLayout(self.holo_copyright_hbox)
        self.hcrw_hbox.addStretch(1)
        self.hcrw_hbox.addLayout(self.rare_water_hbox)
        self.hcrw_hbox.setStretch(0, 4)
        self.hcrw_hbox.setStretch(2, 4)


        self.source_load_hbox = QHBoxLayout()
        self.local_image_folder = ''
        self.source_hbox = QHBoxLayout()
        self.source_label = QLabel('本地卡图')
        self.source_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.source_toggle = ToggleButton(height=20, width=42, on_color=QColor(0, 0, 0), check=False)
        self.source_toggle.toggled.connect(self.on_toggle_source)
        self.source_toggle.setToolTip('开启后,检索卡片时会使用本地图片作为卡图。图片须使用卡密作为文件名')
        self.source_btn = QPushButton('来源文件夹', self)
        self.source_btn.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.source_btn.clicked.connect(self.on_local_clicked)
        self.source_btn.setEnabled(False)
        self.source_helper = HelpButton()
        self.source_helper.clicked.connect(self.source_helper_clicked)
        self.source_hbox.addWidget(self.source_label)
        self.source_hbox.addWidget(self.source_toggle)
        self.source_hbox.addWidget(self.source_btn)
        self.source_hbox.addWidget(self.source_helper)

        self.load_hbox = QHBoxLayout()
        self.export_setting_btn = QPushButton('导出数据')
        self.import_setting_btn = QPushButton('导入数据')
        self.export_setting_btn.clicked.connect(self.on_export_clicked)
        self.import_setting_btn.clicked.connect(self.on_import_clicked)
        self.load_hbox.addWidget(self.export_setting_btn)
        self.load_hbox.addWidget(self.import_setting_btn)

        self.source_load_hbox.addLayout(self.source_hbox)
        self.source_load_hbox.addStretch(1)
        self.source_load_hbox.addLayout(self.load_hbox)
        self.source_load_hbox.setStretch(0, 4)
        self.source_load_hbox.setStretch(2, 4)


        self.toggle_hbox = QHBoxLayout()
        self.label1 = QLabel('卡密')
        self.toggle_pass = ToggleButton(height=20, width=42)
        self.toggle_pass.toggled.connect(self.on_toggle_pass)
        self.label2 = QLabel('卡包')
        self.toggle_pack = ToggleButton(height=20, width=42)
        self.toggle_pack.toggled.connect(self.on_toggle_pack)
        self.label3 = QLabel('防伪')
        self.toggle_holo = ToggleButton(height=20, width=42)
        self.toggle_holo.toggled.connect(self.on_toggle_holo)
        self.label4 = QLabel('版权')
        self.toggle_copy = ToggleButton(height=20, width=42)
        self.toggle_copy.toggled.connect(self.on_toggle_copy)
        self.label5 = QLabel('圆角')
        self.toggle_corner = ToggleButton(check=False, height=20, width=42)
        self.toggle_corner.toggled.connect(self.on_toggle_corner)
        self.toggle_hbox.addWidget(self.label1)
        self.toggle_hbox.addWidget(self.toggle_pass)
        self.toggle_hbox.addStretch(0)
        self.toggle_hbox.addWidget(self.label2)
        self.toggle_hbox.addWidget(self.toggle_pack)
        self.toggle_hbox.addStretch(0)
        self.toggle_hbox.addWidget(self.label3)
        self.toggle_hbox.addWidget(self.toggle_holo)
        self.toggle_hbox.addStretch(0)
        self.toggle_hbox.addWidget(self.label4)
        self.toggle_hbox.addWidget(self.toggle_copy)
        self.toggle_hbox.addStretch(0)
        self.toggle_hbox.addWidget(self.label5)
        self.toggle_hbox.addWidget(self.toggle_corner)


        self.save_hbox = QHBoxLayout()
        self.save_image_button = QPushButton('导出图片', self)
        self.save_image_button.clicked.connect(self.on_save_image)
        self.batch_btn = QPushButton('批量导出', self)
        self.batch_btn.clicked.connect(self.on_batch_clicked)
        self.batch_btn.setFixedWidth(120)
        self.setting_btn = QPushButton('导出设置', self)
        self.setting_btn.clicked.connect(self.on_output_setting)
        self.setting_btn.setFixedWidth(120)
        self.save_hbox.addWidget(self.save_image_button)
        self.save_hbox.addWidget(self.batch_btn)
        self.save_hbox.addWidget(self.setting_btn)


        self.otcg_layout.addLayout(self.name_type_hbox)
        self.otcg_layout.addLayout(self.lan_tran_hbox)
        self.otcg_layout.addLayout(self.color_vbox)
        self.otcg_layout.addLayout(self.upload_btn_hbox)
        self.otcg_layout.addLayout(self.detail_info_hbox)
        self.otcg_layout.addLayout(self.monster_info_hbox)
        self.otcg_layout.addLayout(self.attribute_hbox)
        self.otcg_layout.addLayout(self.level_box)
        self.otcg_layout.addLayout(self.rank_box)
        self.otcg_layout.addLayout(self.ATK_DEF_hbox)
        self.otcg_layout.addLayout(self.LB_info_hbox)
        self.otcg_layout.addWidget(self.LB_text_edit)
        # 效果文本框正上方的特殊符号快捷按钮（「」 ①…⑤ ●）
        self._symbol_bar, self._symbol_watcher = make_symbol_bar(self, self.text_input, (self.LB_text_edit,))
        self.otcg_layout.addWidget(self._symbol_bar)
        self.otcg_layout.addWidget(self.text_input)
        self.otcg_layout.addLayout(self.text_ctrl_hbox)
        self.otcg_layout.addLayout(self.card_info_hbox)
        self.otcg_layout.addLayout(self.align_box)
        self.otcg_layout.addLayout(self.hcrw_hbox)
        self.otcg_layout.addLayout(self.source_load_hbox)
        self.otcg_layout.addLayout(self.toggle_hbox)
        self.otcg_layout.addLayout(self.save_hbox)
        self.otcg_layout.setContentsMargins(0, 5, 0, 0)
        self.setLayout(self.otcg_layout)

        self.init_vis()
        editor_setup._setup_otcg_editor(self)
        rarity._add_extra_rarity_grades(self, ('PSER2',))
        free_text._install_free_text_button(self)
        customization._install_customization_controls(self)
        language_switch._setup_language_translation(self)
        overframe._ocg_of_after_init(self, '__init__')


    def init_vis(self):
        self.language = '简体中文'
        self.card_type = '怪兽卡'
        self.current_template = 0
        self.card_pass_list = None
        self.t2s_converter = OpenCC('t2s')

        self.mix_mode_flag = False
        self.shadow_vis_ratio = 1.0
        self.outline_enabled = True
        self.outline_color = QColor(0, 0, 0)
        self.outline_thickess = 4
        self.shadow_flag = True
        self.shadow_color = QColor(0, 0, 0)
        self.shadow_blur_size = 4
        self.shadow_x_offset = 1
        self.shadow_y_offset = 1
        self.gradient_flag = True
        self.gradient_process = [[True, 0, QColor(255, 220, 0)], [True, 0.23, QColor(255, 255, 255)],
            [True, 0.42, QColor(255, 220, 0)], [True, 0.52, QColor(181, 129, 0)],
            [True, 0.73, QColor(255, 220, 0)], [True, 1, QColor(255, 220, 0)]]
        self.single_color = QColor(0, 0, 0)

        self.outline_enabled_c = True
        self.outline_color_c = QColor(0, 0, 0)
        self.outline_thickess_c = 4
        self.shadow_flag_c = True
        self.shadow_color_c = QColor(0, 0, 0)
        self.shadow_blur_size_c = 4
        self.shadow_x_offset_c = 1
        self.shadow_y_offset_c = 1
        self.gradient_flag_c = True
        self.gradient_process_c = [[True, 0, QColor(255, 220, 0)], [True, 0.23, QColor(255, 255, 255)],
            [True, 0.42, QColor(255, 220, 0)], [True, 0.52, QColor(181, 129, 0)],
            [True, 0.73, QColor(255, 220, 0)], [True, 1, QColor(255, 220, 0)]]
        self.single_color_c = QColor(240, 0, 0)

        self.offical_cn = False

        self.threadpool = QThreadPool()
        self.info_fetcher = InfoFetcher()

        self.color_flag = False
        self.upload_dir = ''
        self.save_dir = os.getcwd()

        self.name_width = self.config.NAME_WIDTH

        self.card_rect = QRectF(QRect(0, 0, self.config.card_rect_w, self.config.card_rect_h))
        self.card_img_size = QSize(self.config.card_img_size_w, self.config.card_img_size_h)
        self.ocard_img_size = QSize(self.config.ocard_img_size_w, self.config.ocard_img_size_h)
        self.LB_img_size = QSize(self.config.LB_img_size_w, self.config.LB_img_size_h)

        self.card_img = Image.open(rpath(self.config.demo_show_img)).convert('RGBA')
        self.display_img = self.card_img.resize((self.ocard_img_size.width(), self.ocard_img_size.height()), Image.Resampling.LANCZOS)
        self.display_img = pillow_img_to_pixmap(self.display_img)

        self.HD_card_img = False
        self.card_img_item = QGraphicsPixmapItem(self.display_img)
        self.card_img_item.setPos(self.config.ocard_x, self.config.ocard_y)
        self.parent_app.scene.addItem(self.card_img_item)

        self.base_item = RoundedPixmapItem(None, radius=28)
        self.parent_app.scene.addItem(self.base_item)

        self.rare_item = RoundedPixmapItem(None, radius=28)
        self.parent_app.scene.addItem(self.rare_item)
        self.rare_item.setVisible(False)

        self.overframe_img = None
        self.of_display_img = None
        self.overframe_item = RoundedPixmapItem(self.of_display_img, radius=28)
        self.overframe_item.setVisible(False)
        self.parent_app.scene.addItem(self.overframe_item)

        self.overframe_mask = RoundedPixmapItem(QPixmap('mold/frame/overframe/LB_OF_mask.png'), radius=28)
        self.overframe_mask.setVisible(False)
        self.parent_app.scene.addItem(self.overframe_mask)

        self.overframe_scale = 1000
        self.overframe_posx = 0
        self.overframe_posy = 0
        self.overframe_sizex = 1626
        self.overframe_sizey = 1626

        self.anniversary_item = QGraphicsPixmapItem()
        self.parent_app.scene.addItem(self.anniversary_item)
        self.anniversary_item.setVisible(False)


        font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.card_name_font[self.language])))[0])
        rtfont = _load_rt_font(self.config)
        self.name_compresstor = CompressText()
        self.name_compresstor.setRtFont(rtfont)
        self.name_compresstor.setRtFontSize(14)
        self.name_compresstor.setRubyFont(font)
        self.name_compresstor.setFontSize(self.config.card_name_size[self.language])
        self.name_compresstor.width = self.config.NAME_WIDTH
        self.name_compresstor.firstLineCompress = True
        self.name_compresstor.rtRatio = _rt_ratio(0.2037037037037037)
        self.name_compresstor.rtTop = 1

        self.name_text_group = NameGroup()
        self.name_text_group.setRubyFont(font)
        self.name_text_group.setRtFont(rtfont)
        self.parent_app.scene.addItem(self.name_text_group)
        self.name_text_group.setPos(*_name_pos(self.config, self.language))
        self.name_text_group.setRubyFontSize(self.config.card_name_size[self.language])

        self.mixname_text_group = MixNameGroup()
        self.mixname_text_group.setRubyFont(font)
        self.mixname_text_group.setRtFont(rtfont)
        self.parent_app.scene.addItem(self.mixname_text_group)
        self.mixname_text_group.setPos(*_name_pos(self.config, self.language))
        self.mixname_text_group.setRubyFontSize(self.config.card_name_size[self.language])
        self.mixname_text_group.setVisible(False)

        self.new_shadow_list = [QGraphicsDropShadowEffect() for _ in range(self.config.NAME_LIST_LEN)]
        for i in range(self.config.NAME_LIST_LEN):
            self.new_shadow_list[i].setColor(self.shadow_color)
            self.new_shadow_list[i].setBlurRadius(self.shadow_blur_size)
            self.new_shadow_list[i].setXOffset(self.shadow_x_offset)
            self.new_shadow_list[i].setYOffset(self.shadow_y_offset)



        self.current_attribute = self.config.demo_attribute
        self.attribute_item = QGraphicsPixmapItem(QPixmap(rpath(self.config.attributes[self.language][self.current_attribute])))
        self.attribute_item.setPos(self.config.attribute_pos_x, self.config.oattribute_pos_y)
        self.parent_app.scene.addItem(self.attribute_item)

        self.MT_type_item = QGraphicsSvgItem(rpath('mold/icon/magic-full-jp.svg'))
        self.MT_type_item.setPos(891, 288)
        self.MT_type_item.setScale(1.7)
        self.parent_app.scene.addItem(self.MT_type_item)
        self.MT_type_item.setVisible(False)


        self.current_level = self.config.demo_card_level
        self.current_rank = self.config.demo_card_level
        self.level_item_list = [QGraphicsPixmapItem(QPixmap(rpath(self.config.level_img))) for _ in range(12)]
        x, y = self.config.level_x, self.config.level_y
        for i, star in enumerate(self.level_item_list, start=1):
            star.setPos(x, y)
            x -= self.config.level_inter
            self.parent_app.scene.addItem(star)
        self.display_level_star()

        self.dark_level_list = [QGraphicsPixmapItem(QPixmap(rpath(self.config.dark_level_img))) for _ in range(12)]
        x, y = self.config.rank_x, self.config.rank_y
        for i, star in enumerate(self.dark_level_list, start=1):
            star.setPos(x, y)
            x += self.config.rank_inter
            self.parent_app.scene.addItem(star)
        self.hide_dark_level()

        x, y = self.config.rank_x, self.config.rank_y
        self.rank_item_list = [QGraphicsPixmapItem(QPixmap(rpath(self.config.rank_img))) for _ in range(12)]
        for i, star in enumerate(self.rank_item_list, start=1):
            star.setPos(x, y)
            x += self.config.rank_inter
            self.parent_app.scene.addItem(star)
        self.hide_rank_star()

        x, y = self.config.rank_13_x, self.config.rank_13_y
        self.thirdteen_rank_item = [QGraphicsPixmapItem(QPixmap(rpath(self.config.rank_img))) for _ in range(13)]
        for star in self.thirdteen_rank_item:
            star.setPos(x, y)
            x += self.config.rank_inter
            self.parent_app.scene.addItem(star)
        self.hide_thirdteen_rank()


        self.icon_item = QGraphicsPixmapItem(QPixmap(rpath(self.config.icons['永续'])))
        self.icon_item.setPos(self.config.icon_pos_x, self.config.icon_pos_y)
        self.parent_app.scene.addItem(self.icon_item)
        self.icon_item.setVisible(False)


        font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.detail_info_font[self.language])))[0])
        rtfont = _load_rt_font(self.config)
        self.detail_compresstor = CompressText()
        self.detail_compresstor.setRtFont(rtfont)
        self.detail_compresstor.setRtFontSize(14)
        self.detail_compresstor.setRubyFont(font)
        self.detail_compresstor.setFontSize(self.config.detail_size[self.language])
        self.detail_compresstor.width = self.config.detail_width[self.language]
        self.detail_compresstor.firstLineCompress = True
        self.detail_compresstor.rtRatio = _rt_ratio(0.30434782608695654)
        self.detail_compresstor.rtTop = -2.5

        self.detail_text_group = TextGroup()
        self.detail_text_group.setRubyFont(font)
        self.detail_text_group.setRtFont(rtfont)
        self.parent_app.scene.addItem(self.detail_text_group)
        self.detail_text_group.setPos(self.config.detail_posx[self.language], self.config.detail_posy[self.language])
        self.detail_text_group.setRubyFontSize(self.config.detail_size[self.language])


        font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.text_item_font[self.language])))[0])
        self.compresstor = CompressText()
        self.compresstor.setRtFont(rtfont)
        self.compresstor.setRtFontSize(14)
        self.compresstor.setRubyFont(font)
        self.compresstor.setFontSize(self.config.text_size[self.language])
        self.compresstor.width = self.config.rect_width
        self.compresstor.height = self.config.rect_height_monster
        self.compresstor.rtRatio = _rt_ratio(0.34210526315789475)
        self.compresstor.rtTop = -3.6

        self.text_group = TextGroup()
        self.text_group.setRubyFont(font)
        self.text_group.setRtFont(rtfont)
        self.parent_app.scene.addItem(self.text_group)
        self.text_group.setPos(self.config.rect_pos_monster_x, self.config.rect_pos_monster_y)


        self.lb_compresstor = CompressText()
        self.lb_compresstor.setRtFont(rtfont)
        self.lb_compresstor.setRtFontSize(14)
        self.lb_compresstor.setRubyFont(font)
        self.lb_compresstor.setFontSize(self.config.lb_text_size[self.language])
        self.lb_compresstor.width = self.config.lb_text_width
        self.lb_compresstor.height = self.config.lb_text_height
        self.lb_compresstor.rtRatio = _rt_ratio(0.3333333333333333)
        self.lb_compresstor.rtTop = -3.6

        self.lb_text_group = TextGroup()
        self.lb_text_group.setRubyFont(font)
        self.lb_text_group.setRtFont(rtfont)
        self.parent_app.scene.addItem(self.lb_text_group)
        self.lb_text_group.setPos(self.config.lb_text_x, self.config.lb_text_y)
        self.lb_text_group.setVisible(False)



        lb_font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.ATK_DEF_font_path)))[0])
        lb_font.setPixelSize(self.config.lb_level_font_size)

        self.LB_level_left = MixTextItem('')
        self.LB_level_left.setDefaultTextColor(Qt.black)
        self.LB_level_left.document().setDocumentMargin(0)
        self.LB_level_left.setFont(lb_font)
        self.LB_level_left.setPos(self.config.lb_level_left_single_pos_x, self.config.lb_level_left_single_pos_y)
        self.parent_app.scene.addItem(self.LB_level_left)

        self.LB_level_right = MixTextItem('')
        self.LB_level_right.setDefaultTextColor(Qt.black)
        self.LB_level_right.document().setDocumentMargin(0)
        self.LB_level_right.setFont(lb_font)
        self.LB_level_right.setPos(self.config.lb_level_right_single_pos_x, self.config.lb_level_right_single_pos_y)
        self.parent_app.scene.addItem(self.LB_level_right)
        self.LB_ratio = 0


        self.cn_ATK_DEF_flag = False
        self.line_item = QGraphicsLineItem(self.config.line_item_x1, self.config.line_item_y1,
            self.config.line_item_x2, self.config.line_item_y2)
        pen = QPen(Qt.black)
        pen.setWidth(4)
        self.line_item.setPen(pen)
        self.parent_app.scene.addItem(self.line_item)
        self.line_item.setVisible(False)

        fz_font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.fz_font_path)))[0])
        fz_font.setPixelSize(self.config.fz_font_size)
        self.cn_ATK_item = MixTextItem('攻 /')
        self.cn_DEF_item = MixTextItem('守 /')
        self.sc_LINK_item = MixTextItem('连 接  -')
        self.tc_LINK_item = MixTextItem('連 接  -')
        self.cn_ATK_item.setPos(self.config.cn_ATK_pos_x, self.config.cn_ATK_DEF_pos_y)
        self.cn_ATK_item.setVisible(False)
        self.cn_DEF_item.setPos(self.config.cn_DEF_pos_x, self.config.cn_ATK_DEF_pos_y)
        self.cn_DEF_item.setVisible(False)
        self.sc_LINK_item.setPos(self.config.cn_LINK_pos_x, self.config.cn_ATK_DEF_pos_y)
        self.sc_LINK_item.setVisible(False)
        self.tc_LINK_item.setPos(self.config.cn_LINK_pos_x, self.config.cn_ATK_DEF_pos_y)
        self.tc_LINK_item.setVisible(False)
        self.cn_ATK_item.setFont(fz_font)
        self.cn_DEF_item.setFont(fz_font)
        self.sc_LINK_item.setFont(fz_font)
        self.tc_LINK_item.setFont(fz_font)
        self.parent_app.scene.addItem(self.cn_ATK_item)
        self.parent_app.scene.addItem(self.cn_DEF_item)
        self.parent_app.scene.addItem(self.sc_LINK_item)
        self.parent_app.scene.addItem(self.tc_LINK_item)

        self.ATK_DEF_item = QGraphicsSvgItem(rpath(self.config.ATK_DEF_svg))
        self.ATK_DEF_item.setPos(self.config.ATK_DEF_pos_x, self.config.ATK_DEF_pos_y)
        self.ATK_DEF_item.setScale(self.config.ATK_DEF_scale)
        self.parent_app.scene.addItem(self.ATK_DEF_item)

        self.ATK_LINK_item = QGraphicsSvgItem(rpath(self.config.ATK_LINK_svg))
        self.ATK_LINK_item.setPos(self.config.ATK_DEF_pos_x, self.config.ATK_DEF_pos_y)
        self.ATK_LINK_item.setScale(self.config.ATK_DEF_scale)
        self.parent_app.scene.addItem(self.ATK_LINK_item)
        self.ATK_LINK_item.setVisible(False)

        ATK_DEF_font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.ATK_DEF_font_path)))[0])
        ATK_DEF_font.setPixelSize(self.config.ATK_DEF_font_size)

        LINK_font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(rpath(self.config.link_font_path)))[0])
        LINK_font.setPixelSize(self.config.LINK_font_size)
        LINK_font.setStretch(self.config.LINK_font_stretch)

        self.ATK_number_item = MixTextItem('')
        self.ATK_number_item.setDefaultTextColor(Qt.black)
        self.ATK_number_item.setFont(ATK_DEF_font)
        self.ATK_number_item.document().setDocumentMargin(0)
        self.ATK_number_item.setPos(self.config.ATK_number_x, self.config.ATK_DEF_number_y)
        self.ATK_number_item.setTextWidth(self.config.ATK_DEF_number_width)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.ATK_number_item.document().setDefaultTextOption(text_option)
        self.parent_app.scene.addItem(self.ATK_number_item)
        self.ATK_number_list = [MixTextItem('') for _ in range(self.config.ATK_number_list_len)]
        for i in range(self.config.ATK_number_list_len):
            self.ATK_number_list[i].setVisible(False)
            self.ATK_number_list[i].setDefaultTextColor(Qt.black)
            self.ATK_number_list[i].document().setDocumentMargin(0)
            self.parent_app.scene.addItem(self.ATK_number_list[i])

        self.DEF_number_item = MixTextItem('')
        self.DEF_number_item.setDefaultTextColor(Qt.black)
        self.DEF_number_item.setFont(ATK_DEF_font)
        self.DEF_number_item.document().setDocumentMargin(0)
        self.DEF_number_item.setPos(self.config.DEF_number_x, self.config.ATK_DEF_number_y)
        self.DEF_number_item.setTextWidth(self.config.ATK_DEF_number_width)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.DEF_number_item.document().setDefaultTextOption(text_option)
        self.parent_app.scene.addItem(self.DEF_number_item)
        self.DEF_number_list = [MixTextItem('') for _ in range(self.config.DEF_number_list_len)]
        for i in range(self.config.DEF_number_list_len):
            self.DEF_number_list[i].setVisible(False)
            self.DEF_number_list[i].setDefaultTextColor(Qt.black)
            self.DEF_number_list[i].document().setDocumentMargin(0)
            self.parent_app.scene.addItem(self.DEF_number_list[i])

        self.LINK_number_item = MixTextItem('')
        self.LINK_number_item.setDefaultTextColor(Qt.black)
        self.LINK_number_item.setFont(LINK_font)
        self.LINK_number_item.document().setDocumentMargin(0)
        self.LINK_number_item.setPos(self.config.LINK_number_x, self.config.LINK_number_y)
        self.LINK_number_item.setPlainText('3')
        self.parent_app.scene.addItem(self.LINK_number_item)
        self.LINK_number_item.setVisible(False)


        pass_font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(rpath(self.config.pass_font_path)))[0])
        pass_font.setPixelSize(self.config.pass_font_size)
        self.card_pass_item = MixTextItem('')
        self.card_pass_item.setDefaultTextColor(Qt.black)
        self.card_pass_item.document().setDocumentMargin(0)
        self.card_pass_item.setFont(pass_font)
        self.card_pass_item.setPos(self.config.ocard_pass_x, self.config.ocard_pass_y)
        self.parent_app.scene.addItem(self.card_pass_item)

        pack_font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(rpath(self.config.pass_font_path)))[0])
        pack_font.setPixelSize(self.config.pack_font_size)
        pack_font.setStretch(self.config.pack_font_stretch)
        self.card_pack_item = MixTextItem('')
        self.card_pack_item.setDefaultTextColor(Qt.black)
        self.card_pack_item.document().setDocumentMargin(0)
        self.card_pack_item.setFont(pack_font)
        self.card_pack_item.setPos(self.config.card_pack_up_x, self.config.card_pack_up_y)
        self.card_pack_item.setTextWidth(self.config.card_pack_item_width)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.card_pack_item.document().setDefaultTextOption(text_option)
        self.parent_app.scene.addItem(self.card_pack_item)


        self.copyright_item = QGraphicsSvgItem(rpath(self.config.copyright_svgs_black[0]))
        self.copyright_item.setPos(self.config.copyright_x[0], self.config.ocopyright_y)
        self.copyright_item.setScale(self.config.copyright_scale[0])
        self.parent_app.scene.addItem(self.copyright_item)

        self.holo_item = QGraphicsPixmapItem(QPixmap(rpath(self.config.holos['样式一'])))
        self.holo_item.setPos(self.config.holo_x, self.config.holo_y)
        self.parent_app.scene.addItem(self.holo_item)


        self.arrow_top_on = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_on['top'])))
        self.arrow_top_off = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_off['top'])))
        self.arrow_down_on = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_on['down'])))
        self.arrow_down_off = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_off['down'])))
        self.arrow_left_on = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_on['left'])))
        self.arrow_left_off = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_off['left'])))
        self.arrow_right_on = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_on['right'])))
        self.arrow_right_off = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_off['right'])))
        self.arrow_lefttop_on = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_on['lefttop'])))
        self.arrow_lefttop_off = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_off['lefttop'])))
        self.arrow_leftdown_on = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_on['leftdown'])))
        self.arrow_leftdown_off = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_off['leftdown'])))
        self.arrow_righttop_on = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_on['righttop'])))
        self.arrow_righttop_off = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_off['righttop'])))
        self.arrow_rightdown_on = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_on['rightdown'])))
        self.arrow_rightdown_off = QGraphicsPixmapItem(QPixmap(rpath(self.config.arrows_off['rightdown'])))
        self.arrow_top_on.setPos(self.config.arrow_top_x, self.config.arrow_top_y)
        self.arrow_top_off.setPos(self.config.arrow_top_x, self.config.arrow_top_y)
        self.arrow_down_on.setPos(self.config.arrow_down_x, self.config.arrow_down_y)
        self.arrow_down_off.setPos(self.config.arrow_down_x, self.config.arrow_down_y)
        self.arrow_left_on.setPos(self.config.arrow_left_x, self.config.arrow_left_y)
        self.arrow_left_off.setPos(self.config.arrow_left_x, self.config.arrow_left_y)
        self.arrow_right_on.setPos(self.config.arrow_right_x, self.config.arrow_right_y)
        self.arrow_right_off.setPos(self.config.arrow_right_x, self.config.arrow_right_y)
        self.arrow_lefttop_on.setPos(self.config.arrow_lefttop_x, self.config.arrow_lefttop_y)
        self.arrow_lefttop_off.setPos(self.config.arrow_lefttop_x, self.config.arrow_lefttop_y)
        self.arrow_leftdown_on.setPos(self.config.arrow_leftdown_x, self.config.arrow_leftdown_y)
        self.arrow_leftdown_off.setPos(self.config.arrow_leftdown_x, self.config.arrow_leftdown_y)
        self.arrow_righttop_on.setPos(self.config.arrow_righttop_x, self.config.arrow_righttop_y)
        self.arrow_righttop_off.setPos(self.config.arrow_righttop_x, self.config.arrow_righttop_y)
        self.arrow_rightdown_on.setPos(self.config.arrow_rightdown_x, self.config.arrow_rightdown_y)
        self.arrow_rightdown_off.setPos(self.config.arrow_rightdown_x, self.config.arrow_rightdown_y)

        self.arrow_on_list = [self.arrow_lefttop_on, self.arrow_top_on, self.arrow_righttop_on,
            self.arrow_left_on, self.arrow_right_on,
            self.arrow_leftdown_on, self.arrow_down_on, self.arrow_rightdown_on]
        self.arrow_off_list = [self.arrow_lefttop_off, self.arrow_top_off, self.arrow_righttop_off,
            self.arrow_left_off, self.arrow_right_off,
            self.arrow_leftdown_off, self.arrow_down_off, self.arrow_rightdown_off]
        self.arrow_status_list = [False, False, False, False, False, False, False, False]

        for item in self.arrow_on_list:
            self.parent_app.scene.addItem(item)
            item.setVisible(False)
        for item in self.arrow_off_list:
            self.parent_app.scene.addItem(item)
            item.setVisible(False)

        self.official_link_arrows = [QGraphicsPixmapItem(QPixmap(rpath(p))) for p in self.config.official_arrows]
        for item in self.official_link_arrows:
            self.parent_app.scene.addItem(item)
            item.setVisible(False)


        self.watermark_item = QGraphicsPixmapItem(None)
        self.parent_app.scene.addItem(self.watermark_item)
        self.watermark_item.setVisible(False)


        self.output_format = 0
        self.output_name = 0

        self.typing_components = [self.text_input, self.LB_text_edit, self.card_name_edit, self.ATK_edit,
            self.DEF_edit, self.card_pass_edit, self.card_pack_edit]

        self.title_color = QColor(Qt.black)
        self.rt_color = QColor(Qt.black)
        self.race_selector.setCurrentIndex(self.config.demo_race)
        self.info_selector_left.setCurrentIndex(self.config.demo_call_way)
        self.info_selector_mid.setCurrentIndex(self.config.demo_extra1)
        self.info_selector_right.setCurrentIndex(self.config.demo_extra2)
        self.update_language()
        self.card_pass_typed = False
        self.update_card_name()
        self.switch_info()

        self.attribute_item.setVisible(True)
        self.parent_app.scene.setSceneRect(self.card_rect)
        overframe._ensure_overframe_drag(self)
        free_text._ensure_free_text(self)
        overframe._ocg_of_after_init(self, 'init_vis')

    def on_name_search(self):
        text = self.card_name_edit.text()
        self.card_pass_edit.has_user_type = True
        if '繁体' in self.language:
            text = self.t2s_converter.convert(text)
        dialog = NameSearchDialog(text=text, parent=self)
        dialog.search_btn_clicked()
        dialog.exec_()
        pass

    def update_card_name(self, *args, **kwargs):
        # 卡名按它自己的语言绘制（英文模式下的中文卡名也不会消失）
        return language_switch._render_name_in_own_language(self, OTCGWidget._standard_update_card_name, args, kwargs)

    def _standard_update_card_name(self):
        text = self.card_name_edit.text()
        align = 'justify'
        if self.name_align_selector.currentIndex() == 0:
            align = 'justify'
        elif self.name_align_selector.currentIndex() == 1:
            align = 'center'
        else:
            align = 'right'
        self.name_compresstor.text = text
        self.name_compresstor.textAlign = align
        self.name_compresstor.compressText()
        itemList = self.name_compresstor.getItemList()
        enflag = True if self.language == '英文' else False
        if self.mix_mode_flag:
            self.mixname_text_group.setVisible(True)
            self.name_text_group.setVisible(False)

            self.mixname_text_group.setName(itemList, enflag, self.rt_color, self.title_color, self.name_compresstor.rtZoomRatio,
                self.mix_mode_flag,
                self.gradient_flag,
                outline_enabled=self.outline_enabled,
                outline_color=self.outline_color,
                outline_thickess=self.outline_thickess,
                gradient_process=self.gradient_process,
                edge_points=self.config.gradient_edge_points[self.language],
                single_color=self.single_color)
            if self.mix_mode_flag:
                for i, ruby_item in enumerate(self.mixname_text_group.ruby_items):
                    if self.shadow_flag:
                        ruby_item.setGraphicsEffect(self.new_shadow_list[i])
                    else:
                        ruby_item.setGraphicsEffect(None)
        else:
            self.mixname_text_group.setVisible(False)
            self.name_text_group.setVisible(True)
            self.name_text_group.setName(itemList, enflag, self.rt_color, self.title_color, self.name_compresstor.rtZoomRatio)
        pass

    @watermark._recheck_secret_watermark_after
    def switch_card_type(self):
        selected_key = self.type_selector.currentText()
        self.card_type = selected_key
        self.rare_change()
        self.watermark_change()
        self.copyright_change(self.copyright_selector.currentIndex())

        self.update_text()
        if self.card_type == '怪兽卡':
            if self.MT_type_hbox.parent():
                self.otcg_layout.removeItem(self.MT_type_hbox)
                self.MT_type_label.setVisible(False)
                self.MT_type_selector.setVisible(False)
            self.detail_text_group.setVisible(not self.full_effect_toggle.is_checked)
            self.reappear_monster_items()
            self.MT_type_item.setVisible(False)
            self.icon_item.setVisible(False)
            self.attribute_item.setPixmap(QPixmap(rpath(self.config.attributes[self.language][self.current_attribute])))

            self.update_detail_info()
        else:
            self.switch_base_image()
            self.rt_color = QColor(Qt.white)
            if not self.color_flag:
                self.title_color = QColor(Qt.white)
            self.update_card_name()
            self.detail_text_group.setVisible(False)
            self.ATK_DEF_item.setVisible(False)
            self.ATK_LINK_item.setVisible(False)
            self.line_item.setVisible(False)
            self.cn_ATK_item.setVisible(False)
            self.cn_DEF_item.setVisible(False)
            self.sc_LINK_item.setVisible(False)
            self.tc_LINK_item.setVisible(False)

            if self.ATK_number_item.isVisible():
                self.ATK_number_item.setVisible(False)
            else:
                for i in range(self.config.ATK_number_list_len):
                    self.ATK_number_list[i].setVisible(False)
            if self.DEF_number_item.isVisible():
                self.DEF_number_item.setVisible(False)
            else:
                for i in range(self.config.DEF_number_list_len):
                    self.DEF_number_list[i].setVisible(False)
            self.LINK_number_item.setVisible(False)
            self.hide_monster_items()
            if self.card_type == '魔法卡':
                self.attribute_item.setPixmap(QPixmap(rpath(self.config.attributes[self.language]['魔'])))
            else:
                self.attribute_item.setPixmap(QPixmap(rpath(self.config.attributes[self.language]['罠'])))

            if not self.MT_type_hbox.parent() is not None:
                self.otcg_layout.insertLayout(4, self.MT_type_hbox)
                self.MT_type_label.setVisible(True)
                self.MT_type_selector.setVisible(True)

            self.update_MT_type()
            self.MT_type_item.setVisible(True)

            self.otcg_layout.removeItem(self.link_vbox)
            for btn in self.link_btn_list:
                btn.setVisible(False)
            self.hide_link_arrow()
            self.transform_normal_img()
            if self.LB_info_hbox.parent():
                self.otcg_layout.removeItem(self.LB_info_hbox)
                self.otcg_layout.removeWidget(self.LB_text_edit)
            self.LB_level_label.setVisible(False)
            self.LB_level_edit.setVisible(False)
            self.LB_ratio_label.setVisible(False)
            self.LB_ratio_selector.setVisible(False)
            self.LB_Zack_label.setVisible(False)
            self.LB_Zack_toggle.setVisible(False)
            self.LB_text_edit.setVisible(False)
            self.LB_level_left.setVisible(False)
            self.LB_level_right.setVisible(False)
            self.lb_text_group.setVisible(False)

            text_option = QTextOption()
            text_option.setAlignment(Qt.AlignRight)
            self.card_pack_item.document().setDefaultTextOption(text_option)
            self.card_pack_item.setPos(self.config.card_pack_up_x, self.config.card_pack_up_y)
            self.card_pass_item.setDefaultTextColor(Qt.black)
            self.card_pack_item.setDefaultTextColor(Qt.black)

            self.card_pack_item.setVisible(self.toggle_pack.is_checked)

        if self.full_effect_toggle.is_checked:
            self.hide_effect_item()
        pass

    def switch_template(self, index: int):
        self.current_template = index
        self.switch_base_image()


        if self.card_type == '怪兽卡' and self.detail_call_way == '连接':
            self.display_link_arrow()

        if not (self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆'):
            self.transform_normal_img()

        if ( self.current_template == 0 or self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆' or
            self.info_selector_left.currentText() in ('巨神兵', '天空龙', '翼神龙')):
            posx = self.config.ocard_pass_x
            posy = self.config.ocard_pass_y
            copyright_y = self.config.ocopyright_y
            attribute_y = self.config.oattribute_pos_y
        else:
            posx = self.config.card_pass_x
            posy = self.config.card_pass_y
            copyright_y = self.config.copyright_y
            attribute_y = self.config.attribute_pos_y
        self.card_pass_item.setPos(posx, posy)

        self.copyright_item.setPos(self.copyright_item.pos().x(), copyright_y)

        self.attribute_item.setPos(self.config.attribute_pos_x, attribute_y)

        self.update_card_name()

        self.rare_change()

        if index == 1:
            self.overframe_item.setVisible(False)
            self.overframe_mask.setVisible(False)
            self.overframe_toggle.is_checked = False
            self.overframe_toggle.animate_circle()
        self.overframe_toggle.setEnabled(index == 0)
        self.overframe_upload_btn.setEnabled(index == 0)
        self.overframe_setting_btn.setEnabled(index == 0)
        overframe._ensure_overframe_drag(self)
        overframe._ocg_of_after_layout_change(self)

    def hide_monster_items(self):
        boxes = [self.detail_info_hbox, self.ATK_hbox, self.DEF_hbox, self.attribute_hbox]
        for layout in boxes:
            for i in range(layout.count()):
                widget = layout.itemAt(i).widget()
                if widget:
                    widget.setVisible(False)
        self.attribute_label.setVisible(False)
        self.otcg_layout.removeItem(self.detail_info_hbox)
        self.otcg_layout.removeItem(self.ATK_DEF_hbox)
        self.otcg_layout.removeItem(self.attribute_hbox)

        self.level_label.setVisible(False)
        self.level_zero_btn.setVisible(False)
        for btn in self.level_star_btn_list:
            btn.setVisible(False)
        self.otcg_layout.removeItem(self.level_box)
        self.rank_label.setVisible(False)
        self.rank_zero_btn.setVisible(False)
        for btn in self.rank_star_btn_list:
            btn.setVisible(False)
        self.otcg_layout.removeItem(self.rank_box)
        self.hide_level_star()
        self.hide_rank_star()
        self.hide_dark_level()
        self.hide_thirdteen_rank()

        self.ATK_DEF_type_label.setVisible(False)
        self.ATK_DEF_type_toggle.setVisible(False)

        self.detail_custom_label.setEnabled(False)
        self.detail_custom_toggle.setEnabled(False)
        self.detail_custom_edit.setEnabled(False)

    def reappear_monster_items(self):
        boxes = [self.detail_info_hbox, self.ATK_hbox, self.DEF_hbox, self.attribute_hbox]
        for layout in boxes:
            for i in range(layout.count()):
                widget = layout.itemAt(i).widget()
                if widget:
                    widget.setVisible(True)
        self.attribute_label.setVisible(True)
        if not self.detail_info_hbox.parent():
            self.otcg_layout.insertLayout(4, self.detail_info_hbox)
        if not self.attribute_hbox.parent():
            self.otcg_layout.insertLayout(6, self.attribute_hbox)
        if not self.ATK_DEF_hbox.parent():
            self.otcg_layout.insertLayout(7, self.ATK_DEF_hbox)

        if not self.detail_call_way == '超量':
            self.level_label.setVisible(True)
            self.level_zero_btn.setVisible(True)
            for btn in self.level_star_btn_list:
                btn.setVisible(True)
            if not self.level_box.parent():
                self.otcg_layout.insertLayout(7, self.level_box)
            self.display_level_star()
        else:
            self.rank_label.setVisible(True)
            self.rank_zero_btn.setVisible(True)
            for btn in self.rank_star_btn_list:
                btn.setVisible(True)
            if not self.rank_box.parent():
                self.otcg_layout.insertLayout(7, self.rank_box)
            if self.current_rank < 13:
                self.display_rank_star()
            else:
                self.display_thirdteen_rank()

        self.ATK_DEF_type_label.setVisible(True)
        self.ATK_DEF_type_toggle.setVisible(True)

        self.detail_custom_label.setEnabled(True)
        self.detail_custom_toggle.setEnabled(True)
        self.detail_custom_edit.setEnabled(self.detail_custom_toggle.is_checked)

    @overframe._sync_ocg_layers_after
    def switch_base_image(self):
        base_key = ''
        template = self.config.base_images_official if self.current_template == 0 else self.config.base_images
        overframe_template = self.config.overframe_mask
        if self.card_type in ('魔法卡', '陷阱卡'):
            base_key = self.card_type

        elif self.detail_extra1 == '灵摆':
            if self.LB_Zack_toggle.is_checked:
                base_key = '扎克灵摆'

            elif self.detail_call_way in ('巨神兵', '天空龙', '翼神龙'):
                base_key = '效果灵摆'
            else:
                base_key = f'{self.detail_call_way}灵摆'
        else:
            base_key = self.info_selector_left.currentText()
        self.base_item.setPixmap(QPixmap(rpath(template[base_key])))
        self.overframe_mask.setPixmap(QPixmap(rpath(overframe_template[base_key])))
        self.parent_app.view.fitInView(self.base_item.boundingRect(), Qt.KeepAspectRatio)

    def update_language(self, *args, **kwargs):
        # 切换前记下各语言的文字，用户亲手切换语言时据此翻译或还原（language_switch）
        return language_switch._update_language_keeping_text(self, OTCGWidget._standard_update_language, args, kwargs)

    def _standard_update_language(self):
        # config 各张表（race_map、detail_map……）没有「语言+2」这一项时，「类型2」不可用：
        # 选了会在后面查表时 KeyError，槽函数里的异常会让程序闪退。将来 config 补上就自动放行。
        tc_supported = (self.lan_selector.currentText() + '2') in self.config.race_map
        if not tc_supported:
            self.tc_type = 0
        self.language = self.lan_selector.currentText()
        if self.language == '简体中文':
            self.language = '简体中文' if self.tc_type == 0 else '简体中文2'
        if self.lan_selector.currentText() == '简体中文':
            if not self.tc_type_selector.layout() is not None:
                self.lan_hbox.addWidget(self.tc_type_selector)
                self.tc_type_selector.setVisible(True)
        else:
            self.lan_hbox.removeWidget(self.tc_type_selector)
            self.tc_type_selector.setVisible(False)
        self.switch_info()


        font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.card_name_font[self.language])))[0])
        font.setPixelSize(self.config.card_name_size[self.language])
        self.name_compresstor.setRubyFont(font)
        self.name_text_group.setRubyFont(font)
        self.name_compresstor.setFontSize(self.config.card_name_size[self.language])
        self.name_text_group.setRubyFontSize(self.config.card_name_size[self.language])
        self.name_text_group.setPos(*_name_pos(self.config, self.language))
        self.mixname_text_group.setRubyFont(font)
        self.mixname_text_group.setRubyFontSize(self.config.card_name_size[self.language])
        self.mixname_text_group.setPos(*_name_pos(self.config, self.language))




        font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.detail_info_font[self.language])))[0])
        font.setPixelSize(self.config.detail_size[self.language])
        self.detail_compresstor.setRubyFont(font)
        self.detail_text_group.setRubyFont(font)
        self.detail_compresstor.setFontSize(self.config.detail_size[self.language])
        self.detail_compresstor.width = self.config.detail_width[self.language]
        self.detail_text_group.setRubyFontSize(self.config.detail_size[self.language])
        self.detail_text_group.setPos(self.config.detail_posx[self.language], self.config.detail_posy[self.language])



        font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.text_item_font[self.language])))[0])
        self.compresstor.setRubyFont(font)
        self.text_group.setRubyFont(font)
        self.lb_compresstor.setRubyFont(font)
        self.lb_text_group.setRubyFont(font)
        self.update_text()
        self.update_lb_text()

        if self.card_type != '怪兽卡':
            self.update_MT_type()
        self.update_card_name()
        self.update_detail_info()

        if self.card_type == '怪兽卡':
            self.attribute_item.setPixmap(QPixmap(rpath(self.config.attributes[self.language][self.current_attribute])))
        elif self.card_type == '魔法卡':
            self.attribute_item.setPixmap(QPixmap(rpath(self.config.attributes[self.language]['魔'])))
        else:
            self.attribute_item.setPixmap(QPixmap(rpath(self.config.attributes[self.language]['罠'])))



        flag = True
        for compo in self.typing_components:
            if compo.has_user_type:
                flag = False
                break
        if flag:
            self.card_name_edit.setText(self.config.demo_card_name[self.language])
            self.text_input.setText(self.config.demo_card_text[self.language])
            self.card_pass_edit.setText(self.config.demo_card_pass)
            self.card_pack_edit.setText(self.config.demo_card_pack)

        if not tc_supported:
            # 不留一个「能选但没反应」的下拉
            blocked = self.tc_type_selector.blockSignals(True)
            self.tc_type_selector.setCurrentIndex(0)
            self.tc_type_selector.blockSignals(blocked)
            self.tc_type_selector.setVisible(False)

    def update_trans_type(self, index):
        if index == 0:
            self.offical_cn = False
        else:
            self.offical_cn = True
        self.info_fetcher.set_trans_type(self.offical_cn)

    def on_overframe_upload(self):
        file_name, _ = QFileDialog.getOpenFileName(self, '选择本地图片', self.upload_dir, 'Image Files (*.png *.jpg *.bmp)')
        self.upload_dir = os.path.dirname(file_name)
        if file_name:
            self.set_overframe_img(file_name)
        pass

    def set_overframe_img(self, img_path):
        img = Image.open(img_path).convert('RGBA')
        pixmap = pillow_img_to_pixmap(img)
        crop_dialog = CropDialog(pixmap, self, mode='OverFrame')
        if crop_dialog.exec_():
            pixmap = crop_dialog.get_cropped_pixmap()
            self.overframe_img = qpixmap_to_pillow(pixmap)

            width, height = self.overframe_img.size
            cw, ch = self.card_rect.width(), self.card_rect.height()
            if width / height >= cw / ch:
                self.overframe_sizex, self.overframe_sizey = int(cw), int(height * cw / width)
            else:
                self.overframe_sizex, self.overframe_sizey = int(width * ch / height), int(ch)
            self.of_display_img = self.overframe_img.resize((self.overframe_sizex, self.overframe_sizey), Image.Resampling.LANCZOS)
            self.of_display_img = pillow_img_to_pixmap(self.of_display_img)
            self.overframe_item.setPixmap(self.of_display_img)
            self.overframe_item.setPos(0, 0)
            self.overframe_scale = 1000
            self.overframe_posx, self.overframe_posy = (0, 0)
        overframe._ensure_overframe_drag(self)

    def load_image_nocrop(self):

        file_name, _ = QFileDialog.getOpenFileName(self, '选择本地图片', self.upload_dir, 'Image Files (*.png *.jpg *.bmp)')
        self.upload_dir = os.path.dirname(file_name)
        if file_name:
            self.set_card_img_nocrop(file_name)

    def set_card_img_nocrop(self, img_path):
        self.card_img = Image.open(img_path).convert('RGBA')
        if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
            self.transform_LB_img()
        else:
            self.transform_normal_img()

    def load_image_crop(self):

        file_name, _ = QFileDialog.getOpenFileName(self, '选择本地图片', self.upload_dir, 'Image Files (*.png *.jpg *.bmp)')
        self.upload_dir = os.path.dirname(file_name)
        if file_name:
            self.set_card_img_crop(file_name)

    def set_card_img_crop(self, img_path):
        pil_image = Image.open(img_path).convert('RGBA')
        pixmap = pillow_img_to_pixmap(pil_image)
        crop_dialog = CropDialog(pixmap, self)
        if crop_dialog.exec_():
            pixmap = crop_dialog.get_cropped_pixmap()
            self.card_img = qpixmap_to_pillow(pixmap)
            if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
                self.transform_LB_img()
            else:
                self.transform_normal_img()
        pass

    def _transform_identity(self):
        """卡图缩放的全部输入（图片、尺寸、模式、版面参数）。没变时不必重算 PIL 的 LANCZOS 缩放——
        一次切卡会调用 4 次（标签页套用、导入、update_detail_info、switch_info 各一次）。"""
        image = getattr(self, 'card_img', None)
        if image is None:
            return None
        try:
            size = tuple(image.size)
            mode = str(getattr(image, 'mode', ''))
        except Exception:
            return None
        # 标签页管理会给缓存图片的副本标上原图身份（_ygodiy_identity），同一张图的副本视为同一输入
        return (getattr(image, '_ygodiy_identity', None) or id(image), size, mode, self.current_template,
                str(self.info_selector_left.currentText()), self.ocard_img_size, self.card_img_size)

    @overframe._sync_ocg_layers_after
    def transform_normal_img(self):
        identity = self._transform_identity()
        if identity is not None and getattr(self, '_transform_key_normal', None) == identity:
            return None
        result = self._transform_normal_img()
        if identity is not None:
            self._transform_key_normal = identity
        return result

    @overframe._sync_ocg_layers_after
    def transform_LB_img(self):
        identity = self._transform_identity()
        if identity is not None and getattr(self, '_transform_key_LB', None) == identity:
            return None
        result = self._transform_LB_img()
        if identity is not None:
            self._transform_key_LB = identity
        return result

    def _transform_normal_img(self):
        card_img_size = (self.ocard_img_size if ( self.current_template == 0 or
            self.info_selector_left.currentText() in ('巨神兵', '天空龙', '翼神龙')) else self.card_img_size)
        self.display_img = self.card_img.resize((card_img_size.width(), card_img_size.height()), Image.Resampling.LANCZOS)
        self.display_img = pillow_img_to_pixmap(self.display_img)
        self.card_img_item.setPixmap(self.display_img)
        card_x = (self.config.ocard_x if ( self.current_template == 0 or
            self.info_selector_left.currentText() in ('巨神兵', '天空龙', '翼神龙')) else self.config.card_x)
        card_y = (self.config.ocard_y if ( self.current_template == 0 or
            self.info_selector_left.currentText() in ('巨神兵', '天空龙', '翼神龙')) else self.config.card_y)
        self.card_img_item.setPos(card_x, card_y)

    def _transform_LB_img(self):
        if self.LB_ratio == 0:
            self.display_img = apply_fade_to_alpha(crop_square_image(self.card_img), fade_ratio=0.02)
            self.display_img = self.display_img.resize((self.LB_img_size.width(), self.LB_img_size.width()), Image.Resampling.LANCZOS)
        else:
            self.display_img = self.card_img.resize((self.LB_img_size.width(), self.LB_img_size.height()), Image.Resampling.LANCZOS)
        self.display_img = pillow_img_to_pixmap(self.display_img)
        self.card_img_item.setPixmap(self.display_img)
        self.card_img_item.setPos(self.config.LB_x, self.config.LB_y)








    def overframe_toggle_change(self, checked: bool):
        self.overframe_upload_btn.setEnabled(checked)
        self.overframe_setting_btn.setEnabled(checked)
        self.overframe_item.setVisible(checked)
        self.overframe_mask.setVisible(checked)
        overframe._ocg_of_after_toggle(self, checked)

    def show_overframe_setting(self):
        if not self.overframe_img is not None:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle('提示')
            msg_box.setText('还未上传超框卡图')
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec_()
            return
        dialog = OverFrameSettingDialog(parent=self)
        if dialog.exec_():
            pass
        pass

    def switch_info(self):
        self.detail_call_way = self.info_selector_left.currentText()
        if self.detail_call_way in ('巨神兵', '天空龙', '翼神龙'):
            self.detail_call_way = '效果'
        self.detail_extra1 = self.info_selector_mid.currentText()
        self.detail_extra2 = self.info_selector_right.currentText()
        self.update_detail_info()


    def update_detail_text_only(self):
        info_text = ''

        if not self.detail_custom_toggle.is_checked:
            self.race_text = self.config.race_map[self.language][self.race_selector.currentText()]
            cur_map = self.config.detail_map[self.language]
            info_text_list = []
            info_text_list.append(self.race_text)
            info_text_list.append(cur_map[self.detail_call_way])
            if not self.detail_call_way == '通常':
                info_text_list.append(cur_map['效果'])
            if self.detail_call_way == '衍生物' or self.detail_call_way == '效果':
                info_text_list.pop(-2)

            if self.detail_extra1 and self.detail_extra1 != self.detail_extra2:
                if self.detail_extra1 == '通常':
                    if len(info_text_list) > 2:
                        info_text_list.pop(-1)
                    if self.detail_call_way == '衍生物':
                        info_text_list[-1] = cur_map['通常']
                else:
                    info_text_list.insert(-1, cur_map[self.detail_extra1])

            if self.detail_extra2 and self.detail_extra2 != self.detail_extra1:
                if self.detail_extra2 == '通常':
                    if len(info_text_list) > 2 and info_text_list[-1] == cur_map['效果'] and self.detail_call_way != '效果':
                        info_text_list.pop(-1)

                elif info_text_list[-1] == cur_map['效果'] or info_text_list[-1] == cur_map['通常']:
                    info_text_list.insert(-1, cur_map[self.detail_extra2])
                else:
                    info_text_list.append(cur_map[self.detail_extra2])

            if self.detail_extra1 == self.detail_extra2 and self.detail_extra1 != '':
                if self.detail_extra1 == '通常':
                    info_text_list.pop(-1)
                else:
                    info_text_list.insert(-1, cur_map[self.detail_extra1])

            if self.detail_extra1 == '特殊召唤' or self.detail_extra2 == '特殊召唤':
                index = info_text_list.index(cur_map['特殊召唤'])
                if not index == 1:
                    info_text_list.pop(index)
                    info_text_list.insert(1, cur_map['特殊召唤'])
                pass

            if self.language == '英文':
                info_text = '[' + '/'.join(info_text_list) + ']'
            else:
                info_text = '【' + '/'.join(info_text_list) + '】'
            if self.offical_cn:
                info_text = info_text.replace('同调', '同步')
                info_text = info_text.replace('调整', '协调')
        else:

            if self.language == '英文':
                info_text = '[' + self.detail_custom_edit.text() + ']'
            else:
                info_text = '【' + self.detail_custom_edit.text() + '】'
            pass

        if '日文' in self.language:
            info_text = info_text.replace('/', '／')



        fontweight = self.text_weight_slider.value() / 10 if self.text_weightable else 0

        self.detail_compresstor.text = info_text
        self.detail_compresstor.compressText()
        itemList = self.detail_compresstor.getItemList()
        self.detail_text_group.setTexts(itemList, fontweight, self.detail_compresstor.rtZoomRatio)
        pass


    @watermark._recheck_secret_watermark_after
    def update_detail_info(self):
        if not self.card_type == '怪兽卡':
            return

        LB_index = self.info_selector_mid.findText('灵摆')
        if self.detail_call_way == '连接' or self.detail_call_way == '衍生物' or self.detail_call_way == '暗黑同调':
            if LB_index >= 0:
                self.info_selector_mid.removeItem(LB_index)

        elif LB_index < 0:
            self.info_selector_mid.addItem('灵摆')

        self.update_detail_text_only()
        self.copyright_change(self.copyright_selector.currentIndex())
        self.switch_base_image()

        if self.detail_extra1 == '灵摆':
            text_option = QTextOption()
            text_option.setAlignment(Qt.AlignLeft)
            self.card_pack_item.document().setDefaultTextOption(text_option)
            self.card_pack_item.setPos(self.config.card_pack_bottom_x, self.config.card_pack_bottom_y)
            self.transform_LB_img()
            if not self.LB_info_hbox.parent():
                self.otcg_layout.insertLayout(9, self.LB_info_hbox)
                self.otcg_layout.insertWidget(10, self.LB_text_edit)
            self.LB_level_label.setVisible(True)
            self.LB_level_edit.setVisible(True)
            self.LB_ratio_label.setVisible(True)
            self.LB_ratio_selector.setVisible(True)
            self.LB_Zack_label.setVisible(True)
            self.LB_Zack_toggle.setVisible(True)
            self.LB_text_edit.setVisible(True)
            self.LB_level_left.setVisible(True)
            self.LB_level_right.setVisible(True)
            self.lb_text_group.setVisible(True)
        else:
            text_option = QTextOption()
            text_option.setAlignment(Qt.AlignRight)
            self.card_pack_item.document().setDefaultTextOption(text_option)
            self.card_pack_item.setPos(self.config.card_pack_up_x, self.config.card_pack_up_y)
            self.transform_normal_img()
            if self.LB_info_hbox.parent():
                self.otcg_layout.removeItem(self.LB_info_hbox)
                self.otcg_layout.removeWidget(self.LB_text_edit)
            self.LB_level_label.setVisible(False)
            self.LB_level_edit.setVisible(False)
            self.LB_ratio_label.setVisible(False)
            self.LB_ratio_selector.setVisible(False)
            self.LB_Zack_label.setVisible(False)
            self.LB_Zack_toggle.setVisible(False)
            self.LB_text_edit.setVisible(False)
            self.LB_level_left.setVisible(False)
            self.LB_level_right.setVisible(False)
            self.lb_text_group.setVisible(False)

        if self.detail_call_way == '超量':
            if not self.rank_box.parent():
                self.otcg_layout.insertLayout(7, self.rank_box)
                self.rank_label.setVisible(True)
                self.rank_zero_btn.setVisible(True)
                for btn in self.rank_star_btn_list:
                    btn.setVisible(True)
            if self.level_box.parent():
                self.otcg_layout.removeItem(self.level_box)
                self.level_label.setVisible(False)
                self.level_zero_btn.setVisible(False)
                for btn in self.level_star_btn_list:
                    btn.setVisible(False)
            self.hide_level_star()
            self.hide_dark_level()
            if self.current_rank == 13:
                self.display_thirdteen_rank()
            else:
                self.display_rank_star()

            if self.cn_ATK_DEF_flag:
                self.line_item.setVisible(True)
                self.cn_ATK_item.setVisible(True)
                self.cn_DEF_item.setVisible(True)
                self.ATK_DEF_item.setVisible(False)
            else:
                self.line_item.setVisible(False)
                self.cn_ATK_item.setVisible(False)
                self.cn_DEF_item.setVisible(False)
                self.ATK_DEF_item.setVisible(True)
            self.ATK_LINK_item.setVisible(False)
            self.LINK_number_item.setVisible(False)
            self.sc_LINK_item.setVisible(False)
            self.tc_LINK_item.setVisible(False)
            self.update_ATK()
            self.update_DEF()
            self.DEF_edit.setEnabled(True)

        elif self.detail_call_way == '连接':
            self.ATK_DEF_item.setVisible(False)
            if self.cn_ATK_DEF_flag:
                self.ATK_LINK_item.setVisible(False)
                self.cn_ATK_item.setVisible(True)
                self.cn_DEF_item.setVisible(False)
                if self.language == '简体中文' or self.language == '简体中文2':
                    self.sc_LINK_item.setVisible(False)
                    self.tc_LINK_item.setVisible(True)
                else:
                    self.sc_LINK_item.setVisible(True)
                    self.tc_LINK_item.setVisible(False)
            else:
                self.ATK_LINK_item.setVisible(True)
            self.update_link_number()
            self.LINK_number_item.setVisible(True)
            self.update_ATK()
            if self.DEF_number_item.isVisible():
                self.DEF_number_item.setVisible(False)
            else:
                for i in range(self.config.DEF_number_list_len):
                    self.DEF_number_list[i].setVisible(False)
            self.DEF_edit.setDisabled(True)
            if self.level_box.parent():
                self.otcg_layout.removeItem(self.level_box)
                self.level_label.setVisible(False)
                self.level_zero_btn.setVisible(False)
                for btn in self.level_star_btn_list:
                    btn.setVisible(False)
            if self.rank_box.parent():
                self.otcg_layout.removeItem(self.rank_box)
                self.rank_label.setVisible(False)
                self.rank_zero_btn.setVisible(False)
                for btn in self.rank_star_btn_list:
                    btn.setVisible(False)
            self.hide_level_star()
            self.hide_rank_star()
            self.hide_dark_level()
            self.hide_thirdteen_rank()
            text_option = QTextOption()
            text_option.setAlignment(Qt.AlignRight)
            self.card_pack_item.document().setDefaultTextOption(text_option)
            self.card_pack_item.setPos(self.config.card_pack_link_x, self.config.card_pack_link_y)
        else:
            if self.cn_ATK_DEF_flag:
                self.line_item.setVisible(True)
                self.cn_ATK_item.setVisible(True)
                self.cn_DEF_item.setVisible(True)
                self.ATK_DEF_item.setVisible(False)
            else:
                self.line_item.setVisible(False)
                self.cn_ATK_item.setVisible(False)
                self.cn_DEF_item.setVisible(False)
                self.ATK_DEF_item.setVisible(True)
            self.ATK_LINK_item.setVisible(False)
            self.LINK_number_item.setVisible(False)
            self.sc_LINK_item.setVisible(False)
            self.tc_LINK_item.setVisible(False)
            self.update_ATK()
            self.update_DEF()
            self.DEF_edit.setEnabled(True)
            if not self.level_box.parent():
                self.otcg_layout.insertLayout(7, self.level_box)
                self.level_label.setVisible(True)
                self.level_zero_btn.setVisible(True)
                for btn in self.level_star_btn_list:
                    btn.setVisible(True)
            if self.rank_box.parent():
                self.otcg_layout.removeItem(self.rank_box)
                self.rank_label.setVisible(False)
                self.rank_zero_btn.setVisible(False)
                for btn in self.rank_star_btn_list:
                    btn.setVisible(False)
            self.hide_rank_star()
            self.hide_thirdteen_rank()
            if self.detail_call_way == '暗黑同调':
                self.hide_level_star()
                self.display_dark_level()
            else:
                self.hide_dark_level()
                self.display_level_star()

        if self.detail_call_way == '连接':
            if not self.link_vbox.parent():
                self.otcg_layout.insertLayout(8, self.link_vbox)
            for btn in self.link_btn_list:
                btn.setVisible(True)
            self.display_link_arrow()
        else:
            self.otcg_layout.removeItem(self.link_vbox)
            for btn in self.link_btn_list:
                btn.setVisible(False)
            self.hide_link_arrow()

        if not self.color_flag:
            if self.detail_call_way == '连接' or self.detail_call_way == '超量' or self.detail_call_way == '暗黑同调':
                self.title_color = QColor(Qt.white)
            else:
                self.title_color = QColor(Qt.black)
        if self.detail_call_way == '连接' or self.detail_call_way == '超量' or self.detail_call_way == '暗黑同调':
            self.rt_color = QColor(Qt.white)
        else:
            self.rt_color = QColor(Qt.black)
        self.update_card_name()

        self.rare_change()
        self.watermark_change()


        if self.detail_call_way == '超量' and self.detail_extra1 != '灵摆':
            self.card_pass_item.setDefaultTextColor(Qt.white)
            self.card_pack_item.setDefaultTextColor(Qt.white)
        else:
            self.card_pass_item.setDefaultTextColor(Qt.black)
            self.card_pack_item.setDefaultTextColor(Qt.black)

        if ( self.current_template == 0 or self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆' or
            self.info_selector_left.currentText() in ('巨神兵', '天空龙', '翼神龙')):
            posx = self.config.ocard_pass_x
            posy = self.config.ocard_pass_y
        else:
            posx = self.config.card_pass_x
            posy = self.config.card_pass_y
        self.card_pass_item.setPos(posx, posy)

        if self.full_effect_toggle.is_checked:
            self.hide_effect_item()
        if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
            self.card_pack_item.setVisible(self.toggle_pack.is_checked and not self.full_effect_toggle.is_checked)
        else:
            self.card_pack_item.setVisible(self.toggle_pack.is_checked)
        pass

    def attribute_clicked(self):
        button = self.sender()
        btn_text = button.text()
        self.current_attribute = btn_text
        for k, btn in self.attribute_btn_dict.items():
            if k == btn_text:
                btn.setColor(self.attribute_on_colors[k])
            else:
                btn.setColor(self.attribute_off_colors[k])
        self.attribute_item.setPixmap(QPixmap(rpath(self.config.attributes[self.language][btn_text])))
        pass

    def attribute_update(self, attr: str):
        self.current_attribute = attr
        self.attribute_item.setPixmap(QPixmap(rpath(self.config.attributes[self.language][attr])))
        for k, btn in self.attribute_btn_dict.items():
            if k == attr:
                btn.setColor(self.attribute_on_colors[k])
            else:
                btn.setColor(self.attribute_off_colors[k])
        pass

    def star_zero_clicked(self):
        self.current_level = 0
        for btn in self.level_star_btn_list:
            btn.setStarColor(self.star_undo_color)
            btn.setCircleColor(self.bg_undo_color)
        self.update_level_label()
        self.hide_level_star()
        self.hide_dark_level()

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
        if self.detail_call_way == '暗黑同调':
            self.display_dark_level()
        else:
            self.display_level_star()

    def update_level_label(self):
        self.level_label.setText(f'等级 {self.current_level}')

    def display_level_btn(self):
        for i, btn in enumerate(self.level_star_btn_list):
            if i + 1 <= self.current_level:
                btn.setStarColor(self.star_level_color)
                btn.setCircleColor(self.level_bg_color)
            else:
                btn.setStarColor(self.star_undo_color)
                btn.setCircleColor(self.bg_undo_color)
        pass

    def rank_zero_clicked(self):
        self.current_rank = 0
        for btn in self.rank_star_btn_list:
            btn.setStarColor(self.star_undo_color)
            btn.setCircleColor(self.bg_undo_color)
        self.update_rank_label()
        self.hide_rank_star()
        self.hide_thirdteen_rank()

    def rank_clicked(self):
        button = self.sender()
        flag = True
        for i, btn in enumerate(self.rank_star_btn_list):
            if flag:
                btn.setStarColor(self.star_rank_color)
                btn.setCircleColor(self.rank_bg_color)
            else:
                btn.setStarColor(self.star_undo_color)
                btn.setCircleColor(self.bg_undo_color)
            if btn is button:
                self.current_rank = i + 1
                flag = False
        self.update_rank_label()
        if self.current_rank < 13:
            self.hide_thirdteen_rank()
            self.display_rank_star()
        else:
            self.hide_rank_star()
            self.display_thirdteen_rank()

    def update_rank_label(self):
        self.rank_label.setText(f'阶级 {self.current_rank}')

    def display_rank_btn(self):
        for i, btn in enumerate(self.rank_star_btn_list):
            if i + 1 <= self.current_rank:
                btn.setStarColor(self.star_rank_color)
                btn.setCircleColor(self.rank_bg_color)
            else:
                btn.setStarColor(self.star_undo_color)
                btn.setCircleColor(self.bg_undo_color)
        pass

    def display_level_star(self):
        for i, star in enumerate(self.level_item_list, start=1):
            star.setVisible(i <= self.current_level)

    def display_rank_star(self):
        for i, star in enumerate(self.rank_item_list, start=1):
            star.setVisible(i <= self.current_rank)

    def display_dark_level(self):
        for i, star in enumerate(self.dark_level_list, start=1):
            star.setVisible(i <= self.current_level)

    def hide_level_star(self):
        for star in self.level_item_list:
            star.setVisible(False)

    def hide_rank_star(self):
        for star in self.rank_item_list:
            star.setVisible(False)

    def hide_dark_level(self):
        for star in self.dark_level_list:
            star.setVisible(False)

    def display_thirdteen_rank(self):
        for star in self.thirdteen_rank_item:
            star.setVisible(True)

    def hide_thirdteen_rank(self):
        for star in self.thirdteen_rank_item:
            star.setVisible(False)

    def detail_custom_cliked(self, check: bool):
        self.detail_custom_edit.setEnabled(check)
        self.update_detail_text_only()
        pass

    def show_hide_attr(self, checked: bool):
        self.attribute_item.setVisible(checked)
        if checked:
            self.name_compresstor.width = self.config.NAME_WIDTH
        else:
            self.name_compresstor.width = self.config.NAME_FULL_WIDTH
        self.update_card_name()
        pass

    def full_effect_clicked(self):
        self.update_detail_info()
        self.switch_card_type()
        pass

    def first_line_compress(self, checked: bool):
        self.compresstor.firstLineCompress = True if checked else False
        self.update_text()
        pass

    def hide_effect_item(self):
        self.detail_text_group.setVisible(False)
        self.ATK_DEF_item.setVisible(False)
        self.ATK_LINK_item.setVisible(False)
        self.cn_ATK_item.setVisible(False)
        self.cn_DEF_item.setVisible(False)
        self.sc_LINK_item.setVisible(False)
        self.tc_LINK_item.setVisible(False)
        self.line_item.setVisible(False)
        self.ATK_number_item.setVisible(False)
        for i in range(self.config.ATK_number_list_len):
            self.ATK_number_list[i].setVisible(False)
        self.DEF_number_item.setVisible(False)
        for i in range(self.config.DEF_number_list_len):
            self.DEF_number_list[i].setVisible(False)
        self.LINK_number_item.setVisible(False)

    def update_MT_type(self):
        text = self.MT_type_selector.currentText()
        svg_file = ''
        x, y = (0, 0)
        scale = 0
        if not text == '通常':
            if self.card_type == '魔法卡':
                svg_file = self.config.MT_type_full_svg[self.language][0]
                x = self.config.MT_type_full_posx_M[self.language]
            else:
                svg_file = self.config.MT_type_full_svg[self.language][1]
                x = self.config.MT_type_full_posx_T[self.language]
            self.icon_item.setPixmap(QPixmap(rpath(self.config.icons[text])))
            self.icon_item.setVisible(True)
        else:
            if self.card_type == '魔法卡':
                svg_file = self.config.MT_type_svg[self.language][0]
                x = self.config.MT_type_posx_M[self.language]
            else:
                svg_file = self.config.MT_type_svg[self.language][1]
                x = self.config.MT_type_posx_T[self.language]
            self.icon_item.setVisible(False)
        y = self.config.MT_type_posy[self.language]
        scale = self.config.MT_type_scale[self.language]

        renderer = QSvgRenderer(rpath(svg_file))
        self.MT_type_item.setSharedRenderer(renderer)
        self.MT_type_item.renderer().load(rpath(svg_file))
        self.MT_type_item.setPos(x, y)
        self.MT_type_item.setScale(scale)
        pass


    def display_link_arrow(self):
        self.hide_link_arrow()
        if self.current_template == 0:
            for status, item in list(zip(self.arrow_status_list, self.official_link_arrows)):
                item.setVisible(status)
            pass
        else:
            for status, on, off in list(zip(self.arrow_status_list, self.arrow_on_list, self.arrow_off_list)):
                if status:
                    on.setVisible(True)
                    off.setVisible(False)
                else:
                    on.setVisible(False)
                    off.setVisible(True)
        pass

    def hide_link_arrow(self):
        for on, off in list(zip(self.arrow_on_list, self.arrow_off_list)):
            on.setVisible(False)
            off.setVisible(False)
        for item in self.official_link_arrows:
            item.setVisible(False)
        pass

    def link_btn_clicked(self):
        button = self.sender()
        i = 0
        for btn in self.link_control_list:
            if btn is button:
                if self.arrow_status_list[i]:
                    btn.setInnerColor(self.link_btn_off_color)
                    self.arrow_status_list[i] = False
                else:
                    btn.setInnerColor(self.link_btn_on_color)
                    self.arrow_status_list[i] = True
            i += 1
        self.display_link_arrow()
        self.update_link_number()

    def update_link_number(self):
        num = 0
        for s in self.arrow_status_list:
            if s:
                num += 1
        self.LINK_number_item.setPlainText(f'{num}')
        if self.full_effect_toggle.is_checked:
            self.LINK_number_item.setVisible(False)

    def update_text(self):
        font_size = self.config.text_size[self.language]
        if self.text_sizeable:
            font_size = font_size + self.text_size_slider.value()

        self.compresstor.setFontSize(font_size)
        self.text_group.setRubyFontSize(font_size)

        pos_x = self.config.rect_pos_monster_x
        pos_y = (self.config.rect_pos_monster_y if self.card_type == '怪兽卡' and not self.full_effect_toggle.is_checked
            else self.config.rect_pos_mt_y)
        self.text_group.setPos(pos_x, pos_y)


        self.compresstor.height = (self.config.rect_height_monster if ( self.card_type == '怪兽卡' and
            not self.full_effect_toggle.is_checked) else self.config.rect_height_mt)


        text_spacing = self.config.text_spacing[self.language]
        line_count = self.compresstor.height // font_size
        extra_space = font_size * text_spacing * (line_count - 1)
        if font_size * line_count + extra_space > self.compresstor.height:
            line_count -= 1
        line_height_value = (self.compresstor.height - font_size) / (line_count - 1)
        line_height = line_height_value / font_size
        self.compresstor.lineHeight = line_height
        self.compresstor.height += (line_height - 1) * font_size + 0.005


        fontweight = self.text_weight_slider.value() / 10 if self.text_weightable else 0


        self.compresstor.textAlign = 'justify' if self.text_align_selector.currentIndex() == 0 else 'center'

        self.compresstor.text = self.text_input.toPlainText()
        self.compresstor.compressText()
        itemList = self.compresstor.getItemList()
        self.text_group.setTexts(itemList, fontweight, self.compresstor.rtZoomRatio)
        pass

    def update_lb_text(self):
        font_size = self.config.lb_text_size[self.language]
        if self.text_sizeable:
            font_size = font_size + self.text_size_slider.value()

        self.lb_compresstor.setFontSize(font_size)
        self.lb_text_group.setRubyFontSize(font_size)

        pos_x = self.config.lb_text_x
        pos_y = self.config.lb_text_y
        self.lb_text_group.setPos(pos_x, pos_y)


        self.lb_compresstor.height = self.config.lb_text_height


        text_spacing = self.config.text_spacing[self.language]
        line_count = self.lb_compresstor.height // font_size
        extra_space = font_size * text_spacing * (line_count - 1)
        if font_size * line_count + extra_space > self.lb_compresstor.height:
            line_count -= 1
        line_height_value = (self.lb_compresstor.height - font_size) / (line_count - 1)
        line_height = line_height_value / font_size
        self.lb_compresstor.lineHeight = line_height
        self.lb_compresstor.height += (line_height - 1) * font_size + 0.005


        fontweight = self.text_weight_slider.value() / 10 if self.text_weightable else 0


        self.lb_compresstor.textAlign = 'justify' if self.text_align_selector.currentIndex() == 0 else 'center'

        self.lb_compresstor.text = self.LB_text_edit.toPlainText()
        self.lb_compresstor.compressText()
        itemList = self.lb_compresstor.getItemList()
        self.lb_text_group.setTexts(itemList, fontweight, self.lb_compresstor.rtZoomRatio)

        pass




    def text_sizeable_toggle(self, checked):
        self.text_sizeable = checked
        if self.text_sizeable:
            self.text_size_slider.setEnabled(True)
        else:
            self.text_size_slider.setEnabled(False)
        self.update_text()
        self.update_lb_text()

    def update_text_size(self):
        change_size = self.text_size_slider.value()
        self.text_size_label.setText(str(change_size))
        self.update_text()
        self.update_lb_text()


    def text_weight_switch(self, checked: bool):
        self.text_weightable = checked
        self.text_weight_slider.setEnabled(checked)
        self.update_text_weight()
        pass

    def update_text_weight(self):
        self.text_weightnum_label.setText(str(self.text_weight_slider.value()))
        weight = self.text_weight_slider.value() / 10
        if weight == 0 or self.text_weight_adjust_btn.is_checked == False:
            for ruby in self.text_group.ruby_items:
                ruby.enableOutline(False)
            for ruby in self.lb_text_group.ruby_items:
                ruby.enableOutline(False)
            for ruby in self.detail_text_group.ruby_items:
                ruby.enableOutline(False)
        else:
            for ruby in self.text_group.ruby_items:
                ruby.enableOutline(True)
                ruby.setOutlineStyle(color=Qt.black, thickness=weight)
            for ruby in self.lb_text_group.ruby_items:
                ruby.enableOutline(True)
                ruby.setOutlineStyle(color=Qt.black, thickness=weight)
            for ruby in self.detail_text_group.ruby_items:
                ruby.enableOutline(True)
                ruby.setOutlineStyle(color=Qt.black, thickness=weight)
        pass

    def update_ATK(self):
        for i in range(self.config.ATK_number_list_len):
            self.ATK_number_list[i].setPlainText('')
            self.ATK_number_list[i].setVisible(False)

        text = self.ATK_edit.text()
        text_len = len(text)
        if not self.check_ATK_len(text):
            fontWid = 100
            while self.ATK_number_item.boundingRect().width() > self.config.ATK_DEF_number_width:
                fontWid -= 1
                font = self.ATK_number_item.font()
                font.setStretch(fontWid)
                self.ATK_number_item.setFont(font)
                self.ATK_number_item.setPlainText(text)
            pass

            self.ATK_number_item.setVisible(False)
            font = self.ATK_number_item.font()
            metrics = QFontMetricsF(font)
            text_width = metrics.width(text)
            remain_space = self.config.ATK_DEF_number_width - text_width
            extra_spacing = remain_space / (text_len - 1)
            x_pos = self.config.ATK_number_x
            for i, char in enumerate(text):
                self.ATK_number_list[i].setFont(font)
                self.ATK_number_list[i].setPos(x_pos, self.config.ATK_DEF_number_y)
                x_pos += metrics.width(char) + extra_spacing
                self.ATK_number_list[i].setPlainText(char)
                self.ATK_number_list[i].setVisible(True)
        else:
            self.ATK_number_item.setVisible(True)

        if self.full_effect_toggle.is_checked:
            self.ATK_number_item.setVisible(False)
            for i in range(self.config.ATK_number_list_len):
                self.ATK_number_list[i].setVisible(False)
        pass

    def update_DEF(self):
        for i in range(self.config.DEF_number_list_len):
            self.DEF_number_list[i].setPlainText('')
            self.DEF_number_list[i].setVisible(False)

        text = self.DEF_edit.text()
        text_len = len(text)
        if not self.check_DEF_len(text):
            fontWid = 100
            while self.DEF_number_item.boundingRect().width() > self.config.ATK_DEF_number_width:
                fontWid -= 1
                font = self.DEF_number_item.font()
                font.setStretch(fontWid)
                self.DEF_number_item.setFont(font)
                self.DEF_number_item.setPlainText(text)
            pass

            self.DEF_number_item.setVisible(False)
            font = self.DEF_number_item.font()
            metrics = QFontMetricsF(font)
            text_width = metrics.width(text)
            remain_space = self.config.ATK_DEF_number_width - text_width
            extra_spacing = remain_space / (text_len - 1)
            x_pos = self.config.DEF_number_x
            for i, char in enumerate(text):
                self.DEF_number_list[i].setFont(font)
                self.DEF_number_list[i].setPos(x_pos, self.config.ATK_DEF_number_y)
                x_pos += metrics.width(char) + extra_spacing
                self.DEF_number_list[i].setPlainText(char)
                self.DEF_number_list[i].setVisible(True)
        else:
            self.DEF_number_item.setVisible(True)
        if self.full_effect_toggle.is_checked:
            self.DEF_number_item.setVisible(False)
            for i in range(self.config.DEF_number_list_len):
                self.DEF_number_list[i].setVisible(False)
        pass

    def check_ATK_len(self, text):
        font = self.ATK_number_item.font()
        font.setStretch(100)
        self.ATK_number_item.setFont(font)
        self.ATK_number_item.setPlainText(text)
        return self.ATK_number_item.boundingRect().width() <= self.config.ATK_DEF_number_width

    def check_DEF_len(self, text):
        font = self.DEF_number_item.font()
        font.setStretch(100)
        self.DEF_number_item.setFont(font)
        self.DEF_number_item.setPlainText(text)
        return self.DEF_number_item.boundingRect().width() <= self.config.ATK_DEF_number_width

    def color_btn_clicked(self):
        self.color_flag = True
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
        self.update_card_name()

        for btn in self.color_btn_list:
            if btn is button:
                btn.display_ring()
            else:
                btn.hide_ring()
        for btn in self.color_advanced_list:
            btn.hide_ring()

    def change_color_mode(self, checked):
        if checked:
            if self.color_btn_hbox.parent():
                self.color_vbox.removeItem(self.color_btn_hbox)
            for btn in self.color_btn_list:
                btn.setVisible(False)
            if not self.color_advanced_hbox.parent() is not None:
                self.color_vbox.addLayout(self.color_advanced_hbox)
            for btn in self.color_advanced_list:
                btn.setVisible(True)
        else:
            if self.color_advanced_hbox.parent():
                self.color_vbox.removeItem(self.color_advanced_hbox)
            for btn in self.color_advanced_list:
                btn.setVisible(False)
            if not self.color_btn_hbox.parent() is not None:
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
            self.outline_thickess = 4
            self.shadow_flag = True
            self.shadow_color = QColor(0, 0, 0)
            self.shadow_blur_size = 5
            self.shadow_x_offset = 1
            self.shadow_y_offset = 1
            self.gradient_flag = True
            self.gradient_process = [[True, 0, QColor(222, 222, 222)], [True, 0.21, QColor(255, 255, 255)],
                [True, 0.42, QColor(217, 217, 217)], [True, 0.52, QColor(141, 141, 141)],
                [True, 0.66, QColor(161, 161, 161)], [True, 1, QColor(255, 255, 255)]]
            self.single_color = QColor(0, 0, 0)
        elif btn_text == '金字':
            self.mix_option = 1
            self.outline_enabled = True
            self.outline_color = QColor(0, 0, 0)
            self.outline_thickess = 4
            self.shadow_flag = True
            self.shadow_color = QColor(0, 0, 0)
            self.shadow_blur_size = 5
            self.shadow_x_offset = 1
            self.shadow_y_offset = 1
            self.gradient_flag = True
            self.gradient_process = [[True, 0, QColor(255, 220, 0)], [True, 0.23, QColor(255, 255, 255)],
                [True, 0.42, QColor(255, 220, 0)], [True, 0.52, QColor(181, 129, 0)],
                [True, 0.73, QColor(255, 220, 0)], [True, 1, QColor(255, 220, 0)]]
            self.single_color = QColor(0, 0, 0)
        elif btn_text == '青字':
            self.mix_option = 2
            self.outline_enabled = True
            self.outline_color = QColor(0, 0, 0)
            self.outline_thickess = 4
            self.shadow_flag = True
            self.shadow_color = QColor(0, 0, 0)
            self.shadow_blur_size = 5
            self.shadow_x_offset = 1
            self.shadow_y_offset = 1
            self.gradient_flag = True
            self.gradient_process = [[True, 0, QColor(76, 255, 190)], [True, 0.23, QColor(255, 255, 255)],
                [True, 0.42, QColor(0, 255, 174)], [True, 0.54, QColor(0, 153, 163)],
                [True, 0.73, QColor(0, 255, 174)], [True, 1, QColor(76, 244, 255)]]
            self.single_color = QColor(0, 0, 0)
        elif btn_text == '红字':
            self.mix_option = 3
            self.outline_enabled = True
            self.outline_color = QColor(0, 0, 0)
            self.outline_thickess = 4
            self.shadow_flag = True
            self.shadow_color = QColor(0, 0, 0)
            self.shadow_blur_size = 5
            self.shadow_x_offset = 1
            self.shadow_y_offset = 1
            self.gradient_flag = False
            self.gradient_process = [[True, 0, QColor(222, 222, 222)], [True, 0.21, QColor(255, 255, 255)],
                [True, 0.42, QColor(217, 217, 217)], [True, 0.52, QColor(141, 141, 141)],
                [True, 0.66, QColor(161, 161, 161)], [True, 1, QColor(255, 255, 255)]]
            self.single_color = QColor(230, 0, 0)
            pass
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
        self.color_flag = True
        self.mix_mode_flag = True
        self.update_mix_param()
        self.update_card_name()

        for btn in self.color_advanced_list:
            if btn is button:
                btn.display_ring()
            else:
                btn.hide_ring()
        for btn in self.color_btn_list:
            btn.hide_ring()
        pass

    def update_mix_param(self):
        self.update_shadow_ratio()
        for i in range(self.config.NAME_LIST_LEN):
            self.new_shadow_list[i] = QGraphicsDropShadowEffect()
            self.new_shadow_list[i].setColor(self.shadow_color)
            self.new_shadow_list[i].setBlurRadius(self.shadow_blur_size * self.shadow_vis_ratio)
            self.new_shadow_list[i].setXOffset(self.shadow_x_offset * self.shadow_vis_ratio)
            self.new_shadow_list[i].setYOffset(self.shadow_y_offset * self.shadow_vis_ratio)
        pass

    def update_card_pass(self):
        text = self.card_pass_edit.text()
        self.card_pass_item.setPlainText(text)

    def on_pass_btn_clicked(self):
        if self.card_pass_edit.has_user_type:
            self.on_cardpass_return()

    def update_card_pack(self):
        text = self.card_pack_edit.text()
        self.card_pack_item.setPlainText(text)

    def holo_change(self, *_args):
        # 防伪下拉里有可增删的自定义项：推迟到下一轮事件循环，由 customization 判断选的是自定义项还是标准样式
        customization._defer_custom_combo_change(self, 'holo', OTCGWidget._standard_holo_change)

    def _standard_holo_change(self):
        text = self.holo_selector.currentText()
        self.holo_item.setPixmap(QPixmap(rpath(self.config.holos[text])))

    def copyright_change(self, *_args):
        # 版权下拉里有可增删的自定义项：推迟到下一轮事件循环，由 customization 判断选的是自定义项还是标准样式
        customization._defer_custom_combo_change(self, 'copyright', OTCGWidget._standard_copyright_change)

    def _standard_copyright_change(self, index: int):
        if ( self.current_template == 0 or self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆' or
            self.info_selector_left.currentText() in ('巨神兵', '天空龙', '翼神龙')):
            copyright_y = self.config.ocopyright_y
        else:
            copyright_y = self.config.copyright_y

        if self.card_type == '怪兽卡' and self.detail_call_way == '超量' and self.detail_extra1 != '灵摆':
            self.copyright_item.renderer().load(rpath(self.config.copyright_svgs_white[index]))
        else:
            self.copyright_item.renderer().load(rpath(self.config.copyright_svgs_black[index]))

        self.copyright_item.setScale(self.config.copyright_scale[index])
        self.copyright_item.setPos(self.config.copyright_x[index], copyright_y)

        self.copyright_item.renderer().setAspectRatioMode(Qt.KeepAspectRatio)
        self.parent_app.view.update()

    def rare_change(self):
        # 罕贵度分底图和前景两层，前景压在卡面最上层（rarity）
        rarity._apply_otcg_rarity(self)

    def watermark_change(self):
        # 秘密水印在灵摆卡上向上延伸（watermark）
        watermark._watermark_change_with_pendulum(self)

    def _standard_watermark_change(self):
        current_text = self.water_selector.currentText()
        if current_text == '无':
            self.watermark_item.setVisible(False)
            self.anniversary_item.setVisible(False)

        elif current_text == 'secret':
            if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
                self.watermark_item.setPixmap(QPixmap(rpath(self.config.watermark_img[current_text][1])))
            else:
                self.watermark_item.setPixmap(QPixmap(rpath(self.config.watermark_img[current_text][0])))
            self.watermark_item.setVisible(True)
            self.anniversary_item.setVisible(False)

        elif current_text == '20th' or current_text == '25th':
            self.anniversary_item.setPixmap(QPixmap(rpath(self.config.watermark_img[current_text])))
            self.anniversary_item.setVisible(True)
            self.watermark_item.setVisible(False)
        else:
            self.watermark_item.setPixmap(QPixmap(rpath(self.config.watermark_img[current_text])))
            self.watermark_item.setVisible(True)
            self.anniversary_item.setVisible(False)
        pass

    def update_lb_level(self):
        text = self.LB_level_edit.text()
        self.LB_level_left.setPlainText(text)
        self.LB_level_right.setPlainText(text)
        if len(text) <= 1:
            self.LB_level_left.setPos(self.config.lb_level_left_single_pos_x, self.config.lb_level_left_single_pos_y)
            self.LB_level_right.setPos(self.config.lb_level_right_single_pos_x, self.config.lb_level_right_single_pos_y)
        else:
            self.LB_level_left.setPos(self.config.lb_level_left_double_pos_x, self.config.lb_level_left_double_pos_y)
            self.LB_level_right.setPos(self.config.lb_level_right_double_pos_x, self.config.lb_level_right_double_pos_y)

    @watermark._recheck_secret_watermark_after
    def LB_ratio_changed(self, index: int):
        self.LB_ratio = index
        self.transform_LB_img()

    @watermark._recheck_secret_watermark_after
    def LB_Zack_clicked(self):
        self.switch_base_image()
        pass

    def on_cardpass_return(self):
        worker = Worker(self.fetch_info)
        worker.signals.finished.connect(self.after_info_fetch)
        self.parent_app.show_loading_gif()
        self.name_search_btn.setEnabled(False)
        self.card_pass_btn.setEnabled(False)
        self.random_btn.setEnabled(False)
        self.threadpool.start(worker)

    def fetch_info(self):
        card_pass = self.card_pass_edit.text()
        if len(card_pass) < 8:
            card_pass = card_pass.zfill(8)
        self.card_pass_edit.setText(card_pass)
        self.info_fetcher.set_card_pass(card_pass, self.language)

    @card_tabs._restore_after_search_refetch
    @watermark._recheck_secret_watermark_after
    def after_info_fetch(self):
        if not self.info_fetcher.valid:
            QToolTip.showText(self.card_pass_edit.mapToGlobal(self.card_pass_edit.rect().topLeft()) + QPoint(-3, -40),
                '无效卡密', self.card_pass_edit)
            self.parent_app.hide_loading_gif()
            self.name_search_btn.setEnabled(True)
            self.card_pass_btn.setEnabled(True)
            self.random_btn.setEnabled(True)
            return
        card_name = self.info_fetcher.card_name
        effect_text = self.info_fetcher.effect_text
        self.card_name_edit.setText(card_name)
        self.text_input.setText(effect_text)
        if self.info_fetcher.card_type in ('怪兽卡', '魔法卡', '陷阱卡'):
            self.type_selector.setCurrentText(self.info_fetcher.card_type)
        self.card_pack_edit.setText(self.info_fetcher.card_pack)

        if self.card_type == '怪兽卡':
            if self.info_fetcher.race in self.config.race_list:
                self.race_selector.setCurrentText(self.info_fetcher.race)

            if self.info_fetcher.attribute in ('光', '暗', '风', '水', '炎', '地', '神'):
                self.attribute_update(self.info_fetcher.attribute)

            if self.info_fetcher.call_way in self.call_way_list:
                self.info_selector_left.setCurrentText(self.info_fetcher.call_way)
            if self.info_fetcher.extra1 in self.extra1_list:
                self.info_selector_mid.setCurrentText(self.info_fetcher.extra1)
            if self.info_fetcher.extra2 in self.extra2_list:
                self.info_selector_right.setCurrentText(self.info_fetcher.extra2)

            level = self.info_fetcher.level
            if self.detail_call_way != '连接':
                if self.detail_call_way == '超量':
                    self.current_rank = level
                    self.display_rank_btn()
                    self.update_rank_label()
                    if level < 13:
                        self.hide_thirdteen_rank()
                        self.display_rank_star()
                    else:
                        self.hide_rank_star()
                        self.display_thirdteen_rank()
                else:
                    self.current_level = level
                    self.display_level_btn()
                    self.update_level_label()
                    self.display_level_star()
            else:

                self.arrow_status_list = self.info_fetcher.link_arrow_status
                self.display_link_arrow()
                for btn, status in list(zip(self.link_control_list, self.arrow_status_list)):
                    if status:
                        btn.setInnerColor(self.link_btn_on_color)
                    else:
                        btn.setInnerColor(self.link_btn_off_color)
                self.update_link_number()

            self.ATK_edit.setText(self.info_fetcher.atk_num)
            if self.detail_call_way != '连接':
                self.DEF_edit.setText(self.info_fetcher.def_num)

            if self.detail_extra1 == '灵摆':
                self.LB_level_edit.setText(self.info_fetcher.lb_level)
                self.LB_text_edit.setText(self.info_fetcher.lb_text)
        else:


            self.MT_type_selector.setCurrentText(self.info_fetcher.MT_type)


        self.card_img = self.info_fetcher.card_img
        if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
            self.transform_LB_img()
        else:
            self.transform_normal_img()

        self.parent_app.hide_loading_gif()
        self.name_search_btn.setEnabled(True)
        self.card_pass_btn.setEnabled(True)
        self.random_btn.setEnabled(True)
        pass

    def on_toggle_source(self, checked):
        self.source_btn.setEnabled(checked)
        self.info_fetcher.local_image_use = checked

    def on_local_clicked(self):
        folder = QFileDialog.getExistingDirectory(self, '选择卡图来源文件夹')
        if folder:
            self.local_image_folder = folder
            self.source_helper.setExtraText(f'当前卡图来源  {folder}')
            self.info_fetcher.local_image_source = folder
        pass

    def source_helper_clicked(self):
        QToolTip.showText(self.source_helper.mapToGlobal(self.source_helper.rect().topLeft() + QPoint(0, 15)),
            self.source_helper.helptext + self.source_helper.extratext, self)
        pass

    def on_toggle_pass(self, checked):
        self.card_pass_item.setVisible(checked)

    def on_toggle_pack(self, chekced):
        if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
            self.card_pack_item.setVisible(chekced and not self.full_effect_toggle.is_checked)
        else:
            self.card_pack_item.setVisible(chekced)


    def on_toggle_holo(self, checked):
        self.holo_item.setVisible(checked)

    def on_toggle_copy(self, checked):
        self.copyright_item.setVisible(checked)

    def on_toggle_corner(self, checked):
        self.base_item.set_rounded(checked)
        self.rare_item.set_rounded(checked)
        self.overframe_item.set_rounded(checked)

    def on_toggle_ATK_DEF(self, checked):
        self.cn_ATK_DEF_flag = checked
        if self.cn_ATK_DEF_flag:
            self.ATK_DEF_item.setVisible(False)
            self.ATK_LINK_item.setVisible(False)
            self.line_item.setVisible(True)
            self.cn_ATK_item.setVisible(True)
            if self.detail_call_way == '连接':
                self.cn_DEF_item.setVisible(False)
                if self.language == '简体中文' or self.language == '简体中文2':
                    self.sc_LINK_item.setVisible(False)
                    self.tc_LINK_item.setVisible(True)
                else:
                    self.sc_LINK_item.setVisible(True)
                    self.tc_LINK_item.setVisible(False)
            else:
                self.cn_DEF_item.setVisible(True)
        else:
            self.line_item.setVisible(False)
            if self.detail_call_way == '连接':
                self.ATK_LINK_item.setVisible(True)
                self.ATK_DEF_item.setVisible(False)
            else:
                self.ATK_LINK_item.setVisible(False)
                self.ATK_DEF_item.setVisible(True)
            self.cn_ATK_item.setVisible(False)
            self.cn_DEF_item.setVisible(False)
            self.tc_LINK_item.setVisible(False)
            self.sc_LINK_item.setVisible(False)

        if self.full_effect_toggle.is_checked:
            self.ATK_DEF_item.setVisible(False)
            self.ATK_LINK_item.setVisible(False)
            self.cn_ATK_item.setVisible(False)
            self.cn_DEF_item.setVisible(False)
            self.sc_LINK_item.setVisible(False)
            self.tc_LINK_item.setVisible(False)
            self.line_item.setVisible(False)
        pass

    def update_tc_type(self):
        self.tc_type = self.tc_type_selector.currentIndex()
        self.language = '简体中文' if self.tc_type == 0 else '简体中文2'

        font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.card_name_font[self.language])))[0])
        font.setPixelSize(self.config.card_name_size[self.language])
        self.name_compresstor.setRubyFont(font)
        self.name_text_group.setRubyFont(font)
        self.name_compresstor.setFontSize(self.config.card_name_size[self.language])
        self.name_text_group.setRubyFontSize(self.config.card_name_size[self.language])
        self.name_text_group.setPos(*_name_pos(self.config, self.language))
        self.mixname_text_group.setRubyFont(font)
        self.mixname_text_group.setRubyFontSize(self.config.card_name_size[self.language])
        self.mixname_text_group.setPos(*_name_pos(self.config, self.language))

        font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.text_item_font[self.language])))[0])
        self.compresstor.setRubyFont(font)
        self.text_group.setRubyFont(font)
        self.lb_compresstor.setRubyFont(font)
        self.lb_text_group.setRubyFont(font)

        font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.detail_info_font[self.language])))[0])
        font.setPixelSize(self.config.detail_size[self.language])
        self.detail_compresstor.setRubyFont(font)
        self.detail_text_group.setRubyFont(font)
        self.detail_compresstor.setFontSize(self.config.detail_size[self.language])
        self.detail_compresstor.width = self.config.detail_width[self.language]
        self.detail_text_group.setRubyFontSize(self.config.detail_size[self.language])
        self.detail_text_group.setPos(self.config.detail_posx[self.language], self.config.detail_posy[self.language])

        name_text = self.card_name_edit.text()
        name_font = None
        effect_text = self.text_input.toPlainText()
        lb_text = self.LB_text_edit.toPlainText()

        name_font = QFont(QFontDatabase.applicationFontFamilies(add_application_font(
            rpath(self.config.card_name_font[self.language])))[0])
        name_font.setPixelSize(self.config.card_name_size[self.language])

        self.card_name_edit.setText(name_text)
        self.text_input.setText(effect_text)
        self.LB_text_edit.setText(lb_text)

        self.update_detail_info()
        if self.card_type != '怪兽卡':
            self.update_MT_type()
        pass

    def name_align_change(self):
        self.update_card_name()
        pass

    def text_align_change(self):
        self.update_text()

    @watermark._recheck_secret_watermark_after
    def random_card(self):
        # 有离线卡库就从里面随机抽，不联网
        card_pass = card_library._random_card_pass()
        if card_pass is not None:
            if hasattr(self.card_pass_edit, 'has_user_type'):
                self.card_pass_edit.has_user_type = True
            self.card_pass_edit.setText(card_pass)
            return self.on_cardpass_return()
        url = 'https://gitee.com/scutlzl/game-king-card-maker/raw/master/data/cardpass_int.npy'
        if not self.card_pass_list is not None:
            try:
                response = requests.get(url, timeout=5)
                file_content = io.BytesIO(response.content)
                self.card_pass_list = np.load(file_content)
            except Exception as e:
                QToolTip.showText(self.random_btn.mapToGlobal(self.random_btn.rect().topLeft() + QPoint(0, -45)),
                    '加载失败', self.random_btn)
                return
        random_num = np.random.choice(self.card_pass_list)
        cardpass = str(random_num).zfill(8)
        self.card_pass_edit.has_user_type = True
        self.card_pass_edit.setText(cardpass)
        self.on_cardpass_return()

    def export_card_data(self):
        """编辑器当前这张卡的数据（与「导出数据」写进 JSON 的内容相同，含卡图）。"""
        data = dict()

        data['name'] = self.card_name_edit.text()
        data['card_type'] = self.type_selector.currentIndex()
        data['template'] = self.template_selector.currentIndex()
        data['language'] = self.lan_selector.currentIndex()
        data['tc_type'] = self.tc_type_selector.currentIndex()
        data['translation'] = self.trans_selector.currentIndex()
        data['mt_type'] = self.MT_type_selector.currentIndex()

        data['color_flag'] = self.color_flag
        data['color_option'] = self.color_option
        data['title_color'] = [self.title_color.red(), self.title_color.green(), self.title_color.blue()]
        data['color_advanced_activated'] = self.color_advanced_btn.is_checked
        data['mix_mode_flag'] = self.mix_mode_flag
        data['mix_option'] = self.mix_option
        data['outline_enabled'], data['outline_enabled_c'] = self.outline_enabled, self.outline_enabled_c
        data['outline_color'] = [self.outline_color.red(), self.outline_color.green(), self.outline_color.blue()]
        data['outline_color_c'] = [self.outline_color_c.red(), self.outline_color_c.green(), self.outline_color_c.blue()]
        data['outline_thickess'], data['outline_thickess_c'] = self.outline_thickess, self.outline_thickess_c

        data['shadow_flag'], data['shadow_flag_c'] = self.shadow_flag, self.shadow_flag_c
        data['shadow_color'] = [self.shadow_color.red(), self.shadow_color.green(), self.shadow_color.blue()]
        data['shadow_color_c'] = [self.shadow_color_c.red(), self.shadow_color_c.green(), self.shadow_color_c.blue()]
        data['shadow_blur_size'], data['shadow_blur_size_c'] = self.shadow_blur_size, self.shadow_blur_size_c
        data['shadow_x_offset'], data['shadow_x_offset_c'] = self.shadow_x_offset, self.shadow_x_offset_c
        data['shadow_y_offset'], data['shadow_y_offset_c'] = self.shadow_y_offset, self.shadow_y_offset_c

        data['gradient_flag'], data['gradient_flag_c'] = self.gradient_flag, self.gradient_flag_c
        data['single_color'] = [self.single_color.red(), self.single_color.green(), self.single_color.blue()]
        data['single_color_c'] = [self.single_color_c.red(), self.single_color_c.green(), self.single_color_c.blue()]
        data['gradient_process_flag'] = [v[0] for v in self.gradient_process]
        data['gradient_process_flag_c'] = [v[0] for v in self.gradient_process_c]
        data['gradient_process_pos'] = [v[1] for v in self.gradient_process]
        data['gradient_process_pos_c'] = [v[1] for v in self.gradient_process_c]
        data['gradient_process_r'] = [v[2].red() for v in self.gradient_process]
        data['gradient_process_r_c'] = [v[2].red() for v in self.gradient_process_c]
        data['gradient_process_g'] = [v[2].green() for v in self.gradient_process]
        data['gradient_process_g_c'] = [v[2].green() for v in self.gradient_process_c]
        data['gradient_process_b'] = [v[2].blue() for v in self.gradient_process]
        data['gradient_process_b_c'] = [v[2].blue() for v in self.gradient_process_c]

        data['HD_img_flag'] = 1 if self.HD_card_img else 0
        data['race'], data['call_way'], data['extra1'], data['extra2'] = (self.race_selector.currentIndex(),
            self.info_selector_left.currentIndex(), self.info_selector_mid.currentIndex(), self.info_selector_right.currentIndex())
        data['level'], data['rank'], data['attribute'] = self.current_level, self.current_rank, self.current_attribute
        data['ATK'], data['DEF'] = self.ATK_edit.text(), self.DEF_edit.text()
        data['cn_atk_def_flag'] = self.cn_ATK_DEF_flag
        data['link_status'] = self.arrow_status_list
        data['effect_text'] = self.text_input.toPlainText()
        data['lb_text'] = self.LB_text_edit.toPlainText() if self.detail_extra1 == '灵摆' else ''
        data['lb_level'] = self.LB_level_edit.text()
        data['text_sizeable'] = self.text_sizeable
        data['text_size_change'] = self.text_size_slider.value()
        data['text_weightable'] = self.text_weightable
        data['text_weight_change'] = self.text_weight_slider.value()
        data['cardpass'], data['cardpack'] = self.card_pass_edit.text(), self.card_pack_edit.text()
        data['holo'], data['copyright'] = self.holo_selector.currentIndex(), self.copyright_selector.currentIndex()
        data['rare'], data['watermark'] = self.rare_selector.currentIndex(), self.water_selector.currentIndex()
        data['cardpass_vis'], data['cardpack_vis'] = self.card_pass_item.isVisible(), self.card_pack_item.isVisible()
        data['holo_vis'], data['copyright_vis'] = self.holo_item.isVisible(), self.copyright_item.isVisible()
        data['local_source_flag'] = self.source_toggle.is_checked
        data['local_source_folder'] = self.local_image_folder
        data['round_corner'] = self.toggle_corner.is_checked
        data['output_format'] = self.output_format
        data['output_name'] = self.output_name
        data['detail_custom_toggle'] = self.detail_custom_toggle.is_checked
        data['detail_custom_text'] = self.detail_custom_edit.text()
        data['attr_hide'] = self.attr_hide_toggle.is_checked
        data['full_effect'] = self.full_effect_toggle.is_checked
        data['LB_ratio'] = self.LB_ratio_selector.currentIndex()
        data['LB_Zack'] = self.LB_Zack_toggle.is_checked
        data['name_align'] = self.name_align_selector.currentIndex()
        data['text_align'] = self.text_align_selector.currentIndex()

        buffered = io.BytesIO()
        self.card_img.save(buffered, format='PNG')
        encoded_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        data['image'] = encoded_image


        # 开关开着但还没有图时超框画不出任何东西，按「超框关闭」导出
        # （以前 overframe_img 为 None 会在这里抛异常：标签页快照失败、修改丢失，直接点「导出数据」还会闪退）
        overframe_on = self.overframe_toggle.is_checked and self.overframe_img is not None
        data['overframe'] = overframe_on
        if overframe_on:
            data['overframe_scale'] = self.overframe_scale
            data['overframe_sizex'] = self.overframe_sizex
            data['overframe_sizey'] = self.overframe_sizey
            data['overframe_posx'] = self.overframe_posx
            data['overframe_posy'] = self.overframe_posy
            buffered = io.BytesIO()
            self.overframe_img.save(buffered, format='PNG')
            encoded_overframe_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
            data['overframe_image'] = encoded_overframe_image

        overframe._ocg_of_inject(self, data)  # 超框图层
        free_text._inject_free_text_into_data(self, data)  # 自定义文本
        return data

    def on_export_clicked(self):
        data = self.export_card_data()
        name = clean_filename(self.card_name_edit.text())
        name = name if name != '' else '卡片数据'

        file_name, _ = QFileDialog.getSaveFileName(self, '导出数据', os.path.join(self.save_dir, name),
            'Image Files (*.json)')
        if file_name:
            with open(file_name, 'w', encoding='utf-8') as json_file:
                json.dump(data, json_file, ensure_ascii=False)
        pass

    def on_import_clicked(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        file_name, _ = QFileDialog.getOpenFileName(self, '选择JSON文件', '', 'JSON Files (*.json)', options=options)
        if not file_name:
            watermark._schedule_secret_watermark_recheck(self)  # 没选文件也重查一次秘密水印（与载入后一致）
            return
        with open(file_name, 'r', encoding='utf-8') as json_file:
            data = json.load(json_file)
        self.apply_card_data(data)

    def apply_card_data(self, data, card_image=None):
        """把一张卡的数据（导出的 JSON）套到编辑器上，最后按数据还原超框图层。

        card_image：已经解码好的卡图（标签页管理器缓存的），给了就不再解码 data['image']。"""
        self._ocg_of_importing = True
        try:
            self._apply_card_fields(data, card_image)
        finally:
            self._ocg_of_importing = False
        if isinstance(data, dict):
            try:
                overframe._ocg_of_apply_data(self, data)
            except Exception:
                _tab_log("载入 OCG 超框图层失败:\n" + traceback.format_exc())

    @watermark._recheck_secret_watermark_after
    def _apply_card_fields(self, data, card_image=None):
        # 开着超框却没有图的数据（快速快照只记了开关状态）按超框关闭处理，否则读图时 KeyError、导入中断
        if isinstance(data, dict) and data.get('overframe') and not data.get('overframe_image'):
            data = dict(data)
            data['overframe'] = False

        self.card_name_edit.setText(data.get('name', ''))
        self.type_selector.setCurrentIndex(data.get('card_type', 0))
        self.template_selector.setCurrentIndex(data.get('template', 0))
        self.lan_selector.setCurrentIndex(data.get('language', 0))
        self.tc_type_selector.setCurrentIndex(data.get('tc_type', 0))
        self.HD_card_img = True if data.get('HD_img_flag', 0) == 1 else False
        self.output_format, self.output_name = data.get('output_format', 0), data.get('output_name', 0)
        if self.card_type != '怪兽卡':
            self.MT_type_selector.setCurrentIndex(data.get('mt_type', 0))
        else:

            self.race_selector.setCurrentIndex(data.get('race', 0))
            self.info_selector_left.setCurrentIndex(data.get('call_way', 0))
            self.info_selector_mid.setCurrentIndex(data.get('extra1', 0))
            self.info_selector_right.setCurrentIndex(data.get('extra2', 0))
            self.current_level = data.get('level', 0)
            self.current_rank = data.get('rank', 0)
            self.current_attribute = data.get('attribute', '光')
            for k, btn in self.attribute_btn_dict.items():
                if k == self.current_attribute:
                    btn.setColor(self.attribute_on_colors[k])
                else:
                    btn.setColor(self.attribute_off_colors[k])
            self.attribute_item.setPixmap(QPixmap(rpath(self.config.attributes[self.language][self.current_attribute])))
            self.ATK_edit.setText(data.get('ATK', '0'))

            if self.detail_call_way != '连接':
                if self.detail_call_way == '超量':
                    self.display_rank_btn()
                    self.update_rank_label()
                    if self.current_rank == 13:
                        self.display_thirdteen_rank()
                        self.hide_rank_star()
                    else:
                        self.display_rank_star()
                        self.hide_thirdteen_rank()
                    pass
                else:
                    self.display_level_btn()
                    self.update_level_label()
                    self.display_level_star()

                self.DEF_edit.setText(data.get('DEF', '0'))
                self.hide_link_arrow()
            else:
                self.arrow_status_list = data.get('link_status', [False, False, False, False, False, False, False, False])
                self.display_link_arrow()
                self.update_link_number()
                for i, btn in enumerate(self.link_control_list):
                    if self.arrow_status_list[i]:
                        btn.setInnerColor(self.link_btn_on_color)
                    else:
                        btn.setInnerColor(self.link_btn_off_color)


            self.ATK_DEF_type_toggle.is_checked = data.get('cn_atk_def_flag', False)
            self.ATK_DEF_type_toggle.animate_circle()
            self.on_toggle_ATK_DEF(self.ATK_DEF_type_toggle.is_checked)

            if self.detail_extra1 == '灵摆':
                self.LB_text_edit.setText(data.get('lb_text', ''))
                self.LB_level_edit.setText(data.get('lb_level', ''))
                self.LB_ratio_selector.setCurrentIndex(data.get('LB_ratio', 0))
                self.LB_Zack_toggle.is_checked = data.get('LB_Zack', False)
                self.LB_Zack_toggle.animate_circle()
                self.LB_Zack_clicked()


        self.text_input.setText(data.get('effect_text', ''))

        self.text_adjust_btn.is_checked = self.text_sizeable = data.get('text_sizeable', False)
        self.text_adjust_btn.animate_circle()
        self.text_size_slider.setValue(data.get('text_size_change', 0))
        self.text_sizeable_toggle(self.text_adjust_btn.is_checked)

        self.text_weight_adjust_btn.is_checked = self.text_weightable = data.get('text_weightable', False)
        self.text_weight_adjust_btn.animate_circle()
        self.text_weight_slider.setValue(data.get('text_weight_change', 0))
        self.text_weight_switch(self.text_weight_adjust_btn.is_checked)

        self.card_pass_edit.setText(data.get('cardpass', ''))
        self.card_pack_edit.setText(data.get('cardpack', ''))
        self.holo_selector.setCurrentIndex(data.get('holo', 0))
        self.copyright_selector.setCurrentIndex(data.get('copyright', 0))
        self.rare_selector.setCurrentIndex(data.get('rare', 0))
        self.water_selector.setCurrentIndex(data.get('watermark', 0))
        self.toggle_pass.is_checked = data.get('cardpass_vis', True)
        self.toggle_pass.animate_circle()
        self.on_toggle_pass(self.toggle_pass.is_checked)
        self.toggle_pack.is_checked = data.get('cardpack_vis', True)
        self.toggle_pack.animate_circle()
        self.on_toggle_pack(self.toggle_pack.is_checked)
        self.toggle_holo.is_checked = data.get('holo_vis', True)
        self.toggle_holo.animate_circle()
        self.on_toggle_holo(self.toggle_holo.is_checked)
        self.toggle_copy.is_checked = data.get('copyright_vis', True)
        self.toggle_copy.animate_circle()
        self.on_toggle_copy(self.toggle_copy.is_checked)

        self.source_toggle.is_checked = data.get('local_source_flag', False)
        self.source_toggle.animate_circle()
        self.on_toggle_source(self.source_toggle.is_checked)
        self.local_image_folder = data.get('local_source_folder', '')
        if self.local_image_folder:
            self.source_helper.setHelpText(self.source_helper.helptext + '\n' + f'当前卡图来源:{self.local_image_folder}')
            self.info_fetcher.local_image_source = self.local_image_folder

        self.toggle_corner.is_checked = data.get('round_corner', False)
        self.toggle_corner.animate_circle()
        self.on_toggle_corner(self.toggle_corner.is_checked)

        self.detail_custom_edit.setText(data.get('detail_custom_text', ''))
        self.detail_custom_toggle.is_checked = data.get('detail_custom_toggle', False)
        self.detail_custom_toggle.animate_circle()
        self.detail_custom_cliked(self.detail_custom_toggle.is_checked)
        self.attr_hide_toggle.is_checked = data.get('attr_hide', True)
        self.attr_hide_toggle.animate_circle()
        self.show_hide_attr(self.attr_hide_toggle.is_checked)

        self.full_effect_toggle.is_checked = data.get('full_effect', False)
        self.full_effect_toggle.animate_circle()
        self.full_effect_clicked()

        for btn in self.color_btn_list:
            btn.hide_ring()
        for btn in self.color_advanced_list:
            btn.hide_ring()
        self.color_flag = data.get('color_flag', False)
        title_color = data.get('title_color', [0, 0, 0])
        self.title_color = QColor(title_color[0], title_color[1], title_color[2])
        self.color_advanced_btn.is_checked = data.get('color_advanced_activated', False)
        self.color_advanced_btn.animate_circle()
        self.change_color_mode(self.color_advanced_btn.is_checked)
        self.mix_mode_flag = data.get('mix_mode_flag', False)
        self.color_option = data.get('color_option', 0)
        self.mix_option = data.get('mix_option', 0)


        if self.color_flag:
            if self.mix_mode_flag:
                self.color_advanced_list[self.mix_option].display_ring()

                self.outline_enabled, self.outline_enabled_c = data.get('outline_enabled', False), data.get('outline_enabled_c', False)
                color = data.get('outline_color', [0, 0, 0])
                self.outline_color = QColor(color[0], color[1], color[2])
                color = data.get('outline_color_c', [0, 0, 0])
                self.outline_color_c = QColor(color[0], color[1], color[2])
                self.outline_thickess, self.outline_thickess_c = data.get('outline_thickess', 1), data.get('outline_thickess_c', 1)
                self.shadow_flag, self.shadow_flag_c = data.get('shadow_flag', False), data.get('shadow_flag_c', False)
                self.shadow_blur_size, self.shadow_blur_size_c = data.get('shadow_blur_size', 1), data.get('shadow_blur_size_c', 1)
                self.shadow_x_offset, self.shadow_x_offset_c = data.get('shadow_x_offset', 0), data.get('shadow_x_offset_c', 0)
                self.shadow_y_offset, self.shadow_y_offset_c = data.get('shadow_y_offset', 0), data.get('shadow_y_offset_c', 0)
                self.gradient_flag, self.gradient_flag_c = data.get('gradient_flag', False), data.get('gradient_flag', False)
                color = data.get('single_color')
                self.single_color = QColor(color[0], color[1], color[2])
                color = data.get('single_color_c')
                self.single_color_c = QColor(color[0], color[1], color[2])

                flag = data.get('gradient_process_flag', [True, True, True, True, True, True])
                pos = data.get('gradient_process_pos', [0, 0.2, 0.4, 0.6, 0.8, 1])
                r = data.get('gradient_process_r', [0, 0, 0, 0, 0, 0])
                g = data.get('gradient_process_g', [0, 0, 0, 0, 0, 0])
                b = data.get('gradient_process_b', [0, 0, 0, 0, 0, 0])
                self.gradient_process = [[flag[i], pos[i], QColor(r[i], g[i], b[i])] for i in range(6)]

                flag = data.get('gradient_process_flag_c', [True, True, True, True, True, True])
                pos = data.get('gradient_process_pos_c', [0, 0.2, 0.4, 0.6, 0.8, 1])
                r = data.get('gradient_process_r_c', [0, 0, 0, 0, 0, 0])
                g = data.get('gradient_process_g_c', [0, 0, 0, 0, 0, 0])
                b = data.get('gradient_process_b_c', [0, 0, 0, 0, 0, 0])
                self.gradient_process_c = [[flag[i], pos[i], QColor(r[i], g[i], b[i])] for i in range(6)]

                self.update_mix_param()
            else:

                self.color_btn_list[self.color_option].display_ring()
        self.update_card_name()

        self.name_align_selector.setCurrentIndex(data.get('name_align', 0))
        self.text_align_selector.setCurrentIndex(data.get('text_align', 0))

        if card_image is not None:
            self.card_img = card_image
        else:
            image_data = base64.b64decode(data['image'])
            self.card_img = Image.open(io.BytesIO(image_data))
        if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
            self.transform_LB_img()
        else:
            self.transform_normal_img()

        self.overframe_toggle.is_checked = data.get('overframe', False)
        self.overframe_toggle.animate_circle()
        self.overframe_toggle_change(self.overframe_toggle.is_checked)
        if self.overframe_toggle.is_checked:
            self.overframe_scale = data.get('overframe_scale', 1000)
            self.overframe_sizex = data.get('overframe_sizex', 0)
            self.overframe_sizey = data.get('overframe_sizey', 0)
            self.overframe_posx = data.get('overframe_posx', 0)
            self.overframe_posy = data.get('overframe_posy', 0)
            overframe_image_data = base64.b64decode(data['overframe_image'])
            self.overframe_img = Image.open(io.BytesIO(overframe_image_data))

            w, h = int(self.overframe_sizex * self.overframe_scale / 1000), int(self.overframe_sizey * self.overframe_scale / 1000)
            self.of_display_img = self.overframe_img.resize((w, h), Image.Resampling.LANCZOS)
            self.of_display_img = pillow_img_to_pixmap(self.of_display_img)
            self.overframe_item.setPixmap(self.of_display_img)
            self.overframe_item.setPos(self.overframe_posx, self.overframe_posy)
        else:
            self.reset_overframe_image(data)

        # 卡名默认色按召唤法定（超量 / 连接 / 暗黑同调为白）。上面用文件里存的 title_color
        # 无条件覆盖了一次，而存的默认值就是黑色——用户没手动选过颜色时按卡片类型重算。
        if not self.color_flag and self.card_type == '怪兽卡':
            self.update_detail_info()
        free_text._ensure_free_text(self)
        free_text._apply_free_text_data(self, data)

    def reset_overframe_image(self, data):
        """导入一张超框关闭的卡后，让超框图回到这张卡自己的状态。

        否则 overframe_img 和预览里还是上一张卡的图：在这张卡上打开开关会显示别的卡的超框图，
        导出时还会把它存进这张卡。数据里留着自己的超框图（关掉开关后的快速快照会保留）就载回它，
        否则清空。"""
        image = None
        encoded = data.get('overframe_image')
        if isinstance(encoded, str) and encoded:
            try:
                image = Image.open(io.BytesIO(base64.b64decode(encoded)))
                image.load()
            except Exception:
                image = None
        if image is None:
            self.overframe_img = None
            self.overframe_scale = 1000
            self.overframe_sizex = self.overframe_sizey = 0
            self.overframe_posx = self.overframe_posy = 0
            self.overframe_item.setPixmap(QPixmap())
            self.overframe_item.setPos(0, 0)
            return
        self.overframe_img = image
        self.overframe_scale = data.get('overframe_scale', 1000)
        self.overframe_sizex = data.get('overframe_sizex', 0)
        self.overframe_sizey = data.get('overframe_sizey', 0)
        self.overframe_posx = data.get('overframe_posx', 0)
        self.overframe_posy = data.get('overframe_posy', 0)
        width = max(1, int(self.overframe_sizex * self.overframe_scale / 1000))
        height = max(1, int(self.overframe_sizey * self.overframe_scale / 1000))
        display = image.resize((width, height), Image.Resampling.LANCZOS)
        self.overframe_item.setPixmap(pillow_img_to_pixmap(display.convert('RGBA')))
        self.overframe_item.setPos(self.overframe_posx, self.overframe_posy)

    def on_save_image(self):
        if self.output_name == 0:
            card_name = clean_filename(self.card_name_edit.text())
        else:
            card_name = remove_leading_zeros(self.card_pass_edit.text())
        card_name = remove_annotation(card_name)
        if self.output_format == 0:
            file_name, _ = QFileDialog.getSaveFileName(self, '保存结果', os.path.join(self.save_dir, card_name),
                'Image Files (*.png)')
        else:
            file_name, _ = QFileDialog.getSaveFileName(self, '保存结果', os.path.join(self.save_dir, card_name),
                'Image Files (*.jpg)')
        if file_name:
            self.save_dir = os.path.dirname(file_name)
            self.save_image(file_name)

    def save_image(self, file_name=''):
        if manga._manga_save_image(self, file_name):  # 漫画卡模式导出漫画卡
            return
        if not file_name:
            return
        if self.mix_mode_flag and self.shadow_flag:
            for i in range(self.config.NAME_LIST_LEN):
                self.new_shadow_list[i] = QGraphicsDropShadowEffect()
                self.new_shadow_list[i].setColor(self.shadow_color)
                if self.HD_card_img:
                    self.new_shadow_list[i].setBlurRadius(self.shadow_blur_size * 2)
                    self.new_shadow_list[i].setXOffset(self.shadow_x_offset * 2)
                    self.new_shadow_list[i].setYOffset(self.shadow_y_offset * 2)
                else:
                    self.new_shadow_list[i].setBlurRadius(self.shadow_blur_size)
                    self.new_shadow_list[i].setXOffset(self.shadow_x_offset)
                    self.new_shadow_list[i].setYOffset(self.shadow_y_offset)
            self.update_card_name()

        original_size = QSize(int(self.card_rect.width()), int(self.card_rect.height()))
        res_size = original_size * 2 if self.HD_card_img else original_size
        image = QPixmap(res_size)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self.card_img_item.setVisible(False)
        self.parent_app.scene.render(painter, QRectF(image.rect()), self.parent_app.scene.sceneRect())
        painter.end()
        res_img = None

        if self.current_template == 0 or self.info_selector_left.currentText() in ('巨神兵', '天空龙', '翼神龙'):
            card_x = self.config.ocard_x
            card_y = self.config.ocard_y
            card_img_size = self.ocard_img_size
        else:
            card_x = self.config.card_x
            card_y = self.config.card_y
            card_img_size = self.card_img_size
        if self.HD_card_img:
            combine = QPixmap(QSize(int(self.card_rect.width()) * 2, int(self.card_rect.height()) * 2))
            combine.fill(Qt.transparent)
            painter = QPainter(combine)
            if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
                card_img = None
                if self.LB_ratio == 0:
                    card_img = apply_fade_to_alpha(crop_square_image(self.card_img), fade_ratio=0.02)
                    card_img = card_img.resize((self.LB_img_size.width() * 2, self.LB_img_size.width() * 2), Image.Resampling.LANCZOS)
                else:
                    card_img = self.card_img.resize((self.LB_img_size.width() * 2, self.LB_img_size.height() * 2), Image.Resampling.LANCZOS)
                card_img = pillow_img_to_pixmap(card_img)
                painter.drawPixmap(self.config.LB_x * 2, self.config.LB_y * 2, card_img)
            else:
                card_img = self.card_img.resize((card_img_size.width() * 2, card_img_size.height() * 2), Image.Resampling.LANCZOS)
                card_img = pillow_img_to_pixmap(card_img)
                painter.drawPixmap(card_x * 2, card_y * 2, card_img)
            painter.drawPixmap(0, 0, image)
            painter.end()
            res_img = combine
        else:
            combine = QPixmap(QSize(int(self.card_rect.width()), int(self.card_rect.height())))
            combine.fill(Qt.transparent)
            painter = QPainter(combine)
            if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
                card_img = None
                if self.LB_ratio == 0:
                    card_img = apply_fade_to_alpha(crop_square_image(self.card_img), fade_ratio=0.02)
                    card_img = card_img.resize((self.LB_img_size.width(), self.LB_img_size.width()), Image.Resampling.LANCZOS)
                else:
                    card_img = self.card_img.resize((self.LB_img_size.width(), self.LB_img_size.height()), Image.Resampling.LANCZOS)
                card_img = pillow_img_to_pixmap(card_img)
                painter.drawPixmap(self.config.LB_x, self.config.LB_y, card_img)
            else:
                card_img = self.card_img.resize((card_img_size.width(), card_img_size.height()), Image.Resampling.LANCZOS)
                card_img = pillow_img_to_pixmap(card_img)
                painter.drawPixmap(card_x, card_y, card_img)
            painter.drawPixmap(0, 0, image)
            painter.end()
            res_img = combine
            pass
        if self.output_format == 0:
            res_img.save(file_name, format='PNG')
        else:
            res_img.save(file_name, format='JPG')
        self.card_img_item.setVisible(True)
        self.update_mix_param()
        self.update_card_name()

    def on_batch_clicked(self):
        dialog = BatchDialog(self)
        dialog.exec_()
        pass

    def on_output_setting(self):
        HD_img = 1 if self.HD_card_img else 0
        dialog = OutputSettingDialog(HD_img=HD_img, format=self.output_format, name=self.output_name, parent=self)
        if dialog.exec_():
            self.HD_card_img = True if dialog.HD_img == 1 else False
            self.output_format = dialog.format
            self.output_name = dialog.name
        pass

    def update_shadow_ratio(self):
        W, H = int(self.card_rect.width()), int(self.card_rect.height())
        card_hw_ratio = 1.0 * H / W
        view_width = self.parent_app.view.width()
        view_height = self.parent_app.view.height()
        view_hw_ratio = 1.0 * view_height / view_width
        if view_hw_ratio >= card_hw_ratio:
            self.shadow_vis_ratio = 1.0 * view_width / W
        else:
            self.shadow_vis_ratio = 1.0 * view_height / H
        pass
    pass
