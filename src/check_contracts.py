#!/usr/bin/env python3
"""wallet-lab · проверка адресов: контракт или обычный кошелёк (eth_getCode пачками через JSON-RPC).
Результат кэшируется в state/contracts.json и используется скорингом (flag=contract).

  python3 src/check_contracts.py data/scores state/contracts.json [--rpc URL] [--max N]
Проверяются кандидаты обоих профилей с n>=5 (сначала по рангу), ещё не проверенные.
"""
import sys, os, json, time, urllib.request, pandas as pd
SCORES, OUT = sys.argv[1], sys.argv[2]
arg = lambda k, d: next((a.split('=', 1)[1] for a in sys.argv if a.startswith('--' + k + '=')), d)
RPC = arg('rpc', os.environ.get('RPC_URL', 'https://rpc.mainnet.chain.robinhood.com').split(',')[0])
MAX = int(arg('max', '4000')); BATCH = 40
cache = json.load(open(OUT)) if os.path.exists(OUT) else {}
todo = []
for p in ('fast', 'picker'):
    f = f'{SCORES}/scores_{p}.csv'
    if not os.path.exists(f): continue
    df = pd.read_csv(f)
    for w in df[df.n >= 5].sort_values('score', ascending=False).wallet:
        w = str(w).lower()
        if w not in cache and w not in todo: todo.append(w)
todo = todo[:MAX]
print(f'к проверке: {len(todo)}, в кэше: {len(cache)}', flush=True)

def rpc_batch(addrs):
    body = [{'jsonrpc': '2.0', 'id': i, 'method': 'eth_getCode', 'params': [a, 'latest']} for i, a in enumerate(addrs)]
    req = urllib.request.Request(RPC, data=json.dumps(body).encode(), headers={'content-type': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r: res = json.loads(r.read())
    out = {}
    for item in res:
        if 'result' in item: out[addrs[item['id']]] = (item['result'] not in ('0x', '', None))
    return out

n_ok = 0
for i in range(0, len(todo), BATCH):
    chunk = todo[i:i + BATCH]
    for attempt in range(5):
        try:
            got = rpc_batch(chunk); break
        except Exception as e:
            wait = 5 * (attempt + 1); print(f'  retry {attempt+1}: {str(e)[:80]} — жду {wait}s', flush=True); time.sleep(wait); got = {}
    for a, is_c in got.items(): cache[a] = {'contract': bool(is_c), 'at': int(time.time())}
    n_ok += len(got)
    if (i // BATCH) % 10 == 0:
        json.dump(cache, open(OUT, 'w')); print(f'  {i+len(chunk)}/{len(todo)} проверено, контрактов всего {sum(1 for v in cache.values() if v["contract"])}', flush=True)
    time.sleep(0.3)
json.dump(cache, open(OUT, 'w'))
print(f'готово: проверено {n_ok}, в кэше {len(cache)}, контрактов {sum(1 for v in cache.values() if v["contract"])}')
