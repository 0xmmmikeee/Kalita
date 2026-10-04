'use strict';
// wallet-lab · веб-интерфейс и API. Без внешних зависимостей (Node 18+).
// Данные: data/signals.csv (паспорта), data/scores/scores_<profile>.csv (скоринг).
// Состояние: state/active.json, state/rejected.json, state/log.jsonl, state/rules.json.
const http = require('http'), fs = require('fs'), path = require('path'), { spawn } = require('child_process'), url = require('url');

const ROOT = path.resolve(__dirname, '..');
const DATA = process.env.WL_DATA || path.join(ROOT, 'data');
const STATE = process.env.WL_STATE || path.join(ROOT, 'state');
const PORT = parseInt(process.env.WL_PORT || '8830', 10);
const SRC = process.env.WL_SOURCE || path.join(ROOT, '..', 'scout-bot', 'data', 'launchpad-cache.json');
fs.mkdirSync(STATE, { recursive: true });

const PROFILES = ['fast', 'picker'];
const DEFAULT_RULES = {
  fast:   { min_n: 5, min_excess: 0.05, max_rug: 0.25, min_low: 0.25, size: 300, enter_days: 1, exit_excess: 0.0, exit_days: 3, recheck_days: 14 },
  picker: { min_n: 5, min_excess: 0.05, max_rug: 0.35, min_low: 0.20, size: 100, enter_days: 1, exit_excess: 0.0, exit_days: 5, recheck_days: 14 },
};

// ---------- CSV ----------
// V8 хранит подстроки как SlicedString со ссылкой на родителя: ключ из split() удерживает весь файл в памяти. flat() делает плоскую копию.
const flat = v => Buffer.from(v, 'latin1').toString('latin1');
function readCsv(file) {
  if (!fs.existsSync(file)) return [];
  const txt = fs.readFileSync(file, 'utf8'); const lines = txt.split('\n'); const head = lines[0].split(',');
  const out = [];
  for (let i = 1; i < lines.length; i++) {
    const L = lines[i]; if (!L) continue; const c = L.split(','); const o = {};
    for (let j = 0; j < head.length; j++) { const k = head[j] || 'wallet'; const v = c[j]; if (v === '' || v === undefined) { o[k] = null; continue; } if (/^0x/i.test(v) || k === 'wallet' || k === 'token' || k === 'flag' || k === 'cluster') { o[k] = flat(v.toLowerCase()); continue; } if (v === 'True') { o[k] = true; continue; } if (v === 'False') { o[k] = false; continue; } const n = Number(v); o[k] = Number.isNaN(n) ? v : n; }
    out.push(o);
  }
  return out;
}

function parseRow(line) { const c = line.split(','); const o = {}; for (let j = 0; j < signalsHeader.length; j++) { const k = signalsHeader[j]; const v = c[j]; if (v === '' || v === undefined) { o[k] = null; continue; } if (/^0x/i.test(v) || k === 'wallet' || k === 'token' || k === 'buyer' || k === 'recipient') { o[k] = v.toLowerCase(); continue; } if (v === 'True') { o[k] = true; continue; } if (v === 'False') { o[k] = false; continue; } const n = Number(v); o[k] = Number.isNaN(n) ? v : n; } return o; }
// ---------- data cache ----------
let scores = {}, signalsCount = 0, signalsHeader = [], signalsFile = '', loadedAt = 0, marketBase = {};
// индекс сигналов: sigW[i] = id кошелька, sigOff[i]/sigLen[i] = байтовое смещение и длина строки в signals.csv
let sigW = new Uint32Array(0), sigOff = new Float64Array(0), sigLen = new Uint32Array(0), sigN = 0, sigReady = false, sigGen = 0;
let walletIds = new Map();
function sigPush(id, off, len) {
  if (sigN === sigW.length) { const cap = Math.max(1 << 20, sigW.length * 2); const w = new Uint32Array(cap), o = new Float64Array(cap), l = new Uint32Array(cap); w.set(sigW); o.set(sigOff); l.set(sigLen); sigW = w; sigOff = o; sigLen = l; }
  sigW[sigN] = id; sigOff[sigN] = off; sigLen[sigN] = len; sigN++;
}
function fieldAt(line, col) { let s = 0; for (let k = 0; k < col; k++) { s = line.indexOf(',', s) + 1; if (s === 0) return ''; } const e = line.indexOf(',', s); return e < 0 ? line.slice(s) : line.slice(s, e); }
async function indexSignals() {
  // Побайтовый проход по signals.csv: строки не превращаются в JS-строки целиком (5 ГБ файла), только адрес кошелька
  // копируется как плоская строка. Прежняя версия (chunk.split + slice) удерживала через SlicedString целые 4 МБ куски → heap OOM.
  const gen = ++sigGen; sigReady = false; sigN = 0; walletIds = new Map(); signalsHeader = [];
  if (!fs.existsSync(signalsFile)) { signalsCount = 0; sigReady = true; return; }
  const fh = await fs.promises.open(signalsFile, 'r'); const buf = Buffer.alloc(8 << 20); let pos = 0, carry = Buffer.alloc(0), first = true, wcol = 0, n = 0;
  try {
    for (;;) {
      const { bytesRead } = await fh.read(buf, 0, buf.length, pos); if (bytesRead <= 0) break;
      if (gen !== sigGen) return;   // начался новый load()
      const data = carry.length ? Buffer.concat([carry, buf.subarray(0, bytesRead)]) : buf.subarray(0, bytesRead);
      const base = pos - carry.length; let s = 0;
      for (;;) {
        const e = data.indexOf(10, s); if (e < 0) break;
        const len = e - s;
        if (first) { signalsHeader = data.latin1Slice(s, e).split(','); wcol = signalsHeader.indexOf('wallet'); first = false; }
        else if (len > 0) {
          let a = s; for (let k = 0; k < wcol; k++) { a = data.indexOf(44, a) + 1; if (a === 0 || a > e) { a = e; break; } }
          let z = data.indexOf(44, a); if (z < 0 || z > e) z = e;
          const w = data.latin1Slice(a, z).toLowerCase();
          let id = walletIds.get(w); if (id === undefined) { id = walletIds.size; walletIds.set(w, id); }
          sigPush(id, base + s, len); n++;
        }
        s = e + 1;
      }
      carry = Buffer.from(data.subarray(s)); pos += bytesRead;
      await new Promise(r => setImmediate(r));   // дать event loop обслужить запросы
    }
  } finally { await fh.close(); }
  signalsCount = n; sigReady = true; console.log(`signals index ready: ${n} signals, ${walletIds.size} wallets, heap ${Math.round(process.memoryUsage().heapUsed / 1048576)} MB`);
}
function signalRows(w) {
  const id = walletIds.get(w); if (id === undefined) return [];
  const rows = []; const fd = fs.openSync(signalsFile, 'r');
  try { for (let i = 0; i < sigN; i++) if (sigW[i] === id) { const b = Buffer.alloc(sigLen[i]); fs.readSync(fd, b, 0, sigLen[i], sigOff[i]); rows.push(parseRow(b.toString('utf8'))); } } finally { fs.closeSync(fd); }
  return rows;
}
function load() {
  scores = {};
  for (const p of PROFILES) {
    const rows = readCsv(path.join(DATA, 'scores', `scores_${p}.csv`));
    scores[p] = new Map(rows.map(r => [String(r.wallet).toLowerCase(), r]));
  }
  // сигналы: компактный индекс (typed arrays, ~16 байт на сигнал) строится асинхронно — панель отвечает сразу,
  // карточки кошельков появляются, когда индекс готов. Прежняя версия (Map массивов) на 8M сигналов упиралась в heap V8.
  signalsFile = path.join(DATA, 'signals.csv'); indexSignals().catch(e => console.error('signals index:', e.message));
  try { marketBase = JSON.parse(fs.readFileSync(path.join(DATA, 'scores', 'report.json'), 'utf8')); } catch { marketBase = {}; }
  loadedAt = Date.now();
}
load();

// ---------- state ----------
const jread = (f, d) => { try { return JSON.parse(fs.readFileSync(path.join(STATE, f), 'utf8')); } catch { return d; } };
const jwrite = (f, o) => fs.writeFileSync(path.join(STATE, f), JSON.stringify(o, null, 1));
let active = jread('active.json', {});      // wallet -> {profile, added_at, reason, by}
let rejected = jread('rejected.json', {});  // wallet -> {reason, at, recheck_after, by}
let rules = Object.assign({}, DEFAULT_RULES, jread('rules.json', {}));
function logEvent(e) { e.at = new Date().toISOString(); fs.appendFileSync(path.join(STATE, 'log.jsonl'), JSON.stringify(e) + '\n'); }
function readLog(limit = 500) { try { return fs.readFileSync(path.join(STATE, 'log.jsonl'), 'utf8').trim().split('\n').filter(Boolean).slice(-limit).map(l => JSON.parse(l)).reverse(); } catch { return []; } }

function walletView(w) {
  w = w.toLowerCase();
  const out = { wallet: w, active: active[w] || null, rejected: rejected[w] || null, profiles: {} };
  for (const p of PROFILES) { const r = scores[p] && scores[p].get(w); if (r) out.profiles[p] = r; }
  const rows = sigReady ? signalRows(w) : [];
  out.signals = rows.sort((a, b) => a.ts - b.ts); out.signalsReady = sigReady;
  return out;
}
function eligible(p, r) {
  return r.flag !== 'contract' && !(r.cluster_dup === 'True' || r.cluster_dup === true);
}
const eligCache = {}; const candCache = new Map(); let stateVer = 0;   // stateVer растёт при изменении списков/отклонённых — статус в кандидатах меняется
function elig(p) { if (!eligCache[p] || eligCache[p].at !== loadedAt) eligCache[p] = { at: loadedAt, rows: [...scores[p].values()].filter(r => eligible(p, r)) }; return eligCache[p].rows; }
function candidates(p, { limit = 500, sort = 'score', desc = true, q = '' } = {}) {
  let rows = elig(p);
  if (q) rows = rows.filter(r => String(r.wallet).includes(q.toLowerCase()));
  rows.sort((a, b) => (desc ? -1 : 1) * ((a[sort] ?? -1e9) - (b[sort] ?? -1e9)));
  return rows.slice(0, limit).map(r => Object.assign({ status: active[r.wallet] ? 'active' : rejected[r.wallet] ? 'rejected' : '' }, r));
}
function applyRules(p, by = 'rules') {
  const R = rules[p]; const now = Date.now(); const today = new Date().toISOString().slice(0, 10);
  const enterDays = Math.max(1, R.enter_days || 1), exitDays = Math.max(1, R.exit_days || 1);
  const streak = jread('streak.json', {}); streak[p] = streak[p] || {};   // wallet -> {pass:[дни], fail:[дни]}
  const passes = r => r.n >= R.min_n && r.excess >= R.min_excess && (r.rug ?? 0) <= R.max_rug && r.low >= R.min_low && r.flag !== 'contract';
  const pick = candidates(p, { limit: 100000 }).filter(passes)
    .filter(r => !rejected[r.wallet] || new Date(rejected[r.wallet].recheck_after).getTime() < now)
    .slice(0, R.size);
  const added = [], kept = [], waiting = [];
  const bump = (w, key) => { const st = streak[p][w] = streak[p][w] || { pass: [], fail: [] }; const other = key === 'pass' ? 'fail' : 'pass'; st[other] = []; if (!st[key].includes(today)) st[key].push(today); return st[key].length; };
  for (const r of pick) {
    if (active[r.wallet]) { kept.push(r.wallet); bump(r.wallet, 'pass'); continue; }
    const d = bump(r.wallet, 'pass');
    if (d < enterDays) { waiting.push(r.wallet); continue; }   // гистерезис: ждём N подряд дней прохождения порогов
    active[r.wallet] = { profile: p, added_at: new Date().toISOString(), reason: `rules ${d}d: n=${r.n} excess=${(+r.excess).toFixed(3)} low=${(+r.low).toFixed(3)} rug=${(+(r.rug ?? 0)).toFixed(2)}`, by };
    if (rejected[r.wallet]) delete rejected[r.wallet];
    logEvent({ action: 'add', wallet: r.wallet, profile: p, reason: active[r.wallet].reason, by, metrics: { n: r.n, raw: r.raw, excess: r.excess, low: r.low, rug: r.rug } });
    added.push(r.wallet);
  }
  const pickSet = new Set(pick.map(r => r.wallet));
  for (const w of Object.keys(streak[p])) if (!pickSet.has(w) && !active[w]) delete streak[p][w];   // не прошёл сегодня — серия обнуляется
  const removed = [], failing = [];
  for (const [w, a] of Object.entries(active)) {
    if (a.profile !== p) continue; const r = scores[p].get(w);
    const bad = !r || r.excess < R.exit_excess || (r.rug ?? 0) > R.max_rug || r.flag === 'contract';
    if (!bad) { bump(w, 'pass'); continue; }
    const d = bump(w, 'fail');
    const hard = r && r.flag === 'contract';
    if (d < exitDays && !hard) { failing.push(w); continue; }   // гистерезис: удаляем после N подряд дней ниже порога
    const reason = !r ? 'нет сигналов в текущем окне' : hard ? 'контракт' : `${d}д подряд: excess=${(+r.excess).toFixed(3)} rug=${(+(r.rug ?? 0)).toFixed(2)}`;
    delete active[w]; delete streak[p][w];
    rejected[w] = { reason, at: new Date().toISOString(), recheck_after: new Date(Date.now() + R.recheck_days * 86400e3).toISOString(), by, profile: p };
    logEvent({ action: 'remove', wallet: w, profile: p, reason, by, metrics: r ? { n: r.n, raw: r.raw, excess: r.excess, low: r.low, rug: r.rug } : null });
    removed.push(w);
  }
  (stateVer++, jwrite('active.json', active)); (stateVer++, jwrite('rejected.json', rejected)); jwrite('streak.json', streak);
  return { added, removed, kept, waiting, failing, total: Object.values(active).filter(a => a.profile === p).length };
}

// ---------- recompute ----------
let job = null;
function recompute() {
  if (job) return job;
  job = { started: new Date().toISOString(), lines: [], done: false, ok: null };
  const py = process.env.PYTHON || 'python3';
  const run = (args) => new Promise(res => { const c = spawn(py, args, { cwd: ROOT }); const on = d => job.lines.push(...String(d).split('\n').filter(Boolean)); c.stdout.on('data', on); c.stderr.on('data', d => { const s = String(d); if (!/Warning|nanmean|apply/.test(s)) on(s); }); c.on('close', code => res(code)); });
  (async () => {
    const c1 = await run(['src/build_passports.py', SRC, path.join(DATA, 'signals.csv')]);
    const c2 = c1 === 0 ? await run(['src/score_wallets.py', path.join(DATA, 'signals.csv'), path.join(DATA, 'scores')]) : 1;
    job.ok = c1 === 0 && c2 === 0; job.done = true; job.finished = new Date().toISOString();
    if (job.ok) { load(); logEvent({ action: 'recompute', by: 'ui', signals: signalsCount }); }
    setTimeout(() => { job = null; }, 60000);
  })();
  return job;
}

// ---------- http ----------
const zlib = require('zlib');
// Ответ; JSON и текст крупнее 2 КБ сжимаем gzip, если клиент принимает (res._gz ставит обработчик запроса).
const send = (res, code, body, type = 'application/json', cache = 'no-store') => {
  let out = type.startsWith('application/json') ? JSON.stringify(body) : body; const h = { 'content-type': type + '; charset=utf-8', 'cache-control': cache };
  if (res._gz && typeof out === 'string' && out.length > 2048) { out = zlib.gzipSync(out); h['content-encoding'] = 'gzip'; }
  res.writeHead(code, h); res.end(out);
};
const body = req => new Promise(r => { let s = ''; req.on('data', d => s += d); req.on('end', () => { try { r(JSON.parse(s || '{}')); } catch { r({}); } }); });


// ---------------- вход по кошельку (EIP-191 personal_sign). WL_AUTH=1 включает обязательный вход; WL_ADMINS — адреса через запятую.
const crypto = require('crypto'); const E = require('./ethsig');
const AUTH_ON = process.env.WL_AUTH === '1';
const SECRET = (() => { const f = path.join(STATE, 'auth-secret'); try { return fs.readFileSync(f, 'utf8').trim(); } catch { const s = crypto.randomBytes(32).toString('hex'); fs.writeFileSync(f, s, { mode: 0o600 }); return s; } })();
const ADMINS = new Set((process.env.WL_ADMINS || '').toLowerCase().split(',').map(s => s.trim()).filter(Boolean));
const nonces = new Map();   // nonce -> expires
const users = () => jread('users.json', {});
const sessToken = addr => { const payload = `${addr}.${Date.now() + 30 * 86400e3}`; return payload + '.' + crypto.createHmac('sha256', SECRET).update(payload).digest('hex'); };
function sessionOf(req) {
  const m = /(?:^|;\s*)wl_sess=([^;]+)/.exec(req.headers.cookie || ''); if (!m) return null;
  const parts = decodeURIComponent(m[1]).split('.'); if (parts.length < 3) return null; const mac = parts.pop(), exp = parts.pop(), addr = parts.join('.'); if (!addr || !/^[0-9a-f]{64}$/.test(mac)) return null;
  const ok = crypto.timingSafeEqual(Buffer.from(mac, 'hex'), crypto.createHmac('sha256', SECRET).update(`${addr}.${exp}`).digest()); if (!ok || Date.now() > +exp) return null;
  const u = users()[addr]; if (!u || u.blocked) return null; if (u.demo && Date.parse(u.expires) < Date.now()) return null; return u.demo ? { address: addr, role: 'user', demo: true, expires: u.expires } : { address: addr, role: u.role };
}
const LOGIN_HTML = fs.readFileSync(path.join(__dirname, 'login.html'), 'utf8');
// ---------------- демо-аккаунты (WL_DEMO=1): изолированный пользователь на 24 ч, роль user; удаляется со списками и ключами
const DEMO_PER_HOUR = parseInt(process.env.WL_DEMO_PER_HOUR || '50', 10); const demoHour = []; const demoIp = new Map();
const clientIp = req => String(req.headers['x-forwarded-for'] || req.socket.remoteAddress || '').split(',')[0].trim();
function demoCleanup() {
  try { const U = users(); const now = Date.now(); const dead = Object.keys(U).filter(id => U[id].demo && Date.parse(U[id].expires) < now); if (!dead.length) return 0;
    for (const id of dead) delete U[id]; jwrite('users.json', U);
    const L = jread('userlists.json', {}); let lc = false; for (const id of dead) if (L[id]) { delete L[id]; lc = true; } if (lc) jwrite('userlists.json', L);
    const K = jread('apikeys.json', {}); let kc = false; for (const [h, v] of Object.entries(K)) if (dead.includes(v.user)) { delete K[h]; kc = true; } if (kc) jwrite('apikeys.json', K);
    return dead.length; } catch (e) { return 0; }
}
setInterval(demoCleanup, 3600e3).unref();
async function authRoutes(req, res, p) {
  if (p === '/auth/nonce') { const n = crypto.randomBytes(16).toString('hex'); nonces.set(n, Date.now() + 5 * 60e3); for (const [k, e] of nonces) if (e < Date.now()) nonces.delete(k);
    const msg = `kalita.tech wants you to sign in with your wallet.\n\nThis request will not trigger a blockchain transaction or cost any gas.\n\nNonce: ${n}\nIssued at: ${new Date().toISOString()}`; return send(res, 200, { nonce: n, message: msg }); }
  if (p === '/auth/verify' && req.method === 'POST') { const b = await body(req); const n = /Nonce: ([0-9a-f]{32})/.exec(b.message || '')?.[1];
    if (!n || !nonces.has(n) || nonces.get(n) < Date.now()) return send(res, 400, { error: 'nonce expired' }); nonces.delete(n);
    const rec = E.recoverPersonal(b.message, b.signature || ''); if (!rec || rec !== String(b.address || '').toLowerCase()) return send(res, 401, { error: 'bad signature' });
    const U = users(); const first = Object.keys(U).length === 0; const u = U[rec] || { createdAt: new Date().toISOString(), role: (first || ADMINS.has(rec)) ? 'admin' : 'user' };
    if (ADMINS.has(rec)) u.role = 'admin'; u.lastLogin = new Date().toISOString(); u.logins = (u.logins || 0) + 1; U[rec] = u; jwrite('users.json', U); logEvent({ action: 'login', wallet: rec, by: u.role });
    res.writeHead(200, { 'content-type': 'application/json', 'set-cookie': `wl_sess=${encodeURIComponent(sessToken(rec))}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${30 * 86400}${req.headers['x-forwarded-proto'] === 'https' ? '; Secure' : ''}` }); return res.end(JSON.stringify({ address: rec, role: u.role }));
  }
  if (p === '/auth/demo' && req.method === 'POST') {
    if (process.env.WL_DEMO !== '1') return send(res, 503, { error: 'demo is not enabled' });
    const ip = clientIp(req); const now = Date.now();
    demoHour.splice(0, demoHour.length, ...demoHour.filter(t => now - t < 3600e3)); if (demoHour.length >= DEMO_PER_HOUR) return send(res, 429, { error: 'demo is busy — try again later or sign in with a wallet' });
    const di = (demoIp.get(ip) || []).filter(t => now - t < 86400e3); if (di.length >= 3) return send(res, 429, { error: 'demo limit for today — sign in with a wallet or email to continue' });
    demoCleanup(); const id = 'demo:' + crypto.randomBytes(5).toString('hex'); const expires = new Date(now + 86400e3).toISOString();
    const U = users(); U[id] = { createdAt: new Date(now).toISOString(), role: 'user', demo: true, expires, logins: 1 }; jwrite('users.json', U); demoHour.push(now); di.push(now); demoIp.set(ip, di); logEvent({ action: 'login', wallet: id, by: 'demo' });
    const payload = `${id}.${now + 86400e3}`; const tok = payload + '.' + crypto.createHmac('sha256', SECRET).update(payload).digest('hex');
    res.writeHead(200, { 'content-type': 'application/json', 'set-cookie': `wl_sess=${encodeURIComponent(tok)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400${req.headers['x-forwarded-proto'] === 'https' ? '; Secure' : ''}` }); return res.end(JSON.stringify({ address: id, demo: true, expires }));
  }
  if (p === '/auth/logout') { res.writeHead(302, { 'set-cookie': 'wl_sess=; Path=/; Max-Age=0', location: '/' }); return res.end(); }
  if (p === '/auth/me') return send(res, 200, sessionOf(req) || { address: null });
  if (p === '/auth/users' && (sessionOf(req)?.role === 'admin')) return send(res, 200, users());
  return false;
}

// ---------------- вход по email (magic link через Resend). Включается, когда задан RESEND_API_KEY.
const MAIL_ON = !!process.env.RESEND_API_KEY; const MAIL_FROM = process.env.MAIL_FROM || 'Kalita <sign-in@kalita.tech>';
const mailTokens = new Map();  // token -> {email, exp}
const mailRate = new Map();    // email -> [ts,...]
const mailIp = new Map(); const MAIL_DAILY_MAX = parseInt(process.env.MAIL_DAILY_MAX || '80', 10); let mailDay = { d: '', n: 0 };
const mailDayLeft = () => { const d = new Date().toISOString().slice(0, 10); if (mailDay.d !== d) mailDay = { d, n: 0 }; return MAIL_DAILY_MAX - mailDay.n; };
const validEmail = e => /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e) && e.length <= 120;
async function sendMail(to, link) {
  const html = `<div style="font-family:Manrope,Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px;color:#17161A"><p style="font-size:22px;font-weight:800;margin:0 0 16px">kalita</p><p style="font-size:16px;line-height:1.5">Click the button to sign in. The link works once and expires in 15 minutes.</p><p style="margin:28px 0"><a href="${link}" style="background:#B5602B;color:#F4EFE6;text-decoration:none;padding:14px 22px;border-radius:12px;font-weight:600;display:inline-block">Sign in to Kalita</a></p><p style="font-size:13px;color:#6B6873">If you did not request this, ignore this email.<br>${link}</p></div>`;
  const r = await fetch('' + (process.env.RESEND_URL || 'https://api.resend.com/emails') + '', { method: 'POST', headers: { authorization: 'Bearer ' + process.env.RESEND_API_KEY, 'content-type': 'application/json' },
    body: JSON.stringify({ from: MAIL_FROM, to: [to], subject: 'Sign in to Kalita', html, text: `Sign in to Kalita: ${link} (valid 15 minutes, single use)` }) });
  if (!r.ok) throw new Error('mail ' + r.status + ' ' + (await r.text()).slice(0, 200));
}
async function mailRoutes(req, res, p) {
  if (p === '/auth/email/request' && req.method === 'POST') {
    if (!MAIL_ON) return send(res, 503, { error: 'email sign-in is not configured yet' });
    const b = await body(req); const email = String(b.email || '').trim().toLowerCase(); if (!validEmail(email)) return send(res, 400, { error: 'bad email' });
    const now = Date.now(); if (mailDayLeft() <= 0) return send(res, 503, { error: 'email sign-in is paused for today — use a wallet or try the demo' });
    const ipk = clientIp(req); const ih = (mailIp.get(ipk) || []).filter(t => now - t < 3600e3); if (ih.length >= 5) return send(res, 429, { error: 'too many requests from this network — try again later' }); ih.push(now); mailIp.set(ipk, ih); if (mailIp.size > 5000) mailIp.clear();
    const hist = (mailRate.get(email) || []).filter(t => now - t < 10 * 60e3); if (hist.length >= 3) return send(res, 429, { error: 'too many requests — try again in 10 minutes' });
    hist.push(now); mailRate.set(email, hist);
    const tok = crypto.randomBytes(24).toString('base64url'); mailTokens.set(tok, { email, exp: now + 15 * 60e3 }); for (const [k, v] of mailTokens) if (v.exp < now) mailTokens.delete(k);
    const host = req.headers['x-forwarded-host'] || req.headers.host; const proto = req.headers['x-forwarded-proto'] || 'http';
    try { await sendMail(email, `${proto}://${host}/auth/email/verify?t=${tok}`); mailDay.n++; } catch (e) { mailTokens.delete(tok); return send(res, 502, { error: 'could not send the email' }); }
    return send(res, 200, { ok: true });
  }
  if (p === '/auth/email/verify') {
    const t = String((url.parse(req.url, true).query || {}).t || ''); const rec = mailTokens.get(t); mailTokens.delete(t);
    if (!rec || rec.exp < Date.now()) return send(res, 400, LOGIN_HTML.replace('<div class="err" id="err"></div>', '<div class="err" id="err">This link has expired or was already used. Request a new one.</div>'), 'text/html');
    const id = 'email:' + rec.email; const U = users(); const first = Object.keys(U).length === 0; const u = U[id] || { createdAt: new Date().toISOString(), role: first ? 'admin' : 'user', email: rec.email };
    u.lastLogin = new Date().toISOString(); u.logins = (u.logins || 0) + 1; U[id] = u; jwrite('users.json', U); logEvent({ action: 'login', wallet: id, by: u.role });
    res.writeHead(302, { location: '/', 'set-cookie': `wl_sess=${encodeURIComponent(sessToken(id))}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${30 * 86400}${req.headers['x-forwarded-proto'] === 'https' ? '; Secure' : ''}` }); return res.end();
  }
  if (p === '/auth/config') return send(res, 200, { email: MAIL_ON && mailDayLeft() > 0, google: GOOGLE_ON, demo: process.env.WL_DEMO === '1' });
  return false;
}

// ---------------- вход через Google (OAuth 2.0 code + PKCE; id_token проверяется по JWKS Google). Включается при GOOGLE_CLIENT_ID/SECRET.
const G_ID = process.env.GOOGLE_CLIENT_ID || '', G_SECRET = process.env.GOOGLE_CLIENT_SECRET || ''; const GOOGLE_ON = !!(G_ID && G_SECRET);
const gStates = new Map(); let gJwks = { keys: [], at: 0 };
const b64u = b => Buffer.from(b).toString('base64url');
async function googleKeys() { if (Date.now() - gJwks.at < 6 * 3600e3 && gJwks.keys.length) return gJwks.keys; const r = await fetch('https://www.googleapis.com/oauth2/v3/certs'); const j = await r.json(); gJwks = { keys: j.keys || [], at: Date.now() }; return gJwks.keys; }
async function verifyIdToken(tok) {
  const [h, p, sig] = tok.split('.'); if (!h || !p || !sig) throw new Error('jwt');
  const hdr = JSON.parse(Buffer.from(h, 'base64url')); const key = (await googleKeys()).find(k => k.kid === hdr.kid && k.alg === 'RS256'); if (!key) throw new Error('unknown key');
  const ok = crypto.verify('sha256', Buffer.from(h + '.' + p), crypto.createPublicKey({ key, format: 'jwk' }), Buffer.from(sig, 'base64url')); if (!ok) throw new Error('bad signature');
  const c = JSON.parse(Buffer.from(p, 'base64url'));
  if (!['https://accounts.google.com', 'accounts.google.com'].includes(c.iss) || c.aud !== G_ID || c.exp * 1000 < Date.now() || !c.email || c.email_verified !== true) throw new Error('claims');
  return c;
}
async function googleRoutes(req, res, p) {
  if (p === '/auth/google') {
    if (!GOOGLE_ON) return send(res, 503, { error: 'Google sign-in is not configured yet' });
    const host = req.headers['x-forwarded-host'] || req.headers.host; const proto = req.headers['x-forwarded-proto'] || 'http';
    const state = crypto.randomBytes(16).toString('base64url'), verifier = crypto.randomBytes(32).toString('base64url'), nonce = crypto.randomBytes(12).toString('base64url');
    gStates.set(state, { verifier, nonce, exp: Date.now() + 10 * 60e3 }); for (const [k, v] of gStates) if (v.exp < Date.now()) gStates.delete(k);
    const q = new URLSearchParams({ client_id: G_ID, redirect_uri: `${proto}://${host}/auth/google/callback`, response_type: 'code', scope: 'openid email profile', state, nonce, code_challenge: b64u(crypto.createHash('sha256').update(verifier).digest()), code_challenge_method: 'S256', prompt: 'select_account' });
    res.writeHead(302, { location: 'https://accounts.google.com/o/oauth2/v2/auth?' + q }); return res.end();
  }
  if (p === '/auth/google/callback') {
    const q = url.parse(req.url, true).query || {}; const st = gStates.get(String(q.state || '')); gStates.delete(String(q.state || ''));
    const fail = m => send(res, 400, LOGIN_HTML.replace('<div class="err" id="err"></div>', `<div class="err" id="err">Google sign-in failed: ${m}. Try again.</div>`), 'text/html');
    if (!st || st.exp < Date.now() || !q.code) return fail('expired');
    try {
      const host = req.headers['x-forwarded-host'] || req.headers.host; const proto = req.headers['x-forwarded-proto'] || 'http';
      const tr = await fetch('https://oauth2.googleapis.com/token', { method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams({ code: String(q.code), client_id: G_ID, client_secret: G_SECRET, redirect_uri: `${proto}://${host}/auth/google/callback`, grant_type: 'authorization_code', code_verifier: st.verifier }) });
      const tj = await tr.json(); if (!tr.ok || !tj.id_token) throw new Error(tj.error || 'token');
      const c = await verifyIdToken(tj.id_token); if (c.nonce !== st.nonce) throw new Error('nonce');
      const email = c.email.toLowerCase(); const id = 'email:' + email; const U = users(); const first = Object.keys(U).length === 0;
      const u = U[id] || { createdAt: new Date().toISOString(), role: first ? 'admin' : 'user', email }; u.name = c.name || u.name; u.google = c.sub; u.lastLogin = new Date().toISOString(); u.logins = (u.logins || 0) + 1; U[id] = u; jwrite('users.json', U); logEvent({ action: 'login', wallet: id, by: u.role, via: 'google' });
      res.writeHead(302, { location: '/', 'set-cookie': `wl_sess=${encodeURIComponent(sessToken(id))}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${30 * 86400}${proto === 'https' ? '; Secure' : ''}` }); return res.end();
    } catch (e) { return fail(e.message); }
  }
  return false;
}

// ---------------- личные списки пользователя: state/userlists.json  {userId: {listId: {name, notes, wallets:{addr:{added_at,note}}, created, updated, log:[]}}}
const ulists = () => jread('userlists.json', {});
const ulSave = o => jwrite('userlists.json', o);
const isAddr = a => /^0x[0-9a-f]{40}$/.test(String(a || '').toLowerCase());
async function myRoutes(req, res, p, sess) {
  if (!p.startsWith('/api/my/') && !p.startsWith('/export/my/')) return false;
  if (!sess) return send(res, 401, { error: 'sign in required' });
  const all = ulists(); const mine = all[sess.address] || (all[sess.address] = {});
  const now = new Date().toISOString();
  if (p === '/api/my/lists' && req.method === 'GET') return send(res, 200, Object.entries(mine).map(([id, l]) => ({ id, name: l.name, notes: l.notes || '', size: Object.keys(l.wallets).length, created: l.created, updated: l.updated })));
  if (p === '/api/my/lists' && req.method === 'POST') { const b = await body(req); if (Object.keys(mine).length >= (sess.demo ? 5 : 50)) return send(res, 400, { error: sess.demo ? 'demo: up to 5 lists' : 'too many lists' }); const id = crypto.randomBytes(6).toString('hex'); mine[id] = { name: String(b.name || 'My list').slice(0, 60), notes: String(b.notes || '').slice(0, 2000), wallets: {}, created: now, updated: now, log: [{ at: now, a: 'create' }] }; ulSave(all); return send(res, 200, { id }); }
  const m = /^\/api\/my\/lists\/([0-9a-f]{12})(\/(wallets|export|log))?$/.exec(p) || /^\/export\/my\/([0-9a-f]{12})\.txt$/.exec(p);
  if (!m) return send(res, 404, { error: 'no' });
  const id = m[1]; const l = mine[id]; if (!l) return send(res, 404, { error: 'no such list' });
  if (p.startsWith('/export/my/')) return send(res, 200, Object.keys(l.wallets).sort().join('\n') + '\n', 'text/plain');
  const sub = m[3];
  if (!sub && req.method === 'GET') { const rows = Object.entries(l.wallets).map(([w, v]) => Object.assign({ wallet: w, added_at: v.added_at, note: v.note || '' }, (scores.fast.get(w) || {}), (scores.picker.get(w) ? { picker_excess: scores.picker.get(w).excess } : {}), { status: active[w] ? 'active' : rejected[w] ? 'rejected' : '' })); return send(res, 200, { id, name: l.name, notes: l.notes || '', wallets: rows, log: (l.log || []).slice(-100).reverse() }); }
  if (!sub && req.method === 'PATCH') { const b = await body(req); if (b.name != null) l.name = String(b.name).slice(0, 60); if (b.notes != null) l.notes = String(b.notes).slice(0, 2000); l.updated = now; ulSave(all); return send(res, 200, { ok: true }); }
  if (!sub && req.method === 'DELETE') { delete mine[id]; ulSave(all); return send(res, 200, { ok: true }); }
  if (sub === 'wallets' && req.method === 'POST') { const b = await body(req); const ws = [...new Set((b.wallets || []).map(w => String(w).toLowerCase()).filter(isAddr))]; if (Object.keys(l.wallets).length + ws.length > 2000) return send(res, 400, { error: 'list limit 2000' }); let n = 0; for (const w of ws) if (!l.wallets[w]) { l.wallets[w] = { added_at: now, note: String(b.note || '').slice(0, 200) }; n++; } l.updated = now; (l.log = l.log || []).push({ at: now, a: 'add', n, src: String(b.source || '').slice(0, 80) }); ulSave(all); return send(res, 200, { added: n, size: Object.keys(l.wallets).length }); }
  if (sub === 'wallets' && req.method === 'DELETE') { const b = await body(req); let n = 0; for (const w of (b.wallets || []).map(w => String(w).toLowerCase())) if (l.wallets[w]) { delete l.wallets[w]; n++; } l.updated = now; (l.log = l.log || []).push({ at: now, a: 'remove', n }); ulSave(all); return send(res, 200, { removed: n, size: Object.keys(l.wallets).length }); }
  return send(res, 405, { error: 'method' });
}

// ---------------- API-ключи и публичный API v1. Ключ: заголовок X-API-Key или ?key=. state/apikeys.json {keyHash: {user, name, created, lastUsed, calls}}
const akeys = () => jread('apikeys.json', {}); const akSave = o => jwrite('apikeys.json', o);
const khash = k => crypto.createHash('sha256').update(k).digest('hex');
const rl = new Map();  // rate limit: id -> [windowStart, count]
function limited(id, max = 60) { const now = Date.now(); const w = rl.get(id); if (!w || now - w[0] > 60e3) { rl.set(id, [now, 1]); return false; } if (++w[1] > max) return true; return false; }
function keyUser(req, q) { const k = req.headers['x-api-key'] || q.key; if (!k) return null; const K = akeys(); const rec = K[khash(String(k))]; if (!rec || rec.revoked) return null; if (String(rec.user).startsWith('demo:')) { const du = users()[rec.user]; if (!du || Date.parse(du.expires) < Date.now()) return null; } rec.lastUsed = new Date().toISOString(); rec.calls = (rec.calls || 0) + 1; if (rec.calls % 20 === 1) akSave(K); return rec; }
async function keyRoutes(req, res, p, sess) {
  if (p === '/api/my/keys') {
    if (!sess) return send(res, 401, { error: 'sign in required' }); const K = akeys();
    if (req.method === 'GET') return send(res, 200, Object.entries(K).filter(([, v]) => v.user === sess.address && !v.revoked).map(([h, v]) => ({ id: h.slice(0, 8), name: v.name, created: v.created, lastUsed: v.lastUsed, calls: v.calls || 0, prefix: v.prefix })));
    if (req.method === 'POST') { const b = await body(req); if (Object.values(K).filter(v => v.user === sess.address && !v.revoked).length >= (sess.demo ? 2 : 5)) return send(res, 400, { error: sess.demo ? 'demo: up to 2 keys' : 'max 5 keys' }); const key = 'kl_' + crypto.randomBytes(24).toString('base64url'); K[khash(key)] = { user: sess.address, name: String(b.name || 'key').slice(0, 40), created: new Date().toISOString(), prefix: key.slice(0, 7) }; akSave(K); return send(res, 200, { key }); }
    if (req.method === 'DELETE') { const b = await body(req); for (const [h, v] of Object.entries(K)) if (v.user === sess.address && h.startsWith(String(b.id || '').slice(0, 8)) && b.id) v.revoked = true; akSave(K); return send(res, 200, { ok: true }); }
  }
  if (!p.startsWith('/v1/')) return false;
  const q = url.parse(req.url, true).query || {}; const ku = keyUser(req, q); const who = ku ? 'k:' + ku.prefix : sess ? 'u:' + sess.address : null;
  if (!who) return send(res, 401, { error: 'API key required (X-API-Key). Create one in the panel → My lists → API keys.' });
  if (limited(who)) return send(res, 429, { error: 'rate limit: 60 requests per minute' });
  const m1 = /^\/v1\/list\/(fast|picker|all)$/.exec(p); if (m1) { const pr = m1[1]; const rows = Object.entries(active).filter(([, a]) => pr === 'all' || a.profile === pr).map(([w, a]) => ({ wallet: w, profile: a.profile, added_at: a.added_at, reason: a.reason })); return send(res, 200, { profile: pr, asOf: loadedAt, count: rows.length, wallets: rows }); }
  const m2 = /^\/v1\/wallet\/(0x[0-9a-fA-F]{40})$/.exec(p); if (m2) { const w = m2[1].toLowerCase(); const out = { wallet: w, profiles: {}, active: active[w] || null, rejected: rejected[w] || null }; for (const pr of PROFILES) if (scores[pr] && scores[pr].get(w)) out.profiles[pr] = scores[pr].get(w); return send(res, 200, out); }
  const m3 = /^\/v1\/candidates\/(fast|picker)$/.exec(p); if (m3) { const pr = m3[1]; const lim = Math.min(500, parseInt(q.limit || '100', 10) || 100); const rows = [...scores[pr].values()].filter(r => eligible(pr, r)).sort((a, b) => (b.score || 0) - (a.score || 0)).slice(0, lim); return send(res, 200, { profile: pr, asOf: loadedAt, count: rows.length, candidates: rows }); }
  if (p === '/v1/snapshots') { const dir = path.join(ROOT, 'data', 'registry'); let files = []; try { files = fs.readdirSync(dir).filter(f => /^(fast|picker)-\d{8}\.json$/.test(f)).sort(); } catch {} const out = files.map(f => { try { const j = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')); return { file: f, profile: j.profile, asOf: j.asOf, size: j.size, added: j.added, removed: j.removed, root: j.root }; } catch { return null; } }).filter(Boolean); return send(res, 200, { count: out.length, snapshots: out }); }
  if (p === '/v1/summary') { const per = {}; for (const pr of PROFILES) per[pr] = { candidates: elig(pr).length, active: Object.values(active).filter(a => a.profile === pr).length }; return send(res, 200, { asOf: loadedAt, signals: signalsCount, wallets: walletIds.size, profiles: per, market: marketBase }); }
  return send(res, 404, { error: 'unknown endpoint', endpoints: ['/v1/summary', '/v1/list/{fast|picker|all}', '/v1/candidates/{fast|picker}?limit=100', '/v1/wallet/{address}', '/v1/snapshots'] });
}

const guestHits = new Map();
http.createServer(async (req, res) => {
  res._gz = /\bgzip\b/.test(req.headers['accept-encoding'] || '');
  const u = url.parse(req.url, true); const p = u.pathname; const q = u.query;
  try {
    if (p.startsWith('/auth/')) { let r = await googleRoutes(req, res, p); if (r === false) r = await mailRoutes(req, res, p); if (r === false) r = await authRoutes(req, res, p); if (r !== false) return; return send(res, 404, { error: 'no' }); }
    if (p === '/login') return send(res, 200, LOGIN_HTML, 'text/html');
    if (p === '/favicon.svg') return send(res, 200, fs.readFileSync(path.join(__dirname, 'favicon.svg'), 'utf8'), 'image/svg+xml', 'public, max-age=86400');
    if (p === '/i18n.js') return send(res, 200, fs.readFileSync(path.join(__dirname, 'i18n.js'), 'utf8'), 'application/javascript', 'public, max-age=600');
    // локальные служебные вызовы (deploy/daily.sh): с 127.0.0.1 и заголовком X-WL-Local = state/auth-secret — как админ
    const sess = (req.socket.remoteAddress === '127.0.0.1' || req.socket.remoteAddress === '::ffff:127.0.0.1') && req.headers['x-wl-local'] === SECRET ? { address: 'local', role: 'admin' } : sessionOf(req);
    { const r = await keyRoutes(req, res, p, sess); if (r !== false) return; }
    { const r = await myRoutes(req, res, p, sess); if (r !== false) return; }
    if (AUTH_ON && !sess && process.env.WL_DEMO_PUBLIC === '1' && (p === '/api/summary' || (p === '/api/candidates' && (q.limit === '10' || q.demo === '1')))) { if (p === '/api/candidates') { const pr = PROFILES.includes(q.profile) ? q.profile : 'fast'; const rows = [...scores[pr].values()].filter(r => eligible(pr, r)).sort((a, b) => (b.score || 0) - (a.score || 0)).slice(0, 10).map(r => Object.assign({}, r, { wallet: r.wallet.slice(0, 6) + '…' + r.wallet.slice(-4) })); return send(res, 200, rows); } }
    // гостевой просмотр (WL_GUEST_READ=1): только чтение — кандидаты (≤500), текущий список, карточка кошелька. Лимит 60 запросов/мин на IP.
    const GUEST_READ = process.env.WL_GUEST_READ === '1';
    const guestPath = req.method === 'GET' && (p === '/' || p === '/api/summary' || p === '/api/candidates' || p === '/api/active' || p.startsWith('/api/wallet/'));
    if (AUTH_ON && !sess && GUEST_READ && guestPath) {
      const ip = clientIp(req); const now = Date.now();
      const g = guestHits.get(ip) || { t: now, n: 0 }; if (now - g.t > 60e3) { g.t = now; g.n = 0; } g.n++; guestHits.set(ip, g); if (guestHits.size > 5000) guestHits.clear();
      if (g.n > 60) return send(res, 429, { error: 'too many requests' });
      if (p.startsWith('/api/wallet/')) { const wk = 'gw:' + ip; if (limited(wk, 10)) return send(res, 429, { error: 'too many requests' }); }
      if (p === '/api/candidates') q.limit = String(Math.min(5000, Math.max(1, +(q.limit || 500) || 500)));
    }
    if (sess && sess.demo && limited('d:' + sess.address, 120)) return send(res, 429, { error: 'too many requests' });
    const demoOK = (process.env.WL_DEMO_PUBLIC === '1' && (p === '/' || p === '/api/summary')) || (GUEST_READ && guestPath);
    if (AUTH_ON && !sess && !demoOK) { if (p === '/' ) return send(res, 200, LOGIN_HTML, 'text/html'); return send(res, 401, { error: 'sign in required' }); }
    if (AUTH_ON && req.method === 'POST' && sess.role !== 'admin') return send(res, 403, { error: 'admin only' });
    if (p.startsWith('/export/') && AUTH_ON && !sess) return send(res, 401, { error: 'sign in required' });
    if (p === '/' ) return send(res, 200, fs.readFileSync(path.join(__dirname, 'ui.html'), 'utf8'), 'text/html');
    if (p === '/favicon.svg') return send(res, 200, fs.readFileSync(path.join(__dirname, 'favicon.svg'), 'utf8'), 'image/svg+xml', 'public, max-age=86400');
    if (p === '/api/summary') {
      const per = {}; for (const pr of PROFILES) per[pr] = { candidates: elig(pr).length, active: Object.values(active).filter(a => a.profile === pr).length };
      return send(res, 200, { loadedAt, signals: signalsCount, wallets: walletIds.size, signalsReady: sigReady, profiles: per, rejected: Object.keys(rejected).length, report: marketBase, rules, job });
    }
    if (p === '/api/candidates') {
      const key = [q.profile || 'fast', q.limit || 500, q.sort || 'score', q.desc !== '0', q.q || ''].join('|'); const ver = loadedAt + ':' + stateVer;
      let c = candCache.get(key); if (!c || c.ver !== ver) { const json = JSON.stringify(candidates(q.profile || 'fast', { limit: +(q.limit || 500), sort: q.sort || 'score', desc: q.desc !== '0', q: q.q || '' })); c = { ver, json, gz: json.length > 2048 ? zlib.gzipSync(json) : null }; if (candCache.size > 96) candCache.clear(); candCache.set(key, c); }
      const h = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' }; if (res._gz && c.gz) { h['content-encoding'] = 'gzip'; res.writeHead(200, h); return res.end(c.gz); } res.writeHead(200, h); return res.end(c.json);
    }
    if (p.startsWith('/api/wallet/')) return send(res, 200, walletView(p.split('/').pop()));
    if (p === '/api/active') return send(res, 200, Object.entries(active).map(([w, a]) => Object.assign({ wallet: w }, a, { metrics: scores[a.profile] && scores[a.profile].get(w) || null })));
    if (p === '/api/rejected') return send(res, 200, Object.entries(rejected).map(([w, a]) => Object.assign({ wallet: w }, a)));
    if (p === '/api/log') { const L = readLog(+(q.limit || 500)); return send(res, 200, (sess && sess.role === 'admin') ? L : (Array.isArray(L) ? L.filter(e => e && e.action !== 'login') : L)); }
    if (p === '/api/lists') { try { return send(res, 200, JSON.parse(fs.readFileSync(path.join(DATA, 'scores', 'lists.json'), 'utf8'))); } catch { return send(res, 200, {}); } }
    if (p === '/api/rules' && req.method === 'POST') { const b = await body(req); for (const pr of PROFILES) if (b[pr]) rules[pr] = Object.assign({}, rules[pr], b[pr]); jwrite('rules.json', rules); logEvent({ action: 'rules', by: 'ui', rules }); return send(res, 200, rules); }
    if (p === '/api/apply' && req.method === 'POST') { const b = await body(req); return send(res, 200, applyRules(b.profile || 'fast', b.by || 'ui')); }
    if (p === '/api/add' && req.method === 'POST') { const b = await body(req); const out = []; for (let w of (b.wallets || [])) { w = w.toLowerCase(); active[w] = { profile: b.profile || 'fast', added_at: new Date().toISOString(), reason: b.reason || 'вручную', by: 'ui' }; delete rejected[w]; logEvent({ action: 'add', wallet: w, profile: b.profile || 'fast', reason: b.reason || 'вручную', by: 'ui' }); out.push(w); } (stateVer++, jwrite('active.json', active)); (stateVer++, jwrite('rejected.json', rejected)); return send(res, 200, out); }
    if (p === '/api/reject' && req.method === 'POST') { const b = await body(req); const out = []; for (let w of (b.wallets || [])) { w = w.toLowerCase(); const pr = (active[w] && active[w].profile) || b.profile || 'fast'; delete active[w]; rejected[w] = { reason: b.reason || 'вручную', at: new Date().toISOString(), recheck_after: new Date(Date.now() + (b.days || 14) * 86400e3).toISOString(), by: 'ui', profile: pr }; logEvent({ action: 'remove', wallet: w, profile: pr, reason: b.reason || 'вручную', by: 'ui' }); out.push(w); } (stateVer++, jwrite('active.json', active)); (stateVer++, jwrite('rejected.json', rejected)); return send(res, 200, out); }
    if (p === '/api/restore' && req.method === 'POST') { const b = await body(req); for (let w of (b.wallets || [])) { w = w.toLowerCase(); delete rejected[w]; logEvent({ action: 'restore', wallet: w, by: 'ui' }); } (stateVer++, jwrite('rejected.json', rejected)); return send(res, 200, { ok: true }); }
    if (p === '/api/recompute' && req.method === 'POST') return send(res, 200, recompute());
    if (p === '/api/reload' && req.method === 'POST') { load(); return send(res, 200, { ok: true, signals: signalsCount }); }
    if (p.startsWith('/export/')) { const pr = p.split('/').pop().replace('.txt', ''); const list = Object.entries(active).filter(([, a]) => pr === 'all' || a.profile === pr).map(([w]) => w).sort(); return send(res, 200, list.join('\n') + '\n', 'text/plain'); }
    send(res, 404, { error: 'not found' });
  } catch (e) { send(res, 500, { error: String(e && e.stack || e) }); }
}).listen(PORT, process.env.WL_HOST || '127.0.0.1', () => console.log(`wallet-lab http://${process.env.WL_HOST || '127.0.0.1'}:${PORT}  (signals index building in background)`));
