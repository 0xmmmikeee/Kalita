# Method

Kalita answers one question: *which wallets buy tokens on the Pons bonding curve better than a random buyer
standing at the same spot would?* Everything below serves that question. Each section is written twice: first
the way a statistician would put it, then the way we would explain it over coffee.

## 1. The unit of observation: a signal

**Formally.** A signal is the first `CurveBuy` of wallet *w* in token *t*. For every signal we simulate a follower
entering *d* seconds later (*d* = 2 s, the median delay we measured for a live copy-trader on this chain; also
computed for 0, 5 and 10 s) at the curve price at that moment, and record the forward path of the price relative
to that entry: the maximum on horizons of 1 m, 5 m, 15 m, 30 m, 1 h, 4 h, 12 h, 24 h, 7 d and 30 d and the time
to each maximum, the minimum in the first 10 minutes, the largest drawdown before the first ×1.5, ×2 and ×5, the
graduation time if the token ever reached a pool, and the wallet's own first sell. A horizon is recorded only
when the whole window is inside the observed data; otherwise it is missing, not truncated.

**Plainly.** We don't ask "did this wallet make money" — we can't see its exits reliably and it may have bought at
a price we can't get. We ask "if I had followed this wallet two seconds later, what would have happened to me?"

## 2. Two profiles, two definitions of success

- **fast**: hit = the price reaches ×2 within 1 hour of our entry. Meant for strategies that exit by take-profit
  or by the clock within minutes.
- **picker**: hit = the token graduates to a pool or reaches ×5 within 24 h, *and* the price reaches at least
  ×1.5 from our entry. The second condition matters: buying the last slice of an almost-full curve "graduates"
  with ×1.0 — that is not picking, it is queueing. Signals where more than 60 % of the graduation threshold was
  already collected are excluded from this profile for the same reason.

## 3. The baseline: compare like with like

**Formally.** Let *c* be the fraction of the graduation threshold the curve had collected before the wallet's buy.
We bucket signals by *c* (0–2 %, 2–10 %, 10–30 %, 30–60 %, 60 %+) and compute the market hit rate *p₀(b)* per
bucket on the selection period. A wallet's expected hit rate is the average of *p₀* over the buckets of its own
signals.

**Plainly.** Early buyers hit ×2 far more often than late buyers simply because they are early — the curve does
the work, not the wallet. A wallet that buys 5th every time and hits 30 % is not skilled if every 5th buyer hits
30 %. So every wallet is measured against buyers at *its* position.

## 4. The estimate: shrink, then be pessimistic

**Formally.** With *k* hits in *n* signals and expected rate *p̂*, the shrunk rate is (k + m·p̂)/(n + m) with
*m* = 10 (a Beta prior centred on the wallet's own baseline). The reported lower bound is the one-sided Wilson
80 % bound of *k/n*. *Edge* = lower bound − *p̂*. Ranking score = edge·√n, so that a small edge on many signals
outranks a large edge on five.

**Plainly.** Ten signals tell you almost nothing; the estimate is pulled toward "this wallet is average" until the
evidence accumulates. And we rank by the pessimistic number, not the raw one — a wallet earns its place by being
above the market even in the unlucky reading of its history.

## 5. Out-of-sample validation and placebo

**Formally.** The observation window is split at *T* − 7 days. Scores are computed on the selection part only.
On the validation part we compute, for the top-N list, the pooled hit rate and the expected rate by bucket, and
the same for 50 random lists of *N* wallets drawn from all wallets with ≥ 5 signals (placebo). A list is
interesting only if its validation excess exceeds the placebo's 95th percentile.

**Plainly.** Any rule finds "winners" in the data it was fitted on. The only test that counts is on days the rule
never saw. In our first run the single best wallet (33 % in sample, 183 signals) fell to the market rate on the
validation week — and the panel dropped it. That is the system working.

## 6. Clusters, contracts and bots

Wallets with Jaccard similarity ≥ 0.5 over the tokens they bought *and* over the blocks they bought in are treated
as one owner; only the first of a cluster can enter the list. Addresses with code (`eth_getCode`) are flagged as
contracts and excluded; addresses with ≥ 300 distinct tokens are flagged for review as bots.

## 7. Keeping the list honest: hysteresis

A wallet enters after passing the thresholds on `enter_days` consecutive daily runs and leaves after failing
`exit_excess` on `exit_days` consecutive runs; a removed wallet is quarantined for `recheck_days` before it can
come back. Every change is logged with its reason. This trades a few days of latency for a list that does not
thrash with the noise of a single day.

## 8. The on-chain registry

Each daily list is committed to `KalitaRegistry` as the Merkle root of its members with the size and the number of
wallets added and removed, strictly ordered by the data cut-off time. The full member list and one Merkle proof
per wallet are published alongside. Two things follow: nobody — including us — can claim a wallet was in the list
on a day it was not, and anyone can evaluate the list on trades that happened *after* the snapshot, which is the
only evaluation that means anything.

## 9. Known limits

- Prices after graduation are not tracked on the pool yet; a picker's ×5 must happen on the curve or is missed.
- The gas subsidy on Robinhood Chain ends on 29 Sep 2026; the population of buyers will change and history
  before that date may stop being representative. Every wallet carries a count of signals after the change.
- Copy-trading a 5th buyer as the 7th is not the same trade; the passport measures the follower's path, but real
  fills are checked by a copy-trading execution engine on paper before anything is traded live.
