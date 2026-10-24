#!/usr/bin/env bash
# Snapshot: COPY your live $HOME config INTO this repo, so you can commit it.
# This is the only thing that updates the repo from your machine. It never
# touches your live $HOME files — it only reads them.
set -euo pipefail

DOTFILES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while read -r src dst _rest; do
  [ -z "${src:-}" ] && continue
  case "$src" in \#*) continue ;; esac

  s="$DOTFILES/$src"
  d="$HOME/$dst"
  if [ ! -e "$d" ]; then
    echo "skip   ~/$dst (not on this machine)"
    continue
  fi
  mkdir -p "$(dirname "$s")"
  rm -rf "$s"          # replace cleanly (handles files and directories)
  cp -a "$d" "$s"
  echo "saved  ~/$dst -> $src"
done < "$DOTFILES/manifest.txt"

# Herdr registers its Claude hook with a machine-specific absolute path, and
# `herdr integration install claude` re-adds it on every machine (it does not
# recognise a rewritten entry), so keep that one entry out of the shared
# settings. Your own hooks stay.
if command -v python3 >/dev/null 2>&1; then
  python3 - "$DOTFILES/claude/settings.json" <<'PY'
import json, sys
path = sys.argv[1]
d = json.load(open(path))
changed = False
for groups in (d.get("hooks") or {}).values():
    for g in groups:
        kept = [h for h in g.get("hooks", []) if "herdr-agent-state" not in h.get("command", "")]
        if len(kept) != len(g.get("hooks", [])):
            g["hooks"] = kept
            changed = True
    groups[:] = [g for g in groups if g.get("hooks")]
if changed:
    with open(path, "w") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("strip  Herdr hook entry from claude/settings.json (herdr integration install re-adds it per machine)")
PY
else
  echo "note: python3 not found; claude/settings.json keeps the machine-specific Herdr hook entry"
fi

echo
echo "Review, then commit:"
echo "  git -C \"$DOTFILES\" status && git -C \"$DOTFILES\" diff"
echo "  # run the secret scan (see README) before pushing"
echo "  git -C \"$DOTFILES\" add -A && git -C \"$DOTFILES\" commit -m 'Update dotfiles'"
