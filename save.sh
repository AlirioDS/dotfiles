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

echo
echo "Review, then commit:"
echo "  git -C \"$DOTFILES\" status && git -C \"$DOTFILES\" diff"
echo "  # run the secret scan (see README) before pushing"
echo "  git -C \"$DOTFILES\" add -A && git -C \"$DOTFILES\" commit -m 'Update dotfiles'"
