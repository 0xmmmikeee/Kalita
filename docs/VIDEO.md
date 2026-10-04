# Demo video — narration (v3, ~2:45, 30-day results, voice-over)

`kalita-demo-v3.mp4` (1920×1080, 9 scenes, synthesized narration + music bed) — all numbers from the full 30-day run
(Run 2), no cross-references to other projects. A short cut `kalita-demo-v3-short.mp4` (~2:00) uses `tools/video/lines-short.py`.
Pipeline: `tools/video/build.sh` (gen → render → mapbar → remap → mux); live panel screenshots come from `tools/video/shots.py`
(run on the server, branch `shots`).

| Time | Scene | Say |
|---|---|---|
| 0:00 | Title | Kalita. Follow the wallets that actually beat the market — on Robinhood Chain. |
| 0:06 | Problem | Copy-trading on a launchpad is a “who to follow” problem, and the market answers it dishonestly. Smart-wallet lists are assembled by hindsight, refreshed by hand, and never audited. We measured a popular list of eleven hundred wallets over thirty days: its signals doubled within an hour twenty-three point seven percent of the time, against twenty-one point four expected for random buyers at the same positions on the curve. A lift of one point one — and nobody who follows that list has ever seen that number. |
| 0:37 | Landing | Kalita scores every early buyer on the Pons bonding curve — eight million signals, eight hundred and sixty thousand wallets, four hundred and fifty thousand tokens — and keeps a live, self-correcting list. |
| 0:50 | Method | Three ideas. One: for each wallet's first buy, we simulate a follower entering two seconds later, and record what happens to that follower. Two: a fifth buyer is compared with fifth buyers — the market rate is computed per position on the curve, because early is not the same as skilled. Three: estimates are shrunk and pessimistic; the list is selected on one period and validated on the last seven days, next to a placebo list. |
| 1:19 | Panel | The panel shows candidates with their edge over the market, filter presets, a change log and a rejected-wallet database — in twelve languages. Users sign in with a wallet or an email, keep personal lists, and export straight into a copy-trading engine, or pull the data through the API. |
| 1:38 | Validation | Validation catches luck. A wallet that hit thirty-eight percent on seven hundred and ninety-one signals fell to fifteen percent on the week it had never seen — below the market. It is not on the list. That is the system working. |
| 1:53 | On chain | Every daily list is sealed on chain in Kalita Registry: no contract owner, no admin key, no upgrades. A Merkle root, the size, the wallets added and removed — strictly ordered in time. Anyone can verify that a wallet was on the list on a given day, and measure the list only on trades that came after. Fifteen Foundry tests, including fuzzing. |
| 2:16 | Results | Thirty days, out of sample: the top-hundred list hit two-x within an hour twenty-one point eight percent of the time, against fourteen point eight for the market at the same positions. Placebo lists of the same size stay at the market, and wallet skill persists from week to week. Five pre-registered hypotheses, verdicts published — the negative ones too. |
| 2:39 | Close | kalita dot tech. Who to follow — with a record that cannot be rewritten. |

