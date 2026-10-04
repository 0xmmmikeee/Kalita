#!/usr/bin/env python3
"""wallet-lab · шаг 1: паспорта сигналов.

Вход: launchpad-cache.json движка scout-bot (series: [block, logIndex, ts, price, mode, ethAmt, wallet];
ethAmt < 0 — продажа). Позже сюда же подключается полный поток Pons v2 в том же формате.

Сигнал = первая покупка кошелька на кривой токена (mode == 'curve', eth > 0).
Считаем: цену входа при задержке d ∈ DELAYS; ATH и время до него на горизонтах HORIZONS (только если
горизонт полностью наблюдён, иначе NaN = «ещё неизвестно»); минимум за 10 мин; откат до первого +50% / x2 / x5;
графуацию (миграцию в пул) и время до неё; первую продажу самого кошелька (держит ли, по какой кратности).
"""
import json, sys, os
import numpy as np, pandas as pd

SRC, OUT = sys.argv[1], sys.argv[2]
DELAYS = [0, 2, 5, 10]
HORIZONS = {'1m':60,'5m':300,'15m':900,'30m':1800,'1h':3600,'4h':14400,'12h':43200,'24h':86400,'7d':604800,'30d':2592000}
BASE_DELAY = 2

def process_token(tok, v, s, rows):
    """Паспорта сигналов одного токена: v — метаданные, s — список сделок [bn,li,ts,price,mode,amt,wallet,buyer,recip]."""
    if len(s) < 2: return
    s = sorted(s, key=lambda r: (r[2], r[0], r[1]))
    ts = np.array([r[2] for r in s], float)
    px = np.array([r[3] if r[3] is not None else np.nan for r in s], float)
    eth = np.array([r[5] if r[5] is not None else np.nan for r in s], float)
    blk = np.array([r[0] for r in s], float)
    mode = np.array([r[4] for r in s])
    # цена пула: ориентация (token1/token0 могла оказаться обратной) — сверяем первую цену пула с последней ценой кривой;
    # затем отсев невозможных скачков (>50× к предыдущей валидной точке) только среди точек пула
    if (mode == 'pool').any() and (mode == 'curve').any():
        ci = np.where((mode == 'curve') & ~np.isnan(px) & (px > 0))[0]; pi = np.where((mode == 'pool') & ~np.isnan(px) & (px > 0))[0]
        if len(ci) and len(pi):
            lc, fp = px[ci[-1]], px[pi[0]]
            # кандидаты: прямая/обратная ориентация × поправка на десятичность котировочного токена (18 или 6 знаков)
            best = min(((abs(np.log(f(fp) / lc)), f) for f in (lambda x: x, lambda x: 1 / x, lambda x: x * 1e12, lambda x: x / 1e12, lambda x: 1e12 / x, lambda x: 1 / (x * 1e12))), key=lambda t: t[0])
            if best[0] < np.log(20): px[pi] = best[1](px[pi])
            else: px[pi] = np.nan   # цена пула несопоставима с кривой — не используем
            prev = lc
            for i in pi:
                if px[i] > prev * 50 or px[i] < prev / 50: px[i] = np.nan
                else: prev = px[i]
    # кошелёк = получатель токенов; для покупок через роутер поток уже подставил конечного получателя
    wal = np.array([(r[6] or '').lower() for r in s])
    valid = ~np.isnan(px) & (px > 0)
    if valid.sum() < 2: return
    tok_end = max(v.get('latestTs') or 0, ts[-1])
    first_ts = ts[0]
    is_curve_buy = (mode == 'curve') & (eth > 0)
    curve_cum = np.cumsum(np.where((mode == 'curve') & ~np.isnan(eth), eth, 0.0))   # нетто: покупки минус продажи
    grad_ts = np.nan
    mig = v.get('migrated')
    thr = v.get('gradThreshold') or np.nan
    if v.get('gradTs'):
        grad_ts = float(v['gradTs'])
    elif mig and mig.get('bn'):
        j = np.searchsorted(blk, mig['bn'], side='left')
        grad_ts = ts[j] if j < len(ts) else (ts[-1] + (mig['bn'] - blk[-1]) * (v.get('blockTime') or 0.1))
    elif (mode == 'pool').any():
        grad_ts = ts[np.argmax(mode == 'pool')]
    seen = {}
    for i in range(len(s)):
        w = wal[i]
        if not w or not is_curve_buy[i] or not valid[i] or w in seen: continue
        seen[w] = i
        t0 = ts[i]
        rec = dict(token=tok, wallet=w, ts=t0, block=int(blk[i]), p_sig=px[i], buyer_rank=len(seen),
                   age_sec=t0 - first_ts, curve_eth_before=max(0.0, float(curve_cum[i] - eth[i])),
                   curve_frac_before=(max(0.0, float(curve_cum[i] - eth[i])) / thr) if thr and thr > 0 else np.nan,
                   buyer=(s[i][7].lower() if len(s[i]) > 7 and s[i][7] else w), recipient=((s[i][8] if len(s[i]) > 8 and s[i][8] else s[i][6]) or '').lower(),
                   spend_eth=float(eth[i]), token_migrated=bool(mig),
                   grad=bool((not np.isnan(grad_ts)) and grad_ts > t0),
                   t_grad=(grad_ts - t0) if (not np.isnan(grad_ts) and grad_ts > t0) else np.nan,
                   observed_sec=tok_end - t0)
        for dd in DELAYS:
            j = np.searchsorted(ts, t0 + dd, side='right') - 1
            k = max(j, i)
            while k > i and not valid[k]: k -= 1
            rec[f'p_in_{dd}'] = px[k]
        p_in = rec[f'p_in_{BASE_DELAY}']
        fut = (np.arange(len(s)) > i) & valid & (ts >= t0 + BASE_DELAY)
        fidx = np.where(fut)[0]
        for hname, hsec in HORIZONS.items():
            if GLOBAL_END < t0 + hsec:   # окно не наблюдено целиком (токен мог умереть раньше — это не мешает)
                rec[f'ath_{hname}'] = np.nan; rec[f't_ath_{hname}'] = np.nan; continue
            m = fidx[ts[fidx] <= t0 + hsec]
            if len(m) == 0:
                rec[f'ath_{hname}'] = 1.0; rec[f't_ath_{hname}'] = np.nan; continue
            pk = m[np.argmax(px[m])]
            rec[f'ath_{hname}'] = px[pk] / p_in; rec[f't_ath_{hname}'] = ts[pk] - t0
        m10 = fidx[ts[fidx] <= t0 + 600]
        rec['min_10m'] = (px[m10].min() / p_in) if len(m10) else np.nan
        m24 = fidx[ts[fidx] <= t0 + 86400]
        for lvl, name in ((1.5, 'x15'), (2.0, 'x2'), (5.0, 'x5')):
            hit = m24[px[m24] >= lvl * p_in]
            if len(hit) == 0:
                rec[f'dd_before_{name}'] = np.nan; rec[f't_{name}'] = np.nan; continue
            h = hit[0]; pre = m24[m24 < h]
            rec[f'dd_before_{name}'] = (px[pre].min() / p_in) if len(pre) else 1.0
            rec[f't_{name}'] = ts[h] - t0
        sells = np.where((wal == w) & (eth < 0) & (np.arange(len(s)) > i))[0]
        if len(sells):
            sj = sells[0]
            rec['t_sell'] = ts[sj] - t0; rec['sell_mult'] = (px[sj] / p_in) if valid[sj] else np.nan
        else:
            rec['t_sell'] = np.nan; rec['sell_mult'] = np.nan
        rows.append(rec)


import csv, subprocess, io
FIELDS = None
def fmtv(x):
    if x is None: return ''
    if isinstance(x, (float, np.floating)):
        x = float(x); return '' if np.isnan(x) else repr(x)
    if isinstance(x, (bool, np.bool_)): return 'True' if x else 'False'
    if isinstance(x, (int, np.integer)): return str(int(x))
    return str(x)

def emit(rows, out):
    """Записать накопленные паспорта в CSV (дозапись), вернуть число строк."""
    global FIELDS
    if not rows: return 0
    if FIELDS is None:
        FIELDS = list(rows[0].keys()); out.write(','.join(FIELDS) + '\n')
    for r in rows:
        out.write(','.join(fmtv(r.get(k)) for k in FIELDS) + '\n')
    return len(rows)

def iter_json(src):
    d = json.load(open(src))
    for tok, v in d.items(): yield tok, v, (v.get('series') or [])

def iter_dir(src):
    """Каталог потока: tokens.json + series.csv; внешняя сортировка по токену (sort), группировка по одному токену."""
    meta = json.load(open(os.path.join(src, 'tokens.json')))
    tmpd = os.path.join(src, 'tmp'); os.makedirs(tmpd, exist_ok=True)
    p = subprocess.Popen(['sort', '-t', ',', '-k1,1', '-k2,2n', '-k3,3n', '-S', os.environ.get('WL_SORT_MEM', '400M'), '-T', tmpd, '-u', os.path.join(src, 'series.csv')],
                         stdout=subprocess.PIPE, text=True, bufsize=1 << 20)
    cur, buf = None, []
    for line in p.stdout:
        c = line.rstrip('\n').split(',')
        if len(c) < 9: continue
        tok = c[0]
        if tok != cur:
            if cur is not None and cur in meta: yield cur, meta[cur], buf
            cur, buf = tok, []
        buf.append([int(c[1]), int(c[2]), float(c[3]), (float(c[4]) if c[4] else None), (c[9] if len(c) > 9 and c[9] else 'curve'), float(c[5]), c[6], c[7], c[8]])
    if cur is not None and cur in meta: yield cur, meta[cur], buf
    p.wait()

import os
def _global_end(src):
    try:
        if os.path.isdir(src):
            meta = json.load(open(os.path.join(src, 'tokens.json')))
            st = {}
            try: st = json.load(open(os.path.join(src, 'state.json')))
            except Exception: pass
            m = max([float(v.get('latestTs') or 0) for v in meta.values()] + [float(st.get('lastTs') or 0)])
        else:
            d = json.load(open(src)); m = max(float(v.get('latestTs') or 0) for v in d.values())
        return m if m > 0 else float('inf')
    except Exception:
        return float('inf')
GLOBAL_END = float(os.environ.get('WL_DATA_END') or 0) or _global_end(SRC)
print('конец данных:', GLOBAL_END, flush=True)
src_iter = iter_dir(SRC) if os.path.isdir(SRC) else iter_json(SRC)
n_sig = n_tok = 0; rows = []
with open(OUT + '.tmp', 'w') as out:
    for tok, v, s in src_iter:
        process_token(tok, v, s, rows); n_tok += 1
        if len(rows) >= 20000: n_sig += emit(rows, out); rows = []
    n_sig += emit(rows, out)
os.replace(OUT + '.tmp', OUT)
print('tokens processed:', n_tok, 'signals:', n_sig, flush=True)
df = pd.read_csv(OUT, usecols=lambda c: c in ('wallet','token','grad','t_sell') or c.startswith('ath_') or c == 'min_10m')
print('signals:', len(df), 'wallets:', df.wallet.nunique(), 'tokens:', df.token.nunique())
print('grad rate:', round(df.grad.mean(), 4), '| sold within observation:', round(df.t_sell.notna().mean(), 3))
for h in HORIZONS:
    c = df[f'ath_{h}'].notna().sum()
    if c: print(f'{h:>4}: obs {c:6d}  P(x2)={np.mean(df[f"ath_{h}"]>=2):.3f}  P(x5)={np.mean(df[f"ath_{h}"]>=5):.3f}  median={df[f"ath_{h}"].median():.3f}')
