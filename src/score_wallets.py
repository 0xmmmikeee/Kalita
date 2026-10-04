#!/usr/bin/env python3
"""wallet-lab · шаг 2: скоринг кошельков. Два профиля, условная база по позиции на кривой,
усадка, нижняя граница, кластеры «один хозяин», отбор/проверка вне выборки, плацебо.

  python3 score_wallets.py signals.csv out_dir [--split=UNIX_TS] [--m=10]

Профиль FAST   : hit = ath_1h >= 2 (вход через 2 с). Быстрые стратегии.
Профиль PICKER : hit = графуация ИЛИ ath_24h >= 5. «Отборщики» — токены с реальным спросом.
База p0 считается по корзине curve_eth_before (сколько ETH уже собрала кривая до входа):
на крутом старте x2 достигается геометрией кривой, а не умом кошелька — сравниваем с равными.
Оценка: excess = Wilson_low(k, n) − p_exp, где p_exp = средняя база по корзинам сигналов кошелька.
Ранг: excess * sqrt(n).
"""
import sys, os, math, json
import numpy as np, pandas as pd

SRC, OUT = sys.argv[1], sys.argv[2]
arg = lambda k, dflt: next((a.split('=')[1] for a in sys.argv if a.startswith('--' + k + '=')), dflt)
SPLIT_ARG = arg('split', '')          # unix ts; по умолчанию — последние VAL_DAYS дней = проверка
VAL_DAYS = float(arg('val-days', '7'))
M = float(arg('m', '10'))
os.makedirs(OUT, exist_ok=True)

KNOWN_CONTRACTS = {'0x65050a9b7e5075a2ba5ced7b1b64ee66262c40dc': 'Pons router'}
BUCKETS = [0, 0.1, 0.5, 2.0, 1e9]

NEED = ['wallet','token','ts','block','buyer_rank','curve_eth_before','curve_frac_before','spend_eth','buyer','grad',
        'ath_5m','ath_1h','ath_24h','ath_7d','t_ath_1h','min_10m','dd_before_x2','dd_before_x15','t_x2','t_sell','sell_mult']
hdr = pd.read_csv(SRC, nrows=0).columns
from csvload import read_signals
df = read_signals(SRC, usecols=[c for c in NEED if c in hdr], dtype={**{c: 'float32' for c in NEED if c not in ('wallet','token','buyer','grad','ts','block')}, 'wallet': 'category', 'token': 'category', 'buyer': 'category'})  # адреса как category: в 3–4 раза меньше памяти на 8M строк
df['ts'] = df.ts.astype('float64')
SPLIT = float(SPLIT_ARG) if SPLIT_ARG else float(df.ts.max() - VAL_DAYS * 86400)
print(f'signals {len(df)}; отбор до {pd.to_datetime(SPLIT, unit="s")}, проверка после', flush=True)
if 'curve_frac_before' in df and df.curve_frac_before.notna().mean() > 0.5:
    BUCKETS = [0, 0.02, 0.1, 0.3, 0.6, 1e9]   # доля порога графуации, собранная кривой до входа
    df['bucket'] = pd.cut(df.curve_frac_before.clip(lower=0), BUCKETS, right=False, labels=False)
    BUCKET_KIND = 'frac'
else:
    df['bucket'] = pd.cut(df.curve_eth_before.clip(lower=0), BUCKETS, right=False, labels=False)
    BUCKET_KIND = 'eth'
df['bucket'] = df['bucket'].fillna(0).astype(int)
if 'buyer' in df:
    _c = df.wallet.cat.categories.union(df.buyer.cat.categories); df['via_contract'] = (df.buyer.cat.set_categories(_c).cat.codes != df.wallet.cat.set_categories(_c).cat.codes).astype(float)
else: df['via_contract'] = np.nan
df['rug'] = (df.min_10m < 0.2).astype(float)
df['held_to_x2'] = ((df.t_sell.isna()) | (df.sell_mult >= 2)).astype(float)

REGIME_TS = 1790640000.0   # 2026-09-29T00:00:00Z — конец субсидии газа Robinhood
PROFILES = {
    'fast':   dict(hit=lambda d: (d.ath_1h >= 2).astype(float), need=lambda d: d.ath_1h.notna()),
    # пикер: токен дошёл до пула или x5 за сутки — И при этом от нашего входа был рост хотя бы x1.5
    # (вход в уже почти заполненную кривую «доходит до пула» по x1.0 — это не отбор). Сигналы с заполнением кривой > 60 % исключены.
    'picker': dict(hit=lambda d: (((d.grad) | (d.ath_24h >= 5)) & (d.ath_24h >= 1.5)).astype(float),
                   need=lambda d: d.ath_24h.notna() & ((d.curve_frac_before <= 0.6) if 'curve_frac_before' in d else True)),
}

def wilson_low(k, n, z=1.2816):
    if n == 0: return 0.0
    p = k / n; den = 1 + z*z/n
    return ((p + z*z/(2*n)) - z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / den

def per_wallet(d, p0_by_bucket, m=M):
    g = d.groupby('wallet', observed=True)
    out = pd.DataFrame({
        'n': g.size(), 'hits': g.hit.sum(), 'tokens': g.token.nunique(),
        'n_after_regime': g.ts.apply(lambda x: int((x >= REGIME_TS).sum())),   # сигналы после отмены субсидии газа 29.09.2026
        'p_exp': g.bucket.apply(lambda b: float(np.mean([p0_by_bucket[int(x)] for x in b]))),
        'rug': g.rug.mean(), 'held_to_x2': g.held_to_x2.mean(),
        'med_rank': g.buyer_rank.median(), 'med_curve_eth': g.curve_eth_before.median(),
        'med_spend': g.spend_eth.median(), 'first_ts': g.ts.min(), 'last_ts': g.ts.max(),
        'med_ath_5m': g.ath_5m.median(), 'med_ath_1h': g.ath_1h.median(), 'med_ath_24h': g.ath_24h.median(),
        'med_t_ath_1h': g.t_ath_1h.median(), 'p_x5_24h': g.ath_24h.apply(lambda x: float(np.nanmean(x >= 5))),
        'grad_rate': g.grad.mean(), 'med_dd_before_x2': g.dd_before_x2.median(),
        'via_contract': g.via_contract.mean(), 'med_curve_frac': g.curve_frac_before.median() if 'curve_frac_before' in d else np.nan,
        'mean_ath_24h': g.ath_24h.mean(), 'max_ath_24h': g.ath_24h.max(),
        'best_share_24h': g.ath_24h.apply(lambda x: float(np.nanmax(x) / np.nansum(x)) if np.nansum(x) > 0 else np.nan),
        'med_ath_7d': g.ath_7d.median() if 'ath_7d' in d else np.nan, 'p_x10_24h': g.ath_24h.apply(lambda x: float(np.nanmean(x >= 10))),
        'med_dd_before_x15': g.dd_before_x15.median(), 'med_t_x2': g.t_x2.median(),
        'sigs_per_day': g.ts.apply(lambda t: len(t) / max(1.0, (t.max() - t.min()) / 86400)),
    })
    out['raw'] = out.hits / out.n
    out['shrunk'] = (out.hits + m * out.p_exp) / (out.n + m)
    out['low'] = [wilson_low(k, n) for k, n in zip(out.hits, out.n)]
    out['excess'] = out.low - out.p_exp
    out['lift'] = out.shrunk / out.p_exp
    out['score'] = out.excess * np.sqrt(out.n)
    return out

def clusters(d, cands, thr=0.5):
    """Кошельки, у которых ≥thr общих токенов И совпадение блока покупки — считаем одним хозяином."""
    sub = d[d.wallet.isin(cands)]
    tok = sub.groupby('wallet', observed=True).apply(lambda g: set(zip(g.token, g.block)))
    toks = sub.groupby('wallet', observed=True).token.apply(set)
    parent = {w: w for w in cands}
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    ws = list(cands)
    inv = {}
    for w in ws:
        for t in toks[w]: inv.setdefault(t, []).append(w)
    pairs = {}
    for t, lst in inv.items():
        for a in lst:
            for b in lst:
                if a < b: pairs[(a, b)] = pairs.get((a, b), 0) + 1
    for (a, b), c in pairs.items():
        j = c / len(toks[a] | toks[b])
        if j >= thr:
            same_block = len(tok[a] & tok[b]) / max(1, min(len(tok[a]), len(tok[b])))
            if same_block >= thr: parent[find(a)] = find(b)
    return {w: find(w) for w in ws}

report = {}
for name, P in PROFILES.items():
    d = df[P['need'](df)].copy(); d['hit'] = P['hit'](d)
    sel, val = d[d.ts < SPLIT], d[d.ts >= SPLIT]
    p0 = sel.hit.mean(); p0b = {int(k): v for k, v in sel.groupby('bucket', observed=True).hit.mean().items()}
    for b in range(len(BUCKETS)): p0b.setdefault(b, p0)
    S = per_wallet(sel, p0b); V = per_wallet(val, p0b)
    S['flag'] = ''
    S.loc[(S.tokens >= 300), 'flag'] = 'check-code'   # подозрение на контракт/агрегатор — проверить на VPS
    S.loc[S.index.isin(KNOWN_CONTRACTS), 'flag'] = 'contract'
    cfile = os.path.join(os.path.dirname(os.path.abspath(OUT)), '..', 'state', 'contracts.json')
    cfile = os.environ.get('WL_CONTRACTS', cfile)
    if os.path.exists(cfile):
        try:
            cc = json.load(open(cfile)); contracts = {w for w, v in cc.items() if v.get('contract')}
            S.loc[S.index.isin(contracts), 'flag'] = 'contract'
            S.loc[S.index.isin(set(cc) - contracts) & (S.flag == 'check-code'), 'flag'] = 'eoa-bot'
        except Exception as e: print('contracts.json:', e)
    S = S[S.n >= 5].sort_values('score', ascending=False)
    cl = clusters(sel, S.index[:1500].tolist())
    S['cluster'] = [cl.get(w, w) for w in S.index]
    S['cluster_dup'] = S.duplicated('cluster', keep='first')
    T = S.join(V[['n', 'hits', 'raw', 'p_exp']].add_prefix('val_'), how='left')
    T.to_csv(f'{OUT}/scores_{name}.csv')
    elig = T[(T.flag != 'contract') & (~T.cluster_dup)]
    lines = [f'== {name.upper()}  p0={p0:.4f}  by bucket({BUCKET_KIND})={ {int(k): round(v,4) for k,v in p0b.items()} }',
             f'sel signals={len(sel)} val signals={len(val)} wallets n>=5: {len(S)}  eligible: {len(elig)}']
    for N in (50, 100, 300, 500):
        t = elig.head(N); tv = t[t.val_n.fillna(0) >= 2]
        pooled = tv.val_hits.sum() / tv.val_n.sum() if len(tv) else float('nan')
        exp = float(np.average(tv.val_p_exp, weights=tv.val_n)) if len(tv) else float('nan')
        lines.append(f'top{N:>3}: sel raw={t.raw.mean():.3f} lift={t.lift.mean():.2f} | VAL n_wallets={len(tv)} signals={int(tv.val_n.sum()) if len(tv) else 0} pooled hit={pooled:.3f} expected(by bucket)={exp:.3f}')
    rng = np.random.default_rng(1)
    r = T.loc[rng.choice(T.index.to_numpy(), size=min(300, len(T)), replace=False)]; rv = r[r.val_n.fillna(0) >= 2]
    lines.append(f'placebo300: VAL pooled hit={rv.val_hits.sum()/rv.val_n.sum():.3f}  market VAL={val.hit.mean():.3f}')
    report[name] = lines
    print('\n'.join(lines)); print()
    cols = ['n','hits','raw','p_exp','low','excess','lift','rug','held_to_x2','med_rank','med_curve_eth','grad_rate','p_x5_24h','med_ath_1h','med_t_ath_1h','flag','cluster_dup','val_n','val_raw']
    print(elig.head(15)[cols].round(3).to_string()); print()
json.dump(report, open(f'{OUT}/report.json', 'w'), indent=1, ensure_ascii=False)
