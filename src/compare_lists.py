#!/usr/bin/env python3
"""wallet-lab · сравнение внешних списков кошельков (lists/*.txt) с нашей оценкой.
Для каждого списка: сколько адресов есть в данных, их суммарный хит против ожидаемого рынка,
распределение по нашим рангам, сколько попадает в наши пороги. Результат → data/scores/lists.json (для панели).

  python3 src/compare_lists.py data/signals.csv data/scores lists/ data/scores/lists.json
"""
import sys, os, glob, json, math, numpy as np, pandas as pd
SIG, SCORES, LISTS, OUT = sys.argv[1:5]
from csvload import read_signals
sig = read_signals(SIG, usecols=['wallet','ath_1h','ath_24h','grad'], dtype={'wallet': 'category', 'ath_1h': 'float32', 'ath_24h': 'float32'}); sig['wallet'] = sig.wallet.cat.rename_categories(lambda x: x.lower())
res = {}
for f in sorted(glob.glob(os.path.join(LISTS, '*.txt'))):
    name = os.path.basename(f)[:-4]
    ws = {l.strip().lower() for l in open(f) if l.strip().startswith('0x')}
    entry = {'size': len(ws), 'profiles': {}}
    for p in ('fast', 'picker'):
        sf = f'{SCORES}/scores_{p}.csv'
        if not os.path.exists(sf): continue
        S = pd.read_csv(sf); S['wallet'] = S.wallet.str.lower(); S = S.set_index('wallet')
        inS = S[S.index.isin(ws)]
        allS = S[S.n >= 5]
        rank = allS.reset_index().reset_index().set_index('wallet')['index'] if 'score' in allS else None
        # позиции списка в общем рейтинге (по score)
        ranked = allS.sort_values('score', ascending=False).reset_index()
        ranked['pos'] = np.arange(1, len(ranked) + 1)
        pos = ranked[ranked.wallet.isin(ws)].pos
        hits, n = inS.hits.sum(), inS.n.sum()
        exp = float(np.average(inS.p_exp, weights=inS.n)) if n > 0 else float('nan')
        entry['profiles'][p] = {
            'in_data': int(len(inS)), 'with_n5': int((inS.n >= 5).sum()), 'signals': int(n),
            'pooled_hit': float(hits / n) if n else None, 'expected': exp,
            'lift': float((hits / n) / exp) if n and exp else None,
            'median_excess': float(inS[inS.n >= 5].excess.median()) if (inS.n >= 5).any() else None,
            'share_positive_excess': float((inS[inS.n >= 5].excess > 0).mean()) if (inS.n >= 5).any() else None,
            'in_top100': int((pos <= 100).sum()), 'in_top500': int((pos <= 500).sum()), 'ranked_total': int(len(ranked)),
            'median_rank_pos': float(pos.median()) if len(pos) else None,
            'val_signals': int(inS.val_n.fillna(0).sum()), 'val_hit': float(inS.val_hits.fillna(0).sum() / inS.val_n.fillna(0).sum()) if inS.val_n.fillna(0).sum() else None,
            'val_expected': float(np.average(inS.val_p_exp.fillna(0), weights=inS.val_n.fillna(0))) if inS.val_n.fillna(0).sum() else None,
        }
    res[name] = entry
# рынок для сравнения
res['_market'] = {}
for p, col in (('fast', 'ath_1h'), ('picker', 'ath_24h')):
    d = sig[sig[col].notna()]
    res['_market'][p] = {'hit': float((d[col] >= 2).mean()) if p == 'fast' else float(((d.grad == True) | (d.ath_24h >= 5)).mean())}
json.dump(res, open(OUT, 'w'), indent=1, ensure_ascii=False)
for name, e in res.items():
    if name.startswith('_'): continue
    for p, v in e['profiles'].items():
        print(f"{name:>16} [{p}] в данных {v['in_data']}/{e['size']} (n>=5: {v['with_n5']}), сигналов {v['signals']}, хит {v['pooled_hit'] and round(v['pooled_hit'],3)} vs ожид. {round(v['expected'],3) if v['expected']==v['expected'] else '—'} → ×{v['lift'] and round(v['lift'],2)}; в топ-100: {v['in_top100']}, топ-500: {v['in_top500']}; медиана превышения {v['median_excess'] and round(v['median_excess'],3)}")
