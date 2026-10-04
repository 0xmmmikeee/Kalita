# Перевод записи (замедленной браузером) в реальное время сценария: по карте video_time -> page_time выбираем кадры.
import subprocess, numpy as np, json
pts=json.load(open('map.json')); TOTAL=json.load(open('timeline.json'))['total']/1000+0.4
vt=np.array([p[0] for p in pts]); pt=np.array([p[1] for p in pts])
pt=np.maximum.accumulate(pt)  # монотонно
FPS=30; W,H=1920,1080; N=W*H*3
dec=subprocess.Popen(['ffmpeg','-v','error','-i','raw.webm','-vf',f'fps={FPS}','-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,bufsize=N*4)
enc=subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p','video.mp4'],stdin=subprocess.PIPE)
k=0; i=0; cur=None; written=0
while True:
    p=k/FPS
    if p>TOTAL: break
    tau=float(np.interp(p,pt,vt))  # нужное время в записи
    need=int(round(tau*FPS))
    while i<=need:
        buf=dec.stdout.read(N)
        if len(buf)<N: buf=None; break
        cur=buf; i+=1
    if cur is None: break
    enc.stdin.write(cur); written+=1; k+=1
enc.stdin.close(); enc.wait(); dec.kill(); print('frames',written, written/FPS,'s')
