#!/usr/bin/env bash
set -e; cd "$(dirname "$0")"
python3 gen.py
(python3 -m http.server 8899 >/dev/null 2>&1 &) ; sleep 1
rm -rf rec raw.webm; python3 render.py
kill $(pgrep -f "http.server 8899") 2>/dev/null || true
python3 mapbar.py && python3 remap.py && python3 mux.py
ffprobe -v error -show_entries format=duration -of csv=p=0 out.mp4
