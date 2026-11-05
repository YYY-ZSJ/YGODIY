from dataclasses import dataclass


@dataclass
class Config:
    card_name_font: dict
    detail_info_font: dict
    text_item_font: dict
    ATK_DEF_font_path: str
    pass_font_path: str
    link_font_path: str
    race_list: list[str]
    race_map: dict
    detail_map: dict
    MT_map: dict
    rt_font_path: str

    demo_show_img: str
    demo_card_level: int
    demo_attribute: str
    demo_atk: str
    demo_def: str
    demo_card_pass: str
    demo_card_pack: str
    demo_detail_text: str
    demo_race: str
    demo_call_way: str
    demo_extra1: str
    demo_extra2: str
    demo_card_name: dict
    demo_card_text: dict

    base_images: dict
    base_images_official: dict
    overframe_mask: dict
    attributes: dict
    icons: dict
    MT_type_svg: dict
    MT_type_full_svg: dict
    MT_type_posx_M: dict
    MT_type_posx_T: dict
    MT_type_full_posx_M: dict
    MT_type_full_posx_T: dict
    MT_type_posy: dict
    MT_type_scale: dict

    level_img: str
    rank_img: str
    dark_level_img: str
    ATK_DEF_svg: str
    ATK_LINK_svg: str
    holos: dict
    arrows_on: dict
    arrows_off: dict
    official_arrows: list
    rare_imgs: dict
    orare_imgs: dict
    watermark_img: dict

    loading_gif: str

    gradient_edge_points: dict
    card_rect_w: int
    card_rect_h: int
    card_img_size_w: int
    card_img_size_h: int
    ocard_img_size_w: int
    ocard_img_size_h: int
    LB_img_size_w: int
    LB_img_size_h: int
    card_x: int
    card_y: int
    ocard_x: int
    ocard_y: int
    LB_x: int
    LB_y: int

    card_name_margin: int
    card_name_size: dict
    card_name_posx: dict
    card_name_posy: dict
    ocard_name_posy: dict
    NAME_WIDTH: list
    NAME_FULL_WIDTH: list
    NAME_LIST_LEN: int

    attribute_pos_x: int
    attribute_pos_y: int
    oattribute_pos_y: int

    level_x: int
    level_y: int
    level_inter: float
    rank_x: int
    rank_y: int
    rank_inter: float
    rank_13_x: int
    rank_13_y: int

    icon_pos_x: int
    icon_pos_y: float

    detail_margin: int
    detail_size: dict
    detail_posx: dict
    detail_posy: dict
    detail_width: int
    detail_list_len: int

    text_base_size: int
    lb_base_size: int
    text_margin: int
    text_size: dict
    lb_text_size: dict
    text_spacing: dict
    rect_width: int
    rect_height_monster: int
    rect_height_mt: int
    rect_pos_monster_x: int
    rect_pos_monster_y: int
    rect_pos_mt_x: int
    rect_pos_mt_y: int
    text_line_num: dict
    text_line_num_full: dict

    lb_level_font_size: int
    lb_level_left_single_pos_x: int
    lb_level_left_single_pos_y: int
    lb_level_left_double_pos_x: int
    lb_level_left_double_pos_y: int
    lb_level_right_single_pos_x: int
    lb_level_right_single_pos_y: int
    lb_level_right_double_pos_x: int
    lb_level_right_double_pos_y: int
    lb_text_height: int
    lb_text_width: int
    lb_text_x: int
    lb_text_y: int
    lb_text_row_num: int

    line_item_x1: int
    line_item_y1: int
    line_item_x2: int
    line_item_y2: int

    fz_font_path: str
    fz_font_size: int

    cn_ATK_pos_x: int
    cn_DEF_pos_x: int
    cn_LINK_pos_x: int
    cn_ATK_DEF_pos_y: int
    ATK_DEF_pos_x: int
    ATK_DEF_pos_y: int
    ATK_DEF_scale: float
    ATK_DEF_font_size: int
    LINK_font_size: int
    LINK_font_stretch: int

    ATK_DEF_number_width: int
    ATK_number_x: int
    DEF_number_x: int
    ATK_DEF_number_y: int
    LINK_number_x: int
    LINK_number_y: int
    ATK_number_list_len: int
    DEF_number_list_len: int

    pass_font_size: int
    card_pass_x: int
    card_pass_y: int
    ocard_pass_x: int
    ocard_pass_y: int

    pack_font_size: int
    pack_font_stretch: int
    card_pack_up_x: int
    card_pack_up_y: int
    card_pack_bottom_x: int
    card_pack_bottom_y: int
    card_pack_link_x: int
    card_pack_link_y: int
    card_pack_item_width: int

    copyright_scale: list
    copyright_svgs_black: list
    copyright_svgs_white: list
    copyright_x: list
    copyright_y: int
    ocopyright_y: int
    holo_x: int
    holo_y: int

    arrow_top_x: int
    arrow_top_y: int
    arrow_down_x: int
    arrow_down_y: int
    arrow_left_x: int
    arrow_left_y: int
    arrow_right_x: int
    arrow_right_y: int
    arrow_lefttop_x: int
    arrow_lefttop_y: int
    arrow_leftdown_x: int
    arrow_leftdown_y: int
    arrow_righttop_x: int
    arrow_righttop_y: int
    arrow_rightdown_x: int
    arrow_rightdown_y: int

@dataclass
class BackConfig:
    type_path: dict
    logo_path: dict
    konami_path: str
    rsymbol_path: str
    card_w: int
    card_h: int
    resource: list[str]

@dataclass
class RDConfig:
    card_w: int
    card_h: int
    base_imgs: dict
    mask_imgs: dict
    attribute_imgs: dict
    rare_imgs: dict
    icon_imgs: dict
    level_img: str
    legend_img: str
    ATK_DEF_img: str
    MAX_ATK_img: str
    sample: str

    mask_pos_x: int
    mask_pos_y: int
    card_img_w: int
    card_img_h: int
    card_img_x: int
    card_img_y: int
    icon_x: int
    icon_y: int

    name_font: str
    detail_font: str
    text_font: str
    tip_font: str
    ATK_DEF_font: str

    card_name_size: int
    card_name_posx: int
    card_name_posy: int
    NAME_WIDTH: int
    NAME_LIST_LEN: int
    card_name_margin: int
    gradient_edge_points: list

    detail_text_size: int
    detail_pos_x: int
    detail_pos_y: int

    ATK_DEF_number_size: int
    ATK_DEF_number_width: int
    ATK_number_x: int
    ATK_number_y: int
    DEF_number_x: int
    DEF_number_y: int
    Max_number_x: int
    Max_number_y: int

    race_list: list
    call_way_list: list

    copyright_svgs: list[str]
    copyright_x: int
    copyright_y: int
    copyright_scale: list[float]
    transform_scale: list[float]

    pack_font_size: int
    card_pack_x: int
    card_pack_y: int
    card_pack_width: int
    pack_stretch: int

    holo_imgs: list[str]
    holo_x: int
    holo_y: int

    text_size: int
    text_margin: int
    rect_width: int
    rect_height: int
    rect_pos_x: int
    rect_pos_y: int
    text_line_num: int

    demo_show_img: str
    demo_card_level: int
    demo_attribute: str
    demo_card_pass: str
    demo_card_pack: str
    demo_card_name: str
    demo_card_text: str

    resource: list[str]

@dataclass
class FCConfig:
    card_w: int
    card_h: int
    center_w: int
    center_h: int
    center_full_w: int
    center_full_h: int
    center_x: int
    center_y: int
    center_full_x: int
    center_full_y: int
    back_list: list[str]
    center_list_classic: list[str]
    center_list_full: list[str]
    center_list_back: list[str]
    border_list: list[str]
    text_list: list[str]

    back_imgs: list[str]
    arrow_img: str
    magic_img: str
    icon_imgs: str
    title_imgs: str
    logo_imgs: str
    text_imgs: str
    border_imgs: str
    center_imgs: str
    full_center_imgs: str
    center_stand: str
    back_center_stand: str

    demo_back: int
    demo_center: int
    resource: list[str]

@dataclass
class PastConfig:
    card_name_font: dict
    detail_info_font: dict
    text_item_font: dict
    ATK_DEF_font_path: str
    pass_font_path: str
    link_font_path: str
    race_list: list[str]
    race_map: dict
    detail_map: dict
    MT_map: dict

    demo_show_img: str
    demo_card_level: int
    demo_attribute: str
    demo_atk: str
    demo_def: str
    demo_card_pass: str
    demo_card_pack: str
    demo_detail_text: str
    demo_race: str
    demo_call_way: str
    demo_extra1: str
    demo_extra2: str
    demo_card_name: dict
    demo_card_text: dict

    MT_type_svg: dict
    MT_type_full_svg: dict
    MT_type_posx_M: dict
    MT_type_posx_T: dict
    MT_type_full_posx_M: dict
    MT_type_full_posx_T: dict
    MT_type_posy: dict
    MT_type_scale: dict

    base_images: dict
    attributes: dict
    attributes_s: dict
    icons: dict
    level_img: str
    level_big_img: str
    rank_img: str
    rank_big_img: str
    dark_level_img: str
    dark_big_img: str
    ATK_DEF_svg: str
    ATK_LINK_svg: str
    ATK_DEF_svg_cn: str
    ATK_LINK_svg_sc: str
    ATK_LINK_svg_tc: str
    holos: dict
    official_arrows: list
    orare_imgs: dict
    watermark_img: dict

    loading_gif: str

    gradient_edge_points: dict
    card_rect_w: int
    card_rect_h: int
    card_img_size_w: list
    card_img_size_h: list
    LB_img_size_w: int
    LB_img_size_h: int
    card_x: list
    card_y: list
    LB_x: int
    LB_y: int

    card_name_margin: int
    card_name_size: dict
    card_name_posx: dict
    card_name_posy: dict
    NAME_WIDTH: int
    NAME_FULL_WIDTH: int
    NAME_LIST_LEN: int

    attribute_pos_x: int
    attribute_pos_y: int
    attribute_size: int

    level_x: int
    level_sx: int
    level_12_x: int
    level_y: int
    level_inter: float
    slevel_inter: float

    rank_x: int
    rank_sx: int
    rank_12_x: int
    rank_13_x: int
    rank_y: int
    rank_inter: float
    srank_inter: float

    icon_pos_x: int
    icon_pos_y: float

    detail_margin: int
    detail_size: list
    detail_posx: list
    detail_posy: list
    detail_width: list
    detail_list_len: list

    text_base_size: int
    lb_base_size: int
    text_margin: int
    text_size: dict
    lb_text_size: dict
    rect_width_monster: list
    rect_width_mt: list
    rect_height_monster: list
    rect_height_mt: list
    rect_pos_monster_x: int
    rect_pos_monster_y: int
    rect_pos_mt_x: int
    rect_pos_mt_y: int
    text_line_num: dict
    text_line_num_full: dict

    lb_level_font_size: int
    lb_level_left_single_pos_x: int
    lb_level_left_single_pos_y: int
    lb_level_left_double_pos_x: int
    lb_level_left_double_pos_y: int
    lb_level_right_single_pos_x: int
    lb_level_right_single_pos_y: int
    lb_level_right_double_pos_x: int
    lb_level_right_double_pos_y: int
    lb_text_height: int
    lb_text_width: int
    lb_text_x: int
    lb_text_y: int
    lb_text_row_num: int

    line_item_x1: int
    line_item_y1: int
    line_item_x2: int
    line_item_y2: int

    fz_font_path: str
    fz_font_size: int

    cn_ATK_pos_x: int
    cn_DEF_pos_x: int
    cn_LINK_pos_x: int
    cn_ATK_DEF_pos_y: int
    ATK_DEF_pos_x: int
    ATK_DEF_pos_y: int
    ATK_DEF_scale: float
    ATK_DEF_font_size: int
    LINK_font_size: int
    LINK_font_stretch: int

    ATK_DEF_number_width: int
    ATK_number_x: list
    DEF_number_x: list
    ATK_number_y: list
    DEF_number_y: list
    LINK_number_x: int
    LINK_number_y: int
    ATK_number_list_len: int
    DEF_number_list_len: int

    pass_font_size: int
    card_pass_x: int
    card_pass_y: int

    pack_font_size: int
    pack_font_stretch: int
    card_pack_up_x: int
    card_pack_up_y: int
    card_pack_bottom_x: int
    card_pack_bottom_y: int
    card_pack_link_x: int
    card_pack_link_y: int
    card_pack_item_width: int

    copyright_scale: list
    copyright_svgs_black: list
    copyright_svgs_white: list
    copyright_x: list
    copyright_y: list
    copyright_x_offset: int
    holo_x: int
    holo_y: int

    arrow_top_x: int
    arrow_top_y: int
    arrow_down_x: int
    arrow_down_y: int
    arrow_left_x: int
    arrow_left_y: int
    arrow_right_x: int
    arrow_right_y: int
    arrow_lefttop_x: int
    arrow_lefttop_y: int
    arrow_leftdown_x: int
    arrow_leftdown_y: int
    arrow_righttop_x: int
    arrow_righttop_y: int
    arrow_rightdown_x: int
    arrow_rightdown_y: int

    monster_frame: str
    MT_frame: str

    ATK_label_posx: int
    DEF_label_posx: int
    ATK_label_posy: int
    DEF_label_posy: int
    ATK_label_path: list
    DEF_label_path: list
    ATK_DEF_label_scale: float

    past_ATK_DEF_number_x: int
    past_ATK_number_y: int
    past_DEF_number_y: int

    resource: list[str]


if __name__ == '__main__':

    pass
