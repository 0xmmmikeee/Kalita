# Demo video pipeline (voice-over cut)

0. `build.sh` runs the whole pipeline; `shots.py` (on the server) captures the live panel into branch `shots`; `lines-short.py` is the short cut, `lines-v2.py`/`director-v2.tpl.html` the previous version.
1. `lines.py` — the narration, one entry per scene. `python3 tts.py` → `vo/sN.wav` (piper, voice `en-us-ryan-high`) and `dur.json`.
2. `gen.py` — builds `director.html` from `director.tpl.html`: every scene lasts as long as its narration; beats (captions, count-ups, screenshots) are placed at sentence boundaries.
3. Assets next to the template: `Manrope.ttf`, `Fraunces.ttf`, `mark.svg`, `site.html` (landing with local fonts), `registry/` (registry page + a real snapshot `index.json`), `shot-*.png` (panel screenshots — take them from a local server fed with the data snapshot from job 23).
4. `python3 -m http.server 8899` in this folder, then `render.py` (Playwright records `raw.webm`; headless Chromium records slower than real time) → `remap.py` (reads the progress bar to map recording time back to script time → `video.mp4`).
5. Audio: voice clips placed at each scene's start + 0.5 s, music bed (`music.wav`, synthesized pad) side-chain-ducked under the voice; mux with `-c:v copy`.

`chk2.py s7` renders a still of one scene at 85 % of its length for a quick look.
