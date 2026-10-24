#!/usr/bin/env bash
# bootstrap.sh — set up a fresh Ubuntu/WSL2 machine, then restore config.
#
# Idempotent: detects what's already installed and skips it.
# Usage:
#   ./bootstrap.sh            install anything missing, then run install.sh
#   ./bootstrap.sh --dry-run  report what WOULD be installed; change nothing
#
# Targets Ubuntu/Debian (apt). Installs: base packages, gh, Go, Docker,
# oh-my-zsh, asdf (+ nodejs/lazygit from tool-versions), lazydocker,
# Claude Code, Codex, Herdr (+ its Claude/Codex integrations), and sets zsh
# as the login shell.
set -uo pipefail

DOTFILES="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASDF_VERSION="v0.19.0"
# $USER is not exported in every environment (containers, sudo, non-login shells);
# `set -u` would abort the whole script on it.
TARGET_USER="${USER:-$(id -un)}"

DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

have() { command -v "$1" >/dev/null 2>&1; }
hr()   { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '    \033[32m✓\033[0m %s\n' "$*"; }
todo() { printf '    \033[33m→\033[0m %s\n' "$*"; }
# run a plain command (array-safe); no-op under --dry-run
run()  { [ "$DRY_RUN" = 1 ] && return 0; "$@"; }
# run a shell string (for pipes/redirects); no-op under --dry-run
sh_c() { [ "$DRY_RUN" = 1 ] && return 0; bash -c "$*"; }

if ! have apt-get; then
  echo "This bootstrap targets Ubuntu/Debian (apt) — not found. Aborting." >&2
  exit 1
fi
[ "$DRY_RUN" = 1 ] && echo "(dry-run: reporting only — nothing will be installed)"
ARCH="$(dpkg --print-architecture)"

### 1. Base packages ---------------------------------------------------------
hr "Base packages (apt)"
# python3: Herdr's Claude/Codex hook scripts exit silently without it.
# ncurses-term: terminfo for tmux-256color (default-terminal in tmux.conf).
BASE=(git zsh curl tmux fzf build-essential ca-certificates gnupg python3 ncurses-term)
missing=()
for p in "${BASE[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
if [ "${#missing[@]}" -eq 0 ]; then
  ok "all present: ${BASE[*]}"
else
  todo "install: ${missing[*]}"
  run sudo apt-get update
  run sudo apt-get install -y "${missing[@]}"
fi

### 2. GitHub CLI ------------------------------------------------------------
hr "GitHub CLI (gh)"
if have gh; then
  ok "gh present ($(gh --version 2>/dev/null | head -1 | awk '{print $3}'))"
else
  todo "install gh from cli.github.com apt repo"
  sh_c 'curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg'
  sh_c 'sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg'
  sh_c "echo 'deb [arch=${ARCH} signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main' | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null"
  run sudo apt-get update
  run sudo apt-get install -y gh
fi

### 3. Go --------------------------------------------------------------------
hr "Go toolchain"
if have go; then
  ok "go present ($(go version 2>/dev/null | awk '{print $3}'))"
else
  todo "install golang-go (apt)"
  run sudo apt-get install -y golang-go
fi

### 4. Docker + compose ------------------------------------------------------
hr "Docker + compose"
if have docker; then
  ok "docker present ($(docker --version 2>/dev/null | awk '{print $3}' | tr -d ,))"
else
  todo "install Docker Engine (get.docker.com) + add $TARGET_USER to docker group"
  sh_c 'curl -fsSL https://get.docker.com | sudo sh'
  run sudo usermod -aG docker "$TARGET_USER"
  todo "WSL2 note: start with 'sudo service docker start', or use Docker Desktop integration"
fi

### 5. oh-my-zsh -------------------------------------------------------------
hr "oh-my-zsh"
if [ -d "$HOME/.oh-my-zsh" ]; then
  ok "~/.oh-my-zsh present"
else
  todo "install oh-my-zsh (unattended, keep existing .zshrc)"
  sh_c 'RUNZSH=no CHSH=no KEEP_ZSHRC=yes sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended'
fi

### 6. asdf ------------------------------------------------------------------
hr "asdf"
export ASDF_DATA_DIR="$HOME/.asdf"
export PATH="$HOME/.local/bin:$HOME/.asdf/bin:$HOME/.asdf/shims:$PATH"
if have asdf; then
  ok "asdf present ($(asdf --version 2>/dev/null))"
else
  todo "download asdf ${ASDF_VERSION} binary -> ~/.asdf/bin"
  run mkdir -p "$HOME/.asdf/bin"
  sh_c "curl -fsSL https://github.com/asdf-vm/asdf/releases/download/${ASDF_VERSION}/asdf-${ASDF_VERSION}-linux-${ARCH}.tar.gz | tar xz -C '$HOME/.asdf/bin'"
fi

### 7. Restore config (copies repo -> $HOME, clones omz plugins) -------------
hr "Restore config (install.sh)"
if [ "$DRY_RUN" = 1 ]; then
  todo "run install.sh (copy config into \$HOME, clone oh-my-zsh plugins)"
else
  "$DOTFILES/install.sh"
fi

### 7b. Git identity (machine-local, never committed) -----------------------
hr "Git identity (~/.gitconfig.local)"
if [ -f "$HOME/.gitconfig.local" ]; then
  ok "~/.gitconfig.local present"
elif [ "$DRY_RUN" = 1 ]; then
  todo "create ~/.gitconfig.local (prompt for name/email, or copy the template)"
elif [ -t 0 ]; then
  read -rp "    git user.name:  " gname
  read -rp "    git user.email: " gemail
  printf '[user]\n\temail = %s\n\tname = %s\n' "$gemail" "$gname" > "$HOME/.gitconfig.local"
  ok "wrote ~/.gitconfig.local"
else
  cp "$DOTFILES/git/gitconfig.local.example" "$HOME/.gitconfig.local"
  todo "created ~/.gitconfig.local from template — edit it to set your name/email"
fi

### 8. asdf runtimes from restored ~/.tool-versions --------------------------
hr "asdf runtimes (nodejs, lazygit from ~/.tool-versions)"
if [ "$DRY_RUN" = 1 ]; then
  todo "asdf plugin add nodejs lazygit (if missing), then 'asdf install' in \$HOME"
elif have asdf; then
  for plugin in nodejs lazygit; do
    asdf plugin list 2>/dev/null | grep -qx "$plugin" || asdf plugin add "$plugin"
  done
  ( cd "$HOME" && asdf install ) || todo "asdf install had issues — check ~/.tool-versions"
else
  todo "asdf not on PATH yet; open a new shell and run 'asdf install'"
fi

### 9. lazydocker (official release binary) ---------------------------------
# NOT `go install ...@latest`: that currently fails to compile upstream
# (docker module mismatch). The published release binary always works.
hr "lazydocker"
if have lazydocker; then
  ok "lazydocker present"
elif [ "$DRY_RUN" = 1 ]; then
  todo "download lazydocker release binary -> ~/.local/bin"
else
  todo "download lazydocker release binary -> ~/.local/bin"
  ld_arch="$(uname -m)"
  case "$ld_arch" in aarch64*) ld_arch=arm64 ;; armv7*) ld_arch=armv7 ;; armv6*) ld_arch=armv6 ;; esac
  ld_ver="$(curl -fsSL -H 'Accept: application/json' https://github.com/jesseduffield/lazydocker/releases/latest \
            | sed -e 's/.*"tag_name":"\([^"]*\)".*/\1/')"
  ld_tmp="$(mktemp -d)"
  if [ -n "$ld_ver" ] && curl -fsSL \
      "https://github.com/jesseduffield/lazydocker/releases/download/${ld_ver}/lazydocker_${ld_ver#v}_$(uname -s)_${ld_arch}.tar.gz" \
      | tar xz -C "$ld_tmp" lazydocker 2>/dev/null; then
    install -Dm755 "$ld_tmp/lazydocker" "$HOME/.local/bin/lazydocker"
    ok "lazydocker ${ld_ver} installed"
  else
    todo "lazydocker download failed — install it manually"
  fi
  rm -rf "$ld_tmp"
fi

### 10. Claude Code CLI ------------------------------------------------------
hr "Claude Code CLI"
if have claude; then
  ok "claude present ($(claude --version 2>/dev/null | head -1))"
elif have npm; then
  todo "npm install -g @anthropic-ai/claude-code"
  run bash -c 'npm install -g @anthropic-ai/claude-code && asdf reshim nodejs 2>/dev/null || true'
else
  todo "npm not available yet — install node (step 8) first, then: npm i -g @anthropic-ai/claude-code"
fi

### 10b. Codex CLI ------------------------------------------------------------
hr "Codex CLI"
if have codex; then
  ok "codex present ($(codex --version 2>/dev/null | head -1))"
elif have npm; then
  todo "npm install -g @openai/codex"
  run bash -c 'npm install -g @openai/codex && asdf reshim nodejs 2>/dev/null || true'
else
  todo "npm not available yet — install node (step 8) first, then: npm i -g @openai/codex"
fi

### 10c. Herdr + agent integrations ------------------------------------------
# Herdr organizes terminals/agents inside tmux; its config.toml was restored by
# install.sh (step 7). The integrations write the hook files that let Herdr
# detect Claude Code and Codex; they are NOT part of the tracked claude/ files,
# so they must be (re)installed on every machine.
# The installer fetches the latest release (this setup was verified with 0.9.5);
# to pin a version, download that release's binary from GitHub instead.
hr "Herdr (+ Claude/Codex integrations)"
if have herdr; then
  ok "herdr present ($(herdr --version 2>/dev/null | head -1))"
else
  todo "install herdr (herdr.dev/install.sh -> ~/.local/bin)"
  sh_c 'curl -fsSL https://herdr.dev/install.sh | sh'
fi
if have herdr || [ "$DRY_RUN" = 1 ]; then
  for agent in claude codex; do
    if have "$agent"; then
      todo "herdr integration install $agent"
      run herdr integration install "$agent"
    else
      todo "herdr integration install $agent (skipped: $agent not installed yet)"
    fi
  done
  if [ "$DRY_RUN" = 0 ] && herdr status server 2>/dev/null | grep -q 'status: running'; then
    todo "herdr server reload-config (a Herdr server is already running)"
    run herdr server reload-config >/dev/null
  fi
fi

### 11. Login shell ----------------------------------------------------------
hr "Login shell"
ZSH_BIN="$(command -v zsh || true)"
if [ -n "$ZSH_BIN" ] && [ "${SHELL:-}" = "$ZSH_BIN" ]; then
  ok "login shell already zsh ($ZSH_BIN)"
elif [ -n "$ZSH_BIN" ]; then
  todo "chsh -s $ZSH_BIN (may prompt for your password)"
  run chsh -s "$ZSH_BIN"
else
  todo "zsh not installed yet"
fi

### Summary ------------------------------------------------------------------
hr "Summary"
for t in git zsh gh go docker asdf node lazygit lazydocker claude codex herdr; do
  if have "$t"; then ok "$t"; else todo "$t (not detected)"; fi
done
echo
echo "Open a new terminal (or 'exec zsh') to pick up the new shell/config."
if [ "$DRY_RUN" = 1 ]; then
  echo "This was a dry run. Re-run without --dry-run to apply."
fi
# Explicit success: without this the script would exit with the status of the
# test above (1 on a real run), breaking `./bootstrap.sh && next-command`.
exit 0
