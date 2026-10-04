import os, glob, shutil, subprocess, json
from playwright.sync_api import sync_playwright
tl=json.load(open('timeline.json'))
with sync_playwright() as pw:
    b=pw.chromium.launch(); ctx=b.new_context(viewport={'width':1920,'height':1080},record_video_dir='rec',record_video_size={'width':1920,'height':1080})
    pg=ctx.new_page(); pg.goto('http://127.0.0.1:8899/director.html'); pg.wait_for_timeout(tl['total']+400); pg.close(); ctx.close(); b.close()
v=glob.glob('rec/*.webm')[0]; shutil.move(v,'raw.webm'); print('recorded')
