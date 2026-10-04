#!/usr/bin/env bash
# Деплой KalitaRegistry + регистрация списков + право публикации для горячего ключа. Запускать на VPS:
#   NET=testnet bash deploy/registry-deploy.sh     (Robinhood Chain testnet 46630)
#   NET=mainnet bash deploy/registry-deploy.sh     (Robinhood Chain 4663)
# Нужны в /opt/wallet-lab/.env: KALITA_DEPLOYER_KEY (профинансирован), KALITA_PUBLISHER_KEY. Ничего не пишет в git.
set -eu
cd /opt/wallet-lab; set -a; . ./.env; set +a
export PATH=/opt/foundry:$PATH
NET=${NET:-testnet}
case $NET in
  testnet) RPC=https://rpc.testnet.chain.robinhood.com/rpc; EXPL=https://explorer.testnet.chain.robinhood.com;;
  mainnet) RPC=https://rpc.mainnet.chain.robinhood.com; EXPL=https://explorer.chain.robinhood.com;;
  *) echo "NET=testnet|mainnet"; exit 1;;
esac
DEP=$(cast wallet address --private-key "$KALITA_DEPLOYER_KEY"); PUB=$(cast wallet address --private-key "$KALITA_PUBLISHER_KEY")
BAL=$(cast balance "$DEP" --rpc-url $RPC --ether); echo "deployer $DEP balance $BAL ETH on $NET (chain $(cast chain-id --rpc-url $RPC))"
[ "$(python3 -c "print(float('$BAL')>0)")" = True ] || { echo "deployer has no gas — fund $DEP first"; exit 2; }
cd contracts
if [ -z "${KALITA_REGISTRY:-}" ]; then
  OUT=$(forge create src/KalitaRegistry.sol:KalitaRegistry --rpc-url $RPC --private-key "$KALITA_DEPLOYER_KEY" --broadcast --json)
  REG=$(echo "$OUT" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["deployedTo"])'); TX=$(echo "$OUT" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("transactionHash"))')
  echo "KalitaRegistry deployed: $REG  tx $TX  ($EXPL/address/$REG)"
  echo "KALITA_REGISTRY=$REG" >> ../.env; echo "KALITA_RPC=$RPC" >> ../.env; echo "KALITA_CHAIN=$NET" >> ../.env
else REG=$KALITA_REGISTRY; echo "registry already set: $REG"; fi
for p in fast picker; do
  v="KALITA_LIST_$(echo $p | tr a-z A-Z)"
  if [ -z "${!v:-}" ]; then
    id=$(cast call $REG "listCount()(uint256)" --rpc-url $RPC)
    cast send $REG "registerList(string,bytes32)" $p $(cast keccak "kalita-rules-v1-$p") --rpc-url $RPC --private-key "$KALITA_DEPLOYER_KEY" >/dev/null
    cast send $REG "setPublisher(uint256,address,bool)" $id $PUB true --rpc-url $RPC --private-key "$KALITA_DEPLOYER_KEY" >/dev/null
    echo "$v=$id" >> ../.env; echo "list $p registered as id $id, publisher $PUB allowed"
  fi
done
echo "done. next daily run publishes the first snapshot (or: bash deploy/registry-publish.sh)"
