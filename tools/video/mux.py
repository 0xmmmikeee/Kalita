# Голос по сценам (старт сцены + 0.5 с), музыкальная подложка с дакингом под голос, mux с -c:v copy.
import json, subprocess
tl=json.load(open('timeline.json')); T=tl['total']/1000+0.4
inputs=['-i','video.mp4','-i','music.wav']; fc=[]; n=2; voices=[]
for sc in tl['timeline']:
    inputs+=['-i',f"vo/{sc['id']}.wav"]; d=sc['start']+500
    fc.append(f"[{n}:a]adelay={d}|{d},aformat=sample_rates=48000:channel_layouts=stereo[v{n}]"); voices.append(f"[v{n}]"); n+=1
fc.append(''.join(voices)+f"amix=inputs={len(voices)}:normalize=0:dropout_transition=0,volume=1.0,asplit=2[voice][vkey]")
fc.append(f"[1:a]aloop=loop=-1:size=2e9,atrim=0:{T},aformat=sample_rates=48000:channel_layouts=stereo,volume=0.22,afade=t=out:st={T-3}:d=3[mus]")
fc.append("[mus][vkey]sidechaincompress=threshold=0.02:ratio=8:attack=40:release=600[musd]")
fc.append("[musd][voice]amix=inputs=2:normalize=0,alimiter=limit=0.95[a]")
cmd=['ffmpeg','-y','-v','error']+inputs+['-filter_complex',';'.join(fc),'-map','0:v','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-t',str(T),'out.mp4']
subprocess.run(cmd,check=True); print('muxed out.mp4')
