#!/usr/bin/env python3
"""wallet-lab · анализ на полных данных: пять гипотез.
  python3 src/analyze_full.py data/signals.csv data/scores data/scores/analysis.json
1. Портфель: топ-N (25/50/100/300) по score вне выборки против рынка (по бакетам) и плацебо.
2. Величина: P(ATH ≥ 1.3/1.5/1.8/2/3 за 1ч и 24ч) у топ-100 против рынка на тех же бакетах; доля ранних просадок.
3. Пикеры: то же для профиля picker (после починки хита).
4. Кластер как сигнал: второй кошелёк из топ-100 в том же токене в течение 60 с — хит подтверждённых против одиночных.
5. Стабильность: превышение кошелька неделя к неделе (Спирмен) — есть ли вообще устойчивое «умение».
"""
import sys, os, json, math, numpy as np, pandas as pd
SIG, SCORES, OUT = sys.argv[1:4]
VAL_DAYS = float(os.environ.get('WL_VAL_DAYS', 7))
cols = ['wallet','token','ts','buyer_rank','curve_frac_before','curve_eth_before','grad','ath_5m','ath_1h','ath_24h','min_10m','t_ath_1h','dd_before_x15']
hdr = pd.read_csv(SIG, nrows=0).columns
# память: 8M строк — адреса как category (строки хранятся один раз), числа float32
from csvload import read_signals
df = read_signals(SIG, usecols=[c for c in cols if c in hdr], dtype={**{c: 'float32' for c in cols if c not in ('wallet','token','ts','grad')}, 'wallet': 'category', 'token': 'category'})
df['wallet'] = df.wallet.cat.rename_categories(lambda x: x.lower()); df['ts'] = df.ts.astype('float64')
SPLIT = df.ts.max() - VAL_DAYS * 86400
if 'curve_frac_before' in df and df.curve_frac_before.notna().mean() > 0.5:
    B = [0, 0.02, 0.1, 0.3, 0.6, 1e9]; df['bucket'] = pd.cut(df.curve_frac_before.clip(lower=0), B, right=False, labels=False)
else:
    B = [0, 0.1, 0.5, 2, 1e9]; df['bucket'] = pd.cut(df.curve_eth_before.clip(lower=0), B, right=False, labels=False)
df['bucket'] = df.bucket.fillna(0).astype(int)
R = {'split': SPLIT, 'signals': int(len(df)), 'val_signals': int((df.ts >= SPLIT).sum()), 'days': float((df.ts.max() - df.ts.min()) / 86400)}
lines = [f"сигналов {len(df)}, дней {R['days']:.1f}, проверка = последние {VAL_DAYS:.0f} дней ({R['val_signals']} сигналов)"]

def hit_fast(d): return (d.ath_1h >= 2).astype(float)
def hit_picker(d): return (((d.grad == True) | (d.ath_24h >= 5)) & (d.ath_24h >= 1.5)).astype(float)
PROF = {'fast': (hit_fast, lambda d: d.ath_1h.notna()),
        'picker': (hit_picker, lambda d: d.ath_24h.notna() & (d.curve_frac_before <= 0.6 if 'curve_frac_before' in d else True))}

def expected(val, hitcol, p0b): return float(np.mean([p0b.get(int(b), np.nan) for b in val.bucket])) if len(val) else float('nan')

for name, (hf, need) in PROF.items():
    sf = f'{SCORES}/scores_{name}.csv'
    if not os.path.exists(sf): lines.append(f'{name}: нет scores'); continue
    S = pd.read_csv(sf); S['wallet'] = S.wallet.str.lower()
    S = S[(S.get('flag', '').fillna('') != 'contract') & (~S.get('cluster_dup', False).fillna(False).astype(bool))]
    S = S.sort_values('score', ascending=False) if 'score' in S else S
    d = df[need(df)].copy(); d['hit'] = hf(d)
    sel, val = d[d.ts < SPLIT], d[d.ts >= SPLIT]
    p0b = sel.groupby('bucket', observed=True).hit.mean().to_dict(); p0v = val.groupby('bucket', observed=True).hit.mean().to_dict()
    res = {'market_sel': float(sel.hit.mean()), 'market_val': float(val.hit.mean()), 'by_bucket_val': {int(k): float(v) for k, v in p0v.items()}, 'topN': {}}
    lines.append(f'== {name}: рынок отбор {sel.hit.mean():.3f}, проверка {val.hit.mean():.3f}; по бакетам (проверка) { {int(k): round(v,3) for k,v in p0v.items()} }')
    # 1. портфель
    rng = np.random.default_rng(7)
    for N in (25, 50, 100, 300):
        top = set(S.wallet.head(N)); v = val[val.wallet.isin(top)]
        exp = expected(v, 'hit', p0v)
        # плацебо: N случайных кошельков с n>=5 из S (тот же размер), 50 повторов
        pool = S.wallet.to_numpy(); plc = []
        for _ in range(50):
            rw = set(rng.choice(pool, size=min(N, len(pool)), replace=False)); pv = val[val.wallet.isin(rw)]
            if len(pv) >= 20: plc.append(pv.hit.mean() - expected(pv, 'hit', p0v))
        res['topN'][N] = {'val_signals': int(len(v)), 'val_wallets': int(v.wallet.nunique()), 'hit': float(v.hit.mean()) if len(v) else None,
                          'expected': exp, 'excess': (float(v.hit.mean()) - exp) if len(v) else None,
                          'placebo_excess_mean': float(np.mean(plc)) if plc else None, 'placebo_excess_p95': float(np.percentile(plc, 95)) if plc else None}
        t = res['topN'][N]
        lines.append(f"  топ-{N:<3}: проверка {t['val_signals']} сигн. / {t['val_wallets']} кош. · хит {t['hit'] if t['hit'] is None else round(t['hit'],3)} · ожид. {exp:.3f} · превыш. {t['excess'] if t['excess'] is None else round(t['excess'],3)} · плацебо {t['placebo_excess_mean'] and round(t['placebo_excess_mean'],3)} (p95 {t['placebo_excess_p95'] and round(t['placebo_excess_p95'],3)})")
    # 2. величина: топ-100 против рынка на тех же бакетах (взвешенно)
    top = set(S.wallet.head(100)); v = val[val.wallet.isin(top)]
    if len(v):
        w = v.bucket.value_counts(normalize=True)
        mk = pd.concat([val[val.bucket == b].sample(n=min(int(w[b] * 4000) + 1, (val.bucket == b).sum()), random_state=1) for b in w.index])
        mag = {}
        for h in ('ath_1h', 'ath_24h'):
            if h not in v: continue
            mag[h] = {str(th): {'top': float((v[h] >= th).mean()), 'market_same_buckets': float((mk[h] >= th).mean())} for th in (1.3, 1.5, 1.8, 2, 3, 5)}
            mag[h]['median'] = {'top': float(v[h].median()), 'market': float(mk[h].median())}
        mag['min_10m_lt_0.5'] = {'top': float((v.min_10m < 0.5).mean()), 'market': float((mk.min_10m < 0.5).mean())}
        if 't_ath_1h' in v: mag['t_ath_1h_median'] = {'top': float(v.t_ath_1h.median()), 'market': float(mk.t_ath_1h.median())}
        res['magnitude_top100'] = mag
        for h in ('ath_1h', 'ath_24h'):
            if h in mag: lines.append(f'  величина {h} топ-100 vs рынок: ' + ' · '.join(f"≥{th}: {mag[h][str(th)]['top']:.3f}/{mag[h][str(th)]['market_same_buckets']:.3f}" for th in (1.3,1.5,1.8,2,3,5)) + f" · медиана {mag[h]['median']['top']:.2f}/{mag[h]['median']['market']:.2f}")
        lines.append(f"  просадка <0.5 за 10 мин: топ {mag['min_10m_lt_0.5']['top']:.3f} / рынок {mag['min_10m_lt_0.5']['market']:.3f}")
    # 4. кластер как сигнал (только для fast)
    if name == 'fast' and len(v):
        vv = v.sort_values(['token', 'ts']); conf = []
        for tok, g in vv.groupby('token', observed=True):
            ts = g.ts.to_numpy(); hits = g.hit.to_numpy()
            for i in range(len(g)):
                prior = ((ts < ts[i]) & (ts >= ts[i] - 60)).any()
                conf.append((bool(prior), float(hits[i])))
        c = pd.DataFrame(conf, columns=['confirmed', 'hit'])
        res['cluster_signal'] = {'confirmed_n': int(c.confirmed.sum()), 'confirmed_hit': float(c[c.confirmed].hit.mean()) if c.confirmed.any() else None,
                                 'single_n': int((~c.confirmed).sum()), 'single_hit': float(c[~c.confirmed].hit.mean()) if (~c.confirmed).any() else None}
        cs = res['cluster_signal']; lines.append(f"  подтверждение вторым кошельком из топ-100 за 60 с: подтверждённых {cs['confirmed_n']} хит {cs['confirmed_hit'] and round(cs['confirmed_hit'],3)} · одиночных {cs['single_n']} хит {cs['single_hit'] and round(cs['single_hit'],3)}")
    # 5. стабильность неделя к неделе
    d['week'] = ((d.ts - d.ts.min()) // (7 * 86400)).astype(int)
    p0w = d.groupby(['week', 'bucket'], observed=True).hit.mean()
    d['exp'] = [p0w.get((w, b), np.nan) for w, b in zip(d.week, d.bucket)]
    g = d.groupby(['wallet', 'week'], observed=True).agg(n=('hit', 'size'), hit=('hit', 'mean'), exp=('exp', 'mean')).reset_index()
    g = g[g.n >= 10]; g['ex'] = g.hit - g.exp
    rho = []
    for w in sorted(g.week.unique())[:-1]:
        a = g[g.week == w].set_index('wallet').ex; b = g[g.week == w + 1].set_index('wallet').ex
        j = a.index.intersection(b.index)
        if len(j) >= 30: rho.append((int(w), int(len(j)), float(pd.Series(a[j]).corr(pd.Series(b[j]), method='spearman'))))
    res['week_to_week'] = rho
    lines.append('  стабильность неделя→неделя (Спирмен по превышению, кошельки с n≥10 в обеих): ' + (', '.join(f'н{w}→н{w+1}: ρ={r:.2f} (k={k})' for w, k, r in rho) or 'мало данных'))
    R[name] = res

json.dump(R, open(OUT, 'w'), indent=1, ensure_ascii=False)
print('\n'.join(lines))
