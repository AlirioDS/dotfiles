# Herdr inside tmux: configuration and server handoff

Configuration verified on 20 October 2026, audited independently the same day (19 isolated checks passed, see [Checks performed](#checks-performed)) and reviewed a second time on 24 October 2026 with a Codex (gpt-6-astra) audit. The goal is to keep tmux as the outer environment and use Herdr to organize terminals and agents, with navigation, splits, scrolling and copying that feel like tmux.

The control layout is:

- **tmux uses `Ctrl+b`.**
- **Herdr uses `Ctrl+a`, pressed once per action.** `Ctrl+a` → `Ctrl+a` sends a literal `Ctrl+a` (beginning of line in zsh and in Claude Code).
- The mouse and the wheel reach Herdr whenever it asks for them.
- Shells opened by Herdr do not auto-start another tmux.
- Claude Code and Codex must run directly in Herdr panes so that Herdr detects them.

This file contains the active settings, usage instructions and the criteria for adapting them to the destination server. The configuration blocks are a reference to merge into the existing files; they do not require replacing the server's whole configuration.

## Changes from the audits

20 October:

- `delivery = "system"` became `delivery = "herdr"`: on this WSL, `system` showed no notification at all (see the Herdr section).
- The wheel in tmux copy mode moves 3 lines per notch (`-N 3`), like Herdr; it used to move 1.
- The reload description was corrected: `herdr server reload-config` applies the shortcuts in every client.
- Documented the literal prefix, the closes without confirmation, the OSC 52 rule over SSH and the reproducible tests in `~/herdr-tmux-audit/`.

24 October (second review, with an independent audit by Codex gpt-6-astra; local report at `~/herdr-tmux-audit/codex-audit-2026-10-24.md`, excluded from the repository):

- `.zshrc`: the auto-start creates the numbered session detached, retries with the next number when two shells start at the same time ("duplicate session"), attaches once, and requires a real terminal (`[[ -t 0 && -t 1 ]]`). Comments translated to English.
- `.tmux.conf`: `default-terminal` is `screen-256color` and upgrades to `tmux-256color` when its terminfo entry exists; the `Ctrl+b` prefix and `prefix2 None` are declared explicitly.
- `~/dotfiles`: `bootstrap.sh` installs Codex and Herdr, registers both integrations and adds `python3` and `ncurses-term` to the base packages; the repository tracks `config/herdr/config.toml`, this document and the tests; `.gitignore` excludes credentials and Herdr session state; the README's secret scan no longer reports "clean" on errors nor ignores new files.
- This document: updated status, migration without a blind `kill-session`, the nuances of `clipboard` and `SSH_CONNECTION`, the topology with tmux on both ends, and `NO_TMUX`.

## Source environment

| Component | Observed value |
|---|---|
| Outer terminal | Windows Terminal |
| System | Ubuntu under WSL |
| Interactive shell | zsh |
| Herdr | 0.9.5 |
| Herdr binary | `~/.local/bin/herdr` |
| tmux | 3.4 |
| Herdr configuration | `~/.config/herdr/config.toml` |
| tmux configuration | `~/.tmux.conf` |
| Shell startup | `~/.zshrc` |
| Claude integration | Installed and current, v11 |
| Codex integration | Installed and current, v10 |
| Reproducible tests | `~/herdr-tmux-audit/run_checks.py` |
| Independent audit | `~/herdr-tmux-audit/codex-audit-2026-10-24.md` (Codex gpt-6-astra, max effort; only on this machine, not published in dotfiles) |
| Versioned copy | `~/dotfiles`: `shell/zshrc`, `shell/tmux.conf`, `config/herdr/config.toml`, `docs/herdr-tmux-config.md`, `tools/herdr-tmux-audit/` |

On the destination server, check the versions and the terminal in use before carrying these settings over. Herdr and tmux may have other options or bindings in different versions.

## Session structure

On the source machine:

```text
Windows Terminal
└── Ubuntu on WSL
    └── tmux                         Ctrl+b
        └── Herdr                    Ctrl+a
            ├── Workspace project A
            │   ├── Tab 1 → zsh → Claude Code
            │   └── Tab 2 → zsh → shell or project process
            └── Workspace project B
                └── Tab 1 → zsh → Codex
```

An SSH adaptation can keep the same order:

```text
Local terminal → SSH → server tmux → Herdr → shell → agent
```

The original problem was that zsh's auto-start produced this structure:

```text
tmux → Herdr → another tmux → agent
```

Herdr saw the tmux client in its panes and did not detect the agents behind it. The `HERDR_ENV` check in the shell prevents that second tmux. Herdr documents this limitation and the condition that avoids it in its [agent detection guide](https://herdr.dev/docs/agents/#detection-manifests).

## Active Herdr configuration

File: `~/.config/herdr/config.toml`.

```toml
onboarding = false

[ui.toast]
delivery = "herdr"

[ui]
status_indicators = "symbols"
mouse_capture = true
copy_on_select = true
mouse_scroll_lines = 3
prompt_new_tab_name = false

[keys]
prefix = "ctrl+a"
focus_pane_left = ["prefix+h", "prefix+left"]
focus_pane_down = ["prefix+j", "prefix+down"]
focus_pane_up = ["prefix+k", "prefix+up"]
focus_pane_right = ["prefix+l", "prefix+right"]
split_vertical = ["prefix+v", "prefix+percent"]
split_horizontal = ["prefix+minus", "prefix+double_quote"]
```

The separate prefix allows controlling Herdr without pressing `Ctrl+b` twice. The arrows and the `%` and `"` symbols add tmux's usual movements and splits while keeping Herdr's original bindings (`h/j/k/l`, `v` and `-`).

`mouse_capture` allows clicking in the interface and hands the wheel to Herdr. `copy_on_select` copies the selection when the mouse button is released. `prompt_new_tab_name = false` creates tabs without asking for a name, like the usual tmux flow. `mouse_scroll_lines = 3` matches Herdr's default.

`delivery = "herdr"` shows notifications inside Herdr's interface, for example "● claude finished" when an agent in another workspace finishes, and works the same over SSH. `delivery = "system"` runs `notify-send` from the client; on this WSL it is not installed and there is no D-Bus notification service, and Herdr skips it without logging anything ([implementation](https://github.com/herdrdev/herdr/blob/v0.9.5/src/platform/linux.rs#L974-L1004)). `status_indicators` is a presentation preference.

## Active tmux configuration

File: `~/.tmux.conf`.

```tmux
##### Terminal & colors
# Safe default first (valid on every terminfo database), then upgrade when the tmux-256color entry
# exists (ncurses-term on Debian/Ubuntu). The unconditional line also covers a client that connects
# while the server is still evaluating the if-shell below.
set -g default-terminal "screen-256color"
if-shell 'infocmp tmux-256color >/dev/null 2>&1' 'set -g default-terminal "tmux-256color"'
set -as terminal-overrides ',xterm-256color:Tc'   # truecolor

##### Basics
set -g history-limit 100000
set -g escape-time 0
set -g focus-events on
setw -g mode-keys vi

##### Prefix: Ctrl+b for tmux (Herdr uses Ctrl+a inside); Ctrl+b Ctrl+b sends a literal Ctrl+b
set -g prefix C-b
set -g prefix2 None
bind C-b send-prefix

##### Clipboard: allow Herdr and other pane apps to copy to the system clipboard
set -s set-clipboard on

##### Status (minimal)
set -g status on
set -g status-interval 5
set -g status-left "[#S] "
setw -g automatic-rename on
setw -g automatic-rename-format "#{window_index}:#{pane_current_command}"

##### Mouse: forward events to Herdr and other mouse-aware apps
set -g mouse on
bind -n WheelUpPane if-shell -F -t = '#{||:#{pane_in_mode},#{mouse_any_flag}}' 'send-keys -M' 'copy-mode -e'
bind -n WheelDownPane send-keys -M
bind -T copy-mode-vi WheelUpPane   send-keys -X -N 3 scroll-up
bind -T copy-mode-vi WheelDownPane send-keys -X -N 3 scroll-down

##### Optional: quick toggle (Ctrl-b m) between tmux mouse ON/OFF
bind m if -F '#{mouse}' \
  'set -g mouse off \; display "tmux mouse: OFF (terminal scroll)"' \
  'set -g mouse on  \; display "tmux mouse: ON (pane scroll)"'
```

`Ctrl+b` is tmux's default prefix; since 24 October the file declares it explicitly (`set -g prefix C-b`, `set -g prefix2 None`, `bind C-b send-prefix`), so merging this block into a server configuration that uses another prefix restores `Ctrl+b` for tmux. `Ctrl+b` → `Ctrl+b` sends a `Ctrl+b` to the pane application. If the server must keep its own prefix, drop those three lines and adapt the rest of this document accordingly.

`default-terminal` is set to `screen-256color` first, which every terminfo database has, and then upgraded through `if-shell` to `tmux-256color` when that entry exists (package `ncurses-term` on Debian/Ubuntu). This way the same file works on minimal servers without pane applications failing with "unknown terminal", and a client that connects during the server's first configuration load still gets a valid value. The same entry is needed when connecting over SSH from inside a local tmux, because the connection arrives with `TERM=tmux-256color`: install `ncurses-term` on the server or connect with `TERM=screen-256color ssh ...`.

### Why the wheel bindings changed

Before, wheel-up always activated tmux copy mode. That captured the event before it reached Herdr.

The current binding checks whether the pane is already in copy mode or whether the application requests mouse events. In those cases it delivers the event with `send-keys -M`. For an ordinary shell that does not use the mouse, it opens tmux's history.

Wheel-down is also delivered with `send-keys -M`. The `copy-mode-vi` bindings move 3 lines per notch inside tmux's history (`-N 3`), matching Herdr's `mouse_scroll_lines`; tmux's default is 5.

The expected result is:

- Over Herdr, the wheel reaches Herdr without activating tmux copy mode. In a shell pane, Herdr scrolls its history 3 lines per notch; if the pane application asks for mouse events (Claude Code, Codex, `lazygit`), Herdr hands it the wheel and the application decides how to scroll.
- Over an ordinary tmux shell, the first notch opens the history and the following ones move 3 lines; scrolling down to the end leaves copy mode.
- `Ctrl+b` → `m` still toggles tmux's mouse; to drive Herdr with the mouse it must stay on.

### Why the clipboard was enabled

Herdr 0.9.5 copies with OSC 52 when it detects WSL, `SSH_CONNECTION`, `SSH_TTY` or `VSCODE_IPC_HOOK_CLI` in the `herdr` client's environment; otherwise it first tries `wl-copy` or `xclip` ([implementation](https://github.com/herdrdev/herdr/blob/v0.9.5/src/selection.rs#L337-L376)). OSC 52 is a terminal sequence that asks the client to write text to its clipboard.

tmux was configured with `set-clipboard external`, which prevents inner applications from setting that clipboard. `set-clipboard on` lets those requests through. The outer terminal must accept them too. With several tmux layers nested over SSH, every layer must be checked. [tmux clipboard documentation](https://github.com/tmux/tmux/wiki/Clipboard).

Herdr also forwards the OSC 52 emitted by the applications in its panes (Claude Code, Codex, editors), so those copies reach the outer terminal as well.

Herdr's selection copies automatically when the button is released. To paste in Windows Terminal use `Ctrl+Shift+V`; in other Windows applications, `Ctrl+V`.

## zsh auto-start

This is the active block of `~/.zshrc`. The rest of the file holds the user's usual configuration and is not part of this adaptation.

```zsh
# --- Auto-start tmux: one numbered session per terminal tab (no awk) ---
if [[ $- == *i* ]] && [[ -t 0 && -t 1 ]] && [[ -z "$TMUX" ]] && [[ -z "$NO_TMUX" ]] && [[ "${HERDR_ENV:-}" != 1 ]] && [[ -z "${HC_TERMINAL_ID:-}" ]] && command -v tmux >/dev/null 2>&1; then
  # Existing numeric session names (may be empty)
  sessions="$(tmux ls -F '#{session_name}' 2>/dev/null | grep -E '^[0-9]+$' | sort -n || true)"

  i=0
  # Find the lowest free number
  while echo "$sessions" | grep -qx "$i"; do
    i=$((i+1))
  done

  # Create the session detached first: a failure here that leaves the session existing can only be
  # "duplicate session" (another shell took the same number at the same moment), so try the next one.
  # Any other tmux error is shown and ends the loop.
  until tmux new -d -s "$i"; do
    tmux has-session -t "=$i" 2>/dev/null || break
    i=$((i+1))
  done
  # Attach once; whatever happens to this client later never re-enters the loop.
  tmux attach -t "=$i"
fi
# --- /Auto-start tmux ---
```

The new condition is:

```zsh
[[ "${HERDR_ENV:-}" != 1 ]]
```

Herdr sets `HERDR_ENV=1` in the processes of its panes. The condition keeps tmux's auto-start outside Herdr and prevents it inside. It was checked both ways: without `HERDR_ENV`, the same `.zshrc` creates tmux session `0`; with `HERDR_ENV=1`, it creates none.

A second condition was added on 13 November 2026 for the Herdr desktop app:

```zsh
[[ -z "${HC_TERMINAL_ID:-}" ]]
```

The desktop app does not use the `herdr` binary: its terminals run on herdr-core (`hc`), which sets `HC_TERMINAL_ID` in them and not `HERDR_ENV`. The app starts shells and agents inside the user's interactive shell, so with the `HERDR_ENV` check alone a desktop space opened tmux and its agent never started. It was checked with this `.zshrc` on private tmux sockets: with `HC_TERMINAL_ID` set it creates no session; without it, session `0` as before.

herdr-core itself starts from a non-interactive login shell when the desktop app reaches this machine over SSH, and that shell does not read `.zshrc`. `~/.zprofile` gives login shells the same tool paths (`~/.local/bin`, asdf and its shims, plus `~/go/bin` and `~/.opencode/bin` where they exist), so that herdr-core finds `claude`, `codex` and `opencode`.

The `until tmux new -d -s "$i"` loop was added on 24 October: when several shells start at once (Windows Terminal restoring tabs, several SSH connections), two of them computed the same free number and the second failed with "duplicate session" and stayed outside tmux. Now the session is created detached first — if that fails and the session exists, another shell took the number and the loop tries the next one; any other error is shown and ends the loop — and then `tmux attach` runs exactly once, so nothing that happens to that client later (detach, server killed, client killed) can re-enter the loop. It was verified with three simultaneous shells: sessions `0`, `1` and `2`, all three inside tmux, and exiting or detaching returns to the shell.

`NO_TMUX` with any non-empty value (including `0`) disables the auto-start: `NO_TMUX=1 zsh`. The condition also requires stdin and stdout to be a terminal (`[[ -t 0 && -t 1 ]]`), so `zsh -ic 'command'` without a TTY runs the command without trying to open tmux. An integrated terminal such as VS Code's does meet the condition and opens its numbered session; if that is unwanted, export `NO_TMUX=1` in that terminal.

Another server may have a fixed session, a session manager or a different startup logic. The condition must be merged into that logic, without necessarily copying this machine's numbered-session scheme.

The change applies to new shells. It does not pull processes out of a tmux they are already in, nor does it change the structure of old panes.

## Everyday shortcuts

In every example, press `Ctrl+a`, release it, then press the second key. `Shift+d` means an uppercase `D`.

| Herdr action | Shortcut |
|---|---|
| New tab | `Ctrl+a` → `c` |
| Next tab | `Ctrl+a` → `n` |
| Previous tab | `Ctrl+a` → `p` |
| Go to a tab by number | `Ctrl+a` → `1` to `9` |
| Move focus between panes | `Ctrl+a` → arrow |
| Move focus with vi keys | `Ctrl+a` → `h`, `j`, `k`, `l` |
| Split left and right | `Ctrl+a` → `%` or `v` |
| Split top and bottom | `Ctrl+a` → `"` or `-` |
| Zoom or restore the pane | `Ctrl+a` → `z` |
| Enter resize mode | `Ctrl+a` → `r` |
| Navigate workspaces | `Ctrl+a` → `w` |
| Find an agent or terminal | `Ctrl+a` → `g` |
| Create a workspace | `Ctrl+a` → `Shift+n` |
| Rename a workspace | `Ctrl+a` → `Shift+w` |
| Show or hide the sidebar | `Ctrl+a` → `b` |
| Enter copy mode | `Ctrl+a` → `[` |
| Reload configuration | `Ctrl+a` → `Shift+r` |
| Show help and active bindings | `Ctrl+a` → `?` |
| Send `Ctrl+a` to the application (beginning of line) | `Ctrl+a` → `Ctrl+a` |
| Close the current pane, no confirmation | `Ctrl+a` → `x` |
| Close the current tab, no confirmation | `Ctrl+a` → `Shift+x` |
| Close the current workspace, with confirmation | `Ctrl+a` → `Shift+d` |
| Leave the interface, keeping the session | `Ctrl+a` → `q` |

`x` and `Shift+x` close immediately even if the pane has a running process: an agent working there is terminated. Only closing a workspace asks for confirmation (`Enter` confirms, `Esc` cancels). After cancelling with `Esc`, Herdr stays in navigate mode (`NAVIGATE` in the bottom bar): press `Esc` once more before typing.

In copy mode, move with `h/j/k/l`, `w/b/e` and `{ }`; search down with `/` and up with `?`, repeating with `n/N`; start a selection with `v` or Space; `y` or Enter copy and leave the mode; `q` exits (`Esc` first clears the search). The bottom bar shows this legend. [Herdr keyboard reference](https://herdr.dev/docs/keyboard/#copy-mode).

`Ctrl+b` keeps control of the outer tmux. For example, `Ctrl+b` → `c` creates a tmux window; `Ctrl+a` → `c` creates a Herdr tab.

Leaving with `Ctrl+a` → `q` keeps the agents running. Running `herdr` reconnects to the session, with the same panes and processes.

To stop the Herdr server and its panes, the command is `herdr server stop`. It is a shutdown operation, not a configuration reload step.

## Detecting Claude Code and Codex

For a new agent:

1. Create a Herdr pane or tab.
2. Enter the project directory from that shell.
3. Run `claude` or `codex` directly.
4. Check `herdr agent list` to confirm detection.

In a shell just opened by Herdr:

```sh
printf 'HERDR_ENV=%s TMUX=%s\n' "${HERDR_ENV:-}" "${TMUX:-}"
```

In this structure, the expected result is:

```text
HERDR_ENV=1 TMUX=
```

Agents running in other tmux sessions or terminals do not automatically appear in Herdr. Existing conversations must be resumed directly in Herdr when appropriate; changing the shell does not migrate processes.

Commands to review the integrations:

```sh
herdr integration status
```

If they are missing on the destination server, the install commands are:

```sh
herdr integration install claude
herdr integration install codex
```

Integrations are installed where the agents run. On the source machine both are installed and current. In the isolated test, `codex` run directly in a Herdr pane appeared instantly as agent `codex` (state `idle`) and disappeared on exit. Codex reports its session identity, which Herdr uses to resume it after a restart, from the first request on; the test sent none.

### Status on this machine (24 October 2026)

No tmux is left inside Herdr: the only tmux server has session `0`, which runs Herdr, and `herdr agent list` shows every active agent (Claude and Codex) in Herdr panes. The migration described on 20 October (Codex inside session `4`) is done. If a pane whose visible process is `tmux` appears again: first identify what that session holds (`tmux list-windows -t N` and `tmux list-panes -s -t N -F '#{pane_pid} #{pane_current_command}'`) and which client is the nested one (`tmux list-clients -F '#{client_tty} #{client_pid} #{session_name}'`; its `client_pid` is the `tmux: client` process that `herdr pane process-info` shows for that pane). Exit the agent inside it and, only if the session is left empty or with just that shell, `tmux kill-session -t N`; if it has other windows, detach only that client with `tmux detach-client -t /dev/pts/X` (never `-s N`, which detaches every client of the session) and close the Herdr pane. Then resume the agent in a new Herdr tab (`claude --resume` or `codex resume`).

## Applying and reloading

After merging the tmux changes:

```sh
tmux source-file ~/.tmux.conf
```

`set -as terminal-overrides` appends a duplicate entry on every reload; it is harmless. For a small change, the modified binding alone can be applied with `tmux bind ...`.

After editing Herdr:

```sh
herdr server reload-config
```

This reload applies `config.toml` in the server. The shortcuts, including the prefix, `mouse_scroll_lines` and the notifications reach every connected client at once; this was checked with two clients. If the prefix changes, the new one is active in every client after this reload.

`Ctrl+a` → `Shift+r` does the same from a client and additionally reloads that client's local settings: `mouse_capture`, sound, `host_cursor` and `redraw_on_focus_gained` ([implementation](https://github.com/herdrdev/herdr/blob/v0.9.5/src/client/config_reload.rs#L93-L130)). It is only needed in each client when those settings change. With named sessions, use the corresponding session, for example `herdr --session NAME server reload-config`.

Neither reload restarts the panes: the tests compared the shells' PIDs before and after.

`.zshrc` changes are validated with:

```sh
zsh -n ~/.zshrc
```

Then open a new Herdr tab. Running `herdr` again reconnects to existing panes and does not turn them into new shells.

## Checks performed

Reproducible test:

```sh
python3 ~/herdr-tmux-audit/run_checks.py
```

It uses real tmux and Herdr on private sockets (`TMUX_TMPDIR`, `XDG_CONFIG_HOME` and `HERDR_CONFIG_PATH` inside a temporary directory), the real `~/.tmux.conf` read-only and an identical copy of the Herdr configuration, which it restores after every change. A second private tmux plays the outer terminal: it receives keyboard and SGR mouse events and records the output to decode OSC 52. It does not touch the servers in use; when finished it checks that no test process remains, that the real panes did not change and that the real zsh history received no commands. Results land in `<root>/run/results.json`. Variables: `HERDR_AUDIT_ROOT` (root; keep it short because of the socket path length limit), `AUDIT_SKIP_CODEX=1` (does not open Codex) and `HERDR_AUDIT_PROMPT` (text that identifies the zsh prompt). `--only 17,19` reruns only those checks (01 always starts the stack). The root must be empty or have been created by the test itself; if a server from a previous run is still alive, it refuses to continue until `python3 ~/herdr-tmux-audit/auditlib.py teardown` is run, and it never stops a Herdr server whose socket is outside that root. It exits non-zero if any check or the cleanup fails. Linux only.

Result of the last run, 24 October 2026, 20 of 20:

1. Isolation: the Herdr and tmux sockets stay inside the test root and the synthetic client advertises `clipboard`.
2. A new Herdr shell has `HERDR_ENV=1`, no `TMUX`, runs only `zsh` and prints `HERDR_ENV=1 TMUX=`.
3. Without `HERDR_ENV`, the `.zshrc` creates tmux session `0`; with `HERDR_ENV=1` or with `NO_TMUX=1`, none; `zsh -ic` without a TTY runs the command without trying to open tmux. Also (3b), three shells starting at once get sessions `0`, `1` and `2` with no "duplicate session".
4. Five wheel notches over Herdr move exactly 15 lines without activating tmux copy mode; scrolling down returns to 0.
5. `mouse_scroll_lines` is applied: with 7 it gives 35 lines and, restored, 15.
6. On drag, the OSC 52 reaching the terminal decodes to exactly the selected text and matches the tmux buffer.
7. Copy mode (`Ctrl+a` → `[`, `?text`, `v`, `e`, `y`): exact OSC 52; `y` exits and returns to the bottom.
8. The OSC 52 emitted by an application inside a pane reaches the terminal.
9. `Ctrl+a` → `c` creates a tab without a dialog; `p`, `n`, `1` and `2` switch tabs.
10. `%` and `v` split side by side and `"` and `-` top and bottom, verified by pane geometry; the arrows and `h/j/k/l` move focus; one prefix equals one action.
11. `Ctrl+a` → `Ctrl+a` sends a literal `Ctrl+a`.
12. `herdr server reload-config` changes the prefix and `mouse_scroll_lines` without `Shift+r`; the shells' PIDs do not change.
13. With two connected clients, one server reload changes the prefix in both.
14. `Ctrl+a` → `q` keeps the server and the processes; `herdr` returns to the same panes and PIDs.
15. `x` closes a busy pane without asking; `Shift+x` closes the tab and its shells; `Shift+d` asks, `Esc` cancels and leaves `NAVIGATE` mode, and `Enter` closes the workspace and terminates its shells.
16. `Ctrl+b` → `c` works with Herdr focused; in an ordinary shell, the first wheel notch opens the history and five notches move 12 lines; scrolling down exits; `Ctrl+b` → `Ctrl+b` is `send-prefix`.
17. Codex run in a Herdr pane is detected instantly and disappears on exit (`Esc` closes a startup dialog such as "update available", then `Ctrl+C` twice and, if needed, `/exit`).
18. The help (`Ctrl+a` → `?`) shows `ctrl+a` as the prefix.
19. An agent finishing in another workspace shows "● claude finished" with `delivery = "herdr"`; with `"system"` no notification appears inside Herdr (the test cannot see desktop notifications).

It was also checked that the configuration blocks in this document match the active files byte for byte, that the running tmux has the same bindings and options as a fresh one loaded from `~/.tmux.conf` (except the duplicated `terminal-overrides` entry) and that `herdr config check` answers `ok`.

Still to check from the real client: pasting into a Windows application what was copied in Herdr (only Windows Terminal's acceptance of the OSC 52 remains unconfirmed), how the wheel or touchpad feels in Windows Terminal, the `[`, `%` and `"` keys with the user's keyboard layout, and the complete SSH chain.

### Checks on the destination server

Review versions and state:

```sh
herdr --version
tmux -V
herdr status server
herdr config check
herdr integration status
tmux show-options -g prefix
tmux show-options -g mouse
tmux show-options -s set-clipboard
tmux list-keys -T root WheelUpPane
tmux list-keys -T root WheelDownPane
tmux list-keys -T copy-mode-vi WheelUpPane
tmux list-clients -F '#{client_termname} #{client_termfeatures}'
```

The last line shows, per client, the capabilities tmux detected; `clipboard` appears for `xterm*` terminals (`terminal-features`). If it does not appear, check the `Ms` capability of the *client's* terminal, not of `$TERM` inside tmux (which is tmux's own entry): `tmux info | grep -w Ms` from an attached client, or `infocmp -x "$(tmux display -p '#{client_termname}')" | grep -o 'Ms=[^,]*'`. tmux forwards OSC 52 when `set-clipboard` is `on` and `Ms` exists through either route. The definitive test is still pasting in the local terminal.

Also check the effective settings of the session in use, because it may have its own options overriding the global ones:

```sh
tmux show-options -A mouse
tmux show-options -A prefix
```

In the shell that launches `herdr` on the server:

```sh
printf 'SSH_CONNECTION=%s SSH_TTY=%s\n' "${SSH_CONNECTION:-}" "${SSH_TTY:-}"
```

One of the two must have a value: Herdr prefers OSC 52 when it sees `SSH_CONNECTION` or `SSH_TTY` (also on WSL or VS Code). Without them, for example in a tmux started by systemd or in a shell created before connecting over SSH, it tries `wl-copy` or `xclip` before OSC 52 and the copy may stay on the server.

In a new Herdr shell pane, generate test text:

```sh
seq 1 300
```

Check the wheel in both directions, selection, pasting into a local application, tabs, splits and focus. Run each command in the test shell, not inside the prompt of an agent that is working.

To investigate agents:

```sh
herdr pane list
herdr agent list
```

Copy a real ID from `herdr pane list` and use it in `herdr pane process-info --pane REAL_ID`. If the visible process is `tmux`, there is still a tmux inside that pane.

## Server adaptation and maintenance

The receiving agent must check the shell, the versions, the terminal type and the connection chain. If tmux exists both on the local client and on the remote server, both layers can intervene in the keyboard, the mouse and the clipboard.

Topology with tmux on both ends: `Ctrl+b` is captured by the outermost tmux, that is, the local one. For `Ctrl+b` to control the server's tmux, run `ssh` from a shell that is not inside the local tmux — `Ctrl+b` → `d` detaches to the plain shell the tab started with, or open a Windows Terminal tab whose command is `wsl.exe -e env NO_TMUX=1 zsh` (setting `NO_TMUX=1` inside an existing tmux does not remove that outer layer) — or press `Ctrl+b` `Ctrl+b` (the first is consumed by the local one and the second reaches the remote), or give the local tmux another prefix. The same applies to `Ctrl+a` if Herdr runs on both sides. For the mouse and the clipboard, every tmux layer needs `mouse on` and `set-clipboard on`; with `set-clipboard on`, any program that writes to the terminal can set the clipboard and create tmux buffers, a requirement of this route worth knowing ([tmux: clipboard, security concerns](https://github.com/tmux/tmux/wiki/Clipboard#security-concerns)).

If over SSH the arrows or Alt combinations arrive split, change `set -g escape-time 0` to `set -s escape-time 50` on the server and test again. Apply in this order: packages and binaries → configuration files → Herdr integrations → `herdr config check` → reloads (`tmux source-file`, `herdr server reload-config`) → new shells.

The color settings and `default-terminal` must match the server's terminal and terminfo database. Visual and notification settings can be adapted to the environment; the essential changes for this workflow are the separate prefixes, the wheel forwarding, the clipboard and the `HERDR_ENV` condition.

On this machine, `~/dotfiles` works by copy: `install.sh` copies the repository into `$HOME`, with a backup first, and `save.sh` does the opposite. Since 24 October 2026, `shell/zshrc`, `shell/tmux.conf`, `config/herdr/config.toml`, `docs/herdr-tmux-config.md` (this document) and `tools/herdr-tmux-audit/` match the active files; `git -C ~/dotfiles log -3` shows the commits, which are not published without the user's confirmation. The repository tracks Claude Code's own hooks (`claude/hooks/`) and `claude/settings.json`, but `save.sh` removes the Herdr hook entry because `herdr integration install claude` writes it again on every machine with its absolute path and does not recognise a rewritten entry: after `install.sh`, run `herdr integration install claude` and `herdr integration install codex`, as its README says (`bootstrap.sh` already does). When changing these files, run `save.sh` or copy the specific file before deploying.

If Herdr is not on the server: `curl -fsSL https://herdr.dev/install.sh | sh` installs it in `~/.local/bin` without sudo or prompts (it needs `curl` and `awk`); `brew install herdr` also exists. `~/dotfiles/bootstrap.sh` includes that step, the Codex install and both integrations, and `install.sh` restores `~/.config/herdr/config.toml`; if a Herdr server is already running, run `herdr server reload-config` afterwards. The installer downloads the latest published version; this guide was verified with 0.9.5, and to pin that version download its binary from the GitHub releases.

To carry the configuration over, use the text settings and install the integrations on the destination. Sockets and pane or session IDs belong to the process and machine that created them. The tests in `~/herdr-tmux-audit/` can be copied to the server; they assume zsh, the `Ctrl+a` prefix, Python 3 and an installed Codex (or `AUDIT_SKIP_CODEX=1`).

## Instruction for the agent doing the adaptation

```text
Read this document and adapt my server to use tmux as the outer environment
and Herdr to organize the agents, keeping my existing configuration.

I want Ctrl+b for tmux and Ctrl+a for Herdr, with no double prefix. I want to
move with prefix and arrows, split with % and double quotes, switch tabs with
n and p, use the wheel over the right pane, and copy text to the clipboard of
the terminal I connect from.

Inspect versions, shell, active files, dotfiles and the SSH chain before
editing. Merge the necessary settings and keep the customizations that are
unrelated. Adapt colors to the real environment and use delivery = "herdr"
unless the server has a notification service.

Prevent the shell's auto-start from creating another tmux inside Herdr.
Run the agents directly in Herdr panes, migrate any that are still inside
another tmux, and review their integrations. Keep the existing sessions
during the adaptation.

Check that the shell launching herdr has SSH_CONNECTION or SSH_TTY, and that
every tmux layer has set-clipboard on and a client terminal with the Ms
capability (clipboard in tmux list-clients, or Ms in tmux info); then confirm
with a real paste on my side.

Test keyboard, mouse, scrolling, copying and reloading in an isolated
session; you can adapt ~/herdr-tmux-audit/run_checks.py. Verify that tmux
keeps working outside Herdr. The clipboard test must also cover my client
terminal and any local tmux.

Reload tmux and apply Herdr with herdr server reload-config; Ctrl+a Shift+r
is only needed in each client when its local settings change.
Deliver the modified files, the final shortcuts, the test results and any
step that depends on my terminal or my current sessions.
```
