
import unicodedata
import re
import random
import string
from typing import List
import unicodedata


class LineBreaker:
    def __init__(self):
        self.no_line_start = set('，,。.、；;！？?）)》]】｝}」』”-・·ーッ')
        self.no_line_end = set('（(《[【｛{「『“●@')
        self.quotes = set('"\'')

    def is_cjk(self, ch: str) -> bool:
        return (
            '一' <= ch <= '鿿' or
            '㐀' <= ch <= '䶿' or
            '぀' <= ch <= 'ヿ' or
            '가' <= ch <= '힣'
        )

    def is_word_char(self, ch: str) -> bool:
        cat = unicodedata.category(ch)
        return (
            cat in ('Lu', 'Ll', 'Nd') or
            ch == '_'
        )

    def split(self, text: str):
        result = []
        i = 0
        n = len(text)

        while i < n:
            ch = text[i]




            if ch in self.no_line_end:
                buffer = ''


                while i < n and text[i] in self.no_line_end:
                    buffer += text[i]
                    i += 1


                if i < n:
                    next_ch = text[i]


                    if self.is_cjk(next_ch):
                        buffer += next_ch
                        i += 1


                    elif self.is_word_char(next_ch):
                        start = i
                        while i < n and self.is_word_char(text[i]):
                            i += 1
                        buffer += text[start:i]


                    else:
                        buffer += next_ch
                        i += 1

                result.append(buffer)
                continue




            if ch in self.no_line_start:
                if result:
                    result[-1] += ch
                else:
                    result.append(ch)
                i += 1
                continue




            if ch in self.quotes:
                buffer = ch
                i += 1
                while i < n:
                    buffer += text[i]
                    if text[i] in self.quotes:
                        i += 1
                        break
                    i += 1
                result.append(buffer)
                continue




            if self.is_cjk(ch):
                result.append(ch)
                i += 1
                continue




            if self.is_word_char(ch):
                start = i
                while i < n and self.is_word_char(text[i]):
                    i += 1
                result.append(text[start:i])
                continue




            if ch.isspace():
                result.append(ch)
                i += 1
                continue




            result.append(ch)
            i += 1

        return result



class TextBreaker:
    BRACKET_PAIRS = {
        '(': ')',
        '[': ']',
    }

    OPEN_BRACKETS = set(BRACKET_PAIRS.keys())
    CLOSE_BRACKETS = set(BRACKET_PAIRS.values())

    def __init__(self, locale: str = 'und'):
        self.locale = locale
        self.pattern = re.compile(r'\[.*?\(.*?\)]')
        self.line_breaker = LineBreaker()


























    def splitWithBracketStack(self, text: str) -> List[str]:
        """
        使用 bracket_stack 方法保护括号
        + 空格单独拆分
        + 方括号内部空格不拆
        """
        raw_segments = self.splitBreakWord(text, self.locale)
        result = []
        buffer = ''
        bracket_stack = []

        for seg in raw_segments:
            for ch in seg:
                if ch in self.OPEN_BRACKETS:
                    bracket_stack.append(self.BRACKET_PAIRS[ch])
                elif bracket_stack and ch == bracket_stack[-1]:
                    bracket_stack.pop()

            buffer += seg

            if bracket_stack: continue


            if bool(self.pattern.search(buffer)):
                result.append(buffer)
            else:

                buf = ''
                for ch in buffer:
                    if ch == ' ':
                        if buf:
                            result.append(buf)
                            buf = ''
                        result.append(ch)
                    else:
                        buf += ch
                if buf:
                    result.append(buf)

            buffer = ''




        if buffer:


            if bool(self.pattern.search(buffer)):
                result.append(buffer)
            else:
                buf = ''
                for ch in buffer:
                    if ch == ' ':
                        if buf:
                            result.append(buf)
                            buf = ''
                        result.append(ch)
                    else:
                        buf += ch
                if buf:
                    result.append(buf)

        return result





    def splitWithJSStyle(self, text: str) -> List[str]:
        """
        仿照 JS splitBreakWordWithBracket
        - 占位符保护 [字(假名)]
        - 零宽空格保护相邻占位符
        - ICU 分词 + 空格单独拆分
        - 方括号内部空格不拆
        """
        placeholder_map = {}


        def repl(match):
            unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))
            key = f'__{unique_id}__'
            placeholder_map[key] = match.group(0)
            return key

        pattern = re.compile(r'\[.*?\(.*?\)]')
        replace_text = pattern.sub(repl, text)


        placeholder_regex = re.compile(r'(?<=__[a-z0-9]{9}__)(?=__[a-z0-9]{9}__)')
        final_text = placeholder_regex.sub('​', replace_text)



        split_list = self.line_breaker.split(final_text)


        result = []
        for item in split_list:
            s = item.replace('​', '')
            for key, value in placeholder_map.items():
                s = s.replace(key, value)


            if bool(self.pattern.search(s)):
                result.append(s)
                continue


            buf = ''
            for ch in s:
                if ch == ' ':
                    if buf:
                        result.append(buf)
                        buf = ''
                    result.append(ch)
                else:
                    buf += ch
            if buf:
                result.append(buf)

        return result




    def split(self, text: str, method: str = 'js_style') -> List[str]:
        """
        method:
            - 'bracket_stack' 结构化括号合并
            - 'js_style' 仿照 JS
        """
        if method == 'bracket_stack':
            return self.splitWithBracketStack(text)
        elif method == 'js_style':
            return self.splitWithJSStyle(text)
        else:
            raise ValueError(f'Unknown method: {method}')


if __name__ == '__main__':
    breaker = TextBreaker()

    text = '這個,卡名。'

    res = breaker.split(text)



    print('End result')
    print(res)
