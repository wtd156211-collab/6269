"""切分结果页面：自包含 HTML，数据内联，脚本只渲染不重算。"""

from __future__ import annotations

import json

from .dictionary import Dictionary
from .segmenter import Token

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>wordcut 切分结果</title>
<style>
  :root {
    --c-dict-bg: #d8f3dc; --c-dict-fg: #1b4332;
    --c-latin-bg: #dbeafe; --c-latin-fg: #1e3a8a;
    --c-digit-bg: #ffedd5; --c-digit-fg: #7c2d12;
    --c-other-bg: #e5e7eb; --c-other-fg: #374151;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px; color: #111827;
    font-family: -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #f9fafb;
  }
  h1 { font-size: 20px; margin: 0 0 12px; }
  h2 { font-size: 15px; margin: 24px 0 8px; color: #374151; }
  .card {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 16px; margin-bottom: 16px;
  }
  #stats { display: flex; flex-wrap: wrap; gap: 8px 24px; font-size: 14px; }
  #stats .item b { font-weight: 600; margin-right: 4px; }
  #legend { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; font-size: 13px; }
  #legend .chip { display: inline-flex; align-items: center; gap: 6px; }
  #legend .swatch { width: 14px; height: 14px; border-radius: 3px; display: inline-block; }
  #text {
    white-space: pre-wrap; word-break: break-all;
    font-family: "SF Mono", Consolas, "Courier New", monospace;
    font-size: 15px; line-height: 2;
  }
  .tok { border-radius: 3px; padding: 1px 0; cursor: default; }
  .tok-dict  { background: var(--c-dict-bg);  color: var(--c-dict-fg); }
  .tok-latin { background: var(--c-latin-bg); color: var(--c-latin-fg); }
  .tok-digit { background: var(--c-digit-bg); color: var(--c-digit-fg); }
  .tok-other { background: var(--c-other-bg); color: var(--c-other-fg); }
  .tok:hover { outline: 2px solid #2563eb; }
  #tokens { border-collapse: collapse; width: 100%; font-size: 13px; }
  #tokens th, #tokens td {
    border: 1px solid #e5e7eb; padding: 4px 10px; text-align: left;
  }
  #tokens th { background: #f3f4f6; position: sticky; top: 0; }
  #tokens td.surface { font-family: monospace; }
  .table-wrap { max-height: 480px; overflow: auto; border-radius: 8px; }
</style>
</head>
<body>
<h1>wordcut 切分结果</h1>
<div class="card">
  <div id="stats"></div>
  <div id="legend"></div>
</div>
<h2>正文（悬停切分项查看起止偏移）</h2>
<div class="card"><div id="text"></div></div>
<h2>切分项</h2>
<div class="card table-wrap">
  <table id="tokens">
    <thead><tr><th>#</th><th>起始</th><th>结束</th><th>词面</th><th>类型</th></tr></thead>
    <tbody></tbody>
  </table>
</div>
<script type="application/json" id="segment-data">__SEGMENT_DATA__</script>
<script type="module">
const data = JSON.parse(document.getElementById('segment-data').textContent);

const TYPE_LABEL = { dict: '词典词', latin: '字母串', digit: '数字串', other: '其他' };
const TYPE_ORDER = ['dict', 'latin', 'digit', 'other'];

const stats = document.getElementById('stats');
const statItems = [
  ['输入', data.input],
  ['词典', data.dicts.join(', ')],
  ['词典词条', data.words],
  ['耗时', data.elapsed_ms + ' ms'],
  ['字符数', data.stats.chars],
  ['切分项', data.stats.tokens],
  ['单字项', data.stats.singles],
  ['未登录', data.stats.unknown],
];
for (const [label, value] of statItems) {
  const span = document.createElement('span');
  span.className = 'item';
  const b = document.createElement('b');
  b.textContent = label;
  span.append(b, document.createTextNode(String(value)));
  stats.append(span);
}

const legend = document.getElementById('legend');
for (const type of TYPE_ORDER) {
  const chip = document.createElement('span');
  chip.className = 'chip';
  const swatch = document.createElement('span');
  swatch.className = 'swatch tok-' + type;
  swatch.style.background = 'var(--c-' + type + '-bg)';
  swatch.style.outline = '1px solid var(--c-' + type + '-fg)';
  chip.append(swatch, document.createTextNode(TYPE_LABEL[type]));
  legend.append(chip);
}

const container = document.getElementById('text');
let cursor = 0;
for (const [start, end, surface, type] of data.tokens) {
  if (start > cursor) {
    container.append(document.createTextNode(data.text.slice(cursor, start)));
  }
  const span = document.createElement('span');
  span.className = 'tok tok-' + type;
  span.dataset.start = start;
  span.dataset.end = end;
  span.textContent = surface;
  span.title = '[' + start + ', ' + end + ')';
  container.append(span);
  cursor = end;
}
if (cursor < data.text.length) {
  container.append(document.createTextNode(data.text.slice(cursor)));
}

const tbody = document.querySelector('#tokens tbody');
data.tokens.forEach(([start, end, surface, type], index) => {
  const row = document.createElement('tr');
  for (const value of [index, start, end, surface, TYPE_LABEL[type]]) {
    const cell = document.createElement('td');
    cell.textContent = value;
    row.append(cell);
  }
  row.children[3].className = 'surface tok-' + type;
  tbody.append(row);
});
</script>
</body>
</html>
"""


def render_page(text: str, tokens: list[Token], dictionary: Dictionary,
                input_path: str, dict_paths: list[str], elapsed_ms: int) -> str:
    """生成自包含的结果页面；tokens 必须来自引擎输出。"""
    words = dictionary.words
    token_rows = []
    singles = 0
    unknown = 0
    for start, end, surface_type, _freq in tokens:
        surface = text[start:end]
        token_rows.append([start, end, surface, surface_type])
        if end - start == 1:
            singles += 1
        if surface not in words:
            unknown += 1
    data = {
        'input': input_path,
        'dicts': list(dict_paths),
        'words': len(words),
        'elapsed_ms': elapsed_ms,
        'text': text,
        'tokens': token_rows,
        'stats': {
            'chars': len(text),
            'tokens': len(tokens),
            'singles': singles,
            'unknown': unknown,
        },
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    payload = payload.replace('<', '\\u003c')
    return _TEMPLATE.replace('__SEGMENT_DATA__', payload)
