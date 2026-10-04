# Стоп-кадры сцен на 85% длины: страница открывается с смещением через параметр ?t= (инжект performance.now offset нельзя) — просто ждём.
from playwright.sync_api import sync_playwright
import json,time,sys
tl=json.load(open('timeline.json')); ids=sys.argv[1:]
with sync_playwright() as pw:
    b=pw.chromium.launch(); ctx=b.new_context(viewport={'width':1920,'height':1080}); pg=ctx.new_page()
    pg.goto('http://127.0.0.1:8899/director.html'); t0=time.time()
    for sc in tl['timeline']:
        if sc['id'] not in ids: continue
        mid=sc['start']+sc['len']*0.85
        while (time.time()-t0)*1000<mid: time.sleep(0.05)
        pg.screenshot(path=f"chk-{sc['id']}.png"); print('shot',sc['id'], round(time.time()-t0,1))
    b.close()
