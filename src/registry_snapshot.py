#!/usr/bin/env python3
"""wallet-lab · снимок списка для KalitaRegistry: Merkle-корень, доказательства для каждого адреса, аргументы publishSnapshot.

  python3 src/registry_snapshot.py state/active.json --profile fast --out data/registry [--prev data/registry/fast-latest.json]
  python3 src/registry_snapshot.py --vector          # тест-вектор, общий с contracts/test/KalitaRegistry.t.sol

Схема (как в контракте): лист = keccak256(0x00 ‖ address20), узел = keccak256(0x01 ‖ min ‖ max), нечётный хвост поднимается без пары.
Без внешних зависимостей: keccak-256 реализован здесь же и проверен на стандартном векторе.
"""
import sys, os, json, time

# ----------------------------------------------------------------------------- keccak-256 (FIPS-202 permutation, pad 0x01)
_RC = [0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
       0x8000000080008081, 0x8000000000008009, 0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
       0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
       0x000000000000800A, 0x800000008000000A, 0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M = (1 << 64) - 1
def _rol(x, n): n %= 64; return ((x << n) | (x >> (64 - n))) & _M if n else x
def _f(A):
    for rc in _RC:
        C = [A[x][0] ^ A[x][1] ^ A[x][2] ^ A[x][3] ^ A[x][4] for x in range(5)]
        D = [C[(x - 1) % 5] ^ _rol(C[(x + 1) % 5], 1) for x in range(5)]
        A = [[A[x][y] ^ D[x] for y in range(5)] for x in range(5)]
        B = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5): B[y][(2 * x + 3 * y) % 5] = _rol(A[x][y], _ROT[x][y])
        A = [[B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        A[0][0] ^= rc
    return A
def keccak256(data: bytes) -> bytes:
    rate = 136; A = [[0] * 5 for _ in range(5)]
    msg = bytearray(data) + b'\x01'; msg += b'\x00' * ((-len(msg)) % rate); msg[-1] |= 0x80
    for off in range(0, len(msg), rate):
        blk = msg[off:off + rate]
        for i in range(rate // 8):
            A[i % 5][i // 5] ^= int.from_bytes(blk[8 * i:8 * i + 8], 'little')
        A = _f(A)
    out = b''
    for i in range(4): out += A[i % 5][i // 5].to_bytes(8, 'little')
    return out
assert keccak256(b'').hex() == 'c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470', 'keccak self-test failed'

# ----------------------------------------------------------------------------- merkle
def leaf(addr: str) -> bytes: return keccak256(b'\x00' + bytes.fromhex(addr[2:].lower()))
def node(a: bytes, b: bytes) -> bytes: return keccak256(b'\x01' + (a + b if a < b else b + a))
def build(addrs):
    """Возвращает (root_hex, proofs: {addr: [hex,...]}); порядок листьев = порядок addrs (сортируем адреса заранее)."""
    leaves = [leaf(a) for a in addrs]
    if not leaves: raise ValueError('пустой список')
    proofs = {a: [] for a in addrs}; idx = {a: i for i, a in enumerate(addrs)}
    level = leaves[:]; pos = dict(idx)
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level): nxt.append(node(level[i], level[i + 1]))
            else: nxt.append(level[i])
        for a, p in pos.items():
            sib = p ^ 1
            if sib < len(level): proofs[a].append('0x' + level[sib].hex())
        pos = {a: p // 2 for a, p in pos.items()}; level = nxt
    return '0x' + level[0].hex(), proofs
def verify(root_hex, addr, proof):
    h = leaf(addr)
    for p in proof: h = node(h, bytes.fromhex(p[2:]))
    return '0x' + h.hex() == root_hex

# ----------------------------------------------------------------------------- main
def main():
    a = sys.argv[1:]
    if '--vector' in a:
        addrs = ['0x' + c * 40 for c in '123']
        root, proofs = build(addrs)
        print('root(3 fixed addresses):', root); print('proof[2]:', proofs[addrs[2]]); print('verify:', verify(root, addrs[2], proofs[addrs[2]]))
        return
    def arg(k, d=None):
        return a[a.index('--' + k) + 1] if '--' + k in a else d
    src = a[0]; profile = arg('profile', 'fast'); out = arg('out', 'data/registry'); prev_f = arg('prev', os.path.join(out, f'{profile}-latest.json'))
    as_of = int(arg('as-of', 0)) or int(time.time())
    os.makedirs(out, exist_ok=True)
    if src.endswith('.txt'):
        addrs = sorted({l.strip().lower() for l in open(src) if l.strip().lower().startswith('0x') and len(l.strip()) == 42})
    else:
        act = json.load(open(src))  # state/active.json: {wallet: {profile, ...}}
        addrs = sorted({w.lower() for w, v in act.items() if (v.get('profile') if isinstance(v, dict) else v) == profile})
    if not addrs: print(f'список «{profile}» пуст — снимок не делаем'); sys.exit(2)
    root, proofs = build(addrs)
    prev = set()
    if os.path.exists(prev_f):
        try: prev = set(json.load(open(prev_f)).get('members', []))
        except Exception: prev = set()
    added = len([w for w in addrs if w not in prev]); removed = len([w for w in prev if w not in set(addrs)])
    snap = {'profile': profile, 'asOf': as_of, 'size': len(addrs), 'added': added if prev else len(addrs), 'removed': removed if prev else 0,
            'root': root, 'members': addrs, 'proofs': proofs, 'scheme': 'leaf=keccak(0x00||addr) node=keccak(0x01||min||max)'}
    fn = os.path.join(out, f'{profile}-{time.strftime("%Y%m%d", time.gmtime(as_of))}.json')
    json.dump(snap, open(fn, 'w'), indent=1); json.dump(snap, open(os.path.join(out, f'{profile}-latest.json'), 'w'), indent=1)
    assert all(verify(root, w, proofs[w]) for w in addrs)
    print(f'{profile}: {len(addrs)} адресов, +{snap["added"]} −{snap["removed"]}, root {root}')
    print(f'publishSnapshot args: <id> {root} {snap["size"]} {snap["added"]} {snap["removed"]} {as_of} "https://kalita.tech/registry/{os.path.basename(fn)}"')
    print(fn)

if __name__ == '__main__': main()
