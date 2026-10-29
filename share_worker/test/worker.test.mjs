// Testovi Worker-a bez Cloudflare naloga: lažni KV u memoriji + Node-ov fetch API.
//   cd share_worker && npm test
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { beforeEach, describe, it } from "node:test";

import worker from "../src/index.js";

class MemoryKV {
  constructor() { this.data = new Map(); }
  async get(key) { return this.data.has(key) ? this.data.get(key) : null; }
  async put(key, value) { this.data.set(key, String(value)); }
  async delete(key) { this.data.delete(key); }
  async list({ prefix = "" } = {}) {
    const keys = [...this.data.keys()].filter((k) => k.startsWith(prefix)).sort()
      .map((name) => ({ name }));
    return { keys, list_complete: true };
  }
}

const ADMIN_KEY = "test-admin-key-1234567890";
const TOKEN = "AbCdEfGh1234";
const TASK = "0b3a1c52-8a0e-4d0f-9b9b-1234567890ab";
let env;

const call = (path, init = {}) => worker.fetch(new Request(`https://etapa.example.workers.dev${path}`, init), env);
const admin = (path, init = {}) => call(path, {
  ...init, headers: { authorization: `Bearer ${ADMIN_KEY}`, "content-type": "application/json", ...(init.headers || {}) },
});
const publish = (body) => admin(`/api/admin/snapshots/${TOKEN}`, { method: "PUT", body: JSON.stringify(body) });
const comment = (body, headers = {}) => call(`/api/comments/${TOKEN}`, {
  method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(body),
});
const sha = (s) => createHash("sha256").update(s).digest("hex");

beforeEach(() => { env = { SHARES: new MemoryKV(), ADMIN_KEY }; });

describe("administracija", () => {
  it("odbija bez ključa i sa pogrešnim ključem", async () => {
    assert.equal((await call("/api/admin/ping")).status, 401);
    const res = await call("/api/admin/ping", { headers: { authorization: "Bearer pogresan-kljuc-123456" } });
    assert.equal(res.status, 401);
  });

  it("odbija ako ADMIN_KEY nije podešen ili je kratak", async () => {
    env.ADMIN_KEY = "kratak";
    const res = await call("/api/admin/ping", { headers: { authorization: "Bearer kratak" } });
    assert.equal(res.status, 401);
  });

  it("ping vraća verziju", async () => {
    const res = await admin("/api/admin/ping");
    assert.equal(res.status, 200);
    assert.equal((await res.json()).ok, true);
  });

  it("objavljuje i servira snimak sa sigurnosnim zaglavljima", async () => {
    assert.equal((await publish({ html: "<h1>Projekat</h1>" })).status, 200);
    const res = await call(`/p/${TOKEN}`);
    assert.equal(res.status, 200);
    assert.equal(await res.text(), "<h1>Projekat</h1>");
    assert.match(res.headers.get("content-security-policy"), /frame-ancestors 'none'/);
    assert.equal(res.headers.get("x-robots-tag"), "noindex, nofollow");
  });

  it("odbija prazan ili prevelik snimak i neispravan token", async () => {
    assert.equal((await publish({ html: "" })).status, 400);
    assert.equal((await publish({ html: "x".repeat(2_000_001) })).status, 413);
    const bad = await admin("/api/admin/snapshots/kratak", { method: "PUT", body: "{}" });
    assert.equal(bad.status, 400);
  });

  it("opoziv briše snimak i komentare", async () => {
    await publish({ html: "<p>x</p>" });
    await comment({ text: "Super" });
    assert.equal((await admin(`/api/admin/snapshots/${TOKEN}`, { method: "DELETE" })).status, 200);
    assert.equal((await call(`/p/${TOKEN}`)).status, 404);
    assert.equal([...env.SHARES.data.keys()].filter((k) => k.startsWith("c:")).length, 0);
  });
});

describe("komentari", () => {
  beforeEach(async () => { await publish({ html: "<p>x</p>" }); });

  it("gost ostavlja komentar, aplikacija ga preuzima", async () => {
    const res = await comment({ author: "Marko", text: "  Može li veći logo?  ", task_id: TASK });
    assert.equal(res.status, 201);
    const list = await (await admin(`/api/admin/comments/${TOKEN}`)).json();
    assert.equal(list.comments.length, 1);
    assert.deepEqual(
      { author: list.comments[0].author, text: list.comments[0].text, task: list.comments[0].task_id },
      { author: "Marko", text: "Može li veći logo?", task: TASK },
    );
    assert.ok(list.comments[0].id);
    const pub = await (await call(`/api/comments/${TOKEN}`)).json();
    assert.equal(pub.comments.length, 1);
    assert.equal(pub.comments[0].id, undefined); // javno bez internih id-jeva
  });

  it("prazno ime postaje Gost; validacija teksta i zadatka", async () => {
    await comment({ text: "Ok" });
    const list = await (await admin(`/api/admin/comments/${TOKEN}`)).json();
    assert.equal(list.comments[0].author, "Gost");
    assert.equal((await comment({ text: "   " })).status, 400);
    assert.equal((await comment({ text: "x".repeat(2001) })).status, 400);
    assert.equal((await comment({ text: "x", task_id: "<script>" })).status, 400);
    assert.equal((await call(`/api/comments/${TOKEN}`, { method: "POST", body: "nije json" })).status, 400);
  });

  it("ograničava broj komentara po minutu", async () => {
    const headers = { "cf-connecting-ip": "1.2.3.4" };
    for (let i = 0; i < 8; i++) assert.equal((await comment({ text: `k${i}` }, headers)).status, 201);
    assert.equal((await comment({ text: "previše" }, headers)).status, 429);
    assert.equal((await comment({ text: "druga adresa" }, { "cf-connecting-ip": "5.6.7.8" })).status, 201);
  });

  it("komentar na nepostojeći link", async () => {
    const res = await call("/api/comments/Nepostoji1234", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: "x" }),
    });
    assert.equal(res.status, 404);
  });
});

describe("PIN", () => {
  const PIN = "4821";
  beforeEach(async () => { await publish({ html: "<p>tajno</p>", pin_hash: sha(`${TOKEN}:${PIN}`) }); });

  it("bez PIN-a prikazuje formu, ne snimak, i blokira komentare", async () => {
    const res = await call(`/p/${TOKEN}`);
    const body = await res.text();
    assert.equal(res.status, 200);
    assert.match(body, /PIN/);
    assert.doesNotMatch(body, /tajno/);
    assert.equal((await comment({ text: "x" })).status, 403);
    assert.equal((await call(`/api/comments/${TOKEN}`)).status, 403);
  });

  it("pogrešan PIN odbija, tačan daje kolačić i otvara snimak", async () => {
    const wrong = await call(`/p/${TOKEN}/unlock`, { method: "POST", body: new URLSearchParams({ pin: "0000" }) });
    assert.equal(wrong.status, 403);
    const ok = await call(`/p/${TOKEN}/unlock`, { method: "POST", body: new URLSearchParams({ pin: PIN }) });
    assert.equal(ok.status, 303);
    const cookie = ok.headers.get("set-cookie").split(";")[0];
    assert.match(ok.headers.get("set-cookie"), /HttpOnly/);
    const page = await call(`/p/${TOKEN}`, { headers: { cookie } });
    assert.equal(await page.text(), "<p>tajno</p>");
    assert.equal((await comment({ text: "sa PIN-om" }, { cookie })).status, 201);
  });
});

describe("ostalo", () => {
  it("nepoznate putanje i tokeni", async () => {
    assert.equal((await call("/p/../x")).status, 404);
    assert.equal((await call("/p/kratko")).status, 404);
    assert.equal((await call("/nesto")).status, 404);
    assert.equal((await call("/")).status, 200);
    assert.equal((await call(`/p/${TOKEN}`)).status, 404);
  });
});
