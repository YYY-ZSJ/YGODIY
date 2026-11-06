import sys
import os
from PIL import Image
from PyQt5.QtGui import QPixmap, QImage, QFont, QFontDatabase, QPainter, QBrush
from PyQt5.QtSvg import QGraphicsSvgItem, QSvgRenderer
from PyQt5.QtCore import QByteArray, Qt
import numpy as np
from cryptography.fernet import Fernet
import io
import pickle
import requests
import re
from runtime_paths import rpath


def clean_filename(filename: str):
    forbidden_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
    for char in forbidden_chars:
        filename = filename.replace(char, '')
    return filename

def remove_leading_zeros(s: str):
    return s.lstrip('0') or '0'

def filter_strings(string_list: list[str]):
    filtered_list = [
        s for s in string_list
        if s.isdigit() and len(s) <= 8
    ]
    return filtered_list

def pillow_img_to_pixmap(pil_image: Image.Image) -> QPixmap:
    width, height = pil_image.size
    image_data = pil_image.tobytes('raw', 'RGBA')
    bytes_per_line = 4 * width
    q_image = QImage(image_data, width, height, bytes_per_line, QImage.Format_RGBA8888)
    q_pixmap = QPixmap.fromImage(q_image)
    return q_pixmap

def qpixmap_to_pillow(qpixmap: QPixmap) -> Image.Image:
    qimage = qpixmap.toImage()
    width = qimage.width()
    height = qimage.height()
    channels = 4
    buffer = qimage.bits()
    buffer.setsize(qimage.byteCount())
    img_array = np.frombuffer(buffer, dtype=np.uint8).reshape((height, width, channels))
    img_array = img_array[:, :, [2, 1, 0, 3]]
    pil_image = Image.frombytes('RGBA', (width, height), img_array.tobytes())
    return pil_image

# 解密结果缓存：卡框、稀有度图大多是 1626x2370 的整卡图，首次解密 + 解码约 110 ms，
# 而一次切卡里同一批图会被反复取用。按条数和字节数双重封顶（整卡图每张约 15 MB，
# 只按条数限制时离屏遍历全部选项实测进程涨到 3.5 GB）。
_DECRYPT_CACHE = {}
_DECRYPT_CACHE_SIZES = {}
_DECRYPT_CACHE_ORDER = []
_DECRYPT_CACHE_BYTES = [0]
_DECRYPT_CACHE_LIMIT = 512
_DECRYPT_CACHE_BYTE_LIMIT = 512 * 1024 * 1024


def _cached_value_bytes(value):
    """缓存项大约占用的内存（QPixmap 按像素算，QByteArray 按长度算）。"""
    try:
        if hasattr(value, 'depth') and hasattr(value, 'width'):
            return max(0, int(value.width()) * int(value.height()) * max(1, int(value.depth())) // 8)
        if hasattr(value, 'size') and callable(value.size):
            return max(0, int(value.size()))
    except Exception:
        pass
    return 0


def _cache_decrypted(func):
    """同一个文件只解密、解码一次。"""
    def cached(input_encrypted_path, *args, **kwargs):
        key = (func.__name__, str(input_encrypted_path), args)
        hit = _DECRYPT_CACHE.get(key)
        if hit is not None:
            return hit
        result = func(input_encrypted_path, *args, **kwargs)
        if result is not None:
            size = _cached_value_bytes(result)
            _DECRYPT_CACHE[key] = result
            _DECRYPT_CACHE_SIZES[key] = size
            _DECRYPT_CACHE_BYTES[0] += size
            _DECRYPT_CACHE_ORDER.append(key)
            while len(_DECRYPT_CACHE_ORDER) > 1 and (
                    len(_DECRYPT_CACHE_ORDER) > _DECRYPT_CACHE_LIMIT
                    or _DECRYPT_CACHE_BYTES[0] > _DECRYPT_CACHE_BYTE_LIMIT):
                stale = _DECRYPT_CACHE_ORDER.pop(0)
                _DECRYPT_CACHE.pop(stale, None)
                _DECRYPT_CACHE_BYTES[0] -= _DECRYPT_CACHE_SIZES.pop(stale, 0)
        return result
    cached.__name__, cached.__qualname__, cached.__doc__ = func.__name__, func.__qualname__, func.__doc__
    cached.__wrapped__ = func
    return cached


def runtime_resource_exists(path):
    """资源文件是否存在：先按原路径找，再到打包目录（sys._MEIPASS）里找。"""
    value = str(path or '')
    if not value:
        return False
    if os.path.exists(value):
        return True
    return os.path.exists(rpath(value))


def runtime_resource_path(path):
    """相对路径在当前目录下找不到时，改用打包目录（sys._MEIPASS）里的同名文件。"""
    value = str(path or '')
    if not value or os.path.isabs(value) or os.path.exists(value):
        return path
    candidate = rpath(value)
    return candidate if os.path.exists(candidate) else path


def _resolve_runtime_path(func):
    """解密函数收到的资源路径先按 runtime_resource_path 解析（套在解密缓存外面，缓存按解析后的路径记）。"""
    def resolved(input_encrypted_path, *args, **kwargs):
        return func(runtime_resource_path(input_encrypted_path), *args, **kwargs)
    resolved.__name__, resolved.__qualname__, resolved.__doc__ = func.__name__, func.__qualname__, func.__doc__
    resolved.__wrapped__ = func
    return resolved


def encrypt_image(input_image_path, output_encrypted_path):
    with open(rpath('mold/secret.key'), 'rb') as key_file:
        key = key_file.read()
    cipher_suite = Fernet(key)
    with open(input_image_path, 'rb') as image_file:
        image_data = image_file.read()
    encrypted_data = cipher_suite.encrypt(image_data)
    with open(output_encrypted_path, 'wb') as encrypted_file:
        encrypted_file.write(encrypted_data)

@_resolve_runtime_path
@_cache_decrypted
def decrypt_image_qpixmap(input_encrypted_path) -> QPixmap:
    with open(rpath('mold/secret.key'), 'rb') as key_file:
        key = key_file.read()
    cipher_suite = Fernet(key)
    with open(input_encrypted_path, 'rb') as encrypted_file:
        encrypted_data = encrypted_file.read()
    decrypted_data = cipher_suite.decrypt(encrypted_data)
    image_data = io.BytesIO(decrypted_data)
    qimage = QImage()
    qimage.loadFromData(image_data.read())
    pixmap = QPixmap.fromImage(qimage)
    return pixmap

@_resolve_runtime_path
def decrypt_image_pillow(input_encrypted_path):
    with open(rpath('mold/secret.key'), 'rb') as key_file:
        key = key_file.read()
    cipher_suite = Fernet(key)
    with open(input_encrypted_path, 'rb') as encrypted_file:
        encrypted_data = encrypted_file.read()
    decrypted_data = cipher_suite.decrypt(encrypted_data)
    image = Image.open(io.BytesIO(decrypted_data))
    image = image.convert('RGBA')
    return image

@_resolve_runtime_path
def decrypt_font(input_encrypted_path) -> QFont:
    with open(rpath('mold/secret.key'), 'rb') as key_file:
        key = key_file.read()
    cipher_suite = Fernet(key)
    with open(input_encrypted_path, 'rb') as encrypted_file:
        encrypted_data = encrypted_file.read()
    decrypted_data = cipher_suite.decrypt(encrypted_data)
    font_data = io.BytesIO(decrypted_data)
    font_id = QFontDatabase.addApplicationFontFromData(font_data.read())
    if font_id == -1:
        print('Failed to load font.')
        return None
    font_families = QFontDatabase.applicationFontFamilies(font_id)
    if not font_families:
        print('No font families found.')
        return None
    font_family = font_families[0]
    return QFont(font_family)

@_resolve_runtime_path
@_cache_decrypted
def decrypt_svg(input_encrypted_path):
    with open(rpath('mold/secret.key'), 'rb') as key_file:
        key = key_file.read()
    cipher_suite = Fernet(key)
    with open(input_encrypted_path, 'rb') as encrypted_file:
        encrypted_data = encrypted_file.read()
    decrypted_data = cipher_suite.decrypt(encrypted_data)
    svg_data = QByteArray(decrypted_data)
    return svg_data

@_resolve_runtime_path
def decrypt_file(input_encrypted_path, output_decrypted_path):
    with open(rpath('mold/secret.key'), 'rb') as key_file:
        key = key_file.read()
    cipher_suite = Fernet(key)
    with open(input_encrypted_path, 'rb') as encrypted_file:
        encrypted_data = encrypted_file.read()
    decrypted_data = cipher_suite.decrypt(encrypted_data)
    with open(output_decrypted_path, 'wb') as decrypted_file:
        decrypted_file.write(decrypted_data)

def rounded_pixmap(pixmap: QPixmap, radius: float):
    """对 QPixmap 图片裁剪为圆角"""
    if radius == 0:
        return pixmap
    size = pixmap.size()
    rounded = QPixmap(size)
    rounded.fill(Qt.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing)
    brush = QBrush(pixmap)
    painter.setBrush(brush)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(0, 0, size.width(), size.height(), radius, radius)
    painter.end()
    return rounded

def crop_square_image(img: Image.Image) -> Image.Image:
    width, height = img.size
    if height >= width:

        new_height = width
        top = 0
        bottom = new_height
        left = 0
        right = width
        img = img.crop((left, top, right, bottom))

    else:
        img = img.resize((width, width), Image.Resampling.LANCZOS)
    return img

def apply_fade_to_alpha(img: Image.Image, fade_ratio: float) -> Image.Image:
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    width, height = img.size
    fade_start_row = int(height * (1 - fade_ratio))
    img_data = np.array(img)
    for y in range(height):
        if y < fade_start_row:
            img_data[y, :, 3] = 255
        else:
            alpha_value = int(255 * (1 - (y - fade_start_row) / (height - fade_start_row)))
            img_data[y, :, 3] = alpha_value
    img = Image.fromarray(img_data)
    return img


def remove_annotation(text: str) -> str:

    text = re.sub(r'\[([^\[\]()]+?)\([^()]*?\)\]', r'\1', text)


    text = re.sub(r'\([^()]*?\)', '', text)


    text = text.replace('[', '').replace(']', '')

    return text

if __name__ == '__main__':













    print(2.5)
    pass
