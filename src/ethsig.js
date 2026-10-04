'use strict';
// Минимальная криптография для входа по кошельку (EIP-191 personal_sign + восстановление адреса из подписи).
// Без зависимостей: keccak-256 и secp256k1 на BigInt. Достаточно для проверки подписи; для подписи на сервере не используется.

// ---------------- keccak-256
const RC = [1n, 0x8082n, 0x800000000000808an, 0x8000000080008000n, 0x808bn, 0x80000001n, 0x8000000080008081n, 0x8000000000008009n, 0x8an, 0x88n, 0x80008009n, 0x8000000an, 0x8000808bn, 0x800000000000008bn, 0x8000000000008089n, 0x8000000000008003n, 0x8000000000008002n, 0x8000000000000080n, 0x800an, 0x800000008000000an, 0x8000000080008081n, 0x8000000000008080n, 0x80000001n, 0x8000000080008008n];
const ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]];
const M64 = (1n << 64n) - 1n;
const rol = (x, n) => n % 64 === 0 ? x : (((x << BigInt(n % 64)) | (x >> BigInt(64 - n % 64))) & M64);
function keccakF(A) {
  for (let r = 0; r < 24; r++) {
    const C = [0, 1, 2, 3, 4].map(x => A[x][0] ^ A[x][1] ^ A[x][2] ^ A[x][3] ^ A[x][4]);
    const D = [0, 1, 2, 3, 4].map(x => C[(x + 4) % 5] ^ rol(C[(x + 1) % 5], 1));
    for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++) A[x][y] ^= D[x];
    const B = [[], [], [], [], []];
    for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++) B[y][(2 * x + 3 * y) % 5] = rol(A[x][y], ROT[x][y]);
    for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++) A[x][y] = B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y] & M64);
    A[0][0] ^= RC[r];
  }
}
function keccak256(buf) {
  const rate = 136; const A = [[0n, 0n, 0n, 0n, 0n], [0n, 0n, 0n, 0n, 0n], [0n, 0n, 0n, 0n, 0n], [0n, 0n, 0n, 0n, 0n], [0n, 0n, 0n, 0n, 0n]];
  const msg = Buffer.concat([buf, Buffer.from([1])]); const pad = Buffer.alloc((rate - msg.length % rate) % rate); const full = Buffer.concat([msg, pad]);
  full[full.length - 1] |= 0x80;
  for (let off = 0; off < full.length; off += rate) {
    for (let i = 0; i < rate / 8; i++) { const w = full.readBigUInt64LE(off + 8 * i); A[i % 5][Math.floor(i / 5)] ^= w; }
    keccakF(A);
  }
  const out = Buffer.alloc(32); for (let i = 0; i < 4; i++) out.writeBigUInt64LE(A[i % 5][Math.floor(i / 5)], 8 * i); return out;
}

// ---------------- secp256k1
const P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2Fn, N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141n;
const G = [0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798n, 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8n];
const mod = (a, m = P) => ((a % m) + m) % m;
function inv(a, m = P) { let [g, x, y] = [mod(a, m), 1n, 0n], [b, u, v] = [m, 0n, 1n]; while (b) { const q = g / b; [g, b] = [b, g - q * b]; [x, u] = [u, x - q * u]; } return mod(x, m); }
function add(p, q) { if (!p) return q; if (!q) return p; const [x1, y1] = p, [x2, y2] = q; if (x1 === x2) { if (mod(y1 + y2) === 0n) return null; const l = mod(3n * x1 * x1 * inv(2n * y1)); const x3 = mod(l * l - 2n * x1); return [x3, mod(l * (x1 - x3) - y1)]; } const l = mod((y2 - y1) * inv(x2 - x1)); const x3 = mod(l * l - x1 - x2); return [x3, mod(l * (x1 - x3) - y1)]; }
function mul(k, p) { let r = null, a = p; while (k > 0n) { if (k & 1n) r = add(r, a); a = add(a, a); k >>= 1n; } return r; }
function modpow(b, e, m) { let r = 1n; b = mod(b, m); while (e > 0n) { if (e & 1n) r = r * b % m; b = b * b % m; e >>= 1n; } return r; }
function pubToAddress(pub) { const b = Buffer.concat([Buffer.from(pub[0].toString(16).padStart(64, '0'), 'hex'), Buffer.from(pub[1].toString(16).padStart(64, '0'), 'hex')]); return '0x' + keccak256(b).slice(12).toString('hex'); }
function recover(hash, sig) {
  const s = Buffer.from(sig.replace(/^0x/, ''), 'hex'); if (s.length !== 65) return null;
  const r = BigInt('0x' + s.slice(0, 32).toString('hex')), sv = BigInt('0x' + s.slice(32, 64).toString('hex')); let v = s[64]; if (v >= 27) v -= 27; if (v > 1) return null;
  if (r <= 0n || r >= N || sv <= 0n || sv >= N) return null;
  const x = r; const y2 = mod(x ** 3n + 7n); let y = modpow(y2, (P + 1n) / 4n, P); if ((y & 1n) !== BigInt(v)) y = P - y;
  const R = [x, y]; const e = BigInt('0x' + hash.toString('hex')); const rinv = inv(r, N);
  const Q = add(mul(mod(sv * rinv, N), R), mul(mod(-e * rinv, N), G)); if (!Q) return null;
  return pubToAddress(Q);
}
function personalHash(message) { const m = Buffer.from(message, 'utf8'); return keccak256(Buffer.concat([Buffer.from('\x19Ethereum Signed Message:\n' + m.length, 'utf8'), m])); }
/** Адрес, подписавший `message` через personal_sign, или null. */
function recoverPersonal(message, signature) { try { return recover(personalHash(message), signature); } catch { return null; } }
// подпись (только для тестов; k детерминированный от hash+key, без RFC6979 — не для продакшена)
function signForTest(hash, priv) { const e = BigInt('0x' + hash.toString('hex')); const k = mod(BigInt('0x' + keccak256(Buffer.concat([hash, Buffer.from(priv.toString(16).padStart(64, '0'), 'hex')])).toString('hex')), N) || 1n; const R = mul(k, G); const r = mod(R[0], N); const s = mod(inv(k, N) * (e + r * priv), N); const v = Number(R[1] & 1n); return '0x' + r.toString(16).padStart(64, '0') + s.toString(16).padStart(64, '0') + (27 + v).toString(16); }
module.exports = { keccak256, recover, recoverPersonal, personalHash, pubToAddress, mul, G, signForTest };
