#!/usr/bin/env bash
# Снимок каждого списка → data/registry/*.json (и копия в site/registry/), затем publishSnapshot в KalitaRegistry,
# если заданы KALITA_REGISTRY (адрес контракта), KALITA_RPC, KALITA_PUBLISHER_KEY и id списков (KALITA_LIST_FAST / KALITA_LIST_PICKER).
# Ключ публикации — отдельный «горячий» адрес с правом setPublisher, не владелец.
set -u
cd /opt/wallet-lab; [ -f .env ] && set -a && . ./.env && set +a
mkdir -p data/registry site/registry
rebuild_index(){ python3 - <<'PY'
import json,glob,os
out=[]
log={}
try:
    for l in open("state/registry.log"):
        p=l.split()
        if len(p)>=9: log[(p[1],p[6])]=p[8]
except Exception: pass
for f in sorted(glob.glob("site/registry/*-*.json")):
    if f.endswith("latest.json"): continue
    try: j=json.load(open(f))
    except Exception: continue
    out.append({"file":os.path.basename(f),"profile":j["profile"],"asOf":j["asOf"],"size":j["size"],"added":j["added"],"removed":j["removed"],"root":j["root"],"tx":log.get((j["profile"],str(j["asOf"])))})
json.dump(out,open("site/registry/index.json","w"))
print("index:",len(out))
PY
}
AS_OF=$(date -u +%s)
for p in fast picker; do
  out=$(python3 src/registry_snapshot.py state/active.json --profile $p --out data/registry --as-of $AS_OF 2>&1) || { echo "$p: $out"; continue; }
  echo "$out" | head -2
  cp data/registry/${p}-*.json site/registry/ 2>/dev/null
  idvar="KALITA_LIST_$(echo $p | tr a-z A-Z)"; id="${!idvar:-}"
  if [ -n "${KALITA_REGISTRY:-}" ] && [ -n "${KALITA_PUBLISHER_KEY:-}" ] && [ -n "$id" ] && command -v cast >/dev/null; then
    args=$(echo "$out" | sed -n 's/^publishSnapshot args: <id> //p')
    # args: root size added removed asOf "uri"
    eval set -- $args
    tx=$(cast send "$KALITA_REGISTRY" "publishSnapshot(uint256,bytes32,uint32,uint32,uint32,uint64,string)" "$id" "$1" "$2" "$3" "$4" "$5" "$6" \
         --rpc-url "${KALITA_RPC:-https://rpc.mainnet.chain.robinhood.com}" --private-key "$KALITA_PUBLISHER_KEY" --json 2>&1 | python3 -c 'import sys,json
try: d=json.load(sys.stdin); print(d.get("transactionHash"))
except Exception: print("ERR", sys.stdin.read()[:300])')
    echo "$p: on-chain $tx"; echo "$(date -u +%FT%TZ) $p $id $1 $2 $3 $4 $5 $tx" >> state/registry.log
  else
    echo "$p: без публикации в чейн (нет KALITA_REGISTRY/KEY/id или cast)"
  fi
done
rebuild_index
