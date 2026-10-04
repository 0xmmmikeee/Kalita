# Генерирует director.html: сцены синхронизированы с длительностью озвучки; биты — по границам предложений.
import json, re
from lines import LINES
dur = json.load(open('dur.json'))
LEAD, TAIL = 500, 900   # мс до начала речи в сцене и после
def beats(k):
    """Смещения начала каждого предложения (мс) пропорционально длине текста."""
    s = [x for x in re.split(r'(?<=[.!?])\s+', LINES[k].strip()) if x]
    tot = sum(len(x) for x in s); t = 0; out = []
    for x in s: out.append(int(LEAD + dur[k]*1000*t/tot)); t += len(x)
    return out, int(LEAD + dur[k]*1000 + TAIL)
order = ['s1','s2','s3','s4','s5','s6','s7','s8','s9']
B = {k: beats(k) for k in order}
labels = {'s1':'','s2':'01 · The problem','s3':'02 · Kalita','s4':'03 · Method','s5':'04 · Panel','s6':'05 · Validation','s7':'06 · On chain','s8':'07 · Results','s9':''}
# биты: (scene, beatIndex, selector или JS)
html = open('director.tpl.html').read()
timeline = []; t = 0; total = 0
for k in order:
    bts, L = B[k]
    timeline.append({'id': k, 'start': t, 'len': L, 'beats': [t + b for b in bts], 'label': labels[k]}); t += L
total = t + 600
html = html.replace('__TIMELINE__', json.dumps(timeline)).replace('__TOTAL__', str(total))
open('director.html', 'w').write(html)
json.dump({'timeline': timeline, 'total': total}, open('timeline.json', 'w'))
print('total ms', total, [ (x['id'], x['start'], len(x['beats'])) for x in timeline])
