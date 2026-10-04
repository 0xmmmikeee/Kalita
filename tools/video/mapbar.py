# Карта время-записи → время-страницы по ширине оранжевого прогресс-бара (верхние 6 px) в raw.webm.
import subprocess, json, numpy as np
tl=json.load(open('timeline.json')); TOTAL=tl['total']/1000
W,H=1920,1080; N=W*H*3; STEP=0.5
dec=subprocess.Popen(['ffmpeg','-v','error','-i','raw.webm','-vf',f'fps=1/{STEP}','-f','rawvideo','-pix_fmt','rgb24','-'],stdout=subprocess.PIPE,bufsize=N*2)
pts=[]; k=0
while True:
    buf=dec.stdout.read(N)
    if len(buf)<N: break
    fr=np.frombuffer(buf,np.uint8).reshape(H,W,3); row=fr[2]  # y=2 внутри бара
    orange=(row[:,0]>140)&(row[:,1]>60)&(row[:,1]<140)&(row[:,2]<90)
    w=int(orange.sum()); pts.append([k*STEP, w/W*TOTAL]); k+=1
json.dump(pts,open('map.json','w')); print('map points',len(pts),'last',pts[-1])
