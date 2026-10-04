#!/usr/bin/env python3
"""Render data/scores/analysis.json (src/analyze_full.py) into a Markdown section for docs/RESULTS.md.
  python3 tools/results_md.py data/scores/analysis.json [summary-line]  → prints Markdown
Honest by construction: every hypothesis gets a verdict from the numbers (supported / not supported / inconclusive)."""
import json, sys, datetime as dt
R = json.load(open(sys.argv[1])); note = sys.argv[2] if len(sys.argv) > 2 else ''
pct = lambda x: '—' if x is None else f'{x*100:.1f} %'
f3 = lambda x: '—' if x is None else f'{x:+.3f}'
out = []
split = dt.datetime.utcfromtimestamp(R['split']).strftime('%d %b %H:%M UTC')
out.append(f"## Run 2 — full 30-day stream ({dt.date.today():%d %b %Y})")
out.append(f"{R['signals']:,} signals over {R['days']:.1f} days; validation = signals after {split} ({R['val_signals']:,} signals), never used for selection. {note}".strip())
out.append('')
for prof in ('fast', 'picker'):
    if prof not in R: continue
    r = R[prof]; title = 'Fast profile (×2 within 1 h)' if prof == 'fast' else 'Picker profile (pool or ×5 within 24 h, ≥ ×1.5 from entry)'
    out.append(f'### {title}')
    out.append(f"Market hit rate: selection {pct(r['market_sel'])}, validation {pct(r['market_val'])}; by curve bucket on validation: " + ', '.join(f'b{k}: {pct(v)}' for k, v in sorted(r['by_bucket_val'].items(), key=lambda kv: int(kv[0]))) + '.')
    out.append('')
    out.append('**H1 · Portfolio.** Top-N by score on the validation period vs the market at the same curve positions and vs placebo lists of the same size (50 random draws).')
    out.append('')
    out.append('| List | Val. signals | Wallets | Hit | Expected | Excess | Placebo excess (mean / p95) |')
    out.append('| --- | --- | --- | --- | --- | --- | --- |')
    verdict = []
    for N, t in sorted(r['topN'].items(), key=lambda kv: int(kv[0])):
        out.append(f"| top-{N} | {t['val_signals']} | {t['val_wallets']} | {pct(t['hit'])} | {pct(t['expected'])} | {f3(t['excess'])} | {f3(t['placebo_excess_mean'])} / {f3(t['placebo_excess_p95'])} |")
        if t['excess'] is not None and t['placebo_excess_p95'] is not None and t['val_signals'] >= 50: verdict.append((int(N), t['excess'] > t['placebo_excess_p95'], t['excess']))
    beats = [N for N, ok, _ in verdict if ok]
    if not verdict: v = 'inconclusive — too few validation signals.'
    elif beats: v = f"**supported** for top-{', '.join(map(str, beats))}: excess above the placebo 95th percentile" + (f"; not for top-{', '.join(str(N) for N, ok, _ in verdict if not ok)}." if len(beats) < len(verdict) else '.')
    else: v = '**not supported** — no list beats the placebo 95th percentile on the validation period.'
    out.append(''); out.append(f'Verdict: {v}'); out.append('')
    m = r.get('magnitude_top100')
    if m:
        out.append('**H2 · Magnitude.** Top-100 vs the market re-weighted to the same curve buckets.')
        out.append('')
        out.append('| Threshold | ' + ' | '.join(f'≥{th}' for th in ('1.3', '1.5', '1.8', '2', '3', '5')) + ' | median |')
        out.append('| --- | ' + ' | '.join('---' for _ in range(6)) + ' | --- |')
        for h, lab in (('ath_1h', 'peak 1 h'), ('ath_24h', 'peak 24 h')):
            if h not in m: continue
            out.append(f"| {lab} · top-100 | " + ' | '.join(pct(m[h][th]['top']) for th in ('1.3', '1.5', '1.8', '2', '3', '5')) + f" | ×{m[h]['median']['top']:.2f} |")
            out.append(f"| {lab} · market | " + ' | '.join(pct(m[h][th]['market_same_buckets']) for th in ('1.3', '1.5', '1.8', '2', '3', '5')) + f" | ×{m[h]['median']['market']:.2f} |")
        dd = m.get('min_10m_lt_0.5'); tt = m.get('t_ath_1h_median')
        extra = []
        if dd: extra.append(f"drawdown below 0.5× within 10 min: top {pct(dd['top'])} vs market {pct(dd['market'])}")
        if tt: extra.append(f"median time to the 1-h peak: top {tt['top']:.0f} s vs market {tt['market']:.0f} s")
        if extra: out.append(''); out.append('; '.join(extra) + '.')
        a = m.get('ath_1h');
        if a:
            better = sum(a[th]['top'] > a[th]['market_same_buckets'] for th in ('1.3', '1.5', '1.8', '2', '3', '5'))
            out.append(''); out.append('Verdict: ' + ('**supported** — the top-100 leads the market at every threshold, i.e. the edge is in the whole distribution, not only at ×2.' if better == 6 else f'**partly** — top-100 ahead at {better} of 6 thresholds.' if better >= 3 else '**not supported** — the top-100 does not lead the market on magnitude.'))
        out.append('')
    c = r.get('cluster_signal')
    if c and prof == 'fast':
        out.append('**H4 · Confirmation.** A second top-100 wallet buying the same token within 60 s.')
        out.append('')
        out.append(f"Confirmed signals: {c['confirmed_n']} with hit {pct(c['confirmed_hit'])}; single signals: {c['single_n']} with hit {pct(c['single_hit'])}.")
        if c['confirmed_hit'] is not None and c['single_hit'] is not None and c['confirmed_n'] >= 30:
            out.append(''); out.append('Verdict: ' + ('**supported** — confirmed signals hit more often.' if c['confirmed_hit'] > c['single_hit'] + 0.03 else '**not supported** — no meaningful lift from confirmation.'))
        else: out.append(''); out.append('Verdict: inconclusive — fewer than 30 confirmed signals.')
        out.append('')
    w = r.get('week_to_week') or []
    out.append('**H5 · Stability.** Spearman correlation of wallet excess week → next week (wallets with ≥ 10 signals in both).')
    out.append('')
    if w:
        out.append(', '.join(f'week {a}→{a+1}: ρ = {rho:.2f} (n = {k})' for a, k, rho in w) + '.')
        mean_rho = sum(x[2] for x in w) / len(w)
        out.append(''); out.append('Verdict: ' + ('**supported** — skill persists week to week (ρ ≥ 0.2).' if mean_rho >= 0.2 else '**weak** — some persistence (0.1 ≤ ρ < 0.2); selection must keep re-validating.' if mean_rho >= 0.1 else '**not supported** — wallet edge does not persist week to week; the list must be re-selected continuously.'))
    else: out.append('Not enough wallets with ≥ 10 signals in consecutive weeks.')
    out.append('')
if 'picker' in R: out.append('H3 (pickers) is the picker block above.')
print('\n'.join(out))
