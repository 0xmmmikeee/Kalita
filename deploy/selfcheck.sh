#!/usr/bin/env bash
# Самопроверка раз в 2 минуты: сайты через публичный IP и Caddy, панель напрямую. 3 подряд провала → перезапуск Caddy / панели.
S=/opt/wallet-lab/state/selfcheck; mkdir -p $S; L=$S/log; F=$S/fails
ok=1; line="$(date -u +%FT%TZ)"
for h in kalita.tech app.kalita.tech; do
  r=$(curl -sk -o /dev/null -m 12 -w "%{http_code} %{time_total}" --resolve $h:443:159.65.2.155 https://$h/ 2>/dev/null || echo "000 12")
  set -- $r; line="$line $h=$1/${2}s"; case $1 in 200|30[0-9]) ;; *) ok=0;; esac
done
p=$(curl -s -o /dev/null -m 8 -w "%{http_code} %{time_total}" http://127.0.0.1:8830/api/summary 2>/dev/null || echo "000 8"); set -- $p; line="$line panel=$1/${2}s"; [ "$1" = 200 ] || ok=0
echo "$line ok=$ok" >> $L; tail -n 2000 $L > $L.tmp && mv $L.tmp $L
if [ $ok = 1 ]; then echo 0 > $F; exit 0; fi
n=$(( $(cat $F 2>/dev/null || echo 0) + 1 )); echo $n > $F
if [ $n -ge 3 ]; then echo "$(date -u +%FT%TZ) 3 fails → restart caddy + wallet-lab" >> $L; systemctl restart caddy; systemctl restart wallet-lab; echo 0 > $F; fi
