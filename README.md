# Kalita

**A continuously curated, verifiable list of the wallets that actually beat the market on the Pons launchpad (Robinhood Chain).**

Copy-trading lives or dies by *who* you copy. Public "smart wallet" lists are built by hindsight: they show the
wallets that got lucky last week and quietly rotate them out when they stop working. Kalita replaces that with
arithmetic — every early buyer on the bonding curve is scored against the market *at the same point on that
curve*, validated on data it has never seen, and the resulting list is committed on chain daily so it cannot be
rewritten to look good in retrospect.

> Status: research prototype built in September 2026 on Robinhood Chain mainnet data. Not financial advice.

| | |
|---|---|
| Site | https://kalita.tech |
| Panel | https://app.kalita.tech — Overview, candidates (5 000) and today's list are public, no account needed |
| **Try it in one click** | **https://app.kalita.tech/?demo=1** — a private demo account for 24 h: your own lists, export and API keys. The official list can't be changed from it. |
| Public list snapshots | https://kalita.tech/registry/ (Merkle proofs, verifiable in the browser) |
| Results | https://kalita.tech/results/ — every pre-registered hypothesis with its verdict, negative ones included |
| On-chain registry | `KalitaRegistry` on Robinhood Chain mainnet: [`0xC7C5EF8e395e20e626670a9D2a5909e92bce31ca`](https://robinhoodchain.blockscout.com/address/0xC7C5EF8e395e20e626670a9D2a5909e92bce31ca?tab=contract) — no owner, no admin, no upgrades (`contracts/`) |

## What it does

1. **Reads every curve trade.** `src/fetch_stream.py` streams the four Pons v2 events (launch, buy, sell,
   graduation) for the whole chain via HyperSync, and resolves the 45 % of buys routed through the universal
   router to their real owner (100 % resolved). 30 days ≈ 26 M blocks, 450 k+ tokens, 8 M signals.
2. **Builds a passport for every signal.** A signal is a wallet's first buy of a token. For each one we simulate
   our own entry 2 s later (the measured median delay of a copy-trader) and record the peak at 1 m … 30 d, the
   time to peak, the minimum in the first 10 minutes (rug), the drawdown before the first ×1.5 / ×2 / ×5,
   whether the token graduated to a pool, and when the wallet itself first sold.
3. **Scores wallets against their own baseline.** Two profiles: *fast* (hit = ×2 within 1 h) and *picker*
   (hit = graduated or ×5 within 24 h, with at least ×1.5 from our entry). The market rate is computed per
   bucket of "how much of the curve was already filled when the wallet bought", so a wallet is compared with
   buyers at the same position, not with the whole market. Estimates use Beta shrinkage and a Wilson lower bound;
   *edge* = lower bound − expected rate; rank = edge·√n. Wallets sharing ≥ 50 % of tokens and buy blocks are
   collapsed into one cluster.
4. **Validates out of sample.** Selection on the first N−7 days, validation on the last 7; a placebo list of the
   same size is scored alongside. A wallet that looks great in sample and reverts to the market on validation
   does not make the list — which is exactly what happened to the "best" wallet of our first run.
5. **Keeps the list honest over time.** Hysteresis rules (enter after k good days, exit after m bad days,
   quarantine before re-check), a change log and a rejected-wallet database live in the panel.
6. **Serves the list to people and engines.** The panel (12 languages) shows candidates with their edge over the
   market, filter presets, a change log, a rejected-wallet database and a glossary of every metric; users keep
   personal lists and export them in the engine format; a public API (`/v1/summary`, `/v1/list/{profile}`,
   `/v1/candidates/{profile}`, `/v1/wallet/{addr}`, `/v1/snapshots`) serves the same data with an API key.
7. **Commits every snapshot on chain.** `deploy/registry-publish.sh` builds the Merkle root of the list, the
   size and the added/removed counts, publishes them to `KalitaRegistry`, and serves the member list with one
   proof per wallet at `kalita.tech/registry/`. Anyone can verify membership on a given day and measure the
   list's performance strictly after each snapshot.

## Results so far

Full 30-day run (28 Aug – 28 Sep 2026; 8.0 M signals, 862 k wallets, 451 k tokens; validation = the last 7 days,
never used for selection):

- The top-100 list by score hit ×2 within 1 h on **21.8 %** of its out-of-sample signals against **14.8 %**
  expected for buyers at the same curve positions (+7.0 pp; placebo lists of the same size reach +6.2 pp only at
  their 95th percentile). Top-300: 23.5 % vs 17.8 %.
- The edge is in the whole distribution: median 1-h peak ×1.27 vs ×1.07 for the market at the same positions.
- A wallet's edge persists week to week (Spearman ρ = 0.34–0.37 on 7–12 k wallets) — skill is measurable.
- The top wallets are riskier per signal (21.6 % vs 14.6 % of signals fall below 0.5× within 10 min).
- The picker profile is not yet separable from placebo; the pool-price backfill is pending.
- The 1 132-wallet Telegram list scores slightly *above* the market on 30 days (fast lift 1.11, picker 1.62);
  our first 5-day run had it below the market — that claim was a small-sample artefact and is withdrawn.

Every hypothesis with its verdict, negative ones included: https://kalita.tech/results/ (`docs/RESULTS.md`).

## Try it

| What | How |
|---|---|
| Browse without an account | https://app.kalita.tech → Candidates: 17 range filters, presets *fast* / *soft*, sort by any column, click an address for the wallet card |
| Your own lists and API keys | https://app.kalita.tech/?demo=1 — no sign-up; the demo account and everything in it is deleted after 24 h. Sign in with a wallet or an email link to keep your work |
| Verify a snapshot | https://kalita.tech/registry/ → pick a day, paste an address — the Merkle proof is checked in your browser against the root committed on chain |

### Public API (`/v1`, key from *My lists → API keys*, 60 requests/min)

```bash
K=kl_your_key
curl -H "X-API-Key: $K" https://app.kalita.tech/v1/summary
curl -H "X-API-Key: $K" https://app.kalita.tech/v1/list/fast            # today's official list
curl -H "X-API-Key: $K" "https://app.kalita.tech/v1/candidates/fast?limit=100"
curl -H "X-API-Key: $K" https://app.kalita.tech/v1/wallet/0xa60e892ab5fbf4754e3052b7643e48a1bd6b3065
curl -H "X-API-Key: $K" https://app.kalita.tech/v1/snapshots            # daily snapshots with Merkle roots
```

### Verify a snapshot against the chain yourself

```bash
RPC=https://rpc.mainnet.chain.robinhood.com
REG=0xC7C5EF8e395e20e626670a9D2a5909e92bce31ca
cast call $REG "snapshotCount(uint256)(uint256)" 0 --rpc-url $RPC      # list 0 = fast, 1 = picker
cast call $REG "verifyMember(uint256,uint256,address,bytes32[])(bool)" 0 0 <wallet> "[<proof...>]" --rpc-url $RPC
```
Members and proofs for every snapshot are published as JSON next to the registry page (`kalita.tech/registry/*.json`).
Leaf = `keccak256(0x00 ‖ address)`, node = `keccak256(0x01 ‖ min ‖ max)`.

## Repository

```
src/fetch_stream.py       chain → data/stream/ (tokens.json, series.csv, checkpoints)
src/build_passports.py    stream → data/signals.csv (one row per signal, all horizons)
src/score_wallets.py      signals → data/scores/scores_{fast,picker}.csv + report
src/analyze_full.py       five pre-registered hypotheses (portfolio, magnitude, pickers, clusters, stability)
src/compare_lists.py      any external list vs. our scoring (lists/*.txt)
src/registry_snapshot.py  Merkle root + proofs for KalitaRegistry (pure Python keccak, shared test vector)
src/server.js, ui.html    panel and API (Node ≥ 18, no dependencies)
contracts/                KalitaRegistry (Foundry, 15 tests incl. fuzzing)
deploy/                   VPS setup, daily pipeline, autopilot (pulls main every minute, runs jobs/)
site/                     kalita.tech
```

## Run locally

```bash
HYPERSYNC_TOKEN=... python3 src/fetch_stream.py --out data/stream --days 7
python3 src/build_passports.py data/stream data/signals.csv
python3 src/score_wallets.py data/signals.csv data/scores
node src/server.js                      # http://localhost:8830
cd contracts && forge test -vv          # KalitaRegistry
```
Needs python3 + pandas + numpy, node ≥ 18, foundry for the contract.

## Documentation

- [docs/METHOD.md](docs/METHOD.md) — the statistics, in full and in plain words
- [docs/RESULTS.md](docs/RESULTS.md) — what we found, including the negative results
- [contracts/README.md](contracts/README.md) — the on-chain registry and how to verify a list
- [README.ru.md](README.ru.md) — документация по-русски
