#!/usr/bin/env bash
# Тик автопилота (раз в минуту): подтянуть main → обновить приложение → запустить новые jobs/*.sh в фоне →
# опубликовать логи заданий в ветку agent-logs. Параллельные тики исключены через flock.
export HOME=/root; export GIT_SSH_COMMAND="ssh -o ConnectTimeout=20 -o BatchMode=yes"; SRC=/opt/wallet-lab-src; APP=/opt/wallet-lab; LOGS=$APP/state/agent-logs; DONE=$APP/state/jobs-done
mkdir -p $LOGS $DONE
exec 9>/run/wallet-lab-agent.lock; flock -n 9 || exit 0
cd $SRC || exit 1
timeout 90 git fetch -q origin main 2>>$LOGS/_agent.log || { echo "$(date -u +%FT%TZ) fetch failed" >> $LOGS/_agent.log; }
NEW=$(git rev-parse origin/main); CUR=$(git rev-parse HEAD)
if [ "$NEW" != "$CUR" ]; then
  CHANGED=$(git diff --name-only "$CUR" "$NEW" 2>/dev/null)
  git reset -q --hard origin/main
  rsync -a --exclude data --exclude state --exclude .git --exclude .env --exclude jobs "$SRC/" "$APP/"
  # перезапуск панели только если менялся её код (src/, package.json) — коммиты jobs/docs/site не должны ронять сессии
  if [ -z "$CHANGED" ] || echo "$CHANGED" | grep -qE '^(src/|package\.json)'; then systemctl restart wallet-lab 2>/dev/null; R=restart; else R=norestart; fi
  echo "$(date -u +%FT%TZ) updated to $NEW ($R)" >> $LOGS/_agent.log
fi
# задания: jobs/NAME.sh → выполняется один раз, в фоне; лог в agent-logs/NAME.log, код выхода в NAME.exit
for j in $SRC/jobs/*.sh; do
  [ -f "$j" ] || continue; n=$(basename "$j" .sh)
  [ -f "$DONE/$n" ] && continue; touch "$DONE/$n"
  echo "$(date -u +%FT%TZ) start job $n" >> $LOGS/_agent.log
  systemd-run --quiet --unit="wl-job-$n" --collect --working-directory=$APP \
    /bin/bash -c "set -a; [ -f .env ] && . ./.env; set +a; bash '$j' > '$LOGS/$n.log' 2>&1; echo \$? > '$LOGS/$n.exit'" \
    || echo "$(date -u +%FT%TZ) job $n: systemd-run failed" >> $LOGS/_agent.log
done
# публикация логов (последние 400 строк каждого) в ветку agent-logs — постоянный worktree, ошибки в _agent.log
PUB=/opt/wallet-lab-logs
if [ ! -e "$PUB/.git" ]; then
  for w in $(git -C $SRC worktree list --porcelain | awk '/^worktree \/tmp\/tmp\./{print $2}'); do git -C $SRC worktree remove -f "$w" 2>/dev/null; rm -rf "$w"; done; git -C $SRC worktree prune 2>/dev/null
  rm -rf "$PUB"
  git -C $SRC worktree add "$PUB" -B agent-logs >>$LOGS/_agent.log 2>&1 || git -C $SRC worktree add "$PUB" agent-logs >>$LOGS/_agent.log 2>&1 || echo "$(date -u +%FT%TZ) worktree add failed" >>$LOGS/_agent.log
fi
if [ -e "$PUB/.git" ]; then
  mkdir -p "$PUB/logs"; rm -f "$PUB/logs/"*
  for f in $LOGS/*; do [ -f "$f" ] && tail -n 400 "$f" > "$PUB/logs/$(basename "$f")"; done
  { echo "updated: $(date -u +%FT%TZ)"; echo "head: $(git rev-parse --short HEAD)"; systemctl is-active wallet-lab wallet-lab-daily.timer 2>/dev/null | tr '\n' ' '; echo
    ls $APP/data 2>/dev/null | head -50; echo "--- disk"; df -h / | tail -1; echo "--- running jobs"; systemctl list-units "wl-job-*" --no-legend 2>/dev/null; pgrep -af "jobs/" | grep -v pgrep; echo "--- logs dir"; ls -la $LOGS 2>&1; echo "--- done"; ls $DONE 2>&1; echo "--- journal"; for u in $(ls $DONE | tail -3); do echo "== $u"; systemctl status "wl-job-$u" --no-pager 2>&1 | head -12; journalctl -u "wl-job-$u" --no-pager -n 15 2>&1; done; } > "$PUB/logs/_status.txt"
  ( cd "$PUB" && git add -A -f logs && git -c user.email=agent@wallet-lab -c user.name=agent commit -qm "logs $(date -u +%FT%TZ)" >>$LOGS/_agent.log 2>&1; timeout 120 git push -q -f origin agent-logs >>$LOGS/_agent.log 2>&1 || echo "$(date -u +%FT%TZ) push logs failed: $?" >>$LOGS/_agent.log )
fi
# heartbeat (временно, для диагностики без доступа к серверу)
{ echo "head $(git rev-parse --short HEAD) tick $(date -u +%FT%TZ)"; echo "--- agent.log"; tail -n 8 $LOGS/_agent.log; echo "--- worktrees"; git -C $SRC worktree list; ls -la /opt/wallet-lab-logs 2>&1 | head -5; echo "--- 07"; tail -n 3 $LOGS/07-full-fetch.log 2>/dev/null; } > $APP/site/build.txt 2>&1
