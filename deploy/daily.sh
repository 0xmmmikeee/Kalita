#!/usr/bin/env bash
# Ежедневно: дозагрузить поток → паспорта → скоринг → применить правила → экспорт.
set -euo pipefail
cd /opt/wallet-lab
[ -f .env ] && set -a && . ./.env && set +a
python3 src/fetch_stream.py --out data/stream --days "${WL_DAYS:-30}" || echo "fetch_stream: пропуск (нет ключа или сети)"
SRC=data/stream; [ -s $SRC/tokens.json ] || SRC="${WL_SOURCE_FALLBACK:-data/launchpad-cache.json}"
python3 src/build_passports.py "$SRC" data/signals.csv
python3 src/score_wallets.py data/signals.csv data/scores
python3 src/check_contracts.py data/scores state/contracts.json --max=1500 || echo 'check_contracts: пропуск'
python3 src/score_wallets.py data/signals.csv data/scores   # повторно — с учётом контрактов
python3 src/compare_lists.py data/signals.csv data/scores lists data/scores/lists.json || true
LOC="x-wl-local: $(cat state/auth-secret 2>/dev/null)"
curl -s -X POST -H "$LOC" localhost:8830/api/reload >/dev/null || true
for p in fast picker; do curl -s -X POST -H "$LOC" localhost:8830/api/apply -H 'content-type: application/json' -d "{\"profile\":\"$p\",\"by\":\"daily\"}" >/dev/null || true; done
curl -s -H "$LOC" localhost:8830/export/fast.txt > data/export_fast.txt; curl -s -H "$LOC" localhost:8830/export/picker.txt > data/export_picker.txt
# снимки списков для KalitaRegistry: корень + доказательства (публично на kalita.tech/registry/), при наличии ключа — публикация в чейн
bash deploy/registry-publish.sh || echo "registry: пропуск"
echo "daily ok $(date -u +%FT%TZ)"
# публичная страница результатов из docs/RESULTS.md
python3 tools/results_page.py docs/RESULTS.md site/results/index.html || echo "results page: пропуск"
