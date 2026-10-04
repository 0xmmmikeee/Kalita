#!/usr/bin/env bash
# Автопилот wallet-lab на VPS: сервер сам подтягивает код из GitHub раз в минуту,
# выполняет задания из jobs/*.sh и публикует их логи в ветку agent-logs.
# Запуск (один раз): bash /opt/wallet-lab-src/deploy/agent-setup.sh
set -euo pipefail
REPO="${1:-git@github.com-walletlab:0xmmmikeee/wallet-lab.git}"
SRC=/opt/wallet-lab-src; APP=/opt/wallet-lab; KEY=/root/.ssh/wallet_lab_deploy
mkdir -p /root/.ssh $APP/state/jobs-done $APP/data; chmod 700 /root/.ssh
[ -f $KEY ] || ssh-keygen -t ed25519 -N '' -C 'wallet-lab-agent' -f $KEY -q
grep -q 'github.com-walletlab' /root/.ssh/config 2>/dev/null || cat >> /root/.ssh/config <<CFG
Host github.com-walletlab
  HostName github.com
  User git
  IdentityFile $KEY
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
CFG
chmod 600 /root/.ssh/config
command -v git >/dev/null || apt-get install -y -q git >/dev/null
git config --global user.email 'agent@wallet-lab' ; git config --global user.name 'wallet-lab agent'
if [ ! -d $SRC/.git ]; then
  # превращаем скопированную папку в клон репозитория (файлы data/state в ней не хранятся)
  tmp=$(mktemp -d); if git clone -q "$REPO" "$tmp/r" 2>/dev/null; then rm -rf "$SRC"; mv "$tmp/r" "$SRC"; else
    echo; echo "!!! Клонирование не удалось — ключ ещё не добавлен в GitHub. Добавь ключ ниже (Settings → Deploy keys → Add, с галочкой Allow write access) и запусти скрипт ещё раз."; fi
fi
cat > /etc/systemd/system/wallet-lab-agent.service <<UNIT
[Unit]
Description=wallet-lab agent tick
[Service]
Type=oneshot
ExecStart=/bin/bash $SRC/deploy/agent-tick.sh
UNIT
cat > /etc/systemd/system/wallet-lab-agent.timer <<UNIT
[Unit]
Description=wallet-lab agent (every minute)
[Timer]
OnBootSec=30
OnUnitActiveSec=60
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload; systemctl enable --now wallet-lab-agent.timer
echo; echo "=== ПУБЛИЧНЫЙ КЛЮЧ (добавить в GitHub → wallet-lab → Settings → Deploy keys, Allow write access) ==="; cat $KEY.pub; echo "==="
[ -d $SRC/.git ] && echo "автопилот включён: $SRC, тик раз в минуту" || echo "после добавления ключа: bash $SRC/deploy/agent-setup.sh"
