"""wordcut：双向最大匹配分词库。

用法：
    from wordcut import load_dicts, segment
    dictionary = load_dicts(['dict.tsv'])
    tokens = segment(text, dictionary)  # [(start, end, 类型, 词频), ...]
"""

from .dictionary import DictError, Dictionary, load_dicts
from .segmenter import (
    TYPE_DICT,
    TYPE_DIGIT,
    TYPE_LATIN,
    TYPE_OTHER,
    segment,
)

__all__ = [
    'DictError',
    'Dictionary',
    'load_dicts',
    'segment',
    'TYPE_DICT',
    'TYPE_LATIN',
    'TYPE_DIGIT',
    'TYPE_OTHER',
]

__version__ = '0.1.0'
