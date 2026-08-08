// Live xtrpatch demo. Loads Pyodide on demand, mounts the vendored xtrshow
// package into its in-memory filesystem, and calls the real apply_changes().

import { SCENARIOS } from "./scenarios.js";

const PYODIDE_VERSION = "0.26.4";
// ?pyodide=/some/local/dist/ points the runtime at a local copy, for offline
// development and for CI smoke tests that must not reach a CDN.
const PYODIDE_URL =
  new URLSearchParams(location.search).get("pyodide") ||
  `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const VENDOR_FILES = ["__init__.py", "cli.py", "repatch.py"];

const $ = (id) => document.getElementById(id);
const el = {
  src: $("src"),
  patch: $("patch"),
  out: $("out"),
  status: $("status"),
  run: $("run"),
  runLabel: $("run-label"),
  revert: $("revert"),
  reset: $("reset"),
  srcName: $("src-name"),
  scnDesc: $("scn-desc"),
  fstree: $("fstree"),
};

let pyodide = null;
let driver = null;
let booting = null;
let current = "basic";
// Scenarios whose working directory has been seeded this session. Seeding wipes
// .xtrpatch/, so it must happen once per scenario — not on every apply, or
// revert would never have a backup to restore from.
const seeded = new Set();

/* ── terminal output ─────────────────────────────────────── */

const ESC = (s) =>
  String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

// Colourise xtrpatch's own report markers. Purely presentational — the text
// itself is whatever the engine printed.
function paint(text) {
  return ESC(text)
    .split("\n")
    .map((line) => {
      if (/✅|✨/.test(line)) return `<span class="ok">${line}</span>`;
      if (/❌|🗑️/.test(line)) return `<span class="bad">${line}</span>`;
      if (/⚠️|🛑|⚡|!/.test(line)) return `<span class="warn">${line}</span>`;
      if (/🧠|⏭️/.test(line)) return `<span class="info">${line}</span>`;
      if (/^\s*\(/.test(line)) return `<span class="muted">${line}</span>`;
      if (/^📄/.test(line)) return `<span class="hdr">${line}</span>`;
      return line;
    })
    .join("\n");
}

const write = (text) => { el.out.innerHTML = paint(text); };
const setStatus = (msg, cls = "") => {
  el.status.textContent = msg;
  el.status.className = "status " + cls;
};

/* ── boot ────────────────────────────────────────────────── */

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error(`Could not load ${src}`));
    document.head.appendChild(s);
  });
}

async function boot() {
  setStatus("Downloading Python runtime (~5 MB, cached after this)…");
  el.out.innerHTML = "";
  write("Loading Pyodide…");

  await loadScript(PYODIDE_URL + "pyodide.js");
  pyodide = await globalThis.loadPyodide({ indexURL: PYODIDE_URL });

  write("Mounting the xtrshow package…");

  // Mount the vendored package exactly as published — no patching, no shims.
  pyodide.FS.mkdirTree("/vendor/xtrshow");
  const sources = await Promise.all(
    VENDOR_FILES.map((f) =>
      fetch(`vendor/xtrshow/${f}`).then((r) => {
        if (!r.ok) throw new Error(`vendor/xtrshow/${f}: HTTP ${r.status}`);
        return r.text();
      })
    )
  );
  VENDOR_FILES.forEach((f, i) =>
    pyodide.FS.writeFile(`/vendor/xtrshow/${f}`, sources[i])
  );

  const driverSrc = await fetch("assets/driver.py").then((r) => r.text());
  pyodide.FS.writeFile("/vendor/_driver.py", driverSrc);

  pyodide.runPython(`
import sys
sys.path.insert(0, "/vendor")
`);
  driver = pyodide.pyimport("_driver");

  const v = driver.version();
  write(`Ready. xtrshow ${v} running on Python ${pyodide.runPython("import sys; sys.version.split()[0]")} (WebAssembly).\n`);
  setStatus("");
}

function ensureBooted() {
  if (!booting) {
    booting = boot().catch((err) => {
      booting = null;
      throw err;
    });
  }
  return booting;
}

/* ── scenarios ───────────────────────────────────────────── */

function loadScenario(key, { keepEdits = false } = {}) {
  const s = SCENARIOS[key];
  current = key;
  el.srcName.textContent = s.file;
  el.scnDesc.textContent = s.desc;
  if (!keepEdits) {
    el.src.value = s.seed[s.file];
    el.patch.value = s.patch;
  }
  el.revert.disabled = true;
  el.fstree.textContent = "(nothing yet)";

  document.querySelectorAll(".scn").forEach((b) =>
    b.classList.toggle("is-active", b.dataset.scn === key)
  );
}

// Rebuild the scenario's working directory from its seed files. Scenarios like
// "delete" ship auxiliary files (legacy.py) that the patch acts on but which
// never appear in the editor, so this must run before the first apply.
async function seedWorkdir() {
  const s = SCENARIOS[current];
  const seed = { ...s.seed, [s.file]: el.src.value };
  driver.reset(current, JSON.stringify(seed));
  seeded.add(current);
}

async function ensureSeeded() {
  if (!seeded.has(current)) await seedWorkdir();
}

/* ── actions ─────────────────────────────────────────────── */

async function run() {
  el.run.disabled = true;
  try {
    await ensureBooted();
    await ensureSeeded();
    setStatus("Applying…");

    const s = SCENARIOS[current];
    const res = JSON.parse(
      driver.apply_patch(current, s.file, el.src.value, el.patch.value)
    );

    let out = res.report;

    // Reflect the on-disk result back into the editor, plus any file the
    // patch created — this is the actual post-patch state, read back from
    // Pyodide's filesystem.
    const files = res.files;
    if (Object.prototype.hasOwnProperty.call(files, s.file)) {
      el.src.value = files[s.file];
    }

    const others = Object.keys(files)
      .filter((f) => f !== s.file && f !== "changes.txt")
      .sort();
    if (others.length) {
      out += "\n\n── other files in the working tree ──";
      for (const f of others) {
        out += `\n\n--- ${f} ---\n${files[f].replace(/\n$/, "")}`;
      }
    }
    if (!Object.prototype.hasOwnProperty.call(files, s.file)) {
      out += `\n\n(${s.file} no longer exists — it was deleted by the patch)`;
    }

    write(out);
    el.fstree.textContent = res.tree;
    el.revert.disabled = false;
    setStatus("Done — try editing either pane and running again.", "ok");
  } catch (err) {
    write(`Failed to run the demo.\n\n${err && err.message ? err.message : err}`);
    setStatus("Error", "err");
  } finally {
    el.run.disabled = false;
  }
}

async function revert() {
  el.revert.disabled = true;
  try {
    await ensureBooted();
    const s = SCENARIOS[current];
    const res = JSON.parse(driver.revert(current, s.file));
    if (Object.prototype.hasOwnProperty.call(res.files, s.file)) {
      el.src.value = res.files[s.file];
    }
    write(res.report);
    el.fstree.textContent = res.tree;
    setStatus("Reverted from .xtrpatch/ backup.", "ok");
  } catch (err) {
    write(String(err));
    setStatus("Error", "err");
  } finally {
    el.revert.disabled = false;
  }
}

async function reset() {
  loadScenario(current);
  seeded.delete(current);
  if (driver) await seedWorkdir();
  write("Scenario reset.");
  setStatus("");
}

/* ── wiring ──────────────────────────────────────────────── */

document.querySelectorAll(".scn").forEach((btn) =>
  btn.addEventListener("click", async () => {
    loadScenario(btn.dataset.scn);
    seeded.delete(btn.dataset.scn);
    if (driver) await seedWorkdir();
    write("Scenario loaded. Click Apply patch to run it.");
    setStatus("");
  })
);

el.run.addEventListener("click", run);
el.revert.addEventListener("click", revert);
el.reset.addEventListener("click", reset);

// Tab inserts spaces instead of leaving the textarea — indentation matters here.
[el.src, el.patch].forEach((ta) =>
  ta.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    e.preventDefault();
    const { selectionStart: a, selectionEnd: b, value } = ta;
    ta.value = value.slice(0, a) + "    " + value.slice(b);
    ta.selectionStart = ta.selectionEnd = a + 4;
  })
);

document.querySelectorAll(".copy").forEach((btn) =>
  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(btn.dataset.copy);
      const prev = btn.textContent;
      btn.textContent = "Copied";
      btn.classList.add("done");
      setTimeout(() => {
        btn.textContent = prev;
        btn.classList.remove("done");
      }, 1400);
    } catch {
      /* clipboard blocked — the command is selectable anyway */
    }
  })
);

loadScenario("basic");
