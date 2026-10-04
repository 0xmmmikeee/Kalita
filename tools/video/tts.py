import subprocess, json, wave, os
from lines import LINES
P=os.environ.get('PIPER','/tmp/piper/piper/piper'); M=os.environ.get('PIPER_VOICE','/tmp/piper/en-us-ryan-high.onnx')
os.makedirs('vo',exist_ok=True); d={}
for k,t in LINES.items():
    subprocess.run([P,'-m',M,'-f',f'vo/{k}.wav','--length_scale','1.05','--sentence_silence','0.35'],input=t.encode(),check=True,capture_output=True)
    w=wave.open(f'vo/{k}.wav'); d[k]=w.getnframes()/w.getframerate()
json.dump(d,open('dur.json','w')); print(d, sum(d.values()))
