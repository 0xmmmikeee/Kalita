#!/usr/bin/env python3
"""wallet-lab · выгрузка полного потока Pons v2 (Robinhood Chain, chain 4663).

Читает логи четырёх событий по topic0 (без привязки к адресам кривых) и собирает файл в формате
launchpad-cache.json движка scout-bot (series: [block, logIndex, ts, price, mode, quoteAmt, wallet, buyer]),
дополненный полями pairToken, gradThreshold, deployer. Инкрементально: хранит последний блок в <out>.state.json.

Источники:
  --source hypersync   (по умолчанию) Envio HyperSync, токен в переменной HYPERSYNC_TOKEN. Один запрос = тысячи блоков.
  --source rpc         JSON-RPC eth_getLogs (RPC_URL, например Alchemy PAYG), чанками по --chunk блоков.

Примеры:
  HYPERSYNC_TOKEN=... python3 src/fetch_stream.py --out data/stream.json --days 30
  RPC_URL=https://robinhood-mainnet.g.alchemy.com/v2/KEY python3 src/fetch_stream.py --source rpc --out data/stream.json --days 7
"""
import argparse, json, os, sys, time, gzip, urllib.request

HS_URL = os.environ.get('HYPERSYNC_URL', 'https://robinhood.hypersync.xyz')
TOPICS = {
    'launch': '0x8d4aad4953d0ca700d468f3753aa14432d1b35b43ec6409f051fb6aa43a89607',  # TokenLaunched(token,curve,deployer,pairToken,launchConfigId,graduationThreshold)
    'buy':    '0xec36bf571f136799e8dc0b0b8bea4b04d8bd3d43de838aab0d5fc21d4cbfc455',  # CurveBuy(buyer,recipient,quoteIn,tokensOut,fee,tax)
    'sell':   '0x8113d738abdcb6b38357e9d53a54a7157861a09031b453651f0fe7fe151f59df',  # CurveSell(seller,recipient,tokensIn,quoteOut,fee,tax)
    'grad':   '0x0a44ef75df69c534f43cd6c1aa3ef8983065fe5fe79ef9e79f6494e6f258c259',  # PoolGraduated(token,positionId,tokenAmount,pairTokenAmount)
}
T2K = {v: k for k, v in TOPICS.items()}
FACTORY = '0x7ed598bcef8bd9edd8c97a195c6d13f40801ec7e'
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
# Роутеры, которые получают токены с кривой и в той же транзакции пересылают их пользователю.
# Для таких покупок настоящий получатель берётся из Transfer(router → user) в том же tx.
ROUTERS = {'0x65050a9b7e5075a2ba5ced7b1b64ee66262c40dc'}
# Uniswap v4 PoolManager: после графуации ликвидность живёт здесь. Initialize(id,currency0,currency1,fee,tickSpacing,hooks,sqrtPriceX96,tick)
# даёт poolId по адресу токена; Swap(id,sender,amount0,amount1,sqrtPriceX96,liquidity,tick,fee) — цену после миграции.
POOL_MANAGER = '0x8366a39cc670b4001a1121b8f6a443a643e40951'
INIT_V4 = '0xdd466e674ea557f56295e2d0218a125ea4b4f0f6f3307b95f85e6110838d6438'
SWAP_V4 = '0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f'
def i256(x): return x - (1 << 256) if x >> 255 else x
def v4_price(data):
    """(price token1/token0 в сырых единицах, amount0, amount1) из data события Swap v4."""
    w = words(data)
    if len(w) < 3: return None, 0, 0
    sp = w[2] / 2 ** 96; return (sp * sp if sp > 0 else None), i256(w[0]), i256(w[1])
def pad(a): return '0x' + '0' * 24 + a[2:].lower()
BLOCK_SEC = 0.1
LOG = lambda *a: print(time.strftime('%H:%M:%S'), *a, file=sys.stderr, flush=True)

def addr(topic): return '0x' + topic[-40:].lower()
def words(data):
    d = data[2:] if data.startswith('0x') else data
    return [int(d[i:i+64], 16) for i in range(0, len(d), 64)]

def http_json(url, payload=None, headers=None, retries=6):
    for a in range(retries):
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                                         headers=dict({'content-type': 'application/json', 'accept-encoding': 'gzip'}, **(headers or {})))
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read()
                if (r.headers.get('content-encoding') or '').lower() == 'gzip': raw = gzip.decompress(raw)
                return json.loads(raw)
        except Exception as e:
            if a == retries - 1: raise
            msg = str(e); LOG('retry', a + 1, url[:60], msg[:120])
            time.sleep(1 if 'IncompleteRead' in msg else (10 * (a + 1) if '429' in msg else 2 * (a + 1)))

# ---------- sources ----------
def hs_height():
    return int(http_json(HS_URL + '/height')['height'])

def hs_iter(from_block, to_block, token, pools=True, curve=True):
    """HyperSync: yields (logs, blocks_ts_map) batches. pools — добавить логи PoolManager (Initialize, Swap v4)."""
    hdr = {'authorization': 'Bearer ' + token} if token else {}
    sel = ([{'topics': [list(TOPICS.values())]}] if curve else []) + ([{'address': [POOL_MANAGER], 'topics': [[INIT_V4, SWAP_V4]]}] if pools else [])
    q = {'from_block': from_block, 'to_block': to_block + 1, 'max_num_logs': int(os.environ.get('HS_MAX_LOGS', '8000')),
         'logs': sel,
         'field_selection': {'log': ['address', 'data', 'topic0', 'topic1', 'topic2', 'topic3', 'block_number', 'log_index', 'transaction_hash'],
                             'block': ['number', 'timestamp']}}
    cur = from_block
    while cur <= to_block:
        q['from_block'] = cur
        r = http_json(HS_URL + '/query', q, hdr)
        logs, bts = [], {}
        for part in r.get('data', []):
            for b in part.get('blocks', []): bts[int(b['number'])] = int(b['timestamp'], 16) if isinstance(b['timestamp'], str) else int(b['timestamp'])
            for l in part.get('logs', []):
                logs.append(dict(address=l['address'].lower(), data=l['data'], topics=[t for t in (l.get('topic0'), l.get('topic1'), l.get('topic2'), l.get('topic3')) if t],
                                 bn=int(l['block_number']), li=int(l['log_index']), tx=(l.get('transaction_hash') or '').lower()))
        nxt = int(r.get('next_block', cur + 1))
        yield logs, bts, nxt - 1
        if nxt <= cur: nxt = cur + 1
        cur = nxt

def hs_router_transfers(from_block, to_block, tokens, token, batch=600):
    """Transfer(router → user) только по заданным адресам токенов (индексировано, быстро). Возвращает {(tx, token): user}."""
    hdr = {'authorization': 'Bearer ' + token} if token else {}
    out = {}; tokens = sorted(tokens)
    for i in range(0, len(tokens), batch):
        q = {'from_block': from_block, 'to_block': to_block + 1,
             'logs': [{'address': tokens[i:i + batch], 'topics': [[TRANSFER], [pad(r) for r in ROUTERS]]}],
             'field_selection': {'log': ['address', 'topic2', 'transaction_hash']}}
        cur = from_block
        while cur <= to_block:
            q['from_block'] = cur
            r = http_json(HS_URL + '/query', q, hdr)
            for part in r.get('data', []):
                for l in part.get('logs', []):
                    if l.get('topic2'): out[((l.get('transaction_hash') or '').lower(), l['address'].lower())] = addr(l['topic2'])
            nxt = int(r.get('next_block', cur + 1)); cur = nxt if nxt > cur else cur + 1
    return out

def rpc_call(url, method, params):
    r = http_json(url, {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
    if 'error' in r: raise RuntimeError(r['error'])
    return r['result']

def rpc_iter(from_block, to_block, url, chunk):
    cur = from_block
    while cur <= to_block:
        hi = min(to_block, cur + chunk - 1)
        try:
            res = rpc_call(url, 'eth_getLogs', [{'fromBlock': hex(cur), 'toBlock': hex(hi), 'topics': [list(TOPICS.values())]}])
        except Exception as e:
            if chunk > 50: chunk //= 2; LOG('chunk ->', chunk, str(e)[:80]); continue
            raise
        logs = [dict(address=l['address'].lower(), data=l['data'], topics=l['topics'], bn=int(l['blockNumber'], 16), li=int(l['logIndex'], 16), tx=l['transactionHash']) for l in res]
        # block timestamps: anchors every 500 blocks, interpolate
        bts = {}
        for b in range(cur, hi + 1, 500):
            blk = rpc_call(url, 'eth_getBlockByNumber', [hex(b), False]); bts[b] = int(blk['timestamp'], 16)
        blk = rpc_call(url, 'eth_getBlockByNumber', [hex(hi), False]); bts[hi] = int(blk['timestamp'], 16)
        yield logs, bts, hi
        cur = hi + 1

def ts_of(bn, bts, anchors):
    if bn in bts: return bts[bn]
    # interpolate between nearest anchors
    lo = max((b for b in anchors if b <= bn), default=None); hi = min((b for b in anchors if b >= bn), default=None)
    if lo is None and hi is None: return None
    if lo is None: return bts[hi] - (hi - bn) * BLOCK_SEC
    if hi is None or hi == lo: return bts[lo] + (bn - lo) * BLOCK_SEC
    return bts[lo] + (bts[hi] - bts[lo]) * (bn - lo) / (hi - lo)

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True); ap.add_argument('--source', default='hypersync', choices=['hypersync', 'rpc'])
    ap.add_argument('--days', type=float, default=30); ap.add_argument('--from-block', type=int); ap.add_argument('--to-block', type=int)
    ap.add_argument('--chunk', type=int, default=2000); ap.add_argument('--max-blocks', type=int, default=0, help='ограничить объём одного запуска')
    ap.add_argument('--no-pools', action='store_true', help='не читать свопы пулов v4 после графуации')
    ap.add_argument('--pools-only', action='store_true', help='дозагрузить только пулы (Initialize/Swap v4) по уже известным токенам; state — pools_last_block')
    a = ap.parse_args()
    # Режим каталога (рекомендуется для больших окон): <dir>/tokens.json — метаданные токенов,
    # <dir>/series.csv — сделки построчно (token,bn,li,ts,price,amt,wallet,buyer,recip), <dir>/state.json — последний блок.
    DIR = a.out.endswith('/') or os.path.isdir(a.out) or not a.out.endswith('.json')
    if DIR:
        os.makedirs(a.out, exist_ok=True)
        state_f = os.path.join(a.out, 'state.json'); tokens_f = os.path.join(a.out, 'tokens.json'); series_f = os.path.join(a.out, 'series.csv')
        data = json.load(open(tokens_f)) if os.path.exists(tokens_f) else {}
        for v in data.values(): v['series'] = []
    else:
        state_f = a.out + '.state.json'
        data = json.load(open(a.out)) if os.path.exists(a.out) else {}
    state = json.load(open(state_f)) if os.path.exists(state_f) else {}
    curve2tok = {v['curve']: t for t, v in data.items() if v.get('curve')}
    written = {}   # DIR: token -> число строк, чтобы очищать series из памяти после записи
    def flush_series(final=False):
        """DIR: дописать накопленные строки в series.csv и освободить память; сохранить tokens.json и state."""
        if not DIR: return
        with open(series_f, 'a') as f:
            for t, v in data.items():
                for r in v['series']: f.write(f"{t},{r[0]},{r[1]},{r[2]:.3f},{'' if r[3] is None else repr(r[3])},{r[5]:.10g},{r[6]},{r[7]},{r[8]}{'' if r[4] == 'curve' else ',' + r[4]}\n")
                v['series'] = []
        tmp = tokens_f + '.tmp'; json.dump({t: {k: x for k, x in v.items() if k != 'series'} for t, v in data.items()}, open(tmp, 'w')); os.replace(tmp, tokens_f)
        state['pools_last_block' if a.pools_only else 'last_block'] = last; state['updated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()); json.dump(state, open(state_f, 'w'))

    if a.source == 'hypersync':
        token = os.environ.get('HYPERSYNC_TOKEN', ''); head = hs_height()
    else:
        url = os.environ.get('RPC_URL') or sys.exit('RPC_URL не задан'); head = int(rpc_call(url, 'eth_blockNumber', []), 16)
    to_block = a.to_block or head - 20
    from_block = a.from_block or state.get('pools_last_block' if a.pools_only else 'last_block', None)
    if from_block is None: from_block = int(to_block - a.days * 86400 / BLOCK_SEC)
    else: from_block += 1
    if a.pools_only: to_block = min(to_block, state.get('last_block', to_block))   # не обгонять основной поток
    if a.max_blocks: to_block = min(to_block, from_block + a.max_blocks)
    if from_block > to_block: LOG('нечего догружать'); return
    LOG(f'blocks {from_block}..{to_block} ({to_block-from_block+1}) via {a.source}')

    it = hs_iter(from_block, to_block, token, pools=not a.no_pools, curve=not a.pools_only) if a.source == 'hypersync' else rpc_iter(from_block, to_block, url, a.chunk)
    n_logs = 0; n_router = n_resolved = n_pools = n_swaps = 0; t_start = time.time(); last = from_block
    pool2tok = {v['poolId']: t for t, v in data.items() if v.get('poolId')}
    pending = []; pend_from = None   # покупки через роутер: (row, tx, token) — разрешаем пачками точечным запросом
    def resolve(upto):
        nonlocal pending, pend_from, n_resolved
        if not pending or a.source != 'hypersync': pending = []; return
        toks = {t for _, _, t in pending}
        m = hs_router_transfers(pend_from, upto, toks, token)
        for row, tx, t in pending:
            u = m.get((tx, t))
            if u: row[6] = u; n_resolved += 1
        LOG(f'   роутер: {len(pending)} покупок по {len(toks)} токенам, найдено {sum(1 for r,_,_ in pending if r[6] not in ROUTERS)}')
        pending = []; pend_from = None
    for logs, bts, done_to in it:
        anchors = sorted(bts)
        for l in sorted(logs, key=lambda x: (x['bn'], x['li'])):
            t0 = l['topics'][0].lower()
            if l['address'] == POOL_MANAGER:
                ts = ts_of(l['bn'], bts, anchors)
                if ts is None: continue
                if t0 == INIT_V4 and len(l['topics']) >= 4:
                    c0, c1 = addr(l['topics'][2]), addr(l['topics'][3])
                    for tok, idx in ((c0, 0), (c1, 1)):
                        v = data.get(tok)
                        if v and not v.get('poolId'):
                            v['poolId'] = l['topics'][1].lower(); v['poolIdx'] = idx; v['poolInitBn'] = l['bn']; pool2tok[v['poolId']] = tok; n_pools += 1
                elif t0 == SWAP_V4 and len(l['topics']) >= 2:
                    tok = pool2tok.get(l['topics'][1].lower())
                    if not tok: continue
                    v = data[tok]; pr, a0, a1 = v4_price(l['data'])
                    if pr is None: continue
                    if v.get('poolIdx') == 1: pr = 1 / pr
                    q = (a1 if v.get('poolIdx') == 0 else a0) / 1e18   # дельта котировочного актива у свопера: < 0 — купил токен
                    sender = addr(l['topics'][2]) if len(l['topics']) >= 3 else ''
                    v['series'].append([l['bn'], l['li'], ts, pr, 'pool', -q, sender, sender, sender]); v['latestTs'] = max(v['latestTs'], ts); n_swaps += 1
                n_logs += 1
                continue
            k = T2K.get(t0);
            if not k: continue
            ts = ts_of(l['bn'], bts, anchors)
            if ts is None: continue
            if k == 'launch':
                if l['address'] != FACTORY: continue
                tok, curve, dep = addr(l['topics'][1]), addr(l['topics'][2]), addr(l['topics'][3]); w = words(l['data'])
                data[tok] = dict(token=tok, curve=curve, deployer=dep, pairToken=('0x%040x' % w[0]) if w else None,
                                 gradThreshold=(w[2] / 1e18) if len(w) > 2 else None, firstTs=ts, fromBn=l['bn'], mode='curve',
                                 migrated=None, series=[], latestTs=ts, complete=False, source='stream')
                curve2tok[curve] = tok
            elif k in ('buy', 'sell'):
                tok = curve2tok.get(l['address']);
                if not tok: continue
                w = words(l['data']); buyer, recip = addr(l['topics'][1]), addr(l['topics'][2])
                if k == 'buy':
                    quote, tokens = w[0] / 1e18, w[1] / 1e18; price = (quote / tokens) if tokens > 0 else None; amt = quote
                else:
                    tokens, quote = w[0] / 1e18, w[1] / 1e18; price = (quote / tokens) if tokens > 0 else None; amt = -quote
                # [block, logIndex, ts, price, mode, quoteAmt, wallet(разрешённый), buyer(вызывающий), recipient(сырой)]
                row = [l['bn'], l['li'], ts, price, 'curve', amt, recip, buyer, recip]
                v = data[tok]; v['series'].append(row); v['latestTs'] = max(v['latestTs'], ts)
                if k == 'buy' and recip in ROUTERS:
                    n_router += 1; pending.append((row, l['tx'], tok)); pend_from = pend_from or l['bn']
            elif k == 'grad':
                tok = addr(l['topics'][1]); v = data.get(tok)
                if v: v['migrated'] = {'bn': l['bn'], 'tx': l['tx']}; v['gradTs'] = ts; v['latestTs'] = max(v['latestTs'], ts)
            n_logs += 1
        last = done_to
        el = time.time() - t_start; LOG(f'.. {last} ({(last-from_block+1)/(to_block-from_block+1)*100:.1f}%)  logs={n_logs}  {el:.0f}s')
        if pending and (len({t for _, _, t in pending}) >= 500 or last - pend_from >= 30000):
            resolve(last); flush_series()   # чекпоинт: строки на диск, state обновлён — перезапуск продолжит с last_block
        elif DIR and last - state.get('last_block', from_block) >= 100000:
            resolve(last); flush_series()
    resolve(last)
    if DIR:
        flush_series(final=True)
        LOG(f'готово: tokens={len(data)} logs+={n_logs} last_block={last} | через роутер: {n_router}, из них получатель найден: {n_resolved} | пулы: +{n_pools} (всего {len(pool2tok)}), свопов {n_swaps}')
        return
    # режим одного JSON (кэш): обрезка окна и запись
    cutoff = time.time() - a.days * 86400 - 2 * 86400
    for t in [t for t, v in data.items() if v.get('firstTs', 0) < cutoff and v.get('source') == 'stream']: del data[t]
    tmp = a.out + '.tmp'; json.dump(data, open(tmp, 'w')); os.replace(tmp, a.out)
    state['last_block'] = last; state['updated'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()); json.dump(state, open(state_f, 'w'))
    LOG(f'готово: tokens={len(data)} logs+={n_logs} last_block={last} | через роутер: {n_router}, из них получатель найден: {n_resolved}')

if __name__ == '__main__': main()
