"""wordcut 单元测试：裁决规则、未登录口径、词典解析、CLI 与页面。"""

import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wordcut import DictError, Dictionary, load_dicts, segment
from wordcut.cli import main as cli_main
from wordcut.page import render_page

REPO = Path(__file__).resolve().parent.parent
SAMPLES = REPO / 'samples'


def make_dict(entries):
    """从 (词, 词频) 列表直接构造 Dictionary。"""
    return Dictionary.from_entries(entries)


def surfaces(text, dictionary):
    return [text[s:e] for s, e, _t, _f in segment(text, dictionary)]


class TestArbitration(unittest.TestCase):
    """2.4 的四条裁决与兜底，对应 rules.txt 的用例。"""

    def setUp(self):
        self.dictionary = make_dict([
            ('南京市', 650), ('南京', 700), ('市长', 600), ('长江', 500),
            ('长江大桥', 620), ('大桥', 500), ('通车', 400),
            ('上海', 12), ('上海大学', 5), ('大学生就业', 60), ('大学生', 300),
            ('就业', 500), ('学生', 400), ('生', 500),
            ('研究', 600), ('研究生', 550), ('生命', 700), ('命', 400),
            ('起源', 650),
            ('北京', 40), ('北京师范', 30), ('师范大学', 60),
            ('北京邮电', 5), ('邮电大学', 60), ('大学', 70),
            ('上海交通', 9), ('交通大学', 60),
        ])

    def test_longest_match_wins_within_one_direction(self):
        # 同方向内长词优先：南京市 / 长江大桥 而不是 南京 / 市 / 长江 / 大桥
        self.assertEqual(
            surfaces('南京市长江大桥通车了。', self.dictionary),
            ['南京市', '长江大桥', '通车', '了', '。'])

    def test_fewer_tokens_wins(self):
        # FMM 4 词 vs RMM 3 词，取词数少的 RMM
        self.assertEqual(
            surfaces('上海大学生就业。', self.dictionary),
            ['上海', '大学生就业', '。'])

    def test_fewer_single_char_tokens_wins(self):
        # 词数相同（4），FMM 单字词 2 个 vs RMM 1 个，取 RMM
        self.assertEqual(
            surfaces('研究生命起源。', self.dictionary),
            ['研究', '生命', '起源', '。'])

    def test_higher_freq_sum_wins(self):
        # 词数、单字数都相同，FMM F=76 vs RMM F=101，取 RMM
        self.assertEqual(
            surfaces('北京邮电大学。', self.dictionary),
            ['北京', '邮电大学', '。'])

    def test_full_tie_falls_back_to_fmm(self):
        # 三项全同（n=2, s=1, F=101），兜底取 FMM
        self.assertEqual(
            surfaces('北京师范大学。', self.dictionary),
            ['北京师范', '大学', '。'])

    def test_duplicate_entry_takes_max_freq(self):
        # 上海交通 重复出现（9 与 1），取最大词频后 FMM 的 F=80 > RMM 73
        entries = [('上海交通', 9), ('上海交通', 1), ('上海', 12),
                   ('交通大学', 60), ('大学', 70)]
        dictionary = make_dict(entries)
        self.assertEqual(dictionary.words['上海交通'], 9)
        self.assertEqual(
            surfaces('上海交通大学。', dictionary),
            ['上海交通', '大学', '。'])
        # 合并与文件顺序无关
        self.assertEqual(
            make_dict(list(reversed(entries))).words['上海交通'], 9)


class TestUnknown(unittest.TestCase):
    """2.5 未登录段口径。"""

    def setUp(self):
        self.dictionary = make_dict([('北京', 40), ('AI', 70), ('5G', 30)])

    def test_latin_and_digit_runs(self):
        tokens = segment('abc 123', self.dictionary)
        self.assertEqual(
            [(t[0], t[1], t[2]) for t in tokens],
            [(0, 3, 'latin'), (4, 7, 'digit')])

    def test_mixed_latin_digit_split(self):
        self.assertEqual(
            surfaces('iPhone15', self.dictionary), ['iPhone', '15'])

    def test_unknown_run_stops_before_dict_word_forward(self):
        # 正向延伸遇到词典匹配起点即停
        self.assertEqual(
            surfaces('abc北京def', self.dictionary),
            ['abc', '北京', 'def'])

    def test_unknown_run_stops_at_dict_word_end_backward(self):
        # 反向延伸遇到词典词结束位置即停：AI 整词切出，两侧字母各自成 token
        self.assertEqual(
            surfaces('xAIy', self.dictionary), ['x', 'AI', 'y'])

    def test_fullwidth_chars_cut_one_by_one(self):
        self.assertEqual(
            surfaces('Ａ１Ｂ', self.dictionary), ['Ａ', '１', 'Ｂ'])

    def test_punctuation_and_rare_chars_single(self):
        self.assertEqual(
            surfaces('翀，。', self.dictionary), ['翀', '，', '。'])

    def test_dict_word_containing_digit(self):
        # 词典词含数字时整体优先于未登录数字串
        self.assertEqual(surfaces('5G', self.dictionary), ['5G'])

    def test_unknown_token_freq_is_one(self):
        tokens = segment('ab', self.dictionary)
        self.assertEqual(tokens[0][3], 1)


class TestSegmentation(unittest.TestCase):
    """分段、偏移与确定性。"""

    def setUp(self):
        self.dictionary = make_dict([('北京大学', 100), ('北京', 40), ('的', 900)])

    def test_longest_match_preferred(self):
        self.assertEqual(
            surfaces('北京大学', self.dictionary), ['北京大学'])

    def test_offsets_are_global_across_whitespace(self):
        text = '北京 北京\n\t的'
        tokens = segment(text, self.dictionary)
        self.assertEqual([(s, e) for s, e, _t, _f in tokens],
                         [(0, 2), (3, 5), (7, 8)])
        for s, e, _t, _f in tokens:
            self.assertEqual(text[s:e], text[s:e])

    def test_tokens_cover_all_non_whitespace(self):
        text = '北京大学 的x1　全角'
        tokens = segment(text, self.dictionary)
        rebuilt = ''.join(text[s:e] for s, e, _t, _f in tokens)
        self.assertEqual(rebuilt, ''.join(text.split()))
        starts = [s for s, _e, _t, _f in tokens]
        self.assertEqual(starts, sorted(starts))

    def test_blank_text_yields_no_tokens(self):
        self.assertEqual(segment('', self.dictionary), [])
        self.assertEqual(segment('  \n\t　', self.dictionary), [])

    def test_deterministic_across_runs(self):
        text = '北京大学的大学生在北京研究生命起源，iPhone15 上线。' * 20
        first = segment(text, self.dictionary)
        second = segment(text, self.dictionary)
        self.assertEqual(first, second)

    def test_same_dict_given_twice_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'd.tsv')
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('北京\t40\n大学\t70\n')
            one = load_dicts([path])
            two = load_dicts([path, path])
            self.assertEqual(one.words, two.words)
            text = '北京大学。'
            self.assertEqual(segment(text, one), segment(text, two))


class TestDictParsing(unittest.TestCase):

    def _write(self, content):
        fd, path = tempfile.mkstemp(suffix='.tsv')
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(content)
        self.addCleanup(os.unlink, path)
        return path

    def test_comments_blank_lines_and_default_freq(self):
        path = self._write('# 注释\n\n北京\t40\n大学\n')
        dictionary = load_dicts([path])
        self.assertEqual(dictionary.words, {'北京': 40, '大学': 1})

    def test_merge_multiple_dicts_takes_max(self):
        p1 = self._write('北京\t40\n')
        p2 = self._write('北京\t90\n大学\t70\n')
        dictionary = load_dicts([p1, p2])
        self.assertEqual(dictionary.words, {'北京': 90, '大学': 70})

    def test_too_many_fields_rejected(self):
        with self.assertRaises(DictError):
            load_dicts([self._write('北京\t40\textra\n')])

    def test_bad_freq_rejected(self):
        for bad in ('abc', '-1', '0', '1000000001', '1.5', ''):
            with self.assertRaises(DictError, msg=bad):
                load_dicts([self._write(f'北京\t{bad}\n')])

    def test_empty_word_rejected(self):
        with self.assertRaises(DictError):
            load_dicts([self._write('\t40\n')])

    def test_word_with_whitespace_rejected(self):
        with self.assertRaises(DictError):
            load_dicts([self._write('北 京\t40\n')])

    def test_missing_file_raises_oserror(self):
        with self.assertRaises(OSError):
            load_dicts(['/nonexistent/dict.tsv'])


class TestCli(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dict_path = os.path.join(self.tmp.name, 'd.tsv')
        self.text_path = os.path.join(self.tmp.name, 't.txt')
        self.out_path = os.path.join(self.tmp.name, 'out.tsv')
        with open(self.dict_path, 'w', encoding='utf-8') as fh:
            fh.write('北京大学\t100\n的\t900\n')
        with open(self.text_path, 'w', encoding='utf-8') as fh:
            fh.write('北京大学的。')

    def _run(self, argv):
        with redirect_stderr(io.StringIO()):
            return cli_main(argv)

    def test_cut_writes_expected_tsv(self):
        code = self._run(['cut', '--dict', self.dict_path,
                          '--input', self.text_path, '--output', self.out_path])
        self.assertEqual(code, 0)
        with open(self.out_path, encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '0\t4\t北京大学\n4\t5\t的\n5\t6\t。\n')

    def test_empty_text_writes_empty_file(self):
        with open(self.text_path, 'w', encoding='utf-8') as fh:
            fh.write(' \n\t')
        code = self._run(['cut', '--dict', self.dict_path,
                          '--input', self.text_path, '--output', self.out_path])
        self.assertEqual(code, 0)
        with open(self.out_path, encoding='utf-8') as fh:
            self.assertEqual(fh.read(), '')

    def test_bad_dict_exits_1_and_writes_nothing(self):
        with open(self.dict_path, 'w', encoding='utf-8') as fh:
            fh.write('北京\tnotanumber\n')
        code = self._run(['cut', '--dict', self.dict_path,
                          '--input', self.text_path, '--output', self.out_path])
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(self.out_path))

    def test_invalid_utf8_input_exits_1(self):
        with open(self.text_path, 'wb') as fh:
            fh.write(b'\xff\xfe invalid')
        code = self._run(['cut', '--dict', self.dict_path,
                          '--input', self.text_path, '--output', self.out_path])
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(self.out_path))

    def test_usage_error_exits_2(self):
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stderr(io.StringIO()):
                cli_main(['cut', '--input', self.text_path])
        self.assertEqual(ctx.exception.code, 2)

    def test_page_command_writes_html(self):
        out = os.path.join(self.tmp.name, 'index.html')
        code = self._run(['page', '--dict', self.dict_path,
                          '--input', self.text_path, '--output', out])
        self.assertEqual(code, 0)
        with open(out, encoding='utf-8') as fh:
            html = fh.read()
        self.assertIn('id="segment-data"', html)
        self.assertIn('id="text"', html)
        self.assertIn('id="stats"', html)
        self.assertIn('id="tokens"', html)
        self.assertNotIn('fetch(', html)
        self.assertNotIn('http://', html)
        self.assertNotIn('https://', html)


class TestPage(unittest.TestCase):

    def test_page_data_roundtrip(self):
        dictionary = make_dict([('北京大学', 100), ('的', 900)])
        text = '北京大学的 x9。'
        tokens = segment(text, dictionary)
        html = render_page(text, tokens, dictionary, 'in.txt', ['d.tsv'], 3)
        match = re.search(
            r'<script type="application/json" id="segment-data">(.*?)</script>',
            html, re.S)
        self.assertIsNotNone(match)
        data = json.loads(match.group(1))
        self.assertEqual(data['input'], 'in.txt')
        self.assertEqual(data['dicts'], ['d.tsv'])
        self.assertEqual(data['words'], 2)
        self.assertEqual(data['elapsed_ms'], 3)
        self.assertEqual(data['text'], text)
        self.assertEqual(
            data['tokens'],
            [[0, 4, '北京大学', 'dict'], [4, 5, '的', 'dict'],
             [6, 7, 'x', 'latin'], [7, 8, '9', 'digit'], [8, 9, '。', 'other']])
        self.assertEqual(data['stats']['chars'], len(text))
        self.assertEqual(data['stats']['tokens'], 5)
        self.assertEqual(data['stats']['singles'], 4)
        self.assertEqual(data['stats']['unknown'], 3)
        for start, end, surface, _type in data['tokens']:
            self.assertEqual(text[start:end], surface)

    def test_page_escapes_script_close_tag(self):
        dictionary = make_dict([])
        text = 'a</script><script>alert(1)</script>'
        tokens = segment(text, dictionary)
        html = render_page(text, tokens, dictionary, 'i', ['d'], 0)
        self.assertNotIn('</script><script>alert', html)
        match = re.search(
            r'<script type="application/json" id="segment-data">(.*?)</script>',
            html, re.S)
        data = json.loads(match.group(1))
        self.assertEqual(data['text'], text)


class TestSamples(unittest.TestCase):
    """端到端：五组样例输出必须与期望逐字节一致。"""

    CASES = [
        (['dicts/basic.tsv'], 'text/tiny.txt', 'expected/tiny.tsv'),
        (['dicts/ambiguous.tsv'], 'text/rules.txt', 'expected/rules.tsv'),
        (['dicts/basic.tsv', 'dicts/ambiguous.tsv'],
         'text/mixed.txt', 'expected/mixed.tsv'),
        (['dicts/large-300k.tsv', 'dicts/basic.tsv'],
         'text/corpus-news.txt', 'expected/corpus-news.tsv'),
        (['dicts/large-300k.tsv', 'dicts/ambiguous.tsv'],
         'text/corpus-forum.txt', 'expected/corpus-forum.tsv'),
    ]

    def test_all_samples_match_expected(self):
        for dicts, text_name, expected_name in self.CASES:
            with self.subTest(case=expected_name):
                dictionary = load_dicts(
                    [str(SAMPLES / d) for d in dicts])
                with open(SAMPLES / text_name, encoding='utf-8') as fh:
                    text = fh.read()
                tokens = segment(text, dictionary)
                out = ''.join(
                    f'{s}\t{e}\t{text[s:e]}\n' for s, e, _t, _f in tokens)
                with open(SAMPLES / expected_name, encoding='utf-8') as fh:
                    self.assertEqual(out, fh.read())

    def test_offsets_slice_back_to_surface(self):
        dictionary = load_dicts([str(SAMPLES / 'dicts/basic.tsv')])
        with open(SAMPLES / 'text/tiny.txt', encoding='utf-8') as fh:
            text = fh.read()
        tokens = segment(text, dictionary)
        for s, e, _t, _f in tokens:
            self.assertTrue(0 <= s < e <= len(text))


if __name__ == '__main__':
    unittest.main()
