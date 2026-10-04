#!/usr/bin/env bash
# Установка Wallet Lab на VPS (Ubuntu 22/24). Запуск: sudo bash deploy/setup.sh <host>
# <host> — имя хоста для Caddy, например wallets.159-65-2-155.sslip.io
set -euo pipefail
HOST="${1:?host}"; APP=/opt/wallet-lab; SRC="$(cd "$(dirname "$0")/.." && pwd)"
apt-get install -y -q python3-pandas python3-numpy >/dev/null 2>&1 || pip3 install -q pandas numpy
command -v node >/dev/null || { curl -fsSL https://deb.nodesource.com/setup_20.x | bash -; apt-get install -y nodejs; }
mkdir -p $APP/data/scores $APP/state; rsync -a --exclude data --exclude state --exclude .git "$SRC/" $APP/; [ -f $APP/.env ] || cp $APP/.env.example $APP/.env
if [ ! -f $APP/state/.htpasswd ]; then read -rp "логин для панели: " U; read -rsp "пароль: " P; echo; H=$(caddy hash-password --plaintext "$P"); echo "$U $H" > $APP/state/.htpasswd; fi
read -r U H < $APP/state/.htpasswd
cat > /etc/systemd/system/wallet-lab.service <<UNIT
[Unit]
Description=Wallet Lab
After=network.target
[Service]
WorkingDirectory=$APP
Environment=WL_PORT=8830 WL_HOST=127.0.0.1 WL_DATA=$APP/data WL_STATE=$APP/state WL_SOURCE=$APP/data/stream.json
ExecStart=/usr/bin/node src/server.js
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
# ежедневный пересчёт (демон): 03:17 UTC
cat > /etc/systemd/system/wallet-lab-daily.service <<UNIT
[Unit]
Description=Wallet Lab daily recompute
[Service]
Type=oneshot
WorkingDirectory=$APP
ExecStart=/bin/bash $APP/deploy/daily.sh
UNIT
cat > /etc/systemd/system/wallet-lab-daily.timer <<UNIT
[Unit]
Description=Wallet Lab daily timer
[Timer]
OnCalendar=*-*-* 03:17:00
Persistent=true
[Install]
WantedBy=timers.target
UNIT
# Caddy: отдельный блок с basic auth
CADDY=/etc/caddy/Caddyfile
if ! grep -q "$HOST" $CADDY; then cat >> $CADDY <<CFG

$HOST {
	basic_auth {
		$U $H
	}
	reverse_proxy 127.0.0.1:8830
	encode gzip
}
CFG
fi
systemctl daemon-reload; systemctl enable --now wallet-lab wallet-lab-daily.timer; systemctl reload caddy
echo "готово: https://$HOST  (панель); данные: $APP/data, состояние: $APP/state"
