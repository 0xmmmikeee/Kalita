# Results

All numbers are out-of-sample unless stated otherwise. "Hit" = ×2 within 1 h of a follower's entry 2 s after the
wallet (fast profile). "Expected" = the market's hit rate for buyers at the same curve positions.

## Run 1 — 5 days of history (26–27 Sep 2026), before the full stream
- 6 000+ signals from tokens that had at least one tracked buyer.
- Top-100 list by score: **28.8 %** hit on the validation period vs **22–23 %** expected. Placebo lists of the
  same size: ≈ market.
- The 1 132-wallet Telegram list: **17.5 %** vs **24.7 %** expected (lift 0.71). Its wallets buy early, which
  makes their raw hit rate look fine; against buyers at the same positions they are below average.
- The single best wallet in sample (33.3 % on 183 signals, expected 23.7 %) scored between 20 % and 30 % on the
  validation week — regression to the mean; it does not pass a validation threshold of 30 %.

## Run 2 — headline (full 30 days, 28 Sep 2026)

- **8.0 M signals, 862 k wallets, 451 k tokens, 31 days** (28 Aug → 28 Sep 2026); validation = the last 7 days,
  748 k signals never used for selection.
- **The fast list works.** Top-100 wallets by score hit ×2 within 1 h on **21.8 %** of validation signals against
  **14.8 %** expected for buyers at the same curve positions (+7.0 pp, lift 1.47); placebo lists of the same size
  reach +6.2 pp only at their 95th percentile. Top-300: 23.5 % vs 17.8 % (+5.7 pp; placebo p95 +4.4 pp). Top-25 and
  top-50 are positive (+8.6 / +7.0 pp) but not separable from placebo at their sample size.
- **The edge is the whole distribution, not one threshold.** Median 1-h peak ×1.27 for top-100 signals vs ×1.07 for
  the market at the same positions; ahead at every threshold from ×1.3 to ×5, at 1 h and at 24 h.
- **It is riskier per signal.** 21.6 % of top-100 signals fall below 0.5× within 10 minutes vs 14.6 % for the
  market — the wallets that win big also buy tokens that die fast. Position sizing, not the list, has to handle that.
- **Skill persists.** A wallet's excess over the market this week predicts next week: Spearman ρ = 0.34–0.37 on
  7–12 k wallets per pair of weeks. This is the finding that makes a list worth keeping at all.
- **Confirmation helps.** A second top-100 wallet in the same token within 60 s lifts the hit rate from 21.1 % to
  26.3 %.
- **Pickers: not proven yet.** Top lists are +4–5 pp over the market, but placebo lists of the same size are
  themselves +1–2 pp and their 95th percentile is above the observed excess. Week-to-week persistence is strong
  (ρ ≈ 0.5), so the signal may be real, but the pool-price backfill for the first 20 days is still pending and
  the picker hit depends on 24-h peaks after graduation. Re-run after the backfill.
- **Correction to Run 1.** On 5 days the 1 132-wallet Telegram list looked worse than random (17.5 % vs 24.7 %).
  On 30 days it is slightly better than the market: fast 23.7 % vs 21.4 % expected (lift 1.11), picker 15.7 % vs
  9.7 % (lift 1.62); its wallets simply are not concentrated in our top-100 (0 of them) — the earlier claim was a
  small-sample artefact and is withdrawn from the site and the pitch.

## Run 2 — full 30-day stream (28 Sep 2026)
8,011,903 signals over 31.4 days; validation = signals after 21 Sep 12:13 UTC (748,074 signals), never used for selection. Fast-profile passports use curve prices and, from 22 Sep, Uniswap v4 pool prices after graduation; the pool-price backfill for the earlier days is pending, so the picker profile (which depends on 24-h peaks after graduation) is measured conservatively here.

### Fast profile (×2 within 1 h)
Market hit rate: selection 19.9 %, validation 18.3 %; by curve bucket on validation: b0: 7.2 %, b1: 15.5 %, b2: 23.5 %, b3: 28.9 %, b4: 7.0 %.

**H1 · Portfolio.** Top-N by score on the validation period vs the market at the same curve positions and vs placebo lists of the same size (50 random draws).

| List | Val. signals | Wallets | Hit | Expected | Excess | Placebo excess (mean / p95) |
| --- | --- | --- | --- | --- | --- | --- |
| top-25 | 592 | 14 | 20.4 % | 11.8 % | +0.086 | -0.010 / +0.097 |
| top-50 | 3286 | 20 | 21.5 % | 14.5 % | +0.070 | -0.010 / +0.126 |
| top-100 | 3396 | 29 | 21.8 % | 14.8 % | +0.070 | -0.002 / +0.062 |
| top-300 | 5441 | 87 | 23.5 % | 17.8 % | +0.057 | -0.001 / +0.044 |

Verdict: **supported** for top-100, 300: excess above the placebo 95th percentile; not for top-25, 50.

**H2 · Magnitude.** Top-100 vs the market re-weighted to the same curve buckets.

| Threshold | ≥1.3 | ≥1.5 | ≥1.8 | ≥2 | ≥3 | ≥5 | median |
| --- | --- | --- | --- | --- | --- | --- | --- |
| peak 1 h · top-100 | 47.6 % | 37.1 % | 26.1 % | 21.8 % | 10.5 % | 4.0 % | ×1.27 |
| peak 1 h · market | 33.1 % | 24.8 % | 17.7 % | 14.6 % | 7.0 % | 3.1 % | ×1.07 |
| peak 24 h · top-100 | 42.3 % | 32.7 % | 23.0 % | 19.3 % | 9.2 % | 3.8 % | ×1.28 |
| peak 24 h · market | 30.8 % | 23.4 % | 17.1 % | 14.4 % | 7.3 % | 3.4 % | ×1.08 |

drawdown below 0.5× within 10 min: top 21.6 % vs market 14.6 %; median time to the 1-h peak: top 29 s vs market 45 s.

Verdict: **supported** — the top-100 leads the market at every threshold, i.e. the edge is in the whole distribution, not only at ×2.

**H4 · Confirmation.** A second top-100 wallet buying the same token within 60 s.

Confirmed signals: 407 with hit 26.3 %; single signals: 2989 with hit 21.1 %.

Verdict: **supported** — confirmed signals hit more often.

**H5 · Stability.** Spearman correlation of wallet excess week → next week (wallets with ≥ 10 signals in both).

week 0→1: ρ = 0.34 (n = 12065), week 1→2: ρ = 0.37 (n = 11760), week 2→3: ρ = 0.34 (n = 7163), week 3→4: ρ = 0.37 (n = 2183).

Verdict: **supported** — skill persists week to week (ρ ≥ 0.2).

### Picker profile (pool or ×5 within 24 h, ≥ ×1.5 from entry)
Market hit rate: selection 9.5 %, validation 11.5 %; by curve bucket on validation: b0: 3.0 %, b1: 6.7 %, b2: 11.5 %, b3: 22.5 %.

**H1 · Portfolio.** Top-N by score on the validation period vs the market at the same curve positions and vs placebo lists of the same size (50 random draws).

| List | Val. signals | Wallets | Hit | Expected | Excess | Placebo excess (mean / p95) |
| --- | --- | --- | --- | --- | --- | --- |
| top-25 | 13039 | 18 | 15.5 % | 11.8 % | +0.036 | +0.024 / +0.183 |
| top-50 | 16160 | 38 | 16.0 % | 11.9 % | +0.041 | +0.010 / +0.092 |
| top-100 | 21768 | 79 | 16.1 % | 11.8 % | +0.043 | +0.016 / +0.078 |
| top-300 | 29394 | 204 | 17.1 % | 12.2 % | +0.049 | +0.012 / +0.052 |

Verdict: **not supported** — no list beats the placebo 95th percentile on the validation period.

**H2 · Magnitude.** Top-100 vs the market re-weighted to the same curve buckets.

| Threshold | ≥1.3 | ≥1.5 | ≥1.8 | ≥2 | ≥3 | ≥5 | median |
| --- | --- | --- | --- | --- | --- | --- | --- |
| peak 1 h · top-100 | 43.3 % | 33.0 % | 24.0 % | 20.3 % | 10.1 % | 3.8 % | ×1.20 |
| peak 1 h · market | 44.5 % | 34.1 % | 24.2 % | 19.8 % | 8.9 % | 2.9 % | ×1.23 |
| peak 24 h · top-100 | 45.8 % | 36.2 % | 27.4 % | 23.7 % | 13.1 % | 5.5 % | ×1.24 |
| peak 24 h · market | 46.3 % | 36.2 % | 26.4 % | 22.1 % | 10.8 % | 3.6 % | ×1.25 |

drawdown below 0.5× within 10 min: top 18.5 % vs market 30.8 %; median time to the 1-h peak: top 87 s vs market 62 s.

Verdict: **partly** — top-100 ahead at 3 of 6 thresholds.

**H5 · Stability.** Spearman correlation of wallet excess week → next week (wallets with ≥ 10 signals in both).

week 0→1: ρ = 0.51 (n = 10114), week 1→2: ρ = 0.56 (n = 10068), week 2→3: ρ = 0.55 (n = 6026), week 3→4: ρ = 0.51 (n = 1362).

Verdict: **supported** — skill persists week to week (ρ ≥ 0.2).

H3 (pickers) is the picker block above.


Raw numbers: `docs/data/analysis-run2.json` (output of `src/analyze_full.py`).
