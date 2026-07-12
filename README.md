# dotfiles

My WSL2 development environment configuration, version-controlled and
restorable on a fresh machine.

This repo holds **copies** of the config files; the files in your `$HOME` are the
real, independent originals. Nothing here is symlinked into `$HOME`, so editing
this repo never changes your live environment — and changing your live config
never touches this repo — until you deliberately sync. Two scripts do that:

- **`./bootstrap.sh`** — set up a fresh Ubuntu/WSL2 machine end-to-end: install
  every prerequisite, then run `install.sh`. Idempotent; `--dry-run` previews.
- **`./install.sh`** — copy config **from** the repo **into** `$HOME` (config
  only, no installs).
- **`./save.sh`** — copy your live `$HOME` config **into** the repo (snapshot,
  which you then `git commit`).

## Restore on a fresh machine

One command installs everything and copies your config in:

```bash
git clone <repo-url> ~/dotfiles
cd ~/dotfiles
./bootstrap.sh --dry-run   # preview what would be installed (changes nothing)
./bootstrap.sh             # install prerequisites, then run install.sh
```

`bootstrap.sh` targets the **Debian/Ubuntu family (apt/dpkg)** — Ubuntu, Debian,
WSL2, Mint, Pop!_OS, and other derivatives (validated clean-room on Ubuntu 24.04
and Debian 12). On a non-apt OS (Fedora, Arch, macOS, Alpine…) it exits early
with a message instead of doing anything half-broken. It is idempotent — it
detects what's already installed and skips it. It installs base packages (git,
zsh, curl, tmux, fzf, build-essential), **gh**, **Go**, **Docker**, **oh-my-zsh**,
**asdf** (+ `nodejs` & `lazygit` from [`tools/tool-versions`](tools/tool-versions)),
**lazydocker**, and **Claude Code**; sets zsh as your login shell; and finally
runs `install.sh` to copy config into `$HOME`.

Two steps may need follow-up: `chsh` can prompt for your password, and Docker on
WSL2 usually needs `sudo service docker start` (or Docker Desktop's WSL
integration).

Note that apt's `golang-go` version differs by distro (Ubuntu 24.04 → Go 1.22,
Debian 12 → Go 1.19). Nothing in `bootstrap.sh` depends on it, but if you do Go
development, install a current Go from [go.dev](https://go.dev/dl/) instead.

### Config only (no installs)

If the machine already has the tools and you only want the config, skip
`bootstrap.sh` and run `./install.sh` directly. It copies each file from the repo
into `$HOME`, backing up anything it would overwrite into
`~/dotfiles-backup-<timestamp>/`, and clones the oh-my-zsh plugins. Re-running is
safe.

### Not automated (do these by hand)

`bootstrap.sh` can't restore secrets or personal state — after it runs:

- **Git identity** — your name/email live in `~/.gitconfig.local`, which is
  git-ignored and never committed; the tracked `gitconfig` pulls it in via
  `[include]`. `bootstrap.sh` prompts you for these on a fresh machine. If you
  run `install.sh` on its own instead, create it by hand:
  `cp git/gitconfig.local.example ~/.gitconfig.local` and edit.
- **SSH key** — copy your `~/.ssh/id_github` (and any others) onto the machine.
  It's deliberately excluded from this repo. Git over HTTPS still works via `gh`,
  but SSH remotes (`git@github.com:…`) and the `ssh-add` line in `.zshrc` need it.
- **Auth/credentials** — `gh auth login`, plus `~/.aws`, `~/.docker`, etc. as
  needed. None of these live in the repo.

### Docker vs. host installs

Only two tools are asdf-managed on the host — **nodejs** (kept at the latest
release; it's the runtime **Claude Code** itself needs) and **lazygit**.
Everything else is installed another way:

- **ruby**, **redis** — run from Docker images; no host install needed.
- **lazydocker** — installed from its official **release binary** into
  `~/.local/bin` (not asdf-managed). Note: `go install …/lazydocker@latest`
  currently fails to compile upstream, so `bootstrap.sh` uses the release
  tarball instead.

To change Node later: `asdf install nodejs <version>`, set that version in your
live `~/.tool-versions`, then run `./save.sh` to record it in the repo. Note that
global npm CLIs (like `ng`) are installed *per Node version* — after a major Node
bump they'll look "missing" until you reinstall them under the new version.

## Layout

| Path | Contents | Copied to/from |
|---|---|---|
| `shell/` | `zshrc`, `bashrc`, `profile`, `tmux.conf`, `zsh/` (completions) | `~/.zshrc`, `~/.bashrc`, `~/.profile`, `~/.tmux.conf`, `~/.zsh` |
| `git/` | `gitconfig` | `~/.gitconfig` |
| `tools/` | `tool-versions` (asdf version pins) | `~/.tool-versions` |
| `config/` | selected `~/.config`: `gh/config.yml`, `git/ignore` | `~/.config/gh/config.yml`, `~/.config/git/ignore` |
| `claude/` | Claude Code `settings.json`, `settings.local.json`, `statusline.sh` | `~/.claude/…` |

The mapping above is driven by [`manifest.txt`](manifest.txt) — a plain
`repo-path  home-path` list that both `install.sh` and `save.sh` read. To track a
new file, add one line there.

## Security policy

This repo is intended to be published **publicly**, so credentials and
machine-local state are deliberately excluded and never committed:

- `~/.ssh`, `~/.aws`, `~/.docker`, `~/.railway` — credentials and keys
- `~/.claude.json` — contains OAuth / session data
- `~/.config/gh/hosts.yml` — contains a GitHub auth token (only the clean
  `config.yml` is included)
- All shell history (`.zsh_history`, `.bash_history`, any `*history*` file)

[`.gitignore`](.gitignore) guards against adding any of these by accident, but a
`.gitignore` is a safety net, not a guarantee.

**The rule: run the secret scan before every push.**

```bash
git ls-files -z -- ':!:README.md' | xargs -0 grep -lriE \
  'ghp_|gho_|xox[bp]-|AKIA[0-9A-Z]{16}|-----BEGIN.*PRIVATE KEY|authtoken' -- \
  || echo "SCAN CLEAN"
```

Expected output: `SCAN CLEAN` (it lists any offending file, or prints
`SCAN CLEAN` when there are none). `README.md` is excluded from the scan on
purpose: this file *documents* the patterns, so it always matches on its own
definitions — a false positive, not a leak. Every actual config file (`shell/`,
`git/`, `config/`, `claude/`, `tools/`) is still scanned. If
[gitleaks](https://github.com/gitleaks/gitleaks)
is installed, additionally run `gitleaks detect -s . --no-git`.

## Environment files (`.env`)

Real `.env` files are **never committed** — they hold secrets. Instead, commit a
sanitized `.env.example` next to any config that needs one, with placeholder
values:

```dotenv
API_KEY=your-key-here
DATABASE_URL=postgres://user:pass@localhost:5432/dbname
```

The `.gitignore` enforces this: every `.env*` file is ignored, with an explicit
exception for `!.env.example`.

## Saving changes back to the repo

Because nothing is symlinked, editing `~/.zshrc` (or any config) does **not**
change this repo. When you want to snapshot your current setup:

```bash
./save.sh          # copies your live $HOME config into the repo (read-only on $HOME)
git diff           # review exactly what changed
# run the secret scan (below) — it must print SCAN CLEAN
git add -A && git commit -m "Update <whatever changed>"
```

`save.sh` only reads your `$HOME` files; it never modifies them. This is the
deliberate trade-off of copy mode: the repo can drift from your live config until
you run `save.sh`, in exchange for the repo never being able to break your live
environment on its own.

## Publishing & updating

First-time publish (creates a **public** repo — only after the secret scan
above passes):

```bash
gh repo create dotfiles --public --source . --push
```

After that, updating is `./save.sh` to snapshot, the secret scan, then commit and
push:

```bash
./save.sh
# run the secret scan first — it must print SCAN CLEAN
git add -A
git commit -m "Update <whatever changed>"
git push
```

## License

[MIT](LICENSE) — reuse anything here freely.
