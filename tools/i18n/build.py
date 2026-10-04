#!/usr/bin/env python3
"""Собирает src/i18n.js из tools/i18n/<lang>.py (T — строки, H — подсказки). Традиционный китайский (tw) выводится из zh
через s2tw.py (нужны словари OpenCC: git clone --depth 1 --sparse https://github.com/BYVoid/OpenCC и sparse-checkout data/dictionary
рядом с этим файлом)."""
import json, os, sys, importlib
here=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,here)
LANGS=[['en','English'],['zh','简体中文'],['tw','繁體中文'],['ko','한국어'],['ja','日本語'],['vi','Tiếng Việt'],['id','Bahasa Indonesia'],['ms','Bahasa Melayu'],['ru','Русский'],['de','Deutsch'],['fr','Français'],['es','Español']]
I18N={}; HELP={}
for code,_ in LANGS:
    if code in ('en','tw'): continue
    m=importlib.import_module(code); I18N[code]=m.T
    for k,v in m.H.items(): HELP.setdefault(k,{})[code]=v
keys=set(I18N['zh'])
for code,T in I18N.items():
    miss=keys-set(T); assert not miss, (code, miss)
try:
    from s2tw import s2tw
    I18N['tw']={k:s2tw(v) for k,v in I18N['zh'].items()}
    for k in HELP: HELP[k]['tw']=s2tw(HELP[k]['zh'])
except Exception as e:
    print('tw skipped:', e)
en=json.load(open(os.path.join(here,'help_en.json')))
for k,v in en.items(): HELP[k]['en']=v
order=[c for c,_ in LANGS if c in I18N]
out='// Словари интерфейса панели. Ключ — английская строка; en не переводится. Сгенерировано tools/i18n/build.py.\n'
out+='const I18N={\n'+',\n'.join(f'{l}:{json.dumps(I18N[l],ensure_ascii=False)}' for l in order)+'\n};\n'
out+='const HELP='+json.dumps(HELP,ensure_ascii=False)+';\n'
out+='const LANGS='+json.dumps([l for l in LANGS if l[0] in I18N or l[0]=='en'],ensure_ascii=False)+';\n'
open(os.path.join(here,'..','..','src','i18n.js'),'w').write(out); print('src/i18n.js', len(out))
