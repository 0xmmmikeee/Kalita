# Скриншоты живой панели и сайта для видео (запускается на VPS: python3 tools/video/shots.py OUT_DIR COOKIE)
import sys, os
from playwright.sync_api import sync_playwright
out, cookie = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
W, H = 1680, 1000
with sync_playwright() as pw:
    b = pw.chromium.launch(); ctx = b.new_context(viewport={'width': W, 'height': H}, device_scale_factor=1)
    ctx.add_cookies([{'name': 'wl_sess', 'value': cookie, 'domain': '127.0.0.1', 'path': '/'}])
    pg = ctx.new_page(); pg.goto('http://127.0.0.1:8830/'); pg.wait_for_timeout(2500)
    def shot(name, wait=1500):
        pg.wait_for_timeout(wait); pg.screenshot(path=f'{out}/{name}.png'); print('shot', name)
    shot('overview', 3000)
    pg.evaluate("localStorage.setItem('wl-cols','all')")
    for tab in ['cand', 'active', 'log', 'rej', 'lists', 'rules', 'my']:
        try:
            pg.evaluate(f"goTab('{tab}')"); shot(f'tab-{tab}', 3500)
        except Exception as e: print('tab', tab, 'err', str(e)[:100])
    # карточка кошелька: первый адрес в кандидатах
    try:
        pg.evaluate("goTab('cand')"); pg.wait_for_timeout(3000)
        pg.evaluate("card('0xa60e892ab5fbf4754e3052b7643e48a1bd6b3065')"); shot('wallet-card', 4000)
        pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    except Exception as e: print('card err', str(e)[:100])
    try:
        pg.evaluate("showGuide()"); shot('guide', 1200); pg.keyboard.press('Escape'); pg.wait_for_timeout(500)
    except Exception as e: print('guide err', str(e)[:100])
    # язык: японский и корейский
    for lang in ['ja', 'ko', 'zh']:
        try:
            pg.evaluate(f"localStorage.setItem('wl-lang','{lang}')"); pg.reload(); pg.wait_for_timeout(3000); pg.evaluate("goTab('cand')"); shot(f'lang-{lang}', 3500)
        except Exception as e: print('lang', lang, 'err', str(e)[:100])
    pg.evaluate("localStorage.setItem('wl-lang','en')")
    # публичные страницы через Caddy (по localhost с Host)
    for name, url in [('site', 'https://kalita.tech/'), ('results', 'https://kalita.tech/results/'), ('registry', 'https://kalita.tech/registry/')]:
        try:
            p2 = ctx.new_page(); p2.goto(url); p2.wait_for_timeout(2500); p2.screenshot(path=f'{out}/{name}.png', full_page=True); print('shot', name); p2.close()
        except Exception as e: print(name, 'err', str(e)[:120])
    b.close()
