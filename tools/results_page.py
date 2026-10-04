#!/usr/bin/env python3
"""docs/RESULTS.md → site/results/index.html (public results page in the site's light theme).
Minimal Markdown: #/##/### headings, paragraphs, - lists, | tables |, **bold**, *italic*, `code`.
  python3 tools/results_page.py docs/RESULTS.md site/results/index.html"""
import sys, re, html, datetime as dt
src, dst = sys.argv[1], sys.argv[2]
def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s); s = re.sub(r'(?<!\*)\*(?!\*)(.+?)\*(?!\*)', r'<i>\1</i>', s); s = re.sub(r'`(.+?)`', r'<code>\1</code>', s)
    return s
out = []; para = []; lst = []; tbl = []; olst = []
def flush():
    global para, lst, tbl, olst
    if olst: out.append('<ol>' + ''.join(f'<li>{inline(x)}</li>' for x in olst) + '</ol>'); olst = []
    if para: out.append('<p>' + inline(' '.join(para)) + '</p>'); para = []
    if lst: out.append('<ul>' + ''.join(f'<li>{inline(x)}</li>' for x in lst) + '</ul>'); lst = []
    if tbl:
        rows = [[c.strip() for c in r.strip().strip('|').split('|')] for r in tbl if not re.match(r'^\|?\s*-{2,}', r.strip())]
        if rows:
            h = rows[0]; body = rows[1:]
            num = lambda c: bool(re.match(r'^[+\-−]?[\d.,]+\s*(%|s)?$|^—$|^×', c.strip()))
            out.append('<div class="card tbl"><table><thead><tr>' + ''.join(f'<th>{inline(c)}</th>' for c in h) + '</tr></thead><tbody>' +
                       ''.join('<tr>' + ''.join(f'<td class="{"r" if num(c) else ""}">{inline(c)}</td>' for c in r) + '</tr>' for r in body) + '</tbody></table></div>')
        tbl = []
title = 'Results'
for line in open(src, encoding='utf8'):
    line = line.rstrip('\n')
    if line.startswith('|'): para and flush(); tbl.append(line); continue
    if tbl and not line.startswith('|'): flush()
    m = re.match(r'^(#{1,3})\s+(.*)', line)
    if m:
        flush(); lvl = len(m.group(1)); txt = m.group(2)
        if lvl == 1: title = txt; continue
        out.append(f'<h{lvl}>{inline(txt)}</h{lvl}>'); continue
    if line.startswith('- '): para and flush(); lst.append(line[2:]); continue
    mo = re.match(r'^\d+\.\s+(.*)', line)
    if mo: para and flush(); olst.append(mo.group(1)); continue
    if not line.strip(): flush(); continue
    if lst: lst[-1] += ' ' + line.strip(); continue
    if olst: olst[-1] += ' ' + line.strip(); continue
    para.append(line.strip())
flush()
page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kalita — results</title><link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;800&display=swap" rel="stylesheet">
<style>
:root{{--bg:#F4EFE6;--card:#FFFDF9;--ink:#17161A;--mut:#6B6873;--line:#DED9D0;--acc:#B5602B}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15.5px/1.55 Manrope,system-ui,sans-serif}}
.wrap{{max-width:960px;margin:0 auto;padding:40px 24px 80px}}
nav{{display:flex;align-items:center;gap:12px;margin-bottom:36px}}nav b{{font-size:22px;font-weight:800;letter-spacing:-.04em}}nav a{{color:var(--mut);text-decoration:none;margin-left:auto}}
h1{{font-size:40px;font-weight:800;letter-spacing:-.03em;line-height:1.05;margin:0 0 12px}}h2{{font-size:24px;margin:40px 0 12px;letter-spacing:-.02em}}h3{{font-size:17px;margin:26px 0 8px;color:var(--acc)}}
p{{max-width:780px}}ul,ol{{max-width:780px;padding-left:22px}}li{{margin:4px 0}}code{{font-family:ui-monospace,Menlo,monospace;font-size:13px;background:#EFE9DD;padding:1px 5px;border-radius:5px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:6px 12px;margin:14px 0;overflow:auto}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}th,td{{padding:8px 8px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}th{{color:var(--mut);font-size:11.5px;text-transform:uppercase;letter-spacing:.05em}}td.r{{text-align:right;font-variant-numeric:tabular-nums}}tr:last-child td{{border-bottom:0}}
.small{{font-size:13px;color:var(--mut)}}
</style></head><body><div class="wrap">
<nav><svg width="30" height="30" viewBox="0 0 64 64"><circle cx="32" cy="32" r="25" fill="none" stroke="#17161A" stroke-width="6"/><path d="M32 9 40 32 32 34.5 24 32Z" fill="#B5602B"/><path d="M32 55 24 32 32 34.5 40 32Z" fill="#17161A"/><circle cx="32" cy="32" r="3.5" fill="#F4EFE6"/></svg><b>kalita</b><a href="/">← kalita.tech</a></nav>
<h1>{inline(title)}</h1>
<p class="small">Generated from <code>docs/RESULTS.md</code> on {dt.datetime.utcnow():%d %b %Y %H:%M} UTC. Negative results are published too.</p>
{chr(10).join(out)}
</div></body></html>'''
import os; os.makedirs(os.path.dirname(dst), exist_ok=True); open(dst, 'w', encoding='utf8').write(page); print(dst, len(page))
