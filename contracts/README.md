# KalitaRegistry

On-chain, tamper-evident history of Kalita's curated wallet lists. Every daily snapshot of a list is committed as
the Merkle root of its members with the list size and the number of wallets added and removed, strictly ordered
in time. Anyone can prove that a wallet was in the list on a given day (`verifyMember`) and measure the list's
performance only on data that came *after* each snapshot — the list cannot be rewritten to look good in hindsight.

No owner, no admin, no upgrades, no funds held. Merkle scheme:
leaves `keccak(0x00 ‖ address)`, nodes `keccak(0x01 ‖ min ‖ max)`).

```bash
forge install foundry-rs/forge-std     # once
forge test -vv
forge script script/Deploy.s.sol --rpc-url robinhood_testnet --account kalita-deployer --broadcast
```

Off-chain: `python3 src/registry_snapshot.py data/scores/active.json --profile fast --out data/registry/` builds the
root, the member list and one proof per member (`snapshot.json`), and prints the `publishSnapshot` arguments;
`deploy/daily.sh` publishes it with `cast` when `KALITA_REGISTRY` and a publisher key are configured.

Networks: Robinhood Chain mainnet (chain id 4663) and testnet (46630, explorer https://explorer.testnet.chain.robinhood.com).

## Deployments
| Network | Address | Deploy tx |
|---|---|---|
| Robinhood Chain mainnet (4663) | [`0xC7C5EF8e395e20e626670a9D2a5909e92bce31ca`](https://robinhoodchain.blockscout.com/address/0xC7C5EF8e395e20e626670a9D2a5909e92bce31ca?tab=contract) (source verified, exact match) | `0x013717344728729be369dc58eb99cc6f4e981b69eedcdf54febe282c4c414469` |

Lists: `fast` = id 0 (300 wallets), `picker` = id 1 (100 wallets). First snapshots (4 Oct 2026):
fast `0x03780b93732158c08d0760ef9e41cb1cea4ccb983d6d570c079a7bb0e65a4dc7`, picker `0x4fbbeb86360063b708cc226621b42b5c909261d12c3155ade47d599e5e520323`.
