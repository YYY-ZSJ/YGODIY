import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QGraphicsPixmapItem, QFileDialog, QColorDialog, QComboBox, QToolTip, QLabel, QSizePolicy, QSpacerItem, QGraphicsDropShadowEffect, QSlider


from PyQt5.QtGui import QPixmap, QFont, QFontDatabase, QColor, QPainter, QTextOption, QIcon, QTextCursor, QTextBlockFormat, QFontMetricsF, QRegularExpressionValidator, QFontMetrics, QPen

from PyQt5.QtCore import Qt, QRect, QRectF, QPointF, QRegularExpression, QSize, QThreadPool, QPoint
from PyQt5.QtSvg import QGraphicsSvgItem, QSvgRenderer
from customComponents import make_symbol_bar, Worker, AttributeButton, StarButton, CloseButton, LinkButton, ColorButton, CustomTextEdit, CustomLineEdit, CropDialog, ToggleButton, RoundedButton, ColorAdvancedDialog, HelpButton, BatchDialog, RoundedPixmapItem, OutputSettingDialog, HollowHandleStyle, NameSearchDialog


from infoFetcher import InfoFetcher
from mixTextItem import MixTextItem
from PIL import Image
from config import PastConfig
import json
import numpy as np
import requests
from opencc import OpenCC
import io
import base64
from utils import clean_filename, remove_leading_zeros, pillow_img_to_pixmap, qpixmap_to_pillow, rpath, crop_square_image, apply_fade_to_alpha, decrypt_image_qpixmap, runtime_resource_exists

import card_library
import customization
import editor_setup
import free_text
import language_switch
import rarity

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import YuGiOhApp


class PastWidget(QWidget):
    def __init__(self, parent: 'YuGiOhApp' = None):
        super().__init__()
        with open(rpath('config/past_config.json'), 'r', encoding='utf-8') as config_file:
            config_dict = json.load(config_file)
        self.config = PastConfig(**config_dict)

        self.parent_app = parent
        self.past_layout = QVBoxLayout()

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
        self.template_selector.addItems(['第1期', '第2期', '第3期', '第7期', '第8期', '第9期', '第10期'])
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
        self.lan_selector.addItems(['简体中文', '繁体中文', '日文', '日文注音', '英文'])
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
        self.load_image_button_nocrop = QPushButton('上传卡图(不裁剪)', self)
        self.load_image_button_nocrop.clicked.connect(self.load_image_nocrop)
        self.load_image_button_crop = QPushButton('上传卡图(裁剪)', self)
        self.load_image_button_crop.clicked.connect(self.load_image_crop)
        self.upload_btn_hbox.addWidget(self.load_image_button_nocrop)
        self.upload_btn_hbox.addWidget(self.load_image_button_crop)


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
        self.detail_custom_edit.setMaxLength(50)
        self.detail_custom_hbox.addWidget(self.detail_custom_label)
        self.detail_custom_hbox.addWidget(self.detail_custom_toggle)
        self.detail_custom_hbox.addWidget(self.detail_custom_edit)

        self.attr_effect_hbox = QHBoxLayout()
        self.attr_hide_label = QLabel('属性显示', self)
        self.attr_hide_toggle = ToggleButton(check=True, on_color=QColor(0, 0, 0), height=20, width=42)
        self.attr_hide_toggle.toggled.connect(self.show_hide_attr)
        self.only_image_label = QLabel('仅卡图', self)
        self.only_img_toggle = ToggleButton(check=False, on_color=QColor(0, 0, 0), height=20, width=42)
        self.only_img_toggle.toggled.connect(self.frame_status_update)
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
        self.dark_btn = AttributeButton('暗', 35, 25, color=self.attribute_off_colors['暗'])
        self.wind_btn = AttributeButton('风', 35, 25, color=self.attribute_off_colors['风'])
        self.water_btn = AttributeButton('水', 35, 25, color=self.attribute_off_colors['水'])
        self.fire_btn = AttributeButton('炎', 35, 25, color=self.attribute_off_colors['炎'])
        self.ground_btn = AttributeButton('地', 35, 25, color=self.attribute_on_colors['地'])
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
            pass
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

        font = self.font()
        metric = QFontMetrics(font)
        level_label_width = metric.width('等级 10 ')
        self.level_label = QLabel('等级 2 ', self)
        self.level_label.setFixedWidth(level_label_width)
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
        self.rank_label.setFixedWidth(level_label_width)
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
        self.LB_ratio_selector.setEnabled(False)
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
        self.ATK_edit.setMaxLength(4)
        self.ATK_edit.setText(self.config.demo_atk)
        self.ATK_edit.textChanged.connect(self.update_ATK)
        self.ATK_hbox.addWidget(self.ATK_label)
        self.ATK_hbox.addWidget(self.ATK_edit)

        self.DEF_hbox = QHBoxLayout()
        self.DEF_label = QLabel('防御', self)
        self.DEF_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.DEF_edit = CustomLineEdit()
        self.DEF_edit.setPlaceholderText('DEF')
        self.DEF_edit.setMaxLength(4)
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
        self.ATK_DEF_type_toggle.setEnabled(False)

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
        self.holo_label.setEnabled(False)
        self.holo_selector.setEnabled(False)

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

        water_list = ['无', '20th', '25th', 'sample', 'sample2', 'star', 'DIY', '10000']
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
        self.rare_label.setEnabled(False)
        self.rare_selector.setEnabled(False)
        self.water_label.setEnabled(False)
        self.water_selector.setEnabled(False)


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
        self.toggle_holo.setEnabled(False)
        self.label3.setEnabled(False)
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


        self.past_layout.addLayout(self.name_type_hbox)
        self.past_layout.addLayout(self.lan_tran_hbox)
        self.past_layout.addLayout(self.color_vbox)
        self.past_layout.addLayout(self.upload_btn_hbox)
        self.past_layout.addLayout(self.detail_info_hbox)
        self.past_layout.addLayout(self.monster_info_hbox)
        self.past_layout.addLayout(self.attribute_hbox)
        self.past_layout.addLayout(self.level_box)
        self.past_layout.addLayout(self.rank_box)
        self.past_layout.addLayout(self.ATK_DEF_hbox)
        self.past_layout.addLayout(self.LB_info_hbox)
        self.past_layout.addWidget(self.LB_text_edit)
        # 效果文本框正上方的特殊符号快捷按钮（「」 ①…⑤ ●）
        self._symbol_bar, self._symbol_watcher = make_symbol_bar(self, self.text_input, (self.LB_text_edit,))
        self.past_layout.addWidget(self._symbol_bar)
        self.past_layout.addWidget(self.text_input)
        self.past_layout.addLayout(self.text_ctrl_hbox)
        self.past_layout.addLayout(self.card_info_hbox)
        self.past_layout.addLayout(self.align_box)
        self.past_layout.addLayout(self.hcrw_hbox)
        self.past_layout.addLayout(self.source_load_hbox)
        self.past_layout.addLayout(self.toggle_hbox)
        self.past_layout.addLayout(self.save_hbox)
        self.past_layout.setContentsMargins(0, 5, 0, 0)
        self.setLayout(self.past_layout)
        editor_setup._setup_past_editor(self)
        rarity._add_extra_rarity_grades(self, ('PSER2',))
        free_text._install_free_text_button(self)
        customization._install_customization_controls(self)
        language_switch._setup_language_translation(self)

    def init_vis(self):
        if self.check_resource():
            self._init_vis_items()
        else:
            self.parent_app.show_warning_message(mess='旧版卡')
        free_text._ensure_free_text(self)

    def _init_vis_items(self):
        self.template_index = 0
        self.upload_dir = ''
        self.save_dir = os.getcwd()
        self.language = '简体中文'
        self.card_type = '怪兽卡'
        self.offical_cn = False
        self.card_pass_list = None
        self.t2s_converter = OpenCC('t2s')
        self.cn_ATK_DEF_flag = False

        self.title_color = QColor(Qt.black)
        self.color_flag = False

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

        self.threadpool = QThreadPool()
        self.info_fetcher = InfoFetcher()

        self.name_width = self.config.NAME_WIDTH[self.template_index]

        self.card_rect = QRectF(QRect(0, 0, self.config.card_rect_w, self.config.card_rect_h))

        self.card_img = Image.open(rpath(self.config.demo_show_img)).convert('RGBA')
        self.display_img = self.card_img.resize((self.config.card_img_size_w[self.template_index],
            self.config.card_img_size_h[self.template_index]), Image.Resampling.LANCZOS)
        self.display_img = pillow_img_to_pixmap(self.display_img)

        self.HD_card_img = False
        self.card_img_item = QGraphicsPixmapItem(self.display_img)
        self.card_img_item.setPos(self.config.card_x[self.template_index], self.config.card_y[self.template_index])
        self.parent_app.past_scene.addItem(self.card_img_item)

        self.base_item = RoundedPixmapItem(None, radius=28)
        self.parent_app.past_scene.addItem(self.base_item)

        self.anniversary_item = QGraphicsPixmapItem()
        self.parent_app.past_scene.addItem(self.anniversary_item)
        self.anniversary_item.setVisible(False)

        self.rare_item = RoundedPixmapItem(None, radius=28)
        self.parent_app.past_scene.addItem(self.rare_item)
        self.rare_item.setVisible(False)

        self.effect_frame_item = QGraphicsPixmapItem(None)
        self.parent_app.past_scene.addItem(self.effect_frame_item)

        self.current_attribute = self.config.demo_attribute
        self.attribute_size = self.config.attribute_size
        self.attr_dict = self.config.attributes_s if self.template_index in (5, 6) else self.config.attributes
        self.attribute_item = QGraphicsPixmapItem(QPixmap(rpath(self.attr_dict[self.language][self.current_attribute])))
        self.attribute_item.setPos(self.config.attribute_pos_x[self.template_index], self.config.attribute_pos_y[self.template_index])
        self.parent_app.past_scene.addItem(self.attribute_item)

        self.MT_type_item = QGraphicsSvgItem(rpath('mold/icon/magic-full-jp.svg'))
        self.MT_type_item.setPos(891, 288)
        self.MT_type_item.setScale(1.7)
        self.parent_app.past_scene.addItem(self.MT_type_item)
        self.MT_type_item.setVisible(False)

        self.icon_item = QGraphicsPixmapItem(QPixmap(rpath(self.config.icons['永续'])))
        self.icon_item.setPos(self.config.icon_pos_x[self.template_index], self.config.icon_pos_y[self.template_index])
        self.parent_app.past_scene.addItem(self.icon_item)
        self.icon_item.setVisible(False)

        self.current_level = self.config.demo_card_level
        self.current_rank = self.config.demo_card_level


        self.level_item_list = [QGraphicsPixmapItem(QPixmap(rpath(self.config.level_big_img))) for _ in range(11)]
        x, y = self.config.level_x, self.config.level_y[self.template_index]
        for i, star in enumerate(self.level_item_list, start=1):
            star.setPos(x, y)
            x -= self.config.level_inter
            self.parent_app.past_scene.addItem(star)

        self.slevel_item_list = [QGraphicsPixmapItem(QPixmap(rpath(self.config.level_img))) for _ in range(12)]
        x, y = self.config.level_sx, self.config.level_y[4]
        for i, star in enumerate(self.slevel_item_list, start=1):
            star.setPos(x, y)
            x -= self.config.slevel_inter
            self.parent_app.past_scene.addItem(star)
        self.display_level_star()

        self.twelve_level_item = [QGraphicsPixmapItem(QPixmap(rpath(self.config.level_big_img))) for _ in range(12)]
        x, y = self.config.level_12_x, self.config.level_y[self.template_index]
        for star in self.twelve_level_item:
            star.setPos(x, y)
            x -= self.config.level_inter
            self.parent_app.past_scene.addItem(star)


        self.dark_level_list = [QGraphicsPixmapItem(QPixmap(rpath(self.config.dark_big_img))) for _ in range(11)]
        x, y = self.config.rank_x, self.config.rank_y[self.template_index]
        for i, star in enumerate(self.dark_level_list, start=1):
            star.setPos(x, y)
            x += self.config.rank_inter
            self.parent_app.past_scene.addItem(star)

        self.twelve_dark_item = [QGraphicsPixmapItem(QPixmap(rpath(self.config.dark_big_img))) for _ in range(12)]
        x, y = self.config.rank_12_x, self.config.rank_y[self.template_index]
        for star in self.twelve_dark_item:
            star.setPos(x, y)
            x += self.config.rank_inter
            self.parent_app.past_scene.addItem(star)


        self.rank_item_list = [QGraphicsPixmapItem(QPixmap(rpath(self.config.rank_big_img))) for _ in range(11)]
        x, y = self.config.rank_x, self.config.rank_y[self.template_index]
        for i, star in enumerate(self.rank_item_list, start=1):
            star.setPos(x, y)
            x += self.config.rank_inter
            self.parent_app.past_scene.addItem(star)

        self.srank_item_list = [QGraphicsPixmapItem(QPixmap(rpath(self.config.rank_img))) for _ in range(12)]
        x, y = self.config.rank_sx, self.config.rank_y[4]
        for i, star in enumerate(self.srank_item_list, start=1):
            star.setPos(x, y)
            x += self.config.srank_inter
            self.parent_app.past_scene.addItem(star)

        self.twelve_rank_item = [QGraphicsPixmapItem(QPixmap(rpath(self.config.rank_big_img))) for _ in range(12)]
        x, y = self.config.rank_12_x, self.config.rank_y[self.template_index]
        for star in self.twelve_rank_item:
            star.setPos(x, y)
            x += self.config.rank_inter
            self.parent_app.past_scene.addItem(star)

        self.thirdteen_rank_item = [QGraphicsPixmapItem(QPixmap(rpath(self.config.rank_img))) for _ in range(13)]
        x, y = self.config.rank_13_x, self.config.rank_y[self.template_index]
        for star in self.thirdteen_rank_item:
            star.setPos(x, y)
            x += self.config.srank_inter
            self.parent_app.past_scene.addItem(star)

        self.hide_twelve_star()
        self.hide_dark_star()
        self.hide_twelve_dark()
        self.hide_rank_star()
        self.hide_twelve_rank()
        self.hide_thirdteen_rank()

        self.card_name_item = MixTextItem()
        self.card_name_item.setDefaultTextColor(Qt.black)
        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.card_name_font[self.language])))[0])
        font.setPixelSize(self.config.card_name_size[self.template_index][self.language])
        self.card_name_item.setFont(font)
        self.card_name_item.setPos(self.config.card_name_posx[self.template_index][self.language], self.config.card_name_posy[self.template_index][self.language])
        self.card_name_item.document().setDocumentMargin(self.config.card_name_margin)
        self.card_name_item.setTextWidth(self.name_width + 2 * self.config.card_name_margin)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.card_name_item.document().setDefaultTextOption(text_option)
        self.parent_app.past_scene.addItem(self.card_name_item)

        self.card_name_list = [MixTextItem('') for _ in range(self.config.NAME_LIST_LEN)]
        for i in range(self.config.NAME_LIST_LEN):
            self.card_name_list[i].setVisible(False)
            self.card_name_list[i].setDefaultTextColor(Qt.black)
            self.card_name_list[i].document().setDocumentMargin(self.config.card_name_margin)
            self.parent_app.past_scene.addItem(self.card_name_list[i])

        self.mix_name_item = MixTextItem(duplicate=True)
        self.mix_name_item.setDefaultTextColor(Qt.transparent)
        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.card_name_font[self.language])))[0])
        font.setPixelSize(self.config.card_name_size[self.template_index][self.language])
        self.mix_name_item.setFont(font)
        self.mix_name_item.setPos(self.config.card_name_posx[self.template_index][self.language], self.config.card_name_posy[self.template_index][self.language])
        self.mix_name_item.document().setDocumentMargin(self.config.card_name_margin)
        self.mix_name_item.setTextWidth(self.name_width + 2 * self.config.card_name_margin)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignLeft)
        self.mix_name_item.document().setDefaultTextOption(text_option)
        self.parent_app.past_scene.addItem(self.mix_name_item)
        self.mix_name_item.setVisible(False)

        self.mix_name_list = [MixTextItem(duplicate=True) for _ in range(self.config.NAME_LIST_LEN)]
        for i in range(self.config.NAME_LIST_LEN):
            self.mix_name_list[i].setVisible(False)
            self.mix_name_list[i].setDefaultTextColor(Qt.transparent)
            self.mix_name_list[i].document().setDocumentMargin(self.config.card_name_margin)
            self.parent_app.past_scene.addItem(self.mix_name_list[i])

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


        self.ATK_DEF_item = QGraphicsSvgItem(rpath(self.config.ATK_DEF_svg))
        self.ATK_DEF_item.setPos(self.config.ATK_DEF_pos_x[self.template_index], self.config.ATK_DEF_pos_y[self.template_index])
        self.ATK_DEF_item.setScale(self.config.ATK_DEF_scale[self.template_index])
        self.parent_app.past_scene.addItem(self.ATK_DEF_item)
        self.ATK_DEF_item.setVisible(False)

        self.ATK_LINK_item = QGraphicsSvgItem(rpath(self.config.ATK_LINK_svg))
        self.ATK_LINK_item.setPos(127, 2154)
        self.ATK_LINK_item.setScale(1.165)
        self.parent_app.past_scene.addItem(self.ATK_LINK_item)
        self.ATK_LINK_item.setVisible(False)

        self.ATK_label_item = QGraphicsSvgItem(rpath(self.config.ATK_label_path[0]))
        self.DEF_label_item = QGraphicsSvgItem(rpath(self.config.DEF_label_path[0]))
        self.ATK_label_item.setPos(self.config.ATK_label_posx[0], self.config.ATK_label_posy[0])
        self.DEF_label_item.setPos(self.config.DEF_label_posx[0], self.config.DEF_label_posy[0])
        self.ATK_label_item.setScale(self.config.ATK_DEF_label_scale[0])
        self.DEF_label_item.setScale(self.config.ATK_DEF_label_scale[0])
        self.parent_app.past_scene.addItem(self.ATK_label_item)
        self.parent_app.past_scene.addItem(self.DEF_label_item)

        ATK_DEF_font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.ATK_DEF_font_path[self.template_index])))[0])
        ATK_DEF_font.setPixelSize(self.config.ATK_DEF_font_size[self.template_index])

        self.ATK_number_item = MixTextItem('')
        self.ATK_number_item.setDefaultTextColor(Qt.black)
        self.ATK_number_item.setFont(ATK_DEF_font)
        self.ATK_number_item.document().setDocumentMargin(0)
        self.ATK_number_item.setTextWidth(self.config.ATK_DEF_number_width)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.ATK_number_item.document().setDefaultTextOption(text_option)
        self.ATK_number_item.setPos(self.config.ATK_number_x[self.template_index], self.config.ATK_number_y[self.template_index])
        self.parent_app.past_scene.addItem(self.ATK_number_item)

        self.DEF_number_item = MixTextItem('')
        self.DEF_number_item.setDefaultTextColor(Qt.black)
        self.DEF_number_item.setFont(ATK_DEF_font)
        self.DEF_number_item.document().setDocumentMargin(0)
        self.DEF_number_item.setTextWidth(self.config.ATK_DEF_number_width)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.DEF_number_item.document().setDefaultTextOption(text_option)
        self.DEF_number_item.setPos(self.config.DEF_number_x[self.template_index], self.config.DEF_number_y[self.template_index])
        self.parent_app.past_scene.addItem(self.DEF_number_item)


        self.detail_info_item = MixTextItem('')
        self.detail_info_item.enableOutline(False)
        self.detail_info_item.setDefaultTextColor(Qt.black)
        info_font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.detail_info_font[self.language])))[0])
        info_font.setPixelSize(self.config.detail_size[self.template_index][self.language])
        self.detail_info_item.setFont(info_font)
        self.detail_info_item.setPos(self.config.detail_posx[self.template_index][self.language],
            self.config.detail_posy[self.template_index][self.language])
        self.detail_info_item.document().setDocumentMargin(self.config.detail_margin)
        self.parent_app.past_scene.addItem(self.detail_info_item)

        self.detail_list = [MixTextItem('') for _ in range(max(self.config.detail_list_len))]
        for i in range(self.config.detail_list_len[self.template_index]):
            self.detail_list[i].setVisible(False)
            self.detail_list[i].setDefaultTextColor(Qt.black)
            self.detail_list[i].document().setDocumentMargin(self.config.detail_margin)
            self.parent_app.past_scene.addItem(self.detail_list[i])


        self.text_item = MixTextItem('')
        self.text_item.setDefaultTextColor(Qt.black)
        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.text_item_font[self.language])))[0])
        font.setPixelSize(self.config.text_size[self.language])
        self.text_item.setFont(font)

        self.rect_width = self.config.rect_width_monster[self.template_index] + 2 * self.config.text_margin
        self.rect_height = {'怪兽卡': self.config.rect_height_monster[self.template_index] + 2 * self.config.text_margin,
            '魔法卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin,
            '陷阱卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin}
        self.rect_pos = {'怪兽卡': (self.config.rect_pos_monster_x[self.template_index] - self.config.text_margin,
            self.config.rect_pos_monster_y[self.template_index] - self.config.text_margin),
            '魔法卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
            self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin),
            '陷阱卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
            self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin)}
        self.text_display_rect = QRectF(self.rect_pos['怪兽卡'][0], self.rect_pos['怪兽卡'][1],
            self.rect_width, self.rect_height['怪兽卡'])
        self.text_line_num = self.config.text_line_num[self.template_index]
        self.text_item.setTextWidth(self.rect_width)
        self.text_item.setPos(self.rect_pos['怪兽卡'][0], self.rect_pos['怪兽卡'][1])
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignJustify)
        self.text_item.document().setDefaultTextOption(text_option)
        self.text_item.document().setDocumentMargin(self.config.text_margin)
        self.parent_app.past_scene.addItem(self.text_item)


        self.lb_text_item = MixTextItem('')
        self.lb_text_item.setDefaultTextColor(Qt.black)
        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.text_item_font[self.language])))[0])
        font.setPixelSize(self.config.lb_text_size[self.language])
        self.lb_text_item.setFont(font)

        self.lb_text_height, self.lb_text_width = (self.config.lb_text_height + 2 * self.config.text_margin,
            self.config.lb_text_width + 2 * self.config.text_margin)
        self.lb_text_x, self.lb_text_y = (self.config.lb_text_x - self.config.text_margin,
            self.config.lb_text_y - self.config.text_margin)
        self.lb_text_item.setTextWidth(self.lb_text_width)
        self.lb_text_item.setPos(self.lb_text_x, self.lb_text_y)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignJustify)
        self.lb_text_item.document().setDefaultTextOption(text_option)
        self.lb_text_item.document().setDocumentMargin(self.config.text_margin)
        self.lb_text_rect = QRectF(self.lb_text_x, self.lb_text_y, self.lb_text_width, self.lb_text_height)
        self.parent_app.past_scene.addItem(self.lb_text_item)
        self.lb_text_item.setVisible(False)


        lb_font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.ATK_DEF_font_path[6])))[0])
        lb_font.setPixelSize(self.config.lb_level_font_size)

        self.LB_level_left = MixTextItem('')
        self.LB_level_left.setDefaultTextColor(Qt.black)
        self.LB_level_left.document().setDocumentMargin(0)
        self.LB_level_left.setFont(lb_font)
        self.LB_level_left.setPos(self.config.lb_level_left_single_pos_x, self.config.lb_level_left_single_pos_y)
        self.parent_app.past_scene.addItem(self.LB_level_left)
        self.LB_level_left.setVisible(False)

        self.LB_level_right = MixTextItem('')
        self.LB_level_right.setDefaultTextColor(Qt.black)
        self.LB_level_right.document().setDocumentMargin(0)
        self.LB_level_right.setFont(lb_font)
        self.LB_level_right.setPos(self.config.lb_level_right_single_pos_x, self.config.lb_level_right_single_pos_y)
        self.parent_app.past_scene.addItem(self.LB_level_right)
        self.LB_level_right.setVisible(False)

        self.LB_ratio = 0

        self.official_link_arrows = [QGraphicsPixmapItem(decrypt_image_qpixmap(p)) for p in self.config.official_arrows]
        for item in self.official_link_arrows:
            self.parent_app.past_scene.addItem(item)
            item.setVisible(False)
        self.arrow_status_list = [False, False, False, False, False, False, False, False]

        LINK_font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(rpath(self.config.link_font_path)))[0])
        LINK_font.setPixelSize(self.config.LINK_font_size)
        LINK_font.setStretch(self.config.LINK_font_stretch)
        self.LINK_number_item = MixTextItem('')
        self.LINK_number_item.setDefaultTextColor(Qt.black)
        self.LINK_number_item.setFont(LINK_font)
        self.LINK_number_item.document().setDocumentMargin(0)
        self.LINK_number_item.setPos(self.config.LINK_number_x, self.config.LINK_number_y)
        self.LINK_number_item.setPlainText('0')
        self.parent_app.past_scene.addItem(self.LINK_number_item)
        self.LINK_number_item.setVisible(False)

        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(rpath(self.config.pass_font_path[self.template_index])))[0])
        font.setPixelSize(self.config.pass_font_size[self.template_index])
        self.card_pass_item = MixTextItem('', outline_enabled=True, outline_thickness=0.5)
        self.card_pass_item.setDefaultTextColor(Qt.black)
        self.card_pass_item.document().setDocumentMargin(0)
        self.card_pass_item.setFont(font)
        self.card_pass_item.setPos(self.config.card_pass_x[self.template_index], self.config.card_pass_y[self.template_index])
        self.parent_app.past_scene.addItem(self.card_pass_item)

        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(rpath(self.config.pass_font_path[self.template_index])))[0])
        font.setPixelSize(self.config.pack_font_size[self.template_index])
        self.card_pack_item = MixTextItem('', outline_enabled=True, outline_thickness=0.5)
        self.card_pack_item.setDefaultTextColor(Qt.black)
        self.card_pack_item.document().setDocumentMargin(0)
        self.card_pack_item.setFont(font)
        self.card_pack_item.setPos(self.config.card_pack_up_x[self.template_index], self.config.card_pack_up_y[self.template_index])
        self.card_pack_item.setTextWidth(self.config.card_pack_item_width)
        text_option = QTextOption()
        text_option.setAlignment(Qt.AlignRight)
        self.card_pack_item.document().setDefaultTextOption(text_option)
        self.parent_app.past_scene.addItem(self.card_pack_item)

        self.copyright_item = QGraphicsSvgItem(rpath(self.config.copyright_svgs_black[0]))
        self.copyright_item.setScale(self.config.copyright_scale[0])
        self.copyright_item.setPos(self.config.copyright_x[0] + self.config.copyright_x_offset, self.config.copyright_y[self.template_index])
        self.parent_app.past_scene.addItem(self.copyright_item)

        self.holo_item = QGraphicsPixmapItem(QPixmap(rpath(self.config.holos['样式一'])))
        self.holo_item.setPos(self.config.holo_x, self.config.holo_y)
        self.parent_app.past_scene.addItem(self.holo_item)
        self.holo_item.setVisible(False)


        self.watermark_item = QGraphicsPixmapItem(None)
        self.parent_app.past_scene.addItem(self.watermark_item)
        self.watermark_item.setVisible(False)

        self.race_selector.setCurrentIndex(self.config.demo_race)
        self.info_selector_left.setCurrentIndex(self.config.demo_call_way)
        self.info_selector_mid.setCurrentIndex(self.config.demo_extra1)
        self.info_selector_right.setCurrentIndex(self.config.demo_extra2)
        self.switch_info()
        self.card_name_edit.setText(self.config.demo_card_name[self.language])
        self.text_input.setText(self.config.demo_card_text[self.language])
        self.copyright_selector.setCurrentIndex(3)




        self.output_format = 0
        self.output_name = 0
        self.parent_app.past_scene.setSceneRect(self.card_rect)
        self.parent_app.Past_init = True
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

        self.rare_change()
        self.watermark_change()

        self.update_level_status()
        self.update_rank_status()
        self.copyright_change(self.copyright_selector.currentIndex())
        self.update_display_img()
        self.update_ATK_DEF_status()
        self.frame_status_update()
        self.update_link_status()
        self.update_lb_status()
        self.update_cardpack_status()
        self.update_cardpass_status()

        if self.full_effect_toggle.is_checked:
            self.rect_height = {'怪兽卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin,
                '魔法卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin,
                '陷阱卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin}
            self.rect_pos = {'怪兽卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin),
                '魔法卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin),
                '陷阱卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin)}
            self.text_line_num = self.config.text_line_num_full[self.template_index]
        else:
            self.rect_height = {'怪兽卡': self.config.rect_height_monster[self.template_index] + 2 * self.config.text_margin,
                '魔法卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin,
                '陷阱卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin}
            self.rect_pos = {'怪兽卡': (self.config.rect_pos_monster_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_monster_y[self.template_index] - self.config.text_margin),
                '魔法卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin),
                '陷阱卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin)}
            self.text_line_num = self.config.text_line_num[self.template_index]

        self.text_display_rect.setTopLeft(QPointF(self.rect_pos[selected_key][0], self.rect_pos[selected_key][1]))
        self.text_display_rect.setHeight(self.rect_height[selected_key] * 1.0)
        self.text_item.setPos(self.rect_pos[selected_key][0], self.rect_pos[selected_key][1])
        if self.card_type == '怪兽卡':
            self.text_item.setTextWidth(self.config.rect_width_monster[self.template_index] + 2 * self.config.text_margin)
        else:
            self.text_item.setTextWidth(self.config.rect_width_mt[self.template_index] + 2 * self.config.text_margin)
        self.update_text()
        if self.card_type == '怪兽卡':
            if self.MT_type_hbox.parent():
                self.past_layout.removeItem(self.MT_type_hbox)
                self.MT_type_label.setVisible(False)
                self.MT_type_selector.setVisible(False)
            self.detail_info_item.setVisible(True)
            self.reappear_monster_items()
            self.MT_type_item.setVisible(False)
            self.icon_item.setVisible(False)
            self.attribute_item.setPixmap(QPixmap(rpath(self.attr_dict[self.language][self.current_attribute])))
            self.update_detail_info()
        else:
            self.switch_base_image()
            if not self.color_flag:
                self.title_color = QColor(Qt.white)
                self.update_card_name()
            self.detail_info_item.setVisible(False)
            for i in range(len(self.detail_list)):
                self.detail_list[i].setVisible(False)

            self.hide_monster_items()
            if self.card_type == '魔法卡':
                self.attribute_item.setPixmap(QPixmap(rpath(self.attr_dict[self.language]['魔'])))
            else:
                self.attribute_item.setPixmap(QPixmap(rpath(self.attr_dict[self.language]['罠'])))

            if self.MT_type_hbox.parent() is None:
                self.past_layout.insertLayout(4, self.MT_type_hbox)
                self.MT_type_label.setVisible(True)
                self.MT_type_selector.setVisible(True)

            self.update_MT_type()
            self.MT_type_item.setVisible(True)

            self.past_layout.removeItem(self.link_vbox)
            for btn in self.link_btn_list:
                btn.setVisible(False)
            if self.LB_info_hbox.parent():
                self.past_layout.removeItem(self.LB_info_hbox)
                self.past_layout.removeWidget(self.LB_text_edit)
            self.LB_level_label.setVisible(False)
            self.LB_level_edit.setVisible(False)
            self.LB_ratio_label.setVisible(False)
            self.LB_ratio_selector.setVisible(False)
            self.LB_Zack_label.setVisible(False)
            self.LB_Zack_toggle.setVisible(False)
            self.LB_text_edit.setVisible(False)

        pass

    def switch_base_image(self):
        base_key = ''
        if self.card_type in ('魔法卡', '陷阱卡'):
            base_key = self.card_type
            if self.template_index in (0, 1):
                self.effect_frame_item.setPixmap(decrypt_image_qpixmap(self.config.MT_frame[self.template_index][self.card_type]))
        else:
            if self.detail_extra1 == '灵摆':
                if self.LB_Zack_toggle.is_checked:
                    base_key = '扎克灵摆'

                elif self.detail_call_way in ('巨神兵', '天空龙', '翼神龙'):
                    base_key = '效果灵摆'
                else:
                    base_key = f'{self.detail_call_way}灵摆'
            else:
                base_key = self.info_selector_left.currentText()
            if self.template_index in (0, 1):
                self.effect_frame_item.setPixmap(decrypt_image_qpixmap(self.config.monster_frame[self.template_index][self.info_selector_left.currentText()]))
        self.base_item.setPixmap(decrypt_image_qpixmap(self.config.base_images[self.template_selector.currentIndex()][base_key]))
        self.parent_app.view.fitInView(self.base_item.boundingRect(), Qt.KeepAspectRatio)

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

            if cur_map['通常'] in info_text_list and self.template_index in (0, 1):
                normal_index = info_text_list.index(cur_map['通常'])
                info_text_list.pop(normal_index)

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

        for i in range(self.config.detail_list_len[self.template_index]):
            self.detail_list[i].setPlainText('')
            self.detail_list[i].setVisible(False)

        detail_len = len(info_text)
        if not self.check_detail_len(info_text):
            self.detail_info_item.setTextWidth((self.config.detail_width[self.template_index][self.language] +
                2 * self.config.detail_margin))
            self.detail_info_item.setPlainText(info_text)
            fontWid = 100
            while self.count_detail_line() > 1:
                fontWid -= 1
                font = self.detail_info_item.font()
                font.setStretch(fontWid)
                self.detail_info_item.setFont(font)
                self.detail_info_item.setPlainText(info_text)

            self.detail_info_item.setVisible(False)
            font = self.detail_info_item.font()
            metrics = QFontMetricsF(font)
            text_width = metrics.width(info_text)
            remain_space = self.config.detail_width[self.template_index][self.language] - text_width
            extra_spacing = remain_space / (detail_len - 1)
            x_pos = self.config.detail_posx[self.template_index][self.language]
            for i, char in enumerate(info_text):
                self.detail_list[i].setFont(font)
                self.detail_list[i].setPos(x_pos, self.config.detail_posy[self.template_index][self.language])
                x_pos += metrics.width(char) + extra_spacing
                self.detail_list[i].setPlainText(char)
                self.detail_list[i].setVisible(True)
        else:
            self.detail_info_item.setVisible(True)

        only_img = self.only_img_toggle.is_checked
        full_effect = self.full_effect_toggle.is_checked
        detail_visible = self.template_index <= 1 and not only_img and not full_effect or self.template_index > 1 and not full_effect
        if not detail_visible:
            self.detail_info_item.setVisible(False)
            for i in range(len(self.detail_list)):
                self.detail_list[i].setVisible(False)
        pass

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

        self.update_card_name()
        self.update_level_status()
        self.update_rank_status()
        self.switch_base_image()
        self.update_ATK()
        self.update_DEF()
        self.update_display_img()
        self.update_ATK_DEF_status()
        self.frame_status_update()
        self.update_cardpass_status()
        self.update_cardpack_status()
        self.update_link_status()
        self.update_lb_status()
        if self.detail_extra1 == '灵摆':
            if not self.LB_info_hbox.parent():
                self.past_layout.insertLayout(9, self.LB_info_hbox)
                self.past_layout.insertWidget(10, self.LB_text_edit)
            self.LB_level_label.setVisible(True)
            self.LB_level_edit.setVisible(True)
            self.LB_ratio_label.setVisible(True)
            self.LB_ratio_selector.setVisible(True)
            self.LB_Zack_label.setVisible(True)
            self.LB_Zack_toggle.setVisible(True)
            self.LB_text_edit.setVisible(True)
        else:
            if self.LB_info_hbox.parent():
                self.past_layout.removeItem(self.LB_info_hbox)
                self.past_layout.removeWidget(self.LB_text_edit)
            self.LB_level_label.setVisible(False)
            self.LB_level_edit.setVisible(False)
            self.LB_ratio_label.setVisible(False)
            self.LB_ratio_selector.setVisible(False)
            self.LB_Zack_label.setVisible(False)
            self.LB_Zack_toggle.setVisible(False)
            self.LB_text_edit.setVisible(False)

        if self.detail_call_way == '超量':
            if not self.rank_box.parent():
                self.past_layout.insertLayout(7, self.rank_box)
                self.rank_label.setVisible(True)
                self.rank_zero_btn.setVisible(True)
                for btn in self.rank_star_btn_list:
                    btn.setVisible(True)
            if self.level_box.parent():
                self.past_layout.removeItem(self.level_box)
                self.level_label.setVisible(False)
                self.level_zero_btn.setVisible(False)
                for btn in self.level_star_btn_list:
                    btn.setVisible(False)
            self.DEF_edit.setEnabled(True)

        elif self.detail_call_way == '连接':

            self.DEF_edit.setDisabled(True)
            if self.level_box.parent():
                self.past_layout.removeItem(self.level_box)
                self.level_label.setVisible(False)
                self.level_zero_btn.setVisible(False)
                for btn in self.level_star_btn_list:
                    btn.setVisible(False)
            if self.rank_box.parent():
                self.past_layout.removeItem(self.rank_box)
                self.rank_label.setVisible(False)
                self.rank_zero_btn.setVisible(False)
                for btn in self.rank_star_btn_list:
                    btn.setVisible(False)
        else:
            self.DEF_edit.setEnabled(True)
            if not self.level_box.parent():
                self.past_layout.insertLayout(7, self.level_box)
                self.level_label.setVisible(True)
                self.level_zero_btn.setVisible(True)
                for btn in self.level_star_btn_list:
                    btn.setVisible(True)
            if self.rank_box.parent():
                self.past_layout.removeItem(self.rank_box)
                self.rank_label.setVisible(False)
                self.rank_zero_btn.setVisible(False)
                for btn in self.rank_star_btn_list:
                    btn.setVisible(False)

        if self.detail_call_way == '连接':
            if not self.link_vbox.parent():
                self.past_layout.insertLayout(8, self.link_vbox)
            for btn in self.link_btn_list:
                btn.setVisible(True)
        else:
            self.past_layout.removeItem(self.link_vbox)
            for btn in self.link_btn_list:
                btn.setVisible(False)

        self.rare_change()
        self.watermark_change()
        pass

    def detail_custom_cliked(self, check: bool):
        self.detail_custom_edit.setEnabled(check)
        self.update_detail_text_only()
        pass

    def hide_monster_items(self):
        boxes = [self.detail_info_hbox, self.ATK_hbox, self.DEF_hbox, self.attribute_hbox]
        for layout in boxes:
            for i in range(layout.count()):
                widget = layout.itemAt(i).widget()
                if widget:
                    widget.setVisible(False)
        self.attribute_label.setVisible(False)
        self.past_layout.removeItem(self.detail_info_hbox)
        self.past_layout.removeItem(self.ATK_DEF_hbox)
        self.past_layout.removeItem(self.attribute_hbox)

        self.level_label.setVisible(False)
        self.level_zero_btn.setVisible(False)
        for btn in self.level_star_btn_list:
            btn.setVisible(False)
        self.past_layout.removeItem(self.level_box)
        self.rank_label.setVisible(False)
        self.rank_zero_btn.setVisible(False)
        for btn in self.rank_star_btn_list:
            btn.setVisible(False)
        self.past_layout.removeItem(self.rank_box)

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
            self.past_layout.insertLayout(4, self.detail_info_hbox)
        if not self.attribute_hbox.parent():
            self.past_layout.insertLayout(6, self.attribute_hbox)
        if not self.ATK_DEF_hbox.parent():
            self.past_layout.insertLayout(7, self.ATK_DEF_hbox)

        if not self.detail_call_way == '超量':
            self.level_label.setVisible(True)
            self.level_zero_btn.setVisible(True)
            for btn in self.level_star_btn_list:
                btn.setVisible(True)
            if not self.level_box.parent():
                self.past_layout.insertLayout(7, self.level_box)
        else:
            self.rank_label.setVisible(True)
            self.rank_zero_btn.setVisible(True)
            for btn in self.rank_star_btn_list:
                btn.setVisible(True)
            if not self.rank_box.parent():
                self.past_layout.insertLayout(7, self.rank_box)

        self.ATK_DEF_type_label.setVisible(True)
        self.ATK_DEF_type_toggle.setVisible(True)

        self.detail_custom_label.setEnabled(True)
        self.detail_custom_toggle.setEnabled(True)
        self.detail_custom_edit.setEnabled(self.detail_custom_toggle.is_checked)

    def attribute_clicked(self):
        button = self.sender()
        btn_text = button.text()
        self.current_attribute = btn_text
        for k, btn in self.attribute_btn_dict.items():
            if k == btn_text:
                btn.setColor(self.attribute_on_colors[k])
            else:
                btn.setColor(self.attribute_off_colors[k])
        self.attribute_item.setPixmap(QPixmap(rpath(self.attr_dict[self.language][btn_text])))
        pass

    def attribute_update(self, attr: str):
        self.current_attribute = attr
        attr_map = self.config.attributes if self.template_index < 5 else self.config.attributes_s
        self.attribute_item.setPixmap(QPixmap(rpath(attr_map[self.language][attr])))
        for k, btn in self.attribute_btn_dict.items():
            if k == attr:
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
        self.update_level_status()
        pass

    def star_zero_clicked(self):
        self.current_level = 0
        for btn in self.level_star_btn_list:
            btn.setStarColor(self.star_undo_color)
            btn.setCircleColor(self.bg_undo_color)
        self.update_level_label()
        self.hide_level_star()
        self.hide_twelve_star()
        self.hide_dark_star()
        self.hide_twelve_dark()

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
        self.update_rank_status()

    def rank_zero_clicked(self):
        self.current_rank = 0
        for btn in self.rank_star_btn_list:
            btn.setStarColor(self.star_undo_color)
            btn.setCircleColor(self.bg_undo_color)
        self.update_rank_label()
        self.hide_rank_star()
        self.hide_twelve_rank()
        self.hide_thirdteen_rank()

    def display_level_star(self):
        for i, star in enumerate(self.level_item_list, start=1):
            star.setVisible(i <= self.current_level and self.template_index <= 3)
        for i, star in enumerate(self.slevel_item_list, start=1):
            star.setVisible(i <= self.current_level and self.template_index > 3)
        pass

    def hide_level_star(self):
        for star in self.level_item_list:
            star.setVisible(False)
        for star in self.slevel_item_list:
            star.setVisible(False)

    def display_twelve_star(self):
        for star in self.twelve_level_item:
            star.setVisible(True)
        pass

    def hide_twelve_star(self):
        for star in self.twelve_level_item:
            star.setVisible(False)

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

    def update_level_status(self):
        self.hide_level_star()
        self.hide_twelve_star()
        self.hide_dark_star()
        self.hide_twelve_dark()
        self.update_level_label()
        if self.card_type == '怪兽卡' and self.detail_call_way != '超量' and self.detail_call_way != '连接':
            if self.detail_call_way == '暗黑同调' and self.template_index == 2:
                if self.current_level == 12:
                    self.display_twelve_dark()
                else:
                    self.display_dark_star()

            elif self.template_index <= 3 and self.current_level == 12:
                self.display_twelve_star()
            else:
                self.display_level_star()
        pass

    def hide_dark_star(self):
        for star in self.dark_level_list:
            star.setVisible(False)
        pass

    def hide_twelve_dark(self):
        for star in self.twelve_dark_item:
            star.setVisible(False)

    def display_dark_star(self):
        for i, star in enumerate(self.dark_level_list, start=1):
            star.setVisible(i <= self.current_level)

    def display_twelve_dark(self):
        for star in self.twelve_dark_item:
            star.setVisible(True)

    def hide_rank_star(self):
        for star in self.rank_item_list:
            star.setVisible(False)
        for star in self.srank_item_list:
            star.setVisible(False)
        pass

    def hide_twelve_rank(self):
        for star in self.twelve_rank_item:
            star.setVisible(False)

    def hide_thirdteen_rank(self):
        for star in self.thirdteen_rank_item:
            star.setVisible(False)

    def display_rank_star(self):
        for i, star in enumerate(self.rank_item_list, start=1):
            star.setVisible(i <= self.current_rank and self.template_index <= 3)
        for i, star in enumerate(self.srank_item_list, start=1):
            star.setVisible(i <= self.current_rank and self.template_index > 3)
        pass

    def display_twelve_rank(self):
        for star in self.twelve_rank_item:
            star.setVisible(True)

    def display_thirdteen_rank(self):
        for star in self.thirdteen_rank_item:
            star.setVisible(True)

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

    def update_rank_status(self):
        self.hide_rank_star()
        self.hide_twelve_rank()
        self.hide_thirdteen_rank()
        self.update_rank_label()
        if self.card_type == '怪兽卡' and self.detail_call_way == '超量':
            if self.template_index <= 3:
                if self.current_rank == 13:
                    self.display_thirdteen_rank()
                elif self.current_rank == 12:
                    self.display_twelve_rank()
                else:
                    self.display_rank_star()

            elif self.current_rank == 13:
                self.display_thirdteen_rank()
            else:
                self.display_rank_star()
        pass

    def update_MT_type(self):
        text = self.MT_type_selector.currentText()
        svg_file = ''
        x, y = (0, 0)
        scale = 0
        if not text == '通常':
            if self.card_type == '魔法卡':
                svg_file = self.config.MT_type_full_svg[self.language][0]
                x = self.config.MT_type_full_posx_M[self.template_index][self.language]
            else:
                svg_file = self.config.MT_type_full_svg[self.language][1]
                x = self.config.MT_type_full_posx_T[self.template_index][self.language]
            self.icon_item.setPixmap(QPixmap(rpath(self.config.icons[text])))
            self.icon_item.setVisible(True)
        else:
            if self.card_type == '魔法卡':
                svg_file = self.config.MT_type_svg[self.language][0]
                x = self.config.MT_type_posx_M[self.template_index][self.language]
            else:
                svg_file = self.config.MT_type_svg[self.language][1]
                x = self.config.MT_type_posx_T[self.template_index][self.language]
            self.icon_item.setVisible(False)
        y = self.config.MT_type_posy[self.template_index][self.language]
        scale = self.config.MT_type_scale[self.template_index][self.language]

        renderer = QSvgRenderer(rpath(svg_file))
        self.MT_type_item.setSharedRenderer(renderer)
        self.MT_type_item.renderer().load(rpath(svg_file))
        self.MT_type_item.setPos(x, y)
        self.MT_type_item.setScale(scale)
        pass

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
        return language_switch._render_name_in_own_language(self, PastWidget._standard_update_card_name, args, kwargs)

    def _standard_update_card_name(self):
        if not self.color_flag:
            self.title_color = QColor(Qt.black)
            if not self.card_type == '怪兽卡':
                self.title_color = QColor(Qt.white)

            elif self.template_index <= 1:
                self.title_color = QColor(Qt.black)
            elif self.template_index == 2:
                if self.detail_call_way == '超量' or self.detail_call_way == '暗黑同调':
                    self.title_color = QColor(Qt.white)
                pass
            elif self.template_index <= 5:
                if self.detail_call_way == '超量':
                    self.title_color = QColor(Qt.white)
                pass
            else:
                if self.detail_call_way == '超量' or self.detail_call_way == '连接':
                    self.title_color = QColor(Qt.white)
                pass
            pass
        name_item = self.mix_name_item if self.mix_mode_flag else self.card_name_item
        name_list = self.mix_name_list if self.mix_mode_flag else self.card_name_list

        for i in range(self.config.NAME_LIST_LEN):
            name_list[i].setPlainText('')
            name_list[i].setVisible(False)

        card_name_posy = self.config.card_name_posy[self.template_index]
        name_item.setPos(self.config.card_name_posx[self.template_index][self.language], card_name_posy[self.language])

        zwsp = '\u200b'
        text = self.card_name_edit.text()
        if self.language == '英文':
            text = zwsp + text + zwsp
        name_len = len(text)
        if not self.check_name_len(text):
            if self.language == '英文':
                text = text[1:-1]
            name_item.setTextWidth(self.name_width + 2 * self.config.card_name_margin)
            name_item.setPlainText(text)
            fontWid = 100
            # 逐步收窄字体直到卡名挤进一行。中文字符走回退字体、不受 stretch 影响，
            # 英文模式下的中文卡名永远挤不进一行，所以收窄到底（stretch 下限）就停，
            # 之后按逐字定位排布（以前这里会死循环，程序卡死）。
            while fontWid > 0 and self.count_name_line() > 1:
                fontWid -= 1
                font = name_item.font()
                font.setStretch(fontWid)
                name_item.setFont(font)
                name_item.setPlainText(text)

            name_item.setVisible(False)
            font = name_item.font()
            metrics = QFontMetricsF(font)
            text_width = metrics.width(text)
            remain_space = self.name_width - text_width
            extra_spacing = remain_space / (name_len - 1)
            x_pos = self.config.card_name_posx[self.template_index][self.language]
            for i, char in enumerate(text):
                name_list[i].setFont(font)
                name_list[i].setPos(x_pos, card_name_posy[self.language])
                x_pos += metrics.width(char) + extra_spacing
                if self.language == '英文':
                    name_list[i].setPlainText(zwsp + char + zwsp)
                else:
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

            align = self.name_align_selector.currentIndex()
            left = self.config.card_name_posx[self.template_index][self.language]
            name_y = name_item.pos().y()
            L = self.name_width + self.config.card_name_margin * 2
            W = name_item.boundingRect().width()
            if align == 0:
                name_item.setPos(left, name_y)
            elif align == 1:
                name_item.setPos(left + (L - W) * 0.5, name_y)
            else:
                name_item.setPos(left + L - W, name_y)
        pass

    def check_name_len(self, text):
        name_item = self.mix_name_item if self.mix_mode_flag else self.card_name_item
        font = name_item.font()
        font.setStretch(100)
        name_item.setFont(font)
        name_item.setTextWidth(-1)
        name_item.setPlainText(text)
        name_item.setVisible(True)
        return name_item.boundingRect().width() <= self.name_width + 2 * self.config.card_name_margin

    def check_detail_len(self, text):
        font = self.detail_info_item.font()
        font.setStretch(100)
        self.detail_info_item.setFont(font)
        self.detail_info_item.setTextWidth(-1)
        self.detail_info_item.setPlainText(text)
        return self.detail_info_item.boundingRect().width() <= (self.config.detail_width[self.template_index][self.language] +
            2 * self.config.detail_margin)

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

    def count_detail_line(self):
        document = self.detail_info_item.document()
        layout = document.documentLayout()
        visual_lines = 0
        font_metrics = QFontMetrics(self.detail_info_item.font())
        line_height = font_metrics.lineSpacing()

        for block_num in range(document.blockCount()):
            block = document.findBlockByNumber(block_num)
            block_rect = layout.blockBoundingRect(block)
            block_height = block_rect.height()

            visual_lines += int(block_height // line_height)
        return visual_lines

    def update_text(self):
        text = self.text_input.toPlainText()
        if self.text_sizeable:
            self.set_fitin_line_height()
        else:
            self.set_line_height((self.rect_height[self.card_type] - 2 * self.config.text_margin) / self.text_line_num[self.card_type])
        if not self.check_fit_in(text):
            fontWid = 100
            while fontWid > 30 and self.text_item.boundingRect().height() > self.text_display_rect.height():
                fontWid -= 1
                font = self.text_item.font()
                font.setStretch(fontWid)
                self.text_item.setFont(font)
                self.text_item.setPlainText(text)
                if self.text_sizeable:
                    self.set_fitin_line_height()
                else:
                    self.set_line_height((self.rect_height[self.card_type] - 2 * self.config.text_margin) / self.text_line_num[self.card_type])
            if fontWid <= 30:
                fontWid = 100
                font = self.text_item.font()
                font.setStretch(fontWid)
                self.text_item.setFont(font)
                self.text_item.setPlainText(text)
        pass

    def update_lb_text(self):
        text = self.LB_text_edit.toPlainText()
        if self.text_sizeable:
            self.lb_set_fitin_line_height()
        else:
            self.set_lb_line_height((self.lb_text_height - 2 * self.config.text_margin) / self.config.lb_text_row_num)
        if not self.lb_check_fit_in(text):
            fontWid = 100
            while self.lb_text_item.boundingRect().height() > self.lb_text_rect.height():
                fontWid -= 1
                font = self.lb_text_item.font()
                font.setStretch(fontWid)
                self.lb_text_item.setFont(font)
                self.lb_text_item.setPlainText(text)
                if self.text_sizeable:
                    self.lb_set_fitin_line_height()
                else:
                    self.set_lb_line_height((self.lb_text_height - 2 * self.config.text_margin) / self.config.lb_text_row_num)
        pass

    def check_fit_in(self, text):
        font = self.text_item.font()
        font.setStretch(100)
        self.text_item.setFont(font)
        self.text_item.setPlainText(text)
        if self.text_sizeable:
            self.set_fitin_line_height()
        else:
            self.set_line_height((self.rect_height[self.card_type] - 2 * self.config.text_margin) / self.text_line_num[self.card_type])
        return self.text_item.boundingRect().height() <= self.text_display_rect.height()

    def lb_check_fit_in(self, text):
        font = self.lb_text_item.font()
        font.setStretch(100)
        self.lb_text_item.setFont(font)
        self.lb_text_item.setPlainText(text)
        if self.text_sizeable:
            self.lb_set_fitin_line_height()
        else:
            self.set_lb_line_height((self.lb_text_height - 2 * self.config.text_margin) / self.config.lb_text_row_num)
        return self.lb_text_item.boundingRect().height() <= self.lb_text_rect.height()

    def set_line_height(self, line_height):
        cursor = self.text_item.textCursor()
        cursor.select(QTextCursor.Document)
        block_format = QTextBlockFormat()
        block_format.setLineHeight(line_height, QTextBlockFormat.FixedHeight)
        cursor.setBlockFormat(block_format)

    def set_lb_line_height(self, line_height):
        cursor = self.lb_text_item.textCursor()
        cursor.select(QTextCursor.Document)
        block_format = QTextBlockFormat()
        block_format.setLineHeight(line_height, QTextBlockFormat.FixedHeight)
        cursor.setBlockFormat(block_format)

    def set_fitin_line_height(self):
        total_height = self.rect_height[self.card_type] - 2 * self.config.text_margin
        line_height = self.config.text_base_size + self.text_size_slider.value()
        line_count = total_height // line_height
        extra_space = line_height * 0.08 * (line_count - 1)
        if line_height * line_count + extra_space > total_height:
            optimized_line_height = total_height / (line_count - 1)
        else:
            optimized_line_height = total_height / line_count
        self.set_line_height(optimized_line_height)

    def lb_set_fitin_line_height(self):
        total_height = self.lb_text_height - 2 * self.config.text_margin
        line_height = self.config.lb_base_size + self.text_size_slider.value()
        line_count = total_height // line_height
        extra_space = line_height * 0.08 * (line_count - 1)
        if line_height * line_count + extra_space > total_height:
            optimized_line_height = total_height / (line_count - 1)
        else:
            optimized_line_height = total_height / line_count
        self.set_lb_line_height(optimized_line_height)


    def text_sizeable_toggle(self, checked):
        self.text_sizeable = checked
        if self.text_sizeable:
            self.text_size_slider.setEnabled(True)
            self.update_text_size()
        else:
            self.text_size_slider.setEnabled(False)
            font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
                rpath(self.config.text_item_font[self.language])))[0])
            font.setPixelSize(self.config.text_size[self.language])
            self.text_item.setFont(font)
            self.update_text()

            font.setPixelSize(self.config.lb_text_size[self.language])
            self.lb_text_item.setFont(font)
            self.update_lb_text()
        pass

    def update_text_size(self):
        change_size = self.text_size_slider.value()
        self.text_size_label.setText(str(change_size))
        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.text_item_font[self.language])))[0])
        base_size = self.config.text_size[self.language]
        font.setPixelSize(base_size + change_size)
        self.text_item.setFont(font)
        self.update_text()

        base_size = self.config.lb_text_size[self.language]
        font.setPixelSize(base_size + change_size)
        self.lb_text_item.setFont(font)
        self.update_lb_text()

    def text_weight_switch(self, checked: bool):
        self.text_weightable = checked
        self.text_weight_slider.setEnabled(checked)
        self.text_item.enableOutline(checked)

        self.detail_info_item.enableOutline(checked)
        self.update_text_weight()
        pass

    def update_text_weight(self):
        self.text_weightnum_label.setText(str(self.text_weight_slider.value()))
        weight = self.text_weight_slider.value() / 10
        if weight == 0 or self.text_weight_adjust_btn.is_checked == False:
            self.text_item.enableOutline(False)
            self.lb_text_item.enableOutline(False)
            self.detail_info_item.enableOutline(False)
        else:
            self.text_item.enableOutline(True)
            self.lb_text_item.enableOutline(True)
            self.detail_info_item.enableOutline(True)
            self.text_item.setOutlineStyle(color=Qt.black, thickness=weight)
            self.lb_text_item.setOutlineStyle(color=Qt.black, thickness=weight)
            self.detail_info_item.setOutlineStyle(color=Qt.black, thickness=weight)
        pass

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

    def change_color_mode(self, checked):
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

    def update_mix_param(self):
        self.mix_name_item.enableOutline(self.outline_enabled)
        self.mix_name_item.setOutlineStyle(self.outline_color, self.outline_thickess)
        self.mix_name_item.enableGradient(self.gradient_flag)
        self.mix_name_item.setSingleColor(self.single_color)
        self.mix_name_item.setGradientProcess(self.gradient_process)
        edge_points = self.config.gradient_edge_points[self.template_index][self.language]
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
            edge_points = self.config.gradient_edge_points[self.template_index][self.language]
            self.mix_name_list[i].setGradientEdge(edge_points[0], edge_points[1])

            self.shadow_list[i] = QGraphicsDropShadowEffect()
            self.shadow_list[i].setColor(self.shadow_color)
            self.shadow_list[i].setBlurRadius(self.shadow_blur_size * self.shadow_vis_ratio)
            self.shadow_list[i].setXOffset(self.shadow_x_offset * self.shadow_vis_ratio)
            self.shadow_list[i].setYOffset(self.shadow_y_offset * self.shadow_vis_ratio)
        pass

    def update_ATK(self):
        self.ATK_number_item.setPlainText(self.ATK_edit.text())

    def update_DEF(self):
        self.DEF_number_item.setPlainText(self.DEF_edit.text())

    def update_ATK_DEF_status(self):
        self.ATK_DEF_item.setVisible(False)
        self.ATK_LINK_item.setVisible(False)
        self.ATK_number_item.setVisible(False)
        self.DEF_number_item.setVisible(False)
        self.ATK_label_item.setVisible(False)
        self.DEF_label_item.setVisible(False)
        self.LINK_number_item.setVisible(False)
        if not self.card_type == '怪兽卡':
            return
        self.ATK_number_item.setVisible(True)
        self.DEF_number_item.setVisible(True)
        if self.template_index >= 2:
            if self.detail_call_way == '连接' and self.template_index == 6:
                self.DEF_number_item.setVisible(False)
                self.ATK_LINK_item.setVisible(True)
                self.LINK_number_item.setVisible(True)
            else:
                self.ATK_DEF_item.setVisible(True)
                self.ATK_DEF_item.setScale(self.config.ATK_DEF_scale[self.template_index])
                self.ATK_DEF_item.setPos(self.config.ATK_DEF_pos_x[self.template_index], self.config.ATK_DEF_pos_y[self.template_index])
        else:
            self.ATK_label_item.setVisible(True)
            self.DEF_label_item.setVisible(True)

            renderer1 = QSvgRenderer(rpath(self.config.ATK_label_path[self.template_index]))
            self.ATK_label_item.setSharedRenderer(renderer1)
            self.ATK_label_item.renderer().load(rpath(self.config.ATK_label_path[self.template_index]))
            self.ATK_label_item.setPos(self.config.ATK_label_posx[self.template_index], self.config.ATK_label_posy[self.template_index])
            self.ATK_label_item.setScale(self.config.ATK_DEF_label_scale[self.template_index])

            renderer2 = QSvgRenderer(rpath(self.config.DEF_label_path[self.template_index]))
            self.DEF_label_item.setSharedRenderer(renderer2)
            self.DEF_label_item.renderer().load(rpath(self.config.DEF_label_path[self.template_index]))
            self.DEF_label_item.setPos(self.config.DEF_label_posx[self.template_index], self.config.DEF_label_posy[self.template_index])
            self.DEF_label_item.setScale(self.config.ATK_DEF_label_scale[self.template_index])
            pass
        ATK_DEF_font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.ATK_DEF_font_path[self.template_index])))[0])
        ATK_DEF_font.setPixelSize(self.config.ATK_DEF_font_size[self.template_index])
        self.ATK_number_item.setFont(ATK_DEF_font)
        self.DEF_number_item.setFont(ATK_DEF_font)
        self.ATK_number_item.setPos(self.config.ATK_number_x[self.template_index], self.config.ATK_number_y[self.template_index])
        self.DEF_number_item.setPos(self.config.DEF_number_x[self.template_index], self.config.DEF_number_y[self.template_index])
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
        pass

    def display_link_arrow(self):
        self.hide_link_arrow()
        for status, item in list(zip(self.arrow_status_list, self.official_link_arrows)):
            item.setVisible(status)
        pass

    def hide_link_arrow(self):
        for item in self.official_link_arrows:
            item.setVisible(False)
        pass

    def update_link_number(self):
        num = 0
        for s in self.arrow_status_list:
            if s:
                num += 1
        self.LINK_number_item.setPlainText(f'{num}')

    def update_link_status(self):
        self.hide_link_arrow()
        self.LINK_number_item.setVisible(False)
        if self.template_index == 6 and self.card_type == '怪兽卡' and self.detail_call_way == '连接':
            self.display_link_arrow()
            self.LINK_number_item.setVisible(True)
        pass

    def on_toggle_ATK_DEF(self, checked: bool):
        self.cn_ATK_DEF_flag = checked
        if checked:
            self.ATK_DEF_item.renderer().load(rpath(self.config.ATK_DEF_svg_cn))
            self.ATK_LINK_item.renderer().load(rpath(self.config.ATK_LINK_svg_sc))
        else:
            self.ATK_DEF_item.renderer().load(rpath(self.config.ATK_DEF_svg))
            self.ATK_LINK_item.renderer().load(rpath(self.config.ATK_LINK_svg))
        pass

    def update_card_pass(self):
        text = self.card_pass_edit.text()
        self.card_pass_item.setPlainText(text)

    def on_pass_btn_clicked(self):
        if self.card_pass_edit.has_user_type:
            self.on_cardpass_return()

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
                    self.update_rank_status()
                else:
                    self.current_level = level
                    self.display_level_btn()
                    self.update_level_status()


            elif self.template_index == 6:
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

    def random_card(self):
        # 有离线卡库就从里面随机抽，不联网
        card_pass = card_library._random_card_pass()
        if card_pass is not None:
            if hasattr(self.card_pass_edit, 'has_user_type'):
                self.card_pass_edit.has_user_type = True
            self.card_pass_edit.setText(card_pass)
            return self.on_cardpass_return()
        url = 'https://gitee.com/scutlzl/game-king-card-maker/raw/master/data/cardpass_int.npy'
        if self.card_pass_list is None:
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

    def update_cardpass_status(self):
        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(rpath(self.config.pass_font_path[self.template_index])))[0])
        font.setPixelSize(self.config.pass_font_size[self.template_index])
        self.card_pass_item.setFont(font)
        if ( self.card_type == '怪兽卡' and self.detail_call_way == '超量' and
            self.detail_extra1 != '灵摆' and self.template_index >= 2):
            self.card_pass_item.setDefaultTextColor(Qt.white)
        else:
            self.card_pass_item.setDefaultTextColor(Qt.black)
        self.card_pass_item.enableOutline(self.template_index <= 1)
        self.card_pass_item.setPos(self.config.card_pass_x[self.template_index], self.config.card_pass_y[self.template_index])
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
        pass

    def update_lb_status(self):
        self.LB_level_left.setVisible(False)
        self.LB_level_right.setVisible(False)
        self.lb_text_item.setVisible(False)
        if not self.card_type == '怪兽卡' or self.template_index < 5:
            return
        if self.detail_extra1 == '灵摆':
            self.LB_level_left.setVisible(True)
            self.LB_level_right.setVisible(True)
            self.lb_text_item.setVisible(True)
        pass

    def update_card_pack(self):
        text = self.card_pack_edit.text()
        self.card_pack_item.setPlainText(text)

    def update_cardpack_status(self):
        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(rpath(self.config.pass_font_path[self.template_index])))[0])
        font.setPixelSize(self.config.pack_font_size[self.template_index])
        if self.template_index > 1:
            font.setStretch(self.config.pack_font_stretch)
        self.card_pack_item.setFont(font)
        self.card_pack_item.enableOutline(self.template_index <= 1)
        if self.template_index >= 2 and self.card_type == '怪兽卡' and self.detail_call_way == '超量' and self.detail_extra1 != '灵摆':
            self.card_pack_item.setDefaultTextColor(Qt.white)
        else:
            self.card_pack_item.setDefaultTextColor(Qt.black)

        if self.template_index >= 5 and self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
            text_option = QTextOption()
            text_option.setAlignment(Qt.AlignLeft)
            self.card_pack_item.document().setDefaultTextOption(text_option)
            self.card_pack_item.setPos(self.config.card_pack_bottom_x[self.template_index], self.config.card_pack_bottom_y[self.template_index])
        else:
            text_option = QTextOption()
            text_option.setAlignment(Qt.AlignRight)
            self.card_pack_item.document().setDefaultTextOption(text_option)
            if self.template_index == 6 and self.card_type == '怪兽卡' and self.detail_call_way == '连接':
                self.card_pack_item.setPos(self.config.card_pack_link_x[self.template_index], self.config.card_pack_link_y[self.template_index])
            else:
                self.card_pack_item.setPos(self.config.card_pack_up_x[self.template_index], self.config.card_pack_up_y[self.template_index])
        pass

    def copyright_change(self, *_args):
        # 版权下拉里有可增删的自定义项：推迟到下一轮事件循环，由 customization 判断选的是自定义项还是标准样式
        customization._defer_custom_combo_change(self, 'copyright', PastWidget._standard_copyright_change)

    def _standard_copyright_change(self, index: int):
        copyright_y = self.config.copyright_y[self.template_index]
        copyright_x = self.config.copyright_x[index]
        if self.template_index == 0:
            copyright_x += self.config.copyright_x_offset

        if self.card_type == '怪兽卡' and self.detail_call_way == '超量' and self.detail_extra1 != '灵摆' and self.template_index >= 2:
            self.copyright_item.renderer().load(rpath(self.config.copyright_svgs_white[index]))
        else:
            self.copyright_item.renderer().load(rpath(self.config.copyright_svgs_black[index]))

        self.copyright_item.setScale(self.config.copyright_scale[index])
        self.copyright_item.setPos(copyright_x, copyright_y)

        self.copyright_item.renderer().setAspectRatioMode(Qt.KeepAspectRatio)
        self.parent_app.view.update()

    def holo_change(self, *_args):
        # 防伪下拉里有可增删的自定义项：推迟到下一轮事件循环，由 customization 判断选的是自定义项还是标准样式
        customization._defer_custom_combo_change(self, 'holo', PastWidget._standard_holo_change)

    def _standard_holo_change(self):
        text = self.holo_selector.currentText()
        self.holo_item.setPixmap(QPixmap(rpath(self.config.holos[text])))
        pass

    def show_hide_attr(self, checked: bool):
        self.attribute_item.setVisible(checked)
        self.name_width = (self.config.NAME_WIDTH[self.template_index] if checked
            else self.config.NAME_FULL_WIDTH[self.template_index])
        self.update_card_name()
        pass

    def only_img_clicked(self, checked: bool):
        status = not checked
        if self.template_index == 0 or self.template_index == 1:
            self.effect_frame_item.setVisible(status)
            self.text_item.setVisible(status)
            if self.card_type == '怪兽卡':
                self.ATK_label_item.setVisible(status)
                self.DEF_label_item.setVisible(status)
                self.ATK_number_item.setVisible(status)
                self.DEF_number_item.setVisible(status)
                self.detail_info_item.setVisible(status)
                if status:
                    self.detail_info_item.setVisible(True)
                    self.update_detail_info()
                else:
                    self.detail_info_item.setVisible(False)
                    for i in range(self.config.detail_list_len[self.template_index]):
                        self.detail_list[i].setVisible(False)
        else:
            pass
        pass

    def frame_status_update(self):
        only_img = self.only_img_toggle.is_checked
        full_effect = self.full_effect_toggle.is_checked

        if not self.card_type == '怪兽卡':
            self.effect_frame_item.setVisible(self.template_index <= 1 and not only_img)
            self.text_item.setVisible(self.template_index <= 1 and not only_img or self.template_index > 1)
            self.ATK_label_item.setVisible(False)
            self.DEF_label_item.setVisible(False)
            self.ATK_number_item.setVisible(False)
            self.DEF_number_item.setVisible(False)
            self.detail_info_item.setVisible(False)
            for i in range(len(self.detail_list)):
                self.detail_list[i].setVisible(False)
            self.ATK_DEF_item.setVisible(False)
            self.ATK_LINK_item.setVisible(False)
            self.LINK_number_item.setVisible(False)
            return

        self.effect_frame_item.setVisible(self.template_index <= 1 and not only_img)
        self.text_item.setVisible(self.template_index <= 1 and not only_img or self.template_index > 1)
        self.ATK_label_item.setVisible(self.template_index <= 1 and not only_img)
        self.DEF_label_item.setVisible(self.template_index <= 1 and not only_img)
        self.ATK_number_item.setVisible(( self.template_index <= 1 and not only_img or
            self.template_index > 1 and not full_effect))
        self.DEF_number_item.setVisible(( self.template_index <= 1 and not only_img or
            self.template_index > 1 and not full_effect))
        if self.template_index == 6 and self.detail_call_way == '连接':
            self.DEF_number_item.setVisible(False)
        detail_visible = self.template_index <= 1 and not only_img and not full_effect or self.template_index > 1 and not full_effect
        if detail_visible:
            self.update_detail_text_only()
        else:
            self.detail_info_item.setVisible(False)
            for i in range(len(self.detail_list)):
                self.detail_list[i].setVisible(False)

        if self.detail_call_way == '连接':
            self.ATK_DEF_item.setVisible(self.template_index > 1 and self.template_index < 6 and not full_effect)
            self.ATK_LINK_item.setVisible(self.template_index == 6 and not full_effect)
            self.LINK_number_item.setVisible(self.template_index == 6 and not full_effect)
        else:
            self.ATK_DEF_item.setVisible(self.template_index > 1 and not full_effect)
            self.ATK_LINK_item.setVisible(False)
        pass

    def full_effect_clicked(self):
        self.frame_status_update()
        self.switch_card_type()
        pass

    def name_align_change(self):
        self.update_card_name()
        pass

    def text_align_change(self, index: int):
        text_option = QTextOption()
        if index == 0:
            text_option.setAlignment(Qt.AlignJustify)
        else:
            text_option.setAlignment(Qt.AlignCenter)
        self.text_item.document().setDefaultTextOption(text_option)
        self.lb_text_item.document().setDefaultTextOption(text_option)
        pass

    def HD_update(self, index):
        self.HD_card_img = True if index == 1 else False

    def HD_helper_clicked(self):
        QToolTip.showText(self.HD_helper.mapToGlobal(self.HD_helper.rect().topLeft() + QPoint(0, 15)),
            self.HD_helper.helptext, self)

    def switch_template(self, index: int):
        self.template_selector.setEnabled(False)
        self.template_index = index

        if self.template_index in (0, 1):
            self.effect_frame_item.setVisible(True)
        else:
            self.effect_frame_item.setVisible(False)
        self.switch_base_image()


        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.card_name_font[self.language])))[0])
        font.setPixelSize(self.config.card_name_size[self.template_index][self.language])
        self.card_name_item.setFont(font)
        self.mix_name_item.setFont(font)
        self.name_width = (self.config.NAME_WIDTH[self.template_index] if self.attr_hide_toggle.is_checked
            else self.config.NAME_FULL_WIDTH[self.template_index])
        self.update_mix_param()
        offset = 12.5 if self.template_index >= 5 else 13
        self.mix_name_item.setOffsetVer(offset)
        for item in self.mix_name_list:
            item.setOffsetVer(offset)
        self.update_card_name()


        self.attr_dict = self.config.attributes_s if self.template_index in (5, 6) else self.config.attributes
        if self.card_type == '怪兽卡':
            self.attribute_item.setPixmap(QPixmap(rpath(self.attr_dict[self.language][self.current_attribute])))
        elif self.card_type == '魔法卡':
            self.attribute_item.setPixmap(QPixmap(rpath(self.attr_dict[self.language]['魔'])))
        else:
            self.attribute_item.setPixmap(QPixmap(rpath(self.attr_dict[self.language]['罠'])))
        self.attribute_item.setPos(self.config.attribute_pos_x[self.template_index], self.config.attribute_pos_y[self.template_index])


        if self.template_index <= 3:
            x, y = self.config.level_x, self.config.level_y[self.template_index]
            for i, star in enumerate(self.level_item_list, start=1):
                star.setPos(x, y)
                x -= self.config.level_inter
            x, y = self.config.level_12_x, self.config.level_y[self.template_index]
            for star in self.twelve_level_item:
                star.setPos(x, y)
                x -= self.config.level_inter
        else:
            x, y = self.config.level_sx, self.config.level_y[self.template_index]
            for i, star in enumerate(self.slevel_item_list, start=1):
                star.setPos(x, y)
                x -= self.config.slevel_inter
        self.update_level_status()


        if self.template_index <= 3:
            x, y = self.config.rank_x, self.config.rank_y[self.template_index]
            for rank, dark in zip(self.rank_item_list, self.dark_level_list):
                rank.setPos(x, y)
                dark.setPos(x, y)
                x += self.config.rank_inter
            x, y = self.config.rank_12_x, self.config.rank_y[self.template_index]
            for rank, dark in zip(self.twelve_rank_item, self.twelve_dark_item):
                rank.setPos(x, y)
                dark.setPos(x, y)
                x += self.config.rank_inter
        else:
            x, y = self.config.rank_sx, self.config.rank_y[self.template_index]
            for i, star in enumerate(self.srank_item_list, start=1):
                star.setPos(x, y)
                x += self.config.srank_inter

        x, y = self.config.rank_13_x, self.config.rank_y[self.template_index]
        for star in self.thirdteen_rank_item:
            star.setPos(x, y)
            x += self.config.srank_inter

        self.update_rank_status()
        self.update_link_status()
        for btn in self.link_btn_list:
            btn.setEnabled(self.template_index == 6)
        self.update_lb_status()


        self.icon_item.setPos(self.config.icon_pos_x[self.template_index], self.config.icon_pos_y[self.template_index])


        self.update_ATK_DEF_status()


        info_font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.detail_info_font[self.language])))[0])
        info_font.setPixelSize(self.config.detail_size[self.template_index][self.language])
        self.detail_info_item.setFont(info_font)
        self.detail_info_item.setPos(self.config.detail_posx[self.template_index][self.language],
            self.config.detail_posy[self.template_index][self.language])
        if self.card_type == '怪兽卡':
            self.update_detail_text_only()


        self.rect_width = 2 * self.config.text_margin + ((self.config.rect_width_monster[self.template_index]
            if self.card_type == '怪兽卡' else self.config.rect_width_mt[self.template_index]))
        if self.full_effect_toggle.is_checked:
            self.rect_height = {'怪兽卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin,
                '魔法卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin,
                '陷阱卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin}
            self.rect_pos = {'怪兽卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin),
                '魔法卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin),
                '陷阱卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin)}
            self.text_line_num = self.config.text_line_num_full[self.template_index]
        else:
            self.rect_height = {'怪兽卡': self.config.rect_height_monster[self.template_index] + 2 * self.config.text_margin,
                '魔法卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin,
                '陷阱卡': self.config.rect_height_mt[self.template_index] + 2 * self.config.text_margin}
            self.rect_pos = {'怪兽卡': (self.config.rect_pos_monster_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_monster_y[self.template_index] - self.config.text_margin),
                '魔法卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin),
                '陷阱卡': (self.config.rect_pos_mt_x[self.template_index] - self.config.text_margin,
                self.config.rect_pos_mt_y[self.template_index] - self.config.text_margin)}
            self.text_line_num = self.config.text_line_num[self.template_index]
        self.text_display_rect = QRectF(self.rect_pos[self.card_type][0], self.rect_pos[self.card_type][1],
            self.rect_width, self.rect_height[self.card_type])
        self.text_item.setTextWidth(self.rect_width)
        self.text_item.setPos(self.rect_pos[self.card_type][0], self.rect_pos[self.card_type][1])
        self.update_text()


        self.copyright_change(self.copyright_selector.currentIndex())


        self.label3.setEnabled(self.template_index != 0)
        self.toggle_holo.setEnabled(self.template_index != 0)
        self.holo_item.setVisible(self.template_index != 0 and self.toggle_holo.is_checked)
        self.holo_label.setEnabled(self.template_index != 0)
        self.holo_selector.setEnabled(self.template_index != 0)


        self.update_display_img()
        self.LB_ratio_selector.setEnabled(self.template_index >= 5)


        self.update_cardpass_status()
        self.update_cardpack_status()

        self.ATK_DEF_type_toggle.setEnabled(self.template_index > 1)

        self.LB_Zack_label.setEnabled(self.template_index == 5)
        self.LB_Zack_toggle.setEnabled(self.template_index == 5)
        self.only_image_label.setEnabled(self.template_index <= 1)
        self.only_img_toggle.setEnabled(self.template_index <= 1)

        self.rare_selector.setCurrentIndex(0)
        self.water_selector.setCurrentIndex(0)
        self.water_label.setEnabled(self.template_index >= 5)
        self.water_selector.setEnabled(self.template_index >= 5)
        self.rare_label.setEnabled(self.template_index == 6)
        self.rare_selector.setEnabled(self.template_index == 6)
        self.rare_item.setVisible(False)
        self.watermark_item.setVisible(False)
        self.anniversary_item.setVisible(False)

        if self.card_type != '怪兽卡':
            self.update_MT_type()

        self.frame_status_update()
        self.template_selector.setEnabled(True)
        pass

    def update_language(self, *args, **kwargs):
        # 切换前记下各语言的文字，用户亲手切换语言时据此翻译或还原（language_switch）
        return language_switch._update_language_keeping_text(self, PastWidget._standard_update_language, args, kwargs)

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
            if self.tc_type_selector.layout() is None:
                self.lan_hbox.addWidget(self.tc_type_selector)
                self.tc_type_selector.setVisible(True)
        else:
            self.lan_hbox.removeWidget(self.tc_type_selector)
            self.tc_type_selector.setVisible(False)
        self.switch_info()


        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.card_name_font[self.language])))[0])
        font.setPixelSize(self.config.card_name_size[self.template_index][self.language])
        card_name_posy = self.config.card_name_posy[self.template_index]
        self.card_name_item.setFont(font)
        self.card_name_item.setPos(self.config.card_name_posx[self.template_index][self.language], card_name_posy[self.language])
        self.mix_name_item.setFont(font)
        self.mix_name_item.setPos(self.config.card_name_posx[self.template_index][self.language], card_name_posy[self.language])
        if self.language == '英文':
            self.mix_name_item.setOffsetFlag(True)
            for i in range(self.config.NAME_LIST_LEN):
                self.mix_name_list[i].setOffsetFlag(True)
        else:
            self.mix_name_item.setOffsetFlag(False)
            for i in range(self.config.NAME_LIST_LEN):
                self.mix_name_list[i].setOffsetFlag(False)
        edge_points = self.config.gradient_edge_points[self.template_index][self.language]
        self.mix_name_item.setGradientEdge(edge_points[0], edge_points[1])
        for i in range(self.config.NAME_LIST_LEN):
            self.mix_name_list[i].setGradientEdge(edge_points[0], edge_points[1])


        font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
            rpath(self.config.detail_info_font[self.language])))[0])
        font.setPixelSize(self.config.detail_size[self.template_index][self.language])
        self.detail_info_item.setFont(font)
        self.detail_info_item.setPos(self.config.detail_posx[self.template_index][self.language],
            self.config.detail_posy[self.template_index][self.language])


        if self.text_sizeable:
            self.update_text_size()
        else:
            font = QFont(QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(
                rpath(self.config.text_item_font[self.language])))[0])
            font.setPixelSize(self.config.text_size[self.language])
            self.text_item.setFont(font)
            self.update_text()

            font.setPixelSize(self.config.lb_text_size[self.language])
            self.lb_text_item.setFont(font)
            self.update_lb_text()

        if self.card_type != '怪兽卡':
            self.update_MT_type()
        self.update_card_name()
        self.update_detail_info()

        attri_map = self.config.attributes if self.template_index < 5 else self.config.attributes_s
        if self.card_type == '怪兽卡':
            self.attribute_item.setPixmap(QPixmap(rpath(attri_map[self.language][self.current_attribute])))
        elif self.card_type == '魔法卡':
            self.attribute_item.setPixmap(QPixmap(rpath(attri_map[self.language]['魔'])))
        else:
            self.attribute_item.setPixmap(QPixmap(rpath(attri_map[self.language]['罠'])))

        if not tc_supported:
            # 不留一个「能选但没反应」的下拉
            blocked = self.tc_type_selector.blockSignals(True)
            self.tc_type_selector.setCurrentIndex(0)
            self.tc_type_selector.blockSignals(blocked)
            self.tc_type_selector.setVisible(False)

    def update_tc_type(self):
        self.tc_type = self.tc_type_selector.currentIndex()
        self.update_language()
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

    def on_toggle_pass(self, checked: bool):
        self.card_pass_item.setVisible(checked)

    def on_toggle_pack(self, checked: bool):
        self.card_pack_item.setVisible(checked)

    def on_toggle_holo(self, checked: bool):
        self.holo_item.setVisible(checked)
        pass

    def on_toggle_corner(self, checked):
        self.base_item.set_rounded(checked)
        self.rare_item.set_rounded(checked)

    def on_toggle_copy(self, checked):
        self.copyright_item.setVisible(checked)

    def LB_ratio_changed(self, index: int):
        self.LB_ratio = index
        self.transform_LB_img()

    def LB_Zack_clicked(self):
        self.switch_base_image()

    def update_trans_type(self, index):
        if index == 0:
            self.offical_cn = False
        else:
            self.offical_cn = True
        self.info_fetcher.set_trans_type(self.offical_cn)

    def rare_change(self):
        # 罕贵度分底图和前景两层，前景压在卡面最上层（rarity）
        rarity._apply_past_rarity(self)

    def watermark_change(self):
        current_text = self.water_selector.currentText()
        if current_text == '无':
            self.watermark_item.setVisible(False)
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

    def load_image_nocrop(self):

        file_name, _ = QFileDialog.getOpenFileName(self, '选择本地图片', self.upload_dir, 'Image Files (*.png *.jpg *.bmp)')
        self.upload_dir = os.path.dirname(file_name)
        if file_name:
            self.set_card_img_nocrop(file_name)

    def set_card_img_nocrop(self, img_path):
        self.card_img = Image.open(img_path).convert('RGBA')
        if self.template_index >= 5 and self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
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
            if self.template_index >= 5 and self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
                self.transform_LB_img()
            else:
                self.transform_normal_img()
        pass

    def transform_normal_img(self):
        self.display_img = self.card_img.resize((self.config.card_img_size_w[self.template_index],
            self.config.card_img_size_h[self.template_index]), Image.Resampling.LANCZOS)
        self.display_img = pillow_img_to_pixmap(self.display_img)
        self.card_img_item.setPixmap(self.display_img)
        self.card_img_item.setPos(self.config.card_x[self.template_index], self.config.card_y[self.template_index])

    def transform_LB_img(self):
        if self.LB_ratio == 0:
            self.display_img = apply_fade_to_alpha(crop_square_image(self.card_img), fade_ratio=0.02)
            self.display_img = self.display_img.resize((self.config.LB_img_size_w[self.template_index],
                self.config.LB_img_size_w[self.template_index]), Image.Resampling.LANCZOS)
        else:
            self.display_img = self.card_img.resize((self.config.LB_img_size_w[self.template_index],
                self.config.LB_img_size_h[self.template_index]), Image.Resampling.LANCZOS)
        self.display_img = pillow_img_to_pixmap(self.display_img)
        self.card_img_item.setPixmap(self.display_img)
        self.card_img_item.setPos(self.config.LB_x[self.template_index], self.config.LB_y[self.template_index])

    def update_display_img(self):
        if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆' and self.template_index >= 5:
            self.transform_LB_img()
        else:
            self.transform_normal_img()
        pass

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

    def on_export_clicked(self):
        data = dict()

        data['name'] = self.card_name_edit.text()
        data['card_type'] = self.type_selector.currentIndex()
        data['template_index'] = self.template_selector.currentIndex()
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
        data['only_img'] = self.only_img_toggle.is_checked

        buffered = io.BytesIO()
        self.card_img.save(buffered, format='PNG')
        encoded_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
        data['image'] = encoded_image

        name = clean_filename(self.card_name_edit.text())
        name = name if name != '' else '卡片数据'

        file_name, _ = QFileDialog.getSaveFileName(self, '导出数据', os.path.join(self.save_dir, name),
            'Image Files (*.json)')
        if file_name:
            with open(file_name, 'w', encoding='utf-8') as json_file:
                free_text._inject_free_text_into_data(self, data)
                json.dump(data, json_file, ensure_ascii=False)
        pass


    def on_import_clicked(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        file_name, _ = QFileDialog.getOpenFileName(self, '选择JSON文件', '', 'JSON Files (*.json)', options=options)
        if not file_name:
            return
        with open(file_name, 'r', encoding='utf-8') as json_file:
            data = json.load(json_file)

        self.template_selector.setCurrentIndex(data.get('template_index', 0))
        self.card_name_edit.setText(data.get('name', ''))
        self.type_selector.setCurrentIndex(data.get('card_type', 0))
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
                    self.update_rank_status()
                    pass
                else:
                    self.display_level_btn()
                    self.update_level_label()
                    self.update_level_status()

                self.DEF_edit.setText(data.get('DEF', '0'))
                self.hide_link_arrow()

            elif self.template_index == 6:
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

            if self.template_index <= 1:
                self.only_img_toggle.is_checked = data.get('only_img', False)
                self.only_img_toggle.animate_circle()
                self.frame_status_update()

            if self.detail_extra1 == '灵摆' and self.template_index >= 5:
                self.LB_text_edit.setText(data.get('lb_text', ''))
                self.LB_level_edit.setText(data.get('lb_level', ''))
                self.LB_ratio_selector.setCurrentIndex(data.get('LB_ratio', 0))
                if self.template_index == 5:
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

        if self.mix_mode_flag:
            self.mix_name_item.setVisible(True)
            self.card_name_item.setVisible(False)
            for i in range(self.config.NAME_LIST_LEN):
                self.card_name_list[i].setVisible(False)
        else:
            self.card_name_item.setVisible(True)
            self.mix_name_item.setVisible(False)
            for i in range(self.config.NAME_LIST_LEN):
                self.mix_name_list[i].setVisible(False)
            pass
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

        image_data = base64.b64decode(data['image'])
        self.card_img = Image.open(io.BytesIO(image_data))
        if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆':
            self.transform_LB_img()
        else:
            self.transform_normal_img()
        free_text._ensure_free_text(self)
        free_text._apply_free_text_data(self, data)


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

    def save_image(self, file_name=''):
        if not file_name:
            return
        if self.mix_mode_flag and self.shadow_flag:
            self.shadow_effect = QGraphicsDropShadowEffect()
            self.shadow_effect.setColor(self.shadow_color)
            if self.HD_card_img:
                self.shadow_effect.setBlurRadius(self.shadow_blur_size * 2)
                self.shadow_effect.setXOffset(self.shadow_x_offset * 2)
                self.shadow_effect.setYOffset(self.shadow_y_offset * 2)
            else:
                self.shadow_effect.setBlurRadius(self.shadow_blur_size)
                self.shadow_effect.setXOffset(self.shadow_x_offset)
                self.shadow_effect.setYOffset(self.shadow_y_offset)

            for i in range(self.config.NAME_LIST_LEN):
                self.shadow_list[i] = QGraphicsDropShadowEffect()
                self.shadow_list[i].setColor(self.shadow_color)
                if self.HD_card_img:
                    self.shadow_list[i].setBlurRadius(self.shadow_blur_size * 2)
                    self.shadow_list[i].setXOffset(self.shadow_x_offset * 2)
                    self.shadow_list[i].setYOffset(self.shadow_y_offset * 2)
                else:
                    self.shadow_list[i].setBlurRadius(self.shadow_blur_size)
                    self.shadow_list[i].setXOffset(self.shadow_x_offset)
                    self.shadow_list[i].setYOffset(self.shadow_y_offset)
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
        self.parent_app.past_scene.render(painter, QRectF(image.rect()), self.parent_app.past_scene.sceneRect())
        painter.end()
        res_img = None

        if self.HD_card_img:
            res_w, res_h = int(self.card_rect.width()) * 2, int(self.card_rect.height()) * 2
            LB_w, LB_h = self.config.LB_img_size_w[self.template_index] * 2, self.config.LB_img_size_h[self.template_index] * 2
            LB_x, LB_y = self.config.LB_x[self.template_index] * 2, self.config.LB_y[self.template_index] * 2
            card_w, card_h = self.config.card_img_size_w[self.template_index] * 2, self.config.card_img_size_h[self.template_index] * 2
            card_x, card_y = self.config.card_x[self.template_index] * 2, self.config.card_y[self.template_index] * 2
        else:

            res_w, res_h = int(self.card_rect.width()), int(self.card_rect.height())
            LB_w, LB_h = self.config.LB_img_size_w[self.template_index], self.config.LB_img_size_h[self.template_index]
            LB_x, LB_y = self.config.LB_x[self.template_index], self.config.LB_y[self.template_index]
            card_w, card_h = self.config.card_img_size_w[self.template_index], self.config.card_img_size_h[self.template_index]
            card_x, card_y = self.config.card_x[self.template_index], self.config.card_y[self.template_index]

        combine = QPixmap(QSize(res_w, res_h))
        combine.fill(Qt.transparent)
        painter = QPainter(combine)

        if self.card_type == '怪兽卡' and self.detail_extra1 == '灵摆' and self.template_index >= 5:
            card_img = None
            if self.LB_ratio == 0:
                card_img = apply_fade_to_alpha(crop_square_image(self.card_img), fade_ratio=0.02)
                card_img = card_img.resize((LB_w, LB_w), Image.Resampling.LANCZOS)
            else:
                card_img = self.card_img.resize((LB_w, LB_h), Image.Resampling.LANCZOS)
            card_img = pillow_img_to_pixmap(card_img)
            painter.drawPixmap(LB_x, LB_y, card_img)
        else:
            card_img = self.card_img.resize((card_w, card_h), Image.Resampling.LANCZOS)
            card_img = pillow_img_to_pixmap(card_img)
            painter.drawPixmap(card_x, card_y, card_img)

        painter.drawPixmap(0, 0, image)
        painter.end()
        res_img = combine

        if self.output_format == 0:
            res_img.save(file_name, format='PNG')
        else:
            res_img.save(file_name, format='JPG')
        self.card_img_item.setVisible(True)
        self.update_mix_param()
        self.update_card_name()

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
