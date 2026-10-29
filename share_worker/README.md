# Etapa — Worker za deljenje linkom

Mali Cloudflare Worker (besplatan plan) koji:

- prikazuje snimak projekta na linku `https://<tvoj-worker>.workers.dev/p/<token>`,
- prima komentare gledalaca (bez naloga) i čuva ih dok ih aplikacija ne preuzme,
- po želji traži PIN pre otvaranja,
- prima izmene **samo** od tvoje aplikacije (tajni ključ `ADMIN_KEY`).

Postavlja se **jednom** i radi za sve projekte. Besplatni plan je dovoljan
(100.000 zahteva i 1.000 upisa dnevno).

## Postavljanje (≈10 minuta)

Potrebno: besplatan nalog na [cloudflare.com](https://dash.cloudflare.com/sign-up) i
[Node.js LTS](https://nodejs.org/).

U PowerShell-u, iz foldera projekta:

```powershell
cd share_worker
npm install
npx wrangler login
```

`wrangler login` otvara browser — prijavi se na Cloudflare i odobri pristup.

**1. Napravi skladište za snimke i komentare**

```powershell
npx wrangler kv namespace create SHARES
```

Komanda ispiše nešto kao `id = "3f8a…"`. Otvori `wrangler.toml` i zameni `ZAMENI_ME` tim id-jem.

**2. Postavi tajni ključ**

Napravi dugačak nasumičan ključ (sačuvaj ga, trebaće ti u aplikaciji):

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
npx wrangler secret put ADMIN_KEY
```

Druga komanda traži da nalepiš ključ.

**3. Objavi Worker**

```powershell
npx wrangler deploy
```

Na kraju ispiše adresu, npr. `https://etapa-share.tvojnalog.workers.dev`.

**4. Poveži aplikaciju**

U Etapi: **Podešavanja → Deljenje** → upiši adresu i tajni ključ → **Proveri vezu** →
**Sačuvaj**. Ključ se čuva u Windows Credential Manager-u, ne u fajlu.

Sada u svakom projektu dugme **Podeli** pravi link.

## Kako radi

| Putanja | Ko | Šta |
| --- | --- | --- |
| `GET /p/:token` | gledalac | stranica sa snimkom (ili PIN forma) |
| `POST /p/:token/unlock` | gledalac | provera PIN-a, kolačić važi 30 dana |
| `GET/POST /api/comments/:token` | gledalac | čitanje i slanje komentara |
| `PUT/DELETE /api/admin/snapshots/:token` | aplikacija | objava / opoziv |
| `GET /api/admin/comments/:token` | aplikacija | preuzimanje komentara |

Zaštita: tokeni linkova su nasumični (16 znakova), stranica ima strogu Content-Security-Policy
i `noindex`, PIN se čuva samo kao SHA-256 heš, komentari su ograničeni (8 u minuti po adresi,
najviše 300 po linku, do 2.000 znakova), a admin ključ se poredi u konstantnom vremenu.

## Razvoj i testovi

```powershell
npm test              # testovi bez Cloudflare naloga (lažno skladište u memoriji)
npx wrangler dev      # lokalno pokretanje na http://127.0.0.1:8787
```

Za `wrangler dev` napravi fajl `.dev.vars` sa redom `ADMIN_KEY=neki-lokalni-kljuc-od-16+-znakova`
(fajl je u `.gitignore`).

Opoziv linka u aplikaciji briše snimak i komentare sa Worker-a; komentari koji su već preuzeti
ostaju u aplikaciji.
