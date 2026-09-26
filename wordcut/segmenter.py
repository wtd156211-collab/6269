"""FMM/RMM 双向最大匹配与歧义裁决。

正文先按空白切段，段内独立产出正向（FMM）与反向（RMM）两串候选，
再按 (词数 n, 单字词数 s, 词频和 F) 的口径裁决：n 小者胜，s 小者胜，
F 大者胜，三项全同取 FMM。未登录处：ASCII 字母/数字连续串各算一个
token，其余字符逐字一个 token；未登录串不吞词典词。
"""

from __future__ import annotations

from .dictionary import Dictionary

TYPE_DICT = 'dict'
TYPE_LATIN = 'latin'
TYPE_DIGIT = 'digit'
TYPE_OTHER = 'other'

# 切分项: (start, end, 类型, 词频)。未登录 token 词频记 1。
Token = tuple


def _is_latin(ch: str) -> bool:
    return 'A' <= ch <= 'Z' or 'a' <= ch <= 'z'


def _is_digit(ch: str) -> bool:
    return '0' <= ch <= '9'


def _match_forward(text: str, pos: int, end: int, root: dict) -> bool:
    """pos 处是否存在词典匹配（某词以 pos 为起点）。"""
    node = root
    while pos < end:
        node = node.get(text[pos])
        if node is None:
            return False
        if '' in node:
            return True
        pos += 1
    return False


def _match_backward(text: str, pos: int, start: int, root: dict) -> bool:
    """pos 是否是词典词的结束位置（某词以 pos 为终点，半开区间）。"""
    node = root
    pos -= 1
    while pos >= start:
        node = node.get(text[pos])
        if node is None:
            return False
        if '' in node:
            return True
        pos -= 1
    return False


def _fmm(text: str, start: int, end: int, root: dict) -> list[Token]:
    tokens: list[Token] = []
    append = tokens.append
    i = start
    while i < end:
        node = root
        j = i
        best = 0
        freq = 1
        while j < end:
            nxt = node.get(text[j])
            if nxt is None:
                break
            node = nxt
            j += 1
            f = node.get('')
            if f is not None:
                best = j
                freq = f
        if best:
            append((i, best, TYPE_DICT, freq))
            i = best
            continue
        ch = text[i]
        if 'A' <= ch <= 'Z' or 'a' <= ch <= 'z':
            j = i + 1
            while j < end:
                cj = text[j]
                if not ('A' <= cj <= 'Z' or 'a' <= cj <= 'z'):
                    break
                if _match_forward(text, j, end, root):
                    break
                j += 1
            append((i, j, TYPE_LATIN, 1))
            i = j
        elif '0' <= ch <= '9':
            j = i + 1
            while j < end:
                cj = text[j]
                if not '0' <= cj <= '9':
                    break
                if _match_forward(text, j, end, root):
                    break
                j += 1
            append((i, j, TYPE_DIGIT, 1))
            i = j
        else:
            append((i, i + 1, TYPE_OTHER, 1))
            i += 1
    return tokens


def _rmm(text: str, start: int, end: int, root: dict) -> list[Token]:
    tokens: list[Token] = []
    append = tokens.append
    j = end
    while j > start:
        node = root
        m = j - 1
        best = -1
        freq = 1
        while m >= start:
            nxt = node.get(text[m])
            if nxt is None:
                break
            node = nxt
            f = node.get('')
            if f is not None:
                best = m
                freq = f
            m -= 1
        if best >= 0:
            append((best, j, TYPE_DICT, freq))
            j = best
            continue
        ch = text[j - 1]
        if 'A' <= ch <= 'Z' or 'a' <= ch <= 'z':
            k = j - 1
            while k > start:
                ck = text[k - 1]
                if not ('A' <= ck <= 'Z' or 'a' <= ck <= 'z'):
                    break
                if _match_backward(text, k, start, root):
                    break
                k -= 1
            append((k, j, TYPE_LATIN, 1))
            j = k
        elif '0' <= ch <= '9':
            k = j - 1
            while k > start:
                ck = text[k - 1]
                if not '0' <= ck <= '9':
                    break
                if _match_backward(text, k, start, root):
                    break
                k -= 1
            append((k, j, TYPE_DIGIT, 1))
            j = k
        else:
            append((j - 1, j, TYPE_OTHER, 1))
            j -= 1
    tokens.reverse()
    return tokens


def _score(tokens: list[Token]) -> tuple[int, int, int]:
    n = len(tokens)
    singles = 0
    freq_sum = 0
    for start, end, _type, freq in tokens:
        if end - start == 1:
            singles += 1
        freq_sum += freq
    return (n, singles, -freq_sum)


def _cut_span(text: str, start: int, end: int, fwd: dict, bwd: dict) -> list[Token]:
    fmm = _fmm(text, start, end, fwd)
    rmm = _rmm(text, start, end, bwd)
    if _score(rmm) < _score(fmm):
        return rmm
    return fmm


def segment(text: str, dictionary: Dictionary) -> list[Token]:
    """切分整篇正文，返回按 start 递增、互不重叠的切分项序列。"""
    fwd = dictionary.forward
    bwd = dictionary.backward
    tokens: list[Token] = []
    n = len(text)
    i = 0
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        start = i
        while i < n and not text[i].isspace():
            i += 1
        if start < i:
            tokens.extend(_cut_span(text, start, i, fwd, bwd))
    return tokens
