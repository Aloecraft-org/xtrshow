#!/usr/bin/env bash
# Vendor the xtrshow package source into this site.
#
# The live demo runs the real package, so vendor/ must be refreshed whenever
# xtrshow cuts a release. Point XTRSHOW_SRC at a checkout of
# github.com/Aloecraft-org/xtrshow, or let this script clone one.
#
#   ./scripts/sync-xtrshow.sh                  # clone main, vendor it
#   XTRSHOW_SRC=../xtrshow ./scripts/sync-xtrshow.sh
#
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dest="$here/vendor/xtrshow"
files=(__init__.py cli.py repatch.py)

if [[ -n "${XTRSHOW_SRC:-}" ]]; then
  src="$XTRSHOW_SRC"
  cleanup=""
else
  src="$(mktemp -d)/xtrshow"
  git clone --depth 1 https://github.com/Aloecraft-org/xtrshow.git "$src"
  cleanup="$src"
fi

if [[ ! -d "$src/xtrshow" ]]; then
  echo "error: $src does not look like an xtrshow checkout" >&2
  exit 1
fi

mkdir -p "$dest"
for f in "${files[@]}"; do
  cp "$src/xtrshow/$f" "$dest/$f"
  echo "vendored $f"
done

version="$(grep -m1 '^version' "$src/pyproject.toml" | cut -d'"' -f2)"
printf '%s\n' "$version" > "$here/vendor/VERSION"
echo "vendored xtrshow $version"

# The demo imports xtrshow.repatch without curses. Guard the regression that
# made that impossible in the first place.
if grep -q 'from xtrshow.cli import' "$dest/repatch.py"; then
  echo "error: repatch.py imports from cli.py, which imports curses." >&2
  echo "       The browser demo cannot import it. See Aloecraft-org/xtrshow." >&2
  exit 1
fi

[[ -n "$cleanup" ]] && rm -rf "$(dirname "$cleanup")"
echo "done."
