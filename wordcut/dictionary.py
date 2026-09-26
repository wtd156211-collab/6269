"""词典加载与组织结构。

词条 (词, 词频) 合并成一张词表后，组织成正反两棵 trie：
正向 trie 供 FMM 找「以某位置为起点的最长词」，
反向 trie（词逆序插入）供 RMM 找「以某位置为终点的最长词」。
trie 节点是嵌套 dict，终节点的 '' 键存放词频（词非空，不会与字符键冲突）。
"""

from __future__ import annotations

MAX_FREQ = 10**9


class DictError(Exception):
    """词典输入不可用。"""


def _parse_line(line: str, path: str, lineno: int) -> tuple[str, int] | None:
    if not line or line.startswith('#'):
        return None
    fields = line.split('\t')
    if len(fields) > 2:
        raise DictError(f'{path}:{lineno}: 字段多于两个')
    word = fields[0]
    if not word:
        raise DictError(f'{path}:{lineno}: 词为空')
    for ch in word:
        if ch.isspace():
            raise DictError(f'{path}:{lineno}: 词内含空白字符')
    if len(fields) == 1:
        return word, 1
    raw = fields[1]
    if not raw or any(c < '0' or c > '9' for c in raw):
        raise DictError(f'{path}:{lineno}: 词频不是十进制整数: {raw!r}')
    freq = int(raw)
    if not 1 <= freq <= MAX_FREQ:
        raise DictError(f'{path}:{lineno}: 词频超出 1..10^9: {raw!r}')
    return word, freq


class Dictionary:
    """合并后的词表与正反两棵 trie。"""

    __slots__ = ('words', 'forward', 'backward', 'maxlen')

    def __init__(self, words: dict[str, int]):
        self.words = words
        self.forward: dict = {}
        self.backward: dict = {}
        self.maxlen = 0
        for word, freq in words.items():
            node = self.forward
            for ch in word:
                node = node.setdefault(ch, {})
            node[''] = freq
            node = self.backward
            for ch in reversed(word):
                node = node.setdefault(ch, {})
            node[''] = freq
            if len(word) > self.maxlen:
                self.maxlen = len(word)

    def __len__(self) -> int:
        return len(self.words)

    @classmethod
    def from_entries(cls, entries) -> 'Dictionary':
        """从 (词, 词频) 序列建表，重复词条取最大词频。"""
        words: dict[str, int] = {}
        for word, freq in entries:
            prev = words.get(word)
            if prev is None or freq > prev:
                words[word] = freq
        return cls(words)


def load_dicts(paths: list[str]) -> Dictionary:
    """按给定顺序读取多份词典并合并（重复词条取最大词频，与顺序无关）。"""
    words: dict[str, int] = {}
    for path in paths:
        try:
            with open(path, encoding='utf-8', errors='strict', newline='') as fh:
                for lineno, raw in enumerate(fh, 1):
                    parsed = _parse_line(raw.rstrip('\n'), path, lineno)
                    if parsed is None:
                        continue
                    word, freq = parsed
                    prev = words.get(word)
                    if prev is None or freq > prev:
                        words[word] = freq
        except UnicodeDecodeError as exc:
            raise DictError(f'{path}: 非法 UTF-8: {exc}') from exc
    return Dictionary(words)
