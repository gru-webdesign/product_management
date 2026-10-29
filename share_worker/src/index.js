/**
 * Etapa — Cloudflare Worker za deljenje projekta linkom.
 *
 * Javno (gledalac, bez naloga):
 *   GET  /p/:token                 stranica sa snimkom projekta (PIN forma ako je postavljen)
 *   POST /p/:token/unlock          provera PIN-a → kolačić
 *   GET  /api/comments/:token      komentari za prikaz na stranici
 *   POST /api/comments/:token      novi komentar {author, text, task_id}
 *
 * Aplikacija (zaglavlje Authorization: Bearer <ADMIN_KEY>):
 *   GET    /api/admin/ping
 *   PUT    /api/admin/snapshots/:token   {html, pin_hash}
 *   DELETE /api/admin/snapshots/:token   (briše i komentare)
 *   GET    /api/admin/comments/:token
 *
 * Skladište: KV prostor SHARES.
 *   snap:<token>                  {html, pin_hash, updated_at}
 *   c:<token>:<vreme>-<nasumično> {id, author, text, task_id, posted_at}
 *   rl:<ip>:<minut>               brojač za ograničenje slanja komentara
 */

const VERSION = "1.0.0";
const TOKEN_RE = /^[A-Za-z0-9_-]{10,64}$/;
const MAX_COMMENTS = 300;
const MAX_TEXT = 2000;
const MAX_AUTHOR = 80;
const RATE_PER_MINUTE = 8;
const MAX_SNAPSHOT = 2_000_000;

export default {
  async fetch(request, env) {
    try {
      return await route(request, env);
    } catch (err) {
      return json({ error: "Greška na serveru." }, 500);
    }
  },
};

async function route(request, env) {
  const url = new URL(request.url);
  const parts = url.pathname.split("/").filter(Boolean);
  const method = request.method.toUpperCase();

  if (parts[0] === "p" && parts[1]) {
    const token = parts[1];
    if (!TOKEN_RE.test(token)) return notFound();
    if (parts.length === 2 && method === "GET") return viewPage(request, env, token);
    if (parts[2] === "unlock" && method === "POST") return unlock(request, env, token);
    return notFound();
  }

  if (parts[0] === "api" && parts[1] === "comments" && parts[2]) {
    const token = parts[2];
    if (!TOKEN_RE.test(token)) return json({ error: "Nepostojeći link." }, 404);
    if (method === "GET") return publicComments(request, env, token);
    if (method === "POST") return postComment(request, env, token);
    return json({ error: "Metoda nije dozvoljena." }, 405);
  }

  if (parts[0] === "api" && parts[1] === "admin") {
    if (!(await isAdmin(request, env))) return json({ error: "Neovlašćen pristup." }, 401);
    if (parts[2] === "ping" && method === "GET") return json({ ok: true, version: VERSION });
    const token = parts[3];
    if (token && !TOKEN_RE.test(token)) return json({ error: "Neispravan token." }, 400);
    if (parts[2] === "snapshots" && token) {
      if (method === "PUT") return putSnapshot(request, env, token);
      if (method === "DELETE") return deleteSnapshot(env, token);
    }
    if (parts[2] === "comments" && token && method === "GET") {
      return json({ comments: await listComments(env, token) });
    }
    return json({ error: "Nepoznata putanja." }, 404);
  }

  if (parts.length === 0) {
    return html(simplePage("Etapa", "Ovde se otvaraju linkovi za pregled projekata."), 200);
  }
  return notFound();
}

// --- pomoćne -------------------------------------------------------------------------------------

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store",
               ...extra },
  });
}

const CSP = [
  "default-src 'none'",
  "script-src 'unsafe-inline'",
  "style-src 'unsafe-inline'",
  "img-src data:",
  "connect-src 'self'",
  "form-action 'self'",
  "base-uri 'none'",
  "frame-ancestors 'none'",
].join("; ");

function html(body, status = 200, extra = {}) {
  return new Response(body, {
    status,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "content-security-policy": CSP,
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
      "x-robots-tag": "noindex, nofollow",
      ...extra,
    },
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function simplePage(title, text, extra = "") {
  return `<!doctype html><html lang="sr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>${escapeHtml(title)}</title>
<style>body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#f5f5f7;color:#1c2024;
display:grid;place-items:center;min-height:100vh;margin:0;padding:16px}
.box{background:#fff;border:1px solid #e4e4e9;border-radius:12px;padding:28px;max-width:380px;width:100%}
h1{font-size:18px;margin:0 0 8px}p{color:#60646c;margin:0 0 16px;line-height:1.5}
input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #cdced6;border-radius:8px;font-size:16px}
button{margin-top:12px;width:100%;padding:10px;border:0;border-radius:8px;background:#5b5bd6;color:#fff;
font-weight:600;font-size:15px;cursor:pointer}.err{color:#dc3e42;margin-top:10px}
@media (prefers-color-scheme:dark){body{background:#111113;color:#edeef0}.box{background:#18191b;border-color:#2b2d31}
p{color:#b0b4ba}input{background:#111113;color:#edeef0;border-color:#3c3f44}}</style></head>
<body><div class="box"><h1>${escapeHtml(title)}</h1><p>${escapeHtml(text)}</p>${extra}</div></body></html>`;
}

function notFound() {
  return html(simplePage("Link nije dostupan",
    "Ovaj link ne postoji ili ga je vlasnik projekta opozvao."), 404);
}

async function sha256Hex(text) {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function timingSafeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function isAdmin(request, env) {
  const header = request.headers.get("authorization") || "";
  const key = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!env.ADMIN_KEY || env.ADMIN_KEY.length < 16 || !key) return false;
  // poređenje heševa iste dužine, bez otkrivanja vremena
  return timingSafeEqual(await sha256Hex(key), await sha256Hex(env.ADMIN_KEY));
}

async function getSnapshot(env, token) {
  const raw = await env.SHARES.get(`snap:${token}`);
  return raw ? JSON.parse(raw) : null;
}

function cookieValue(request, name) {
  const cookie = request.headers.get("cookie") || "";
  for (const part of cookie.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return v.join("=");
  }
  return "";
}

function unlocked(request, snap, token) {
  if (!snap.pin_hash) return true;
  return timingSafeEqual(cookieValue(request, `etapa_${token}`), snap.pin_hash);
}

// --- stranica i PIN ------------------------------------------------------------------------------

async function viewPage(request, env, token) {
  const snap = await getSnapshot(env, token);
  if (!snap) return notFound();
  if (!unlocked(request, snap, token)) return pinPage(token, false);
  return html(snap.html);
}

function pinPage(token, wrong) {
  const form = `<form method="post" action="/p/${token}/unlock">
<input name="pin" type="password" inputmode="numeric" autocomplete="off" placeholder="PIN" autofocus required maxlength="32">
<button type="submit">Otvori</button>${wrong ? '<div class="err">PIN nije tačan.</div>' : ""}</form>`;
  return html(simplePage("Zaštićen pregled projekta", "Unesi PIN koji si dobio uz link.", form),
    wrong ? 403 : 200);
}

async function unlock(request, env, token) {
  const snap = await getSnapshot(env, token);
  if (!snap) return notFound();
  const form = await request.formData().catch(() => null);
  const pin = form ? String(form.get("pin") || "") : "";
  const hash = await sha256Hex(`${token}:${pin}`);
  if (!snap.pin_hash || !timingSafeEqual(hash, snap.pin_hash)) return pinPage(token, true);
  return new Response(null, {
    status: 303,
    headers: {
      location: `/p/${token}`,
      "set-cookie": `etapa_${token}=${hash}; Path=/; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax`,
    },
  });
}

// --- komentari -----------------------------------------------------------------------------------

async function listComments(env, token) {
  const prefix = `c:${token}:`;
  const keys = [];
  let cursor;
  do {
    const page = await env.SHARES.list({ prefix, cursor });
    keys.push(...page.keys.map((k) => k.name));
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  keys.sort();
  const values = await Promise.all(keys.map((k) => env.SHARES.get(k)));
  return values.filter(Boolean).map((v) => JSON.parse(v));
}

async function publicComments(request, env, token) {
  const snap = await getSnapshot(env, token);
  if (!snap) return json({ error: "Link nije dostupan." }, 404);
  if (!unlocked(request, snap, token)) return json({ error: "Potreban je PIN." }, 403);
  const comments = (await listComments(env, token)).map(({ author, text, task_id, posted_at }) =>
    ({ author, text, task_id, posted_at }));
  return json({ comments });
}

async function postComment(request, env, token) {
  const snap = await getSnapshot(env, token);
  if (!snap) return json({ error: "Link nije dostupan." }, 404);
  if (!unlocked(request, snap, token)) return json({ error: "Potreban je PIN." }, 403);

  const ip = request.headers.get("cf-connecting-ip") || "nepoznat";
  const minute = Math.floor(Date.now() / 60000);
  const rlKey = `rl:${ip}:${minute}`;
  const count = parseInt((await env.SHARES.get(rlKey)) || "0", 10);
  if (count >= RATE_PER_MINUTE) {
    return json({ error: "Previše komentara za kratko vreme, pokušaj ponovo za minut." }, 429);
  }

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Neispravan zahtev." }, 400);
  }
  const author = String(body.author || "").trim().slice(0, MAX_AUTHOR);
  const text = String(body.text || "").trim();
  const taskId = body.task_id ? String(body.task_id).slice(0, 64) : null;
  if (!text) return json({ error: "Komentar je prazan." }, 400);
  if (text.length > MAX_TEXT) return json({ error: `Komentar je duži od ${MAX_TEXT} znakova.` }, 400);
  if (taskId && !/^[0-9a-f-]{36}$/.test(taskId)) return json({ error: "Nepoznat zadatak." }, 400);

  const existing = await env.SHARES.list({ prefix: `c:${token}:` });
  if (existing.keys.length >= MAX_COMMENTS) {
    return json({ error: "Dostignut je najveći broj komentara za ovaj link." }, 409);
  }

  const now = new Date().toISOString();
  const rand = [...crypto.getRandomValues(new Uint8Array(6))]
    .map((b) => b.toString(16).padStart(2, "0")).join("");
  const id = `${now}-${rand}`;
  const comment = { id, author: author || "Gost", text, task_id: taskId, posted_at: now };
  await env.SHARES.put(`c:${token}:${id}`, JSON.stringify(comment));
  await env.SHARES.put(rlKey, String(count + 1), { expirationTtl: 120 });
  return json({ ok: true, id }, 201);
}

// --- administracija ------------------------------------------------------------------------------

async function putSnapshot(request, env, token) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Neispravan JSON." }, 400);
  }
  if (typeof body.html !== "string" || !body.html.trim()) {
    return json({ error: "Nedostaje HTML snimka." }, 400);
  }
  if (body.html.length > MAX_SNAPSHOT) return json({ error: "Snimak je prevelik." }, 413);
  const pinHash = typeof body.pin_hash === "string" && /^[0-9a-f]{64}$/.test(body.pin_hash)
    ? body.pin_hash : "";
  const snap = { html: body.html, pin_hash: pinHash, updated_at: new Date().toISOString() };
  await env.SHARES.put(`snap:${token}`, JSON.stringify(snap));
  return json({ ok: true, updated_at: snap.updated_at });
}

async function deleteSnapshot(env, token) {
  await env.SHARES.delete(`snap:${token}`);
  const comments = await env.SHARES.list({ prefix: `c:${token}:` });
  await Promise.all(comments.keys.map((k) => env.SHARES.delete(k.name)));
  return json({ ok: true });
}
