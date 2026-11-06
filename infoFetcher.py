from bs4 import BeautifulSoup
from bs4.element import Tag
import requests
from requests.exceptions import RequestException
from concurrent.futures import ThreadPoolExecutor
from opencc import OpenCC
import re
from io import BytesIO
from PIL import Image
import os
import sys
from cryptography.fernet import Fernet
import pickle
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
from typing import List
import cloudscraper

import card_library
from runtime_paths import rpath


def split_detail_text(input_string: str):

    stripped_string = input_string.strip()


    result = [line for line in stripped_string.splitlines() if line.strip()]

    return result

def execute_return(s: str, before='。'):
    result = []
    for i in range(len(s)):
        if s[i] == '&':
            if i > 0 and s[i - 1] != before and i + 1 < len(s) and s[i + 1] != '●':
                result.append('\n')
        else:

            result.append(s[i])

    return ''.join(result)


def transform_mark(s: str) -> str:
    s = s.replace('・', '·')
    s = s.replace('“', '「')
    s = s.replace('”', '」')
    return s


class InfoFetcher:
    def __init__(self, offical_cn=False) -> None:
        self.session_baige = requests.Session()
        self.session_jp = requests.Session()
        self.session_en = cloudscraper.create_scraper()
        self.session_ygopro = requests.Session()
        self.session_offcial_cn = requests.Session()

        self.language = ''
        self.card_pass = ''

        self.card_img = None
        self.card_name = ''
        self.card_type = '怪兽卡'
        self.call_way = ''
        self.extra1 = ''
        self.extra2 = ''
        self.level = 0
        self.race = ''
        self.attribute = ''
        self.MT_type = ''
        self.effect_text = ''
        self.lb_text = ''
        self.link_arrow_status = [False, False, False, False, False, False, False, False]
        self.atk_num = ''
        self.def_num = ''
        self.lb_level = ''
        self.card_pack = ''

        self.valid = True

        self.offical_cn = offical_cn
        self.offical_cn_card = None
        self.local_image_use = False
        self.local_image_source = ''

    def set_trans_type(self, value: bool):
        self.offical_cn = value

    def set_card_pass(self, card_pass: str, language: str):
        self.card_pass = card_pass
        self.language = language

        self.card_img = Image.new('RGBA', (100, 100), color='white')
        self.card_name = ''
        self.effect_text = ''
        self.lb_text = ''
        self.call_way = ''
        self.extra1 = ''
        self.extra2 = ''
        self.race = ''
        self.attribute = ''
        self.MT_type = '通常'
        self.link_arrow_status = [False, False, False, False, False, False, False, False]
        self.atk_num = ''
        self.def_num = ''
        self.lb_level = ''
        self.card_pack = ''
        self.valid = True

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(self.update_card_img),
                executor.submit(self.update_other)]


            for future in futures:
                future.result()

    def update_card_img(self):
        # 离线卡库里有这张卡的卡图就直接用
        card_img = card_library._local_card_image(self.card_pass)
        if card_img is not None:
            self.card_img = card_img
            return
        if self.local_image_use and self.local_image_source != '':
            flag = False
            img_list = [os.path.join(self.local_image_source, f'{self.card_pass}.png'),
                os.path.join(self.local_image_source, f'{self.card_pass}.jpg'),
                os.path.join(self.local_image_source, f"{self.card_pass.lstrip('0')}.png"),
                os.path.join(self.local_image_source, f"{self.card_pass.lstrip('0')}.jpg")]
            for img in img_list:
                if os.path.exists(img):
                    self.card_img = Image.open(img).convert('RGBA')
                    flag = True
                    break
            if not flag:
                self.fetch_img_online()
            pass
        else:
            self.fetch_img_online()
        pass

    def fetch_img_online(self):
        url = f"https://images.ygoprodeck.com/images/cards_cropped/{self.card_pass.lstrip('0')}.jpg"
        try:
            response = self.session_ygopro.get(url, timeout=8)
            if response.status_code == 200:
                image_data = BytesIO(response.content)
                self.card_img = Image.open(image_data).convert('RGBA')
        except RequestException as e:
            pass

    def update_other(self):
        # 简体中文先查离线卡库，查到就不联网
        if card_library._apply_local_info(self):
            return
        url = f'https://ygocdb.com/?search={self.card_pass}'
        try:
            response = self.session_baige.get(url, timeout=8)
            if response.status_code != 200:
                raise Exception('网页访问不成功')
            s2t_converter = OpenCC('s2t')
            soup = BeautifulSoup(response.text, 'html.parser')
            search_res = soup.find('div', class_='col-md-12 text-center')
            if search_res:
                self.valid = False
                return
            search_card = None
            results_list = soup.find_all('div', class_='row card result')
            for res in results_list:
                code_area = res.find('div', class_='col-md-6 col-xs-8 names')
                h3_list = code_area.find_all('h3')
                for h3 in h3_list:
                    text = h3.find('span').text
                    if text.isdigit() and text.zfill(8)[:-2] == self.card_pass[:-2]:
                        search_card = res
            if search_card is None:
                self.valid = False
                return
            info_text = search_card.find('div', class_='col-md-3 col-xs-12').text
            info_text_list = split_detail_text(info_text)
            detail_text, effect_text, lb_text = ('', '', '')
            detail_text = info_text_list[1]
            sc_card_name = search_card.find('div', class_='col-md-6 col-xs-8 names').find('h2').find('span').text
            if len(info_text_list) == 3:
                hr_tag = search_card.find('div', class_='col-md-3 col-xs-12').find('hr')
                text_after_hr = ''
                if hr_tag:
                    for sibling in hr_tag.next_siblings:
                        if sibling.name == 'br':
                            text_after_hr += '&'
                        elif isinstance(sibling, str):
                            text_after_hr += sibling
                effect_text = execute_return(text_after_hr.strip())
            elif len(info_text_list) == 4:
                hr_tag0 = search_card.find('div', class_='col-md-3 col-xs-12').find_all('hr')[0]
                hr_tag1 = search_card.find('div', class_='col-md-3 col-xs-12').find_all('hr')[1]
                result = ['', '']
                first_part = ''
                for sibling in hr_tag0.next_siblings:
                    if sibling == hr_tag1:
                        break
                    if sibling.name == 'br':
                        first_part += '&'
                    elif isinstance(sibling, str):
                        first_part += sibling
                result[0] = first_part.strip()
                second_part = ''
                for sibling in hr_tag1.next_siblings:
                    if sibling.name == 'br':
                        second_part += '&'
                    elif isinstance(sibling, str):
                        second_part += sibling
                result[1] = second_part.strip()
                lb_text = execute_return(result[0])
                effect_text = execute_return(result[1])
            detail_text_list = detail_text.split()
            detail_info = detail_text_list[0][1:-1]
            detail_info_list = detail_info.split('|')
            card_type = detail_info_list[0]
            self.card_type = card_type + '卡'
            if self.card_type == '怪兽卡':
                info_list = detail_info_list[1:]
                for info in info_list:
                    if not info == '效果':
                        if info in ('通常', '融合', '仪式', '同调', '超量', '连接', '衍生物'):
                            self.call_way = info
                        elif info == '灵摆':
                            if self.extra1 == '':
                                self.extra1 = '灵摆'
                            else:
                                self.extra2, self.extra1 = self.extra1, info
                        elif self.extra1 == '':
                            self.extra1 = info
                        else:
                            self.extra2 = info
                if self.call_way == '':
                    self.call_way = '效果'
                if '效果' not in info_list and '通常' not in info_list:
                    if self.extra1 == '':
                        self.extra1 = '通常'
                    else:
                        self.extra2 = '通常'
                race_attr_level = detail_text_list[1]
                split_res = race_attr_level.split('/')
                race_text = split_res[0]
                self.race = race_text + '族'
                self.attribute = split_res[1][0]
                if self.call_way == '连接':
                    atk_def_str = detail_text_list[2]
                    split_res = atk_def_str.split('/')
                    self.atk_num, self.def_num = split_res[0], split_res[1]
                    arrow_str = detail_text_list[3][1:]
                    for i in range(0, len(arrow_str), 3):
                        arrow = arrow_str[i]
                        if arrow == '↖':
                            self.link_arrow_status[0] = True
                        elif arrow == '↑':
                            self.link_arrow_status[1] = True
                        elif arrow == '↗':
                            self.link_arrow_status[2] = True
                        elif arrow == '←':
                            self.link_arrow_status[3] = True
                        elif arrow == '→':
                            self.link_arrow_status[4] = True
                        elif arrow == '↙':
                            self.link_arrow_status[5] = True
                        elif arrow == '↓':
                            self.link_arrow_status[6] = True
                        elif arrow == '↘':
                            self.link_arrow_status[7] = True
                else:
                    level_str = split_res[1][3:-1]
                    self.level = int(level_str)
                    atk_def_str = detail_text_list[2]
                    split_res = atk_def_str.split('/')
                    self.atk_num, self.def_num = split_res[0], split_res[1]
                    if self.extra1 == '灵摆':
                        if len(detail_text_list) == 3:
                            self.lb_level = '0'
                        else:
                            self.lb_level = detail_text_list[3].split('/')[0]
            else:
                if len(detail_info_list) == 1:
                    self.MT_type = '通常'
                else:
                    self.MT_type = detail_info_list[1]
                pass
            if self.offical_cn and '中文' in self.language:
                if self.offical_cn_card is None:
                    with open(rpath('mold/secret.key'), 'rb') as key_file:
                        key = key_file.read()
                    cipher = Fernet(key)
                    url = 'https://gitee.com/scutlzl/game-king-card-maker/raw/master/data/card_dict.pkl'
                    response = self.session_offcial_cn.get(url, timeout=8)
                    encrypted_data = response.content
                    decrypted_data = cipher.decrypt(encrypted_data)
                    self.offical_cn_card = pickle.loads(decrypted_data)
                if self.card_pass in self.offical_cn_card:
                    sc_card_name = self.offical_cn_card[self.card_pass][0]
                    effect_text = self.offical_cn_card[self.card_pass][1]
                    lb_text = self.offical_cn_card[self.card_pass][2]
                pass
            target_a = search_card.find('div', class_='btn-group').find('a')
            jp_url = target_a['href'] if target_a else ''
            try:
                jp_res = self.session_jp.get(jp_url, timeout=8)
                if jp_res.status_code != 200:
                    raise Exception('网页访问不成功')
            except Exception:
                pass
            jp_soup = BeautifulSoup(jp_res.text, 'html.parser')
            self.card_pack = jp_soup.find('div', class_='card_number').text.strip()
            if self.language == '简体中文':
                s2t_converter = OpenCC('t2s')
                self.card_name = s2t_converter.convert(
sc_card_name.replace(
'·', '・'))
                self.effect_text = s2t_converter.convert(effect_text)
                self.lb_text = s2t_converter.convert(
lb_text)
                if self.offical_cn and self.card_pass in self.offical_cn_card:
                    self.card_name = transform_mark(self.card_name)
                    self.effect_text = transform_mark(self.effect_text)
                    self.lb_text = transform_mark(self.lb_text)
                return
            if self.language == '繁体中文' or self.language == '繁体中文2':
                self.card_name = s2t_converter.convert(sc_card_name)
                self.effect_text = s2t_converter.convert(effect_text)
                self.lb_text = s2t_converter.convert(lb_text)
                if self.offical_cn and self.card_pass in self.offical_cn_card:
                    self.card_name = transform_mark(self.card_name)
                    self.effect_text = transform_mark(self.effect_text)
                    self.lb_text = transform_mark(self.lb_text)
            else:
                if self.language == '日文' or self.language == '日文注音':
                    try:
                        h1_tag = jp_soup.find('div', id='cardname').find('h1')
                        jp_cardname = ''.join([str(content).strip() for content in h1_tag.contents if isinstance(content, str)])
                        self.card_name = jp_cardname
                        cardtext_list = jp_soup.find_all('div', class_='CardText')
                        effect_index = 0
                        if len(cardtext_list) == 3:
                            effect_index = 1
                        else:
                            effect_index = 2
                            item_box_text = cardtext_list[1].find('div', class_='item_box_text')
                            result = ''
                            for element in item_box_text.descendants:
                                if element.name == 'br':
                                    result += '&'
                                elif isinstance(element, str):
                                    result += element
                            self.lb_text = execute_return(result.strip())
                        item_box_text = cardtext_list[effect_index].find('div', class_='item_box_text')
                        text_title = item_box_text.find('div', class_='text_title')
                        if text_title:
                            text_title.extract()
                        result = ''
                        for element in item_box_text.descendants:
                            if element.name == 'br':
                                result += '&'
                            elif isinstance(element, str):
                                result += element
                        self.effect_text = execute_return(result.strip())
                        return
                        a_tags = soup.select('ul.dropdown-menu.btn-db-dropdown-menu li a')
                        en_url = ''
                        for a in a_tags:
                            if a.get_text(strip=True) == '英文':
                                en_url = a.get('href', '')
                                break
                        try:
                            en_res = self.session_en.get(en_url, timeout=8)
                            if en_res.status_code != 200:
                                raise Exception('网页访问不成功')
                            en_soup = BeautifulSoup(en_res.text, 'html.parser')
                            div = en_soup.find('div', id='cardname')
                            h1_tag = div.find('h1') if div else None
                            self.card_name = h1_tag.get_text(strip=True) if h1_tag else ''
                            text_divs = en_soup.find_all('div', class_='item_box_text')
                            if self.extra1 == '灵摆' and len(text_divs) >= 2:
                                texts = [t.strip() for t in text_divs[0].find_all(string=True, recursive=False) if t.strip()]
                                self.lb_text = ' '.join(texts)
                                texts = [t.strip() for t in text_divs[1].find_all(string=True, recursive=False) if t.strip()]
                                self.effect_text = ' '.join(texts)
                            else:
                                texts = [t.strip() for t in text_divs[0].find_all(string=True, recursive=False) if t.strip()]
                                self.effect_text = ' '.join(texts)
                            return
                            return
                            return
                            return
                            return
                            return
                        except Exception:
                            pass
                    except Exception:
                        pass
                        return
                a_tags = soup.select('ul.dropdown-menu.btn-db-dropdown-menu li a')
                en_url = ''
                for a in a_tags:
                    if a.get_text(strip=True) == '英文':
                        en_url = a.get('href', '')
                        break
                try:
                    en_res = self.session_en.get(en_url, timeout=8)
                    if en_res.status_code != 200:
                        raise Exception('网页访问不成功')
                    en_soup = BeautifulSoup(en_res.text, 'html.parser')
                    div = en_soup.find('div', id='cardname')
                    h1_tag = div.find('h1') if div else None
                    self.card_name = h1_tag.get_text(strip=True) if h1_tag else ''
                    text_divs = en_soup.find_all('div', class_='item_box_text')
                    if self.extra1 == '灵摆' and len(text_divs) >= 2:
                        texts = [t.strip() for t in text_divs[0].find_all(string=True, recursive=False) if t.strip()]
                        self.lb_text = ' '.join(texts)
                        texts = [t.strip() for t in text_divs[1].find_all(string=True, recursive=False) if t.strip()]
                        self.effect_text = ' '.join(texts)
                    else:
                        texts = [t.strip() for t in text_divs[0].find_all(string=True, recursive=False) if t.strip()]
                        self.effect_text = ' '.join(texts)
                    return
                    return
                    return
                    return
                    return
                except Exception:
                    pass
        except RequestException as e:
            pass
        except Exception:
            pass






























    pass


class CardNameFetcher:
    def __init__(self, page_size=5, img_height=90) -> None:
        self.session = requests.Session()
        self.session_img = requests.Session()
        self.page_size = page_size
        self.img_height = img_height
        self.serach_text = ''

        self.total_len = 0
        self.info_len = 0
        self.current_page = 1
        self.card_img_list = [QPixmap() for _ in range(self.page_size)]
        self.name_list = ['' for _ in range(self.page_size)]
        self.code_list = ['' for _ in range(self.page_size)]
        self.detail_list = ['' for _ in range(self.page_size)]
        pass

    def search_info(self, search_text='', current_page=1):
        # 离线卡库可用时在本地搜索（含高级搜索条件 self._advanced_filters），否则联网
        if card_library._search_local_cards(self, search_text, current_page):
            return
        self.serach_text = search_text
        self.current_page = current_page
        self.total_len = 0
        self.info_len = 0
        for i in range(self.page_size):
            self.card_img_list[i] = QPixmap()
            self.name_list[i] = ''
            self.code_list[i] = ''
            self.detail_list[i] = ''
        self.fetch_info()

    def fetch_info(self):
        url = f'https://ygocdb.com/?search={self.serach_text}'
        try:
            response = self.session.get(url, timeout=8)
            if response.status_code != 200:
                raise Exception('网页访问不成功')

            soup = BeautifulSoup(response.text, 'html.parser')
            div_container = soup.find('main').find('div', class_='container')
            total_list = div_container.find_all('div', class_='row card result')
            self.total_len = len(total_list)
            res_list = total_list[(self.current_page - 1) * self.page_size:self.current_page * self.page_size]
            self.info_len = len(res_list)

            for i, res in enumerate(res_list):
                left_div = res.find('div', class_='col-md-3 col-xs-4')
                img_url = left_div.find('img').get('src')
                resp = self.session_img.get(img_url, timeout=8)
                if resp.status_code == 200:
                    img_data = resp.content
                    pixmap = QPixmap()
                    pixmap.loadFromData(img_data)
                    self.card_img_list[i] = pixmap.scaledToHeight(self.img_height, Qt.SmoothTransformation)
                else:
                    pix = QPixmap(62, 90)
                    pix.fill(Qt.white)
                    self.card_img_list[i] = pix

                mid_div = res.find('div', class_='col-md-6 col-xs-8 names')
                card_name = ''
                card_name_h2 = mid_div.find('h2')
                if card_name_h2:
                    card_name = card_name_h2.find('span').text

                card_code = ''
                end_h3 = mid_div.find_all('h3')[-1].find('span')

                if end_h3:
                    card_code = end_h3.text

                right_div = res.find('div', class_='col-md-3 col-xs-12')
                strong_tag = right_div.find('strong', class_='name')
                detail = ''
                if strong_tag:
                    text_after_strong = []
                    for sibling in strong_tag.next_siblings:
                        if sibling.name == 'hr':
                            break
                        if isinstance(sibling, str):
                            text_after_strong.append(sibling.strip())

                    detail = ' '.join(text_after_strong)
                self.name_list[i] = card_name
                self.code_list[i] = card_code
                self.detail_list[i] = detail
                pass
        except Exception:
            pass
        pass
    pass


class RDFetcher:
    def __init__(self) -> None:
        self.session_ygopro = requests.Session()
        self.card_pass = ''
        self.card_info_dict = None
        self.valid = True

    def set_card_pass(self, card_pass: str):
        self.card_img = None
        self.card_info = None
        self.card_pass = card_pass
        self.card_img = Image.new('RGBA', (100, 100), color='white')

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(self.fetch_img_online),
                executor.submit(self.fetch_text_info)]

            for future in futures:
                future.result()
        pass

    def fetch_img_online(self):
        url = f"https://images.ygoprodeck.com/images/cards_cropped/{self.card_pass.lstrip('0')}.jpg"
        try:
            response = self.session_ygopro.get(url, timeout=8)
            if response.status_code == 200:
                image_data = BytesIO(response.content)
                self.card_img = Image.open(image_data).convert('RGBA')
        except RequestException as e:
            pass

    def fetch_text_info(self):
        self.load_rd_info()
        if self.card_info_dict is not None:
            if self.card_pass in self.card_info_dict:
                self.valid = True
                self.card_info = self.card_info_dict[self.card_pass]
            else:
                self.valid = False
                pass
        pass

    def load_rd_info(self):
        if self.card_info_dict is None:
            url = 'https://gitee.com/scutlzl/game-king-card-maker/raw/master/data/csjd_info.pkl'
            with open(rpath('mold/secret.key'), 'rb') as key_file:
                key = key_file.read()
            cipher = Fernet(key)
            try:
                response = requests.get(url, timeout=8)
                encrypted_data = response.content
                decrypted_data = cipher.decrypt(encrypted_data)
                self.card_info_dict = pickle.loads(decrypted_data)
            except:
                pass
        pass

    pass

if __name__ == '__main__':

    pass
