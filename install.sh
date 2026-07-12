#!/usr/bin/env bash
# Restore: COPY config from this repo into $HOME. For a fresh machine.
# Copy mode (not symlinks): your $HOME files stay independent of this repo.
# Existing files are backed up first; re-running is safe.
set -euo pipefail

DOTFILES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP="$HOME/dotfiles-backup-$(date +%Y%m%d-%H%M%S)"

# Read the shared manifest (repo-path  home-path), skipping comments/blanks.
while read -r src dst _rest; do
  [ -z "${src:-}" ] && continue
  case "$src" in \#*) continue ;; esac

  s="$DOTFILES/$src"
  d="$HOME/$dst"
  if [ ! -e "$s" ]; then
    echo "skip   $src (not in repo)"
    continue
  fi
  mkdir -p "$(dirname "$d")"
  if [ -e "$d" ] || [ -L "$d" ]; then
    mkdir -p "$BACKUP/$(dirname "$dst")"
    mv "$d" "$BACKUP/$dst"
    echo "backup ~/$dst -> $BACKUP/$dst"
  fi
  cp -a "$s" "$d"
  echo "copy   $src -> ~/$dst"
done < "$DOTFILES/manifest.txt"

# Third-party oh-my-zsh plugins: cloned, not vendored in this repo.
ZSH_CUSTOM="${ZSH_CUSTOM:-$HOME/.oh-my-zsh/custom}"
if [ -d "$ZSH_CUSTOM" ]; then
  while IFS=' ' read -r name url; do
    if [ ! -d "$ZSH_CUSTOM/plugins/$name" ]; then
      git clone --depth 1 "$url" "$ZSH_CUSTOM/plugins/$name"
    fi
  done <<'PLUGINS'
zsh-autosuggestions https://github.com/zsh-users/zsh-autosuggestions
zsh-completions https://github.com/zsh-users/zsh-completions
zsh-syntax-highlighting https://github.com/zsh-users/zsh-syntax-highlighting
fzf-tab https://github.com/Aloxaf/fzf-tab
PLUGINS
else
  echo "note: oh-my-zsh not installed; skipping plugin clones"
fi

echo
echo "Done. Packages this environment expects:"
echo "  base:   zsh, oh-my-zsh, tmux, vim, gh"
echo "  asdf:   nodejs, lazygit  (versions in tools/tool-versions)"
echo "  docker: ruby, redis"
echo "  binary: lazydocker  (release binary -> ~/.local/bin; see bootstrap.sh)"
