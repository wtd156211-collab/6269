"""命令行入口：python -m wordcut cut|page。"""

from __future__ import annotations

import argparse
import os
import sys
import time

from .dictionary import DictError, load_dicts
from .page import render_page
from .segmenter import segment

EXIT_OK = 0
EXIT_INPUT = 1
EXIT_USAGE = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='wordcut', description='双向最大匹配分词与歧义消解')
    sub = parser.add_subparsers(dest='command', required=True)
    for name, help_text in (('cut', '切分并输出 TSV'), ('page', '生成切分结果页面')):
        p = sub.add_parser(name, help=help_text)
        p.add_argument('--dict', dest='dicts', action='append', required=True,
                       metavar='TSV', help='词典文件，可给多次，按顺序合并')
        p.add_argument('--input', required=True, metavar='TXT', help='正文文件')
        p.add_argument('--output', required=True, metavar='OUT', help='输出文件')
    return parser


def _write_output(path: str, content: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(content)


def _run(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    dictionary = load_dicts(args.dicts)
    with open(args.input, 'rb') as fh:
        raw = fh.read()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise DictError(f'{args.input}: 非法 UTF-8: {exc}') from exc
    tokens = segment(text, dictionary)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if args.command == 'cut':
        lines = []
        for start, end, _type, _freq in tokens:
            lines.append(f'{start}\t{end}\t{text[start:end]}\n')
        _write_output(args.output, ''.join(lines))
    else:
        html = render_page(text, tokens, dictionary,
                           args.input, args.dicts, elapsed_ms)
        _write_output(args.output, html)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (DictError, OSError) as exc:
        print(f'wordcut: {exc}', file=sys.stderr)
        return EXIT_INPUT


if __name__ == '__main__':
    sys.exit(main())
