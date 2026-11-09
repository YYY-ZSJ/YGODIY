import sys
from TextBreaker import TextBreaker
import re
import math
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont, QFontDatabase, QFontMetricsF
from dataclasses import dataclass
from typing import List
from utils import rpath


@dataclass
class MixText:
    text: str = ''
    bold: bool = False
    width: float = 0
    height: float = 0
    originalWidth: float = 0
    originalHeight: float = 0
    paddingLeft: float = 0
    paddingRight: float = 0
    line: int = -1
    x: float = 0
    y: float = 0
    scaleX: float = 1
    letterSpacing: float = 0


@dataclass
class TextItem:
    ruby: MixText = None
    rt: MixText = None


class CompressText:
    def __init__(self):
        self.text_breaker = TextBreaker()

        self.baseLineHeight = 1.17
        self.noCompressText = '●①②③④⑤⑥⑦⑧⑨⑩'
        self.parseList = []
        self.newlineList = []
        self.currentX = 0
        self.currentY = 0
        self.currentLine = 0
        self.textScale = 1
        self.firstLineTextScale = 1
        self.isSmallSize = False
        self.group = None
        self.needCompressTwice = False
        self.bounds = {}

        self.text = ''
        self.fontFamily = QFont('Arial', 20)
        self.fontSize = 45
        self.fontFamily.setPixelSize(self.fontSize)
        self.metric = QFontMetricsF(self.fontFamily)

        self.fontWeight = 0
        self.lineHeight = self.baseLineHeight
        self.letterSpacing = 0
        self.wordSpacing = 0
        self.firstLineCompress = False
        self.textAlign = 'justify'
        self.textJustifyLast = False
        self.color = 'black'
        self.rtFontFamily = QFont('Arial', 20)
        self.rtFontSize = 14
        self.rtFontFamily.setPixelSize(self.rtFontSize)
        self.rtmetric = QFontMetricsF(self.rtFontFamily)
        self.rtRatio = 0.34210526315789475
        self.rtRealSize = 14
        self.rtZoomRatio = 1

        self.rtFontWeight = 0
        self.rtLineHeight = self.baseLineHeight
        self.rtLetterSpacing = 0
        self.rtTop = -3.5
        self.rtColor = 'black'
        self.rtFontScaleX = 1
        self.fontScale = 1
        self.autoSmallSize = False
        self.smallFontSize = 18
        self.width = 0
        self.height = 0
        self.x = 0
        self.y = 0
        self.zIndex = 0
        pass

    def setRubyFont(self, font: QFont):
        self.fontFamily = font
        self.metric = QFontMetricsF(self.fontFamily)

    def setFontSize(self, size: int):
        self.fontSize = size
        self.fontFamily.setPixelSize(self.fontSize)
        self.metric = QFontMetricsF(self.fontFamily)
        self.rtRealSize = self.fontSize * self.rtRatio
        self.rtZoomRatio = self.rtRealSize / self.rtFontSize

    def setRtFont(self, font: QFont):
        self.rtFontFamily = font
        self.rtmetric = QFontMetricsF(self.rtFontFamily)

    def setRtFontSize(self, size: int):
        self.rtFontSize = size
        self.rtFontFamily.setPixelSize(self.rtFontSize)
        self.rtmetric = QFontMetricsF(self.rtFontFamily)

    # compressText 的全部输入。一次排版会被调用 7~8 次，长效果文本单次就要约 0.5 秒
    # （compressRuby 的固定点迭代每步都重跑 updateTextScale），输入没变就直接跳过。
    COMPRESS_KEY_FIELDS = (
        'text', 'width', 'height', 'fontSize', 'fontFamily', 'fontWeight', 'lineHeight', 'baseLineHeight',
        'letterSpacing', 'textScale', 'firstLineTextScale', 'firstLineCompress', 'isSmallSize', 'smallFontSize',
        'autoSmallSize', 'needCompressTwice', 'textAlign', 'textJustifyLast', 'noCompressText', 'rtFontSize',
        'rtFontScaleX', 'rtLetterSpacing', 'rtZoomRatio', 'rtTop', 'rtColor', 'color', 'rtRatio', 'rtRealSize',
        'fontScale', 'rtLineHeight',
    )

    def _compress_key(self):
        def hashable(value):
            try:
                hash(value)
            except Exception:
                return (type(value).__name__,)
            return value
        return tuple(hashable(getattr(self, name, None)) for name in self.COMPRESS_KEY_FIELDS)

    def compressText(self):
        key = self._compress_key()
        if getattr(self, '_compress_key_done', None) == key:
            return None
        result = self._compressText()
        self._compress_key_done = key
        return result

    def _compressText(self):
        self.textScale = 1
        self.firstLineTextScale = 1
        self.isSmallSize = False
        self.needCompressTwice = False
        self.parseList = self.getParseList()
        self.newlineList = self.getNewlineList()
        self.createRuby()
        self.compressRuby()
        self.alignRuby()
        self.createRt()
        pass

    def getParseList(self):
        result = []
        bold = False
        text = self.text.rstrip()

        pattern = f'(<b>|</b>|\\n|[{re.escape(self.noCompressText)}])'
        parts = re.split(pattern, text)
        for value in filter(None, parts):
            if value == '<b>':
                bold = True
                continue
            if value == '</b>':
                bold = False
                continue
            split_list = self.text_breaker.split(value)
            for part in split_list:
                item_list = []
                ruby_parts = re.split(r'(\[.*?\(.*?\)])', part)
                for seg in filter(None, ruby_parts):
                    ruby_text = seg
                    rt_text = ''
                    if re.search(r'\[.*?\(.*?\)]', seg):
                        ruby_text = re.sub(r'\[(.*?)\((.*?)\)]', r'\1', seg)
                        rt_text = re.sub(r'\[(.*?)\((.*?)\)]', r'\2', seg)
                    ruby = MixText(text=ruby_text, bold=bold)
                    rt = MixText(text=rt_text)
                    item = TextItem(ruby=ruby, rt=rt)
                    item_list.append(item)
                result.append(item_list)
        return result


    def getNewlineList(self):
        result = [[]]
        current_index = 0
        for item_list in self.parseList:
            has_break = any(
                item.ruby.text == '\n'
                for item in item_list
            )
            result[current_index].append(item_list)
            if has_break:
                current_index += 1
                result.append([])
        return result


    def getItemList(self) -> List[MixText]:
        return [
            item
            for item_list in self.parseList
            for item in item_list
        ]


    def getRubyList(self) -> List[MixText]:
        return [
            item.ruby
            for item_list in self.parseList
            for item in item_list
        ]


    def getRtList(self) -> List[MixText]:
        return [
            item.rt
            for item_list in self.parseList
            for item in item_list
        ]


    def createRuby(self):
        ruby_list = self.getRubyList()
        for ruby in ruby_list:
            ruby.originalWidth = self.metric.horizontalAdvance(ruby.text)
            ruby.originalHeight = self.fontSize * self.lineHeight
            ruby.width = self.metric.horizontalAdvance(ruby.text)
            ruby.height = self.fontSize * self.lineHeight
            if ruby.text == ' ':
                ruby.originalWidth += self.wordSpacing
                ruby.width += self.wordSpacing

        self.updateTextScale()


    def compressRuby(self):
        rubyList = self.getRubyList()
        if len(rubyList) == 0: return
        if self.firstLineCompress and self.width:
            firstNewlineRubyList = [
                item.ruby
                for item_list in self.newlineList[0]
                for item in item_list
            ]
            firstNewlineTotalWidth = 0
            maxWidth = self.width
            for ruby in firstNewlineRubyList:
                paddingLeft = ruby.paddingLeft or 0
                paddingRight = ruby.paddingRight or 0
                firstNewlineTotalWidth += ruby.originalWidth
                maxWidth -= paddingLeft + paddingRight
            self.firstLineTextScale = min(math.floor(maxWidth / firstNewlineTotalWidth * 1000) / 1000, 1)
            self.updateTextScale()

        lastRuby = rubyList[-1]
        if self.height and lastRuby and self.currentY + lastRuby.height > self.height:
            scale = 0.5
            start, end = 0, self.textScale
            while scale > 0:
                scale = (start + end) / 2
                self.textScale = scale
                self.updateTextScale()
                if self.currentY + lastRuby.height > self.height:
                    end = scale
                else:
                    start = scale
                if self.currentY + lastRuby.height <= self.height and end - start <= 0.01:
                    if self.autoSmallSize and scale < 0.7 and self.fontScale <= 1 and not self.isSmallSize:
                        self.isSmallSize = True
                        self.updateFontSize()
                        scale = 0.5
                        start = 0
                        end = 1
                    else:
                        break
                pass
            pass
        pass


    def alignRuby(self):
        rubyList = self.getRubyList()
        alignLine = 0
        if self.textScale < 1 or self.textAlign in ('center', 'right') or self.textJustifyLast:
            alignLine = self.currentLine + 1
        else:
            alignLine = self.currentLine
        for line in range(alignLine):
            lineList = [ruby for ruby in rubyList if ruby.line == line]
            if len(lineList):
                lastRuby = lineList[-1]
                if self.textAlign == 'center':
                    if len(lineList) > 1 and lineList[-1].text == '\n':
                        lastRuby = lineList[-2]
                    else:
                        lastRuby = lineList[-1]
                lastPaddingRight = lastRuby.paddingRight or 0
                remainWidth = self.width - lastRuby.x - lastRuby.width - lastPaddingRight
                if remainWidth > 0:
                    if self.textAlign == 'center':
                        offset = remainWidth / 2
                        for ruby in lineList:
                            ruby.x += offset
                    elif self.textAlign == 'right':
                        offset = remainWidth
                        for ruby in lineList:
                            ruby.x += offset
                    elif self.textAlign == 'justify':
                        if len(lineList) > 1 and lastRuby.text != '\n':
                            gap = remainWidth / (len(lineList) - 1)
                            for index, ruby in enumerate(lineList):
                                ruby.x += index * gap
            pass
        pass


    def updateTextScale(self):
        self.currentX = 0
        self.currentY = 0
        self.currentLine = 0

        for newlineIndex, newline in enumerate(self.newlineList):
            lastNewline = newlineIndex == len(self.newlineList) - 1
            for itemList in newline:
                itemWidth = 0
                for item in itemList:
                    ruby = item.ruby
                    if self.firstLineCompress and newlineIndex == 0:
                        ruby.scaleX = self.firstLineTextScale
                        ruby.width = ruby.originalWidth * self.firstLineTextScale
                    elif ruby.text not in self.noCompressText and lastNewline:
                        ruby.scaleX = self.textScale
                        ruby.width = ruby.originalWidth * self.textScale
                    paddingLeft = ruby.paddingLeft or 0
                    paddingRight = ruby.paddingRight or 0
                    itemWidth += ruby.width + paddingLeft + paddingRight
                hasBreak = any(item.ruby.text == '\n' for item in itemList)
                isOverWidth = self.width and self.currentX and self.currentX + itemWidth > self.width
                if hasBreak or isOverWidth:
                    self.addLine()
                for item in itemList:
                    ruby = item.ruby
                    self.positionRuby(ruby)
        pass


    def addLine(self):
        self.removeLineLastSpace(self.currentLine)
        fontSize = self.smallFontSize if self.isSmallSize else self.fontSize
        self.currentX = 0
        self.currentY += fontSize * self.lineHeight
        self.currentLine += 1


    def removeLineLastSpace(self, line: int):
        rubyList = self.getRubyList()
        while True:
            lineList = [ruby for ruby in rubyList if ruby.line == line]
            if len(lineList) == 0:
                break
            lastRuby = lineList[-1]
            if not lastRuby.text == ' ':
                break
            lastPaddingLeft = lastRuby.paddingLeft or 0
            lastPaddingRight = lastRuby.paddingRight or 0
            self.currentX -= lastRuby.width + lastPaddingLeft + lastPaddingRight
            lastRuby.line = -1
        pass


    def positionRuby(self, ruby: MixText):
        paddingLeft = ruby.paddingLeft or 0
        paddingRight = ruby.paddingRight or 0
        ruby.x = self.currentX + paddingLeft
        ruby.y = self.currentY
        self.currentX += ruby.width + paddingLeft + paddingRight
        if ruby.text == '\n':
            ruby.line = self.currentLine - 1
        else:

            ruby.line = self.currentLine


    def updateFontSize(self):
        self.textScale = 1
        fontSize = self.smallFontSize if self.isSmallSize else self.fontSize
        sizePercent = fontSize / self.fontSize
        rubyList = self.getRubyList()
        for ruby in rubyList:
            ruby.originalWidth *= sizePercent
            ruby.originalHeight *= sizePercent
            ruby.width *= sizePercent
            ruby.height *= sizePercent
        self.updateTextScale()
        pass


    def createRt(self):
        itemList = [
            item
            for item_list in self.parseList
            for item in item_list
        ]
        for item in itemList:
            rt = item.rt
            rt.originalWidth = self.rtmetric.horizontalAdvance(rt.text) * self.rtZoomRatio
            rt.originalHeight = self.rtRealSize * self.rtLineHeight
            rt.width = self.rtmetric.horizontalAdvance(rt.text) * self.rtZoomRatio
            rt.height = self.rtRealSize * self.rtLineHeight
            self.positionRt(item)
            pass

        if self.needCompressTwice:
            self.updateTextScale()
            self.compressRuby()
            self.alignRuby()
            for item in itemList:
                self.positionRt(item)
        pass


    def _darwin_rt_y(self, ruby: MixText, rt: MixText):
        """macOS：按墨迹边界给正文和注音之间留出固定小空隙。

        rtTop 常数是在 Windows 上目视调好的；macOS 的 CoreText 对同一字体给出的
        字形上缘位置不同（日文字形在 em 盒里偏高），沿用同一常数会算出负间隙，
        注音直接压在正文上。这里用 tightBoundingRect 量出正文墨迹上缘和注音
        墨迹下缘的实际位置，反推注音原点的纵向坐标。失败时退回 rtTop 常数。"""
        try:
            gap = self.fontSize * 0.03
            ruby_top = self.metric.ascent() + self.metric.tightBoundingRect(ruby.text).top()
            rt_bottom = self.rtmetric.ascent() + self.rtmetric.tightBoundingRect(rt.text).bottom()
            return ruby.y + ruby_top - gap - rt_bottom * self.rtZoomRatio
        except Exception:
            return ruby.y + self.rtTop * self.rtZoomRatio

    def positionRt(self, item: TextItem):
        rtStretchRate = 0.9
        rtCompressRate = 0.6
        ruby = item.ruby
        rt = item.rt
        if rt.text and ruby.text:
            paddingLeft = ruby.paddingLeft or 0
            paddingRight = ruby.paddingRight or 0
            rubyWidth = ruby.width + paddingLeft + paddingRight
            rt.x = ruby.x + rubyWidth / 2 - paddingLeft
            rt.y = ruby.y + self.rtTop * self.rtZoomRatio
            if sys.platform == "darwin":
                rt.y = self._darwin_rt_y(ruby, rt)
            if not self.rtFontScaleX == 1:
                rt.scaleX = self.rtFontScaleX
            elif rubyWidth == 0:
                # 日文注音排到行尾附近时，个别汉字会被量出宽度 0（如灰流丽日文里的「墓」）。
                # 位置已经设好，只是没法按汉字宽度调整读音字距，跳过这一步即可。
                pass
            elif rt.width / rubyWidth < rtStretchRate and len(ruby.text) > 1:
                maxLetterSpacing = self.fontSize - self.rtRealSize / 2
                newLetterSpacing = (rubyWidth * rtStretchRate - rt.width) / (len(rt.text) - 1) if len(rt.text) > 1 else math.inf
                rt.letterSpacing = min(newLetterSpacing, maxLetterSpacing)
                rt.x += rt.letterSpacing / 2
            elif rt.width > rubyWidth:
                if rubyWidth / rt.width < rtCompressRate:
                    widen = rtCompressRate * rt.width - rubyWidth
                    rt.scaleX = rtCompressRate
                    ruby.paddingLeft = widen / 2
                    ruby.paddingRight = widen / 2
                    self.needCompressTwice = True
                else:
                    rt.scaleX = rubyWidth / rt.width
            else:
                pass
        pass


if __name__ == '__main__':









    strA = ' '
    if strA:
        print('SSSSSS')
    pass
