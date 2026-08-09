// Minimal tokenizer for the demo editors. Not a real parser — just enough to
// make Python and the xtrshow patch format readable at a glance.
//
// Everything is emitted through esc(), and tokens are matched in a single pass
// with one alternation, so highlighted markup is never re-scanned for tokens.

export const esc = (s) =>
  String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

const KEYWORDS =
  "def|class|return|import|from|if|elif|else|for|while|in|not|and|or|is|None|" +
  "True|False|pass|raise|with|as|try|except|finally|yield|lambda|assert|del|" +
  "break|continue|global|nonlocal|async|await|self";

const PY_RE = new RegExp(
  [
    /(#[^\n]*)/,                                    // 1 comment
    /("""[\s\S]*?"""|'''[\s\S]*?''')/,              // 2 triple-quoted string
    /("(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')/,    // 3 string
    new RegExp(`\\b(${KEYWORDS})\\b`),              // 4 keyword
    /\b(\d+(?:\.\d+)?)\b/,                          // 5 number
    /\b([A-Za-z_]\w*)(?=\s*\()/,                    // 6 call / def name
  ]
    .map((r) => r.source)
    .join("|"),
  "g"
);

const CLASS_FOR = ["t-com", "t-str", "t-str", "t-kw", "t-num", "t-fn"];

export function python(code) {
  let out = "";
  let last = 0;
  PY_RE.lastIndex = 0;
  code.replace(PY_RE, (...args) => {
    const m = args[0];
    const groups = args.slice(1, 1 + CLASS_FOR.length);
    const idx = args[1 + CLASS_FOR.length];
    out += esc(code.slice(last, idx));
    const gi = groups.findIndex((g) => g !== undefined);
    out += gi === -1 ? esc(m) : `<span class="${CLASS_FOR[gi]}">${esc(m)}</span>`;
    last = idx + m.length;
    return m;
  });
  return out + esc(code.slice(last));
}

// The patch format is line-oriented, so classify per line and fall back to
// Python highlighting for the search/replace payload.
export function patch(text) {
  return text
    .split("\n")
    .map((line) => {
      const s = line.trim();
      if (/^(---|\+\+\+)\s/.test(line)) return `<span class="t-hdr">${esc(line)}</span>`;
      if (s.startsWith("@")) return `<span class="t-ann">${esc(line)}</span>`;
      if (/^!\s*DELETE/i.test(s)) return `<span class="t-danger">${esc(line)}</span>`;
      if (s.startsWith("~~~~")) return `<span class="t-wild">${esc(line)}</span>`;
      if (/^(<<<<|<<|====|>>>>)/.test(s)) return `<span class="t-mark">${esc(line)}</span>`;
      return python(line);
    })
    .join("\n");
}

export function markdown(text) {
  return text
    .split("\n")
    .map((line) => {
      if (/^(---|\+\+\+)\s/.test(line)) return `<span class="t-hdr">${esc(line)}</span>`;
      if (/^```/.test(line)) return `<span class="t-mark">${esc(line)}</span>`;
      // "  12:code" — the line-number prefix xtrshow emits
      const m = line.match(/^(\s*\d+:)(.*)$/);
      if (m) return `<span class="t-ln">${esc(m[1])}</span>${python(m[2])}`;
      return python(line);
    })
    .join("\n");
}

export const HIGHLIGHTERS = { python, patch, markdown };
