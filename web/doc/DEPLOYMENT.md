# Deploying the xtrshow site

Integration notes for publishing this site to the same server that serves
`diluvium.aloecraft.org`, presumably as `xtrshow.aloecraft.org`.

Everything under **Server requirements** was verified against this site in a
real browser, not inferred — including the two settings that fail silently.
Where this document assumes something about the existing sync script or the
server, it says so explicitly.

---

## 1. What ships

**There is no build step.** Unlike `diluvium-www`, which runs
`npm run build` (webpack) and deploys the generated `dist/`, this site is
hand-written static files. The repository root *is* the deployable tree.

That is the single most important integration fact: the sync script's source
directory is the checkout itself, not a build output.

| | `diluvium-www` | this site |
|---|---|---|
| Build | `npm run build` → `dist/` | none |
| Sync source | `dist/` | repository root |
| Node/npm on the build host | required | not required |
| Payload | webpack bundle + `libdiluvium.wasm` | 12 files, 122 KB |

### Files the browser actually requests

Captured from a full session — load, install, apply a patch:

```
/index.html
/assets/style.css
/assets/icon.svg
/assets/demo.js
/assets/scenarios.js
/assets/highlight.js
/assets/driver.py
/vendor/VERSION
/vendor/xtrshow/__init__.py
/vendor/xtrshow/cli.py
/vendor/xtrshow/repatch.py
```

Ship `LICENSE` too. Everything else in the repo is development scaffolding and
should be excluded:

```
README.md          doc/            scripts/
.github/           .git/           .gitignore
.pyodide-local/    .pyodide-min/   node_modules/
```

`cli.py` is genuinely needed at runtime even though the demo never opens the
TUI — `repatch.py` is imported from the same package.

---

## 2. Server requirements

### 2.1 `.wasm` must be `application/wasm` — verified, fails silently

This is the one that will cost an afternoon. Serving `pyodide.asm.wasm` as
`application/octet-stream` does **not** produce an error. The page hangs on
"Installing…" forever — tested past 200 seconds with no exception thrown and
no console error. All five runtime files return `200`; only the media type
differs.

Controlled comparison, same server, same files, only `Content-Type` changed:

| `.wasm` served as | Result |
|---|---|
| `application/wasm` | boots, Python 3.12.1 |
| `application/octet-stream` | hangs indefinitely, no error |

nginx has shipped `application/wasm` in `mime.types` since 1.21.5. Confirm
rather than assume:

```bash
curl -sI https://xtrshow.aloecraft.org/vendor/pyodide/pyodide.asm.wasm \
  | grep -i content-type
# expect: content-type: application/wasm
```

If it is wrong, add to the server block:

```nginx
types { application/wasm wasm; }
```

**Likely already fine:** `diluvium-www` serves `libdiluvium.wasm` from this
same server, so if that site works, the MIME mapping is correct already. Worth
one `curl` to confirm.

### 2.2 Content-Security-Policy needs `'wasm-unsafe-eval'` — verified

If the server sends a CSP (many hardened nginx configs do, sometimes from a
shared snippet you did not write), Pyodide will not start without
`'wasm-unsafe-eval'` in `script-src`.

| Policy | Result |
|---|---|
| no CSP | works |
| `script-src 'self'` | **fails** — runtime never boots |
| `script-src 'self' 'wasm-unsafe-eval'` | works |

This exact policy was verified end to end — boot, vendor fetches, patch
applied — against a self-hosted runtime with no CDN:

```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'" always;
```

Note there is **no `'unsafe-inline'`** anywhere in it. The page has no inline
`<script>` and no inline styles — all CSS is in `assets/style.css` and all
behaviour is in module scripts — so the policy can stay tight. If a shared
nginx snippet adds `'unsafe-inline'`, this site does not need it.

If you keep the CDN default instead of self-hosting, add the CDN to both
`script-src` and `connect-src`:

```
script-src  'self' 'wasm-unsafe-eval' https://cdn.jsdelivr.net;
connect-src 'self' https://cdn.jsdelivr.net;
```

**Not required:** Pyodide here does not use threads or `SharedArrayBuffer`, so
you do **not** need `Cross-Origin-Opener-Policy` / `Cross-Origin-Embedder-Policy`.
Adding them is harmless but buys nothing and can break other things.

### 2.3 `.py` files need no special handling — verified

Served as `application/octet-stream` (the nginx default when no `.py` mapping
exists) the demo works fine; the files are read with `fetch().text()`, which
does not care. No `types` entry needed.

The one real risk is a server configured to **execute** `.py` through CGI or
FastCGI. This site has no Python backend and nothing under `/vendor/` should
ever be handed to an interpreter. If the server has any global CGI handler,
exclude this vhost from it.

### 2.4 Compression

`pyodide.asm.wasm` is the whole payload. Precompress it if the sync script can
place files:

| File | Raw | gzip |
|---|---|---|
| `pyodide.asm.wasm` | 9.62 MB | 3.02 MB |
| `python_stdlib.zip` | 2.23 MB | 2.20 MB |
| `pyodide.asm.js` | 1.17 MB | 0.22 MB |
| **Total (5 files)** | **13.14 MB** | **~5.5 MB** |

`python_stdlib.zip` is already a zip — compressing it saves 1% for real CPU
cost. Exclude it. With `gzip_static`, generate `.gz` siblings for the `.wasm`
and `.js` only.

```nginx
gzip on;
gzip_types text/css text/javascript application/javascript application/wasm application/json image/svg+xml;
gzip_min_length 1024;
# gzip_static on;   # if you precompress during sync
```

### 2.5 Caching — read this before setting long max-age

**None of this site's assets are content-hashed.** `demo.js` is always
`demo.js`. A long `max-age` on `/assets/` means a redeploy does not reach
anyone who has already visited until their cache expires.

Safe defaults:

```nginx
# HTML and un-fingerprinted assets: revalidate every time (cheap, 304s)
location / {
    add_header Cache-Control "no-cache";
}

# The runtime is immutable *for a given version path* — see §3
location /vendor/pyodide/ {
    add_header Cache-Control "public, max-age=31536000, immutable";
}
```

`no-cache` does not mean "do not store" — it means revalidate, so repeat visits
are 304s. For a 122 KB site that is the right trade.

If you later want real long-lived caching on `/assets/`, add a hash to the
filenames; do not simply raise `max-age`.

---

## 3. CDN or self-hosted runtime

The Python runtime is **not** in this repository. By default the page loads it
from jsDelivr. On your own server you probably want it local: no third-party
dependency, works behind a firewall, and one less origin in the CSP.

**To self-host**, put these five files — and only these five — in a directory
on the site, then point the page at it. There is no need to copy the full
Pyodide distribution, which is far larger.

```
pyodide.js
pyodide.asm.js
pyodide.asm.wasm
python_stdlib.zip
pyodide-lock.json
```

Fetch them from the **`pyodide-core`** release asset — 5.4 MB, and it contains
exactly these files. Do not use `pyodide-<version>.tar.bz2`: that is the full
distribution, 297 MB, almost all of it scientific packages this site never
loads.

```bash
PYODIDE_VERSION=0.26.4
mkdir -p vendor/pyodide && cd vendor/pyodide
curl -LO "https://github.com/pyodide/pyodide/releases/download/${PYODIDE_VERSION}/pyodide-core-${PYODIDE_VERSION}.tar.bz2"
tar xjf "pyodide-core-${PYODIDE_VERSION}.tar.bz2" --strip-components=1 \
    pyodide/pyodide.js pyodide/pyodide.asm.js pyodide/pyodide.asm.wasm \
    pyodide/python_stdlib.zip pyodide/pyodide-lock.json
rm "pyodide-core-${PYODIDE_VERSION}.tar.bz2"
```

That command was run as written and the resulting directory was verified to
boot the demo.

Then uncomment the meta tag in `index.html`:

```html
<meta name="pyodide-url" content="/vendor/pyodide/">
```

Verified: with that tag set and no query parameter, a full session — boot,
apply a patch — contacts **no host other than the site's own origin**.

Resolution order is query parameter → meta tag → CDN, so `?pyodide=…` still
overrides for local development without touching the deployed config.

Version the directory (`/vendor/pyodide/0.26.4/`) if you want the aggressive
`immutable` cache header from §2.5 to be safe across runtime upgrades.
`PYODIDE_VERSION` in `assets/demo.js` must match whatever you vendored.

---

## 4. Wiring into the existing sync script

I have not seen the diluvium-www sync script — it is not in that repository
(single commit, no deploy tooling) and there is no infra repo in the org. So
this section states what the script has to do rather than patching it. Send me
the script and I will adapt it directly.

Three things differ from the diluvium-www case:

1. **Skip the build.** No `npm ci`, no `npm run build`, no `dist/`. If the
   script is shared, this needs to be conditional — a `build` hook that is a
   no-op here, or a per-site config value.

2. **Source is the checkout root**, with exclusions. An rsync-style invocation:

   ```bash
   rsync -az --delete \
     --exclude='.git*' --exclude='README.md' --exclude='doc/' \
     --exclude='scripts/' --exclude='node_modules/' --exclude='.pyodide-*' \
     ./ "${TARGET}:${DOCROOT}/"
   ```

   `--delete` is what makes a removed file actually disappear from the server;
   without it the docroot accumulates stale files forever.

3. **The runtime is large and rarely changes.** If you self-host, the 13 MB in
   `vendor/pyodide/` is static between Pyodide upgrades. Sync it separately, or
   let rsync's delta check skip it — but do not re-upload it on every deploy.

Whatever the script does for diluvium-www's DNS, TLS, and vhost creation should
carry over unchanged; this is an ordinary static site from the server's point of
view.

---

## 5. Post-deploy smoke test

The site can look perfectly fine and still have a dead demo, because both
failure modes in §2 are silent. Check the demo itself, not just the page.

```bash
SITE=https://xtrshow.aloecraft.org

# 1. Page loads
curl -sfI "$SITE" >/dev/null && echo "page OK"

# 2. Runtime files reachable, correct MIME  (self-hosted only)
curl -sI "$SITE/vendor/pyodide/pyodide.asm.wasm" | grep -i '^content-type'
#    must be: application/wasm

# 3. The vendored package is served, not executed or 404'd
curl -sf "$SITE/vendor/xtrshow/repatch.py" | head -3
#    must be Python source, not a rendered page or an error

# 4. If a CSP is set, it must permit wasm
curl -sI "$SITE" | grep -i content-security-policy
#    if present, must contain 'wasm-unsafe-eval'
```

Then open the page, press **Go**, and apply a patch. Success is a green
`✅ SUCCESS` line in the terminal. If the button says "Installing…" and never
finishes, go straight to §2.1.

---

## 6. Troubleshooting

| Symptom | Cause |
|---|---|
| Stuck on "Installing…" forever, no console error | `.wasm` served with the wrong MIME type (§2.1) |
| Console: *Refused to … 'unsafe-eval' is not an allowed source* | CSP missing `'wasm-unsafe-eval'` (§2.2) |
| Console: *Refused to execute inline script* | a CSP snippet is being applied that this site does not need; see §2.2 |
| Terminal: `vendor/xtrshow/repatch.py: HTTP 404` | `vendor/` excluded from the sync (§1) |
| `ModuleNotFoundError: No module named 'curses'` | vendored `repatch.py` predates the fix that removed the `cli.py` import; re-run `scripts/sync-xtrshow.sh` |
| Demo works locally, fails deployed | almost always §2.1 or §2.2 — local dev servers set `application/wasm` and send no CSP |
| Old JS after a deploy | `max-age` on un-fingerprinted `/assets/` (§2.5) |

---

## 7. Updating after an xtrshow release

The demo runs the vendored copy of the package, so a new release on PyPI does
not change the site until you re-vendor:

```bash
XTRSHOW_SRC=../xtrshow ./scripts/sync-xtrshow.sh   # or omit to clone main
git commit -am "Vendor xtrshow $(cat vendor/VERSION)"
```

`vendor/VERSION` drives the version string in the simulated install line, so it
stays truthful automatically.

The sync script refuses to vendor a tree whose `repatch.py` imports from
`cli.py` — that import pulls in `curses`, which does not exist in
WebAssembly, and would break the demo at load time. The GitHub Pages workflow
re-checks the same invariant. If you deploy through your own server instead,
replicate that check, or the failure only shows up in a browser.
