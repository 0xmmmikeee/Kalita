# быстрый кадр сцены: сдвигаем таймлайн так, чтобы сцена началась сразу
from playwright.sync_api import sync_playwright
import json,sys,time
tl=json.load(open('timeline.json')); html=open('director.html').read()
with sync_playwright() as pw:
    b=pw.chromium.launch(); pg=b.new_context(viewport={'width':1920,'height':1080}).new_page()
    for sid in sys.argv[1:]:
        sc=next(x for x in tl['timeline'] if x['id']==sid); off=sc['start']
        tl2={'timeline':[dict(x,start=x['start']-off,beats=[b-off for b in x['beats']]) for x in tl['timeline']]}
        h=html.replace(json.dumps(tl['timeline']),json.dumps(tl2['timeline']))
        open('director-chk.html','w').write(h); pg.goto('http://127.0.0.1:8899/director-chk.html'); pg.wait_for_timeout(int(sc['len']*0.85)); pg.screenshot(path=f'chk-{sid}.png'); print('shot',sid)
    b.close()
