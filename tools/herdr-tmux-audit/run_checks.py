#!/usr/bin/env python3
"""Reproducible, isolated audit of the tmux → Herdr → zsh setup.

Replaces the stale /tmp/herdr-check.j3ZAkF harness: it uses the real ~/.tmux.conf
(read-only) and a byte-identical copy of ~/.config/herdr/config.toml, asserts exact
values derived from those files, restores the copy after every mutation, and never
touches the live servers (see auditlib.py). Outputs go to <root>/run/: results.json,
terminal-output.bin, live-before.json, live-after.json, help-overlay.txt and the
isolated Herdr logs.

    python3 run_checks.py                         # fresh temp root, all checks
    HERDR_AUDIT_ROOT=/tmp/ha python3 run_checks.py
    AUDIT_SKIP_CODEX=1 python3 run_checks.py      # skip launching Codex (no prompt is ever sent)
    python3 run_checks.py --only 17,19            # rerun selected checks (01 always runs: it starts the stack)
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

import auditlib as A

RESULTS = []
CHECKS = []
REAL_HISTORY = A.HOME / '.zsh_history'
MARKERS = [b'SCROLL_%03g', b'ONE_PREFIX_ONE_ACTION', b'APPCOPY_OK', b'TAB2_OK', b'OUTER_%03g', b'WS2_SHELL_OK']


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


def ntabs():
    return len(A.snap()['tabs'])


def prefix_creates_tab(pfx):
    n = ntabs()
    A.keys(pfx, 'c', pause=1.0)
    ok = ntabs() > n
    if not ok:
        A.keys('C-u', pause=0.3)  # clear the literal keys that reached zsh
    return ok


def layout(tab):
    s = A.snap()
    lay = next(l for l in s['layouts'] if l['tab_id'] == tab)
    return s['focused_pane_id'], {p['pane_id']: p['rect'] for p in lay['panes']}


def visible_range():
    toks = [int(t) for l in A.outer_pane_screen() for t in re.findall(r'SCROLL_(\d{3})', l)]
    return min(toks), max(toks)


def config_value(key, default):
    m = re.search(rf'^\s*{key}\s*=\s*"?([^"\n]*?)"?\s*$', A.HCONF.read_text(), re.M)
    return m.group(1) if m else default


def scroll_lines():
    return int(config_value('mouse_scroll_lines', '3'))


def with_config(old, new):
    text = A.HCONF.read_text()
    expect(old in text, f'{old!r} not in isolated config')
    A.HCONF.write_text(text.replace(old, new))


def restore_config():
    shutil.copyfile(A.REAL_HCONF, A.HCONF)
    expect(A.sha(A.HCONF) == A.sha(A.REAL_HCONF), 'isolated config differs from active config')


# --------------------------------------------------------------------------- checks
@check('01 isolation: isolated Herdr socket and tmux sockets live under the audit root')
def c01():
    pre, post = A.setup()
    sock = re.search(r'socket: (\S+)', post).group(1)
    expect(sock.startswith(str(A.SP)) and 'status: running' in post, post)
    expect(A.sha(A.HCONF) == A.sha(A.REAL_HCONF), 'config copy not identical')
    expect(config_value('prefix', 'ctrl+b') == 'ctrl+a', 'these checks drive Herdr with ctrl+a')
    feats = A.ta('list-clients', '-F', '#{client_termname} #{client_termfeatures}').stdout.strip()
    expect('clipboard' in feats, feats)
    return f'herdr socket={sock}; synthetic client={feats}'


@check('02 new Herdr shell: HERDR_ENV=1, TMUX unset, no nested tmux')
def c02():
    p = A.snap()['focused_pane_id']
    A.wait_for(lambda: A.PROMPT in '\n'.join(A.outer_pane_screen())
               and [x['name'] for x in A.proc_info(p)['foreground_processes']] == ['zsh'], 'first pane prompt', 20)
    pi = A.proc_info(p)
    env = A.proc_env(pi['shell_pid'])
    fg = [x['name'] for x in pi['foreground_processes']]
    expect(env.get(b'HERDR_ENV') == b'1' and b'TMUX' not in env and b'TMUX_PANE' not in env, env)
    expect(fg == ['zsh'], fg)
    A.typ("printf 'HERDR_ENV=%s TMUX=%s\\n' \"${HERDR_ENV:-}\" \"${TMUX:-}\"", pause=0.8)
    out = [l.split('│')[-1].strip() for l in A.outer_pane_screen() if 'HERDR_ENV=1 TMUX=' in l and 'printf' not in l]
    expect(out == ['HERDR_ENV=1 TMUX='], out)
    dflt = A.sh(['tmux', '-L', 'default', 'ls'], check=False)
    expect(dflt.returncode != 0, 'a tmux server exists on the isolated default socket')
    return f'shell {pi["shell_pid"]} env ok, foreground={fg}, printed {out[0]!r}, no default tmux server'


@check('03 .zshrc guard control: auto-start happens without HERDR_ENV and not with HERDR_ENV=1')
def c03():
    def sessions():
        r = A.sh(['tmux', '-L', 'default', 'ls', '-F', '#{session_name}'], check=False)
        return r.stdout.split() if r.returncode == 0 else []
    A.th('new-window', '-d', '-t', 'h:1', 'env -u TMUX -u TMUX_PANE -u HERDR_ENV zsh -i')
    neg = A.wait_for(sessions, 'auto-started tmux without HERDR_ENV', 20)
    A.sh(['tmux', '-L', 'default', 'kill-server'], check=False)
    A.th('kill-window', '-t', 'h:1', check=False)
    time.sleep(1)
    A.th('new-window', '-d', '-t', 'h:1', 'env -u TMUX -u TMUX_PANE HERDR_ENV=1 zsh -i')
    time.sleep(6)
    pos = sessions()
    A.th('kill-window', '-t', 'h:1', check=False)
    # NO_TMUX (any non-empty value) disables auto-start
    A.th('new-window', '-d', '-t', 'h:1', 'env -u TMUX -u TMUX_PANE -u HERDR_ENV NO_TMUX=1 zsh -i')
    time.sleep(6)
    no_tmux = sessions()
    A.th('kill-window', '-t', 'h:1', check=False)
    # an interactive zsh without a terminal (zsh -ic) must not try to open tmux at all
    r = subprocess.run([A.ZSH, '-ic', 'echo NOTTY_OK'], env=A.ENV, text=True, capture_output=True,
                       stdin=subprocess.DEVNULL, timeout=60)
    notty = ('NOTTY_OK' in r.stdout, 'open terminal failed' in r.stderr, sessions())
    expect(neg == ['0'] and pos == [] and no_tmux == [] and notty == (True, False, []), (neg, pos, no_tmux, notty))
    return (f'without HERDR_ENV -> sessions {neg}; with HERDR_ENV=1 -> {pos}; NO_TMUX=1 -> {no_tmux}; '
            f'zsh -ic without TTY -> ran, no tmux error, sessions {notty[2]}')


@check('03b three shells starting at once each get their own tmux session (no "duplicate session")')
def c03b():
    def sessions():
        r = A.sh(['tmux', '-L', 'default', 'ls', '-F', '#{session_name}'], check=False)
        return sorted(r.stdout.split()) if r.returncode == 0 else []
    cmd = 'env -u TMUX -u TMUX_PANE -u HERDR_ENV zsh -i'
    for idx in (1, 2, 3):
        A.th('new-window', '-d', '-t', f'h:{idx}', cmd)
    A.wait_for(lambda: len(sessions()) == 3, 'three auto-started sessions', 25)
    time.sleep(2)
    inside = [A.th('display', '-p', '-t', f'h:{idx}', '#{pane_current_command}').stdout.strip() for idx in (1, 2, 3)]
    errors = [l for idx in (1, 2, 3) for l in A.th('capture-pane', '-p', '-t', f'h:{idx}').stdout.split('\n')
              if 'duplicate' in l or 'error' in l.lower()]
    A.sh(['tmux', '-L', 'default', 'kill-server'], check=False)
    for idx in (1, 2, 3):
        A.th('kill-window', '-t', f'h:{idx}', check=False)
    time.sleep(1)
    expect(sessions() == [] and inside == ['tmux', 'tmux', 'tmux'] and not errors, (inside, errors))
    return f'sessions 0,1,2 created; every shell ended inside tmux={inside}; errors={errors}'


@check('04 wheel over Herdr: exactly mouse_scroll_lines rows/notch, outer tmux never enters copy mode')
def c04():
    p = A.snap()['focused_pane_id']
    n = scroll_lines()
    A.typ("clear; seq -f 'SCROLL_%03g' 1 300")
    A.wait_for(lambda: A.pane(p)['scroll']['max_offset_from_bottom'] > 200, 'scrollback')
    time.sleep(0.5)
    r0 = visible_range()
    A.wheel('up', 5, 80, 20)
    off, mode, r1 = A.pane(p)['scroll']['offset_from_bottom'], A.outer('#{pane_in_mode}'), visible_range()
    expect(off == 5 * n and mode == '0' and r0[0] - r1[0] == 5 * n, (n, off, mode, r0, r1))
    A.wheel('down', 5, 80, 20)
    back = A.pane(p)['scroll']['offset_from_bottom']
    A.wheel('down', 3, 80, 20)
    extra = A.pane(p)['scroll']['offset_from_bottom']
    expect(back == 0 and extra == 0 and A.outer('#{pane_in_mode}') == '0', (back, extra))
    return f'5 up -> offset {off} (rows {r0}->{r1}), outer in_mode={mode}; 5 down -> {back}; 3 more down -> {extra}'


@check('05 mouse_scroll_lines is honoured (7 -> 35 rows) and restored via Ctrl+a R')
def c05():
    p = A.snap()['focused_pane_id']
    n = scroll_lines()
    with_config(f'mouse_scroll_lines = {n}', 'mouse_scroll_lines = 7')
    A.keys('C-a', 'R', pause=1.0)
    A.wheel('up', 5, 80, 20)
    seven = A.pane(p)['scroll']['offset_from_bottom']
    A.wheel('down', 8, 80, 20)
    restore_config()
    A.keys('C-a', 'R', pause=1.0)
    A.wheel('up', 5, 80, 20)
    three = A.pane(p)['scroll']['offset_from_bottom']
    A.wheel('down', 8, 80, 20)
    expect(seven == 35 and three == 5 * n, (seven, three))
    return f'7 lines -> {seven}; restored {n} lines -> {three}; config identical to active'


@check('06 mouse drag copy: decoded OSC 52 at the terminal equals the selected text')
def c06():
    token = 'SCROLL_297'
    x, y = A.wait_for(lambda: A.find_on_terminal(token), 'token on screen')
    off = len(A.raw())
    A.drag(x, y, x + len(token) - 1, y)
    time.sleep(0.8)
    osc, buf, term = A.osc52_since(off), A.ta('show-buffer', check=False).stdout, A.th('show-buffer', check=False).stdout
    expect(osc == [('c', token)] and buf == token and term == token, (osc, buf, term))
    expect(A.outer('#{pane_in_mode}') == '0', 'outer tmux entered copy mode')
    return f'OSC 52 at terminal={osc}; tmux buffer={buf!r}; terminal-side decode={term!r}'


@check('07 keyboard copy mode: Ctrl+a [ , ?search, v e y -> decoded OSC 52')
def c07():
    p = A.snap()['focused_pane_id']
    token = 'SCROLL_123'
    A.keys('C-a', '[', pause=0.8)
    status = A.outer_pane_screen()[-2]
    expect('COPY' in status, status)
    off = len(A.raw())
    A.keys('?', pause=0.4)
    A.typ(token, enter=False, pause=0.3)
    A.keys('Enter', pause=0.8)
    scrolled = A.pane(p)['scroll']['offset_from_bottom']
    A.keys('v', 'e', pause=0.5)
    A.keys('y', pause=1.0)
    osc = A.osc52_since(off)
    after = A.pane(p)['scroll']['offset_from_bottom']
    expect(scrolled > 0 and osc == [('c', token)] and after == 0, (scrolled, osc, after))
    return f'COPY legend shown; search scrolled to offset {scrolled}; OSC 52={osc}; y exited to offset {after}'


@check('08 app-generated OSC 52 inside a Herdr pane reaches the terminal')
def c08():
    A.typ('clear', pause=0.5)
    off = len(A.raw())
    A.typ("""printf '\\033]52;c;%s\\007' "$(printf APPCOPY_OK | base64)"; echo SENT""", pause=1.5)
    osc, buf = A.osc52_since(off), A.ta('show-buffer', check=False).stdout
    expect(osc == [('c', 'APPCOPY_OK')] and buf == 'APPCOPY_OK', (osc, buf))
    return f'OSC 52 at terminal={osc}; tmux buffer={buf!r}'


@check('09 tabs: Ctrl+a c (no name prompt), p/n, 1/2')
def c09():
    t1 = A.snap()['focused_tab_id']
    A.keys('C-a', 'c', pause=0.6)
    A.typ('echo TAB2_OK', pause=1.2)
    s = A.snap()
    t2 = s['focused_tab_id']
    reached = 'TAB2_OK' in A.pane_text(s['focused_pane_id'], 4).split('\n')[-3:].__str__()
    moves = []
    for k, want in (('p', t1), ('n', t2), ('1', t1), ('2', t2)):
        A.keys('C-a', k, pause=0.6)
        moves.append(A.snap()['focused_tab_id'] == want)
    expect(len(s['tabs']) == 2 and t2 != t1 and reached and all(moves), (s['tabs'], reached, moves))
    return f'new tab {t2} took typed input immediately; p/n/1/2 -> {moves}'


@check('10 splits and focus: % and v side-by-side, " and - stacked; arrows and h/j/k/l; one prefix = one action')
def c10():
    tab = A.snap()['focused_tab_id']
    p0, _ = layout(tab)
    A.keys('C-a', '%', pause=0.8)
    pr, r = layout(tab)
    side = r[pr]['x'] > r[p0]['x'] and r[pr]['y'] == r[p0]['y'] and r[pr]['height'] == r[p0]['height']
    lr = []
    for k, want in (('Left', p0), ('l', pr), ('h', p0), ('Right', pr)):
        A.keys('C-a', k, pause=0.5)
        lr.append(A.snap()['focused_pane_id'] == want)
    A.keys('C-a', 'h', pause=0.5)
    A.typ('echo ONE_PREFIX_ONE_ACTION', pause=1.0)
    one = 'ONE_PREFIX_ONE_ACTION' in A.pane_text(p0, 4) and 'ONE_PREFIX_ONE_ACTION' not in A.pane_text(pr, 40)
    A.keys('C-a', 'l', pause=0.5)
    A.keys('C-a', '"', pause=0.8)
    pb, r = layout(tab)
    stacked = r[pb]['x'] == r[pr]['x'] and r[pb]['width'] == r[pr]['width'] and r[pb]['y'] > r[pr]['y']
    ud = []
    for k, want in (('Up', pr), ('j', pb), ('k', pr), ('Down', pb)):
        A.keys('C-a', k, pause=0.5)
        ud.append(A.snap()['focused_pane_id'] == want)
    A.keys('C-a', 'v', pause=0.8)
    pv, r = layout(tab)
    v_side = r[pv]['x'] > r[pb]['x'] and r[pv]['y'] == r[pb]['y']
    A.keys('C-a', '-', pause=0.8)
    pm, r = layout(tab)
    m_stack = r[pm]['x'] == r[pv]['x'] and r[pm]['y'] > r[pv]['y']
    expect(side and all(lr) and one and stacked and all(ud) and v_side and m_stack and len(r) == 5,
           (side, lr, one, stacked, ud, v_side, m_stack, len(r)))
    return f'%={side} v={v_side} "={stacked} -={m_stack}; Left/l/h/Right={lr}; Up/j/k/Down={ud}; text after C-a h only in target pane={one}'


@check('11 Ctrl+a Ctrl+a sends a literal Ctrl+a (zsh beginning-of-line)')
def c11():
    p = A.snap()['focused_pane_id']
    A.typ('clear', pause=0.6)
    A.typ('echo LIT', enter=False, pause=0.3)
    A.keys('C-a', 'C-a', pause=0.5)
    A.typ('echo PRE;', pause=1.0)
    out = [l.strip() for l in A.pane_text(p, 8).split('\n') if l.strip()]
    expect('PRE' in out and 'LIT' in out, out)
    return f'line became "echo PRE;echo LIT" -> printed {[o for o in out if o in ("PRE", "LIT")]}'


@check('12 reload: server reload-config alone switches prefix and scroll lines; pane shells keep their PIDs')
def c12():
    pids0 = A.shell_pids()
    with_config('prefix = "ctrl+a"', 'prefix = "ctrl+y"')
    rel = json.loads(A.herdr('server', 'reload-config').stdout)['result']
    time.sleep(1)
    old_ok, new_ok = prefix_creates_tab('C-a'), prefix_creates_tab('C-y')
    restore_config()
    A.keys('C-y', 'R', pause=1.2)                     # client action with the then-active prefix
    back_ok, stale_ok = prefix_creates_tab('C-a'), prefix_creates_tab('C-y')
    A.keys('C-a', '1', pause=0.6)
    p = A.snap()['focused_pane_id']
    A.typ("clear; seq -f 'SCROLL_%03g' 1 300", pause=1.0)
    with_config(f'mouse_scroll_lines = {scroll_lines()}', 'mouse_scroll_lines = 7')
    A.herdr('server', 'reload-config')
    time.sleep(1)
    A.wheel('up', 5, 80, 20)
    seven = A.pane(p)['scroll']['offset_from_bottom']
    A.wheel('down', 8, 80, 20)
    restore_config()
    A.herdr('server', 'reload-config')
    time.sleep(1)
    pids1 = A.shell_pids()
    kept = all(pids1.get(k) == v and A.alive(v) for k, v in pids0.items())
    expect(rel.get('status') == 'applied' and not old_ok and new_ok and back_ok and not stale_ok and seven == 35 and kept,
           (rel, old_ok, new_ok, back_ok, stale_ok, seven, kept))
    return (f'server reload {rel.get("status")}: ctrl+a works={old_ok}, ctrl+y works={new_ok}; after restore + C-y R: '
            f'ctrl+a={back_ok}, ctrl+y={stale_ok}; server reload applied mouse_scroll_lines=7 -> {seven}; '
            f'{len(pids0)} pre-existing shells kept PIDs={kept}')


@check('13 two attached clients: one server reload-config changes the prefix in both')
def c13():
    A.keys('C-b', 'c', pause=1.5)
    A.wait_for(lambda: A.PROMPT in A.ta('capture-pane', '-p', '-t', 'audit:1.0').stdout, 'zsh in outer window 1', 15)
    A.typ('herdr', pause=0.5)
    A.wait_for(lambda: A.outer('#{pane_current_command}', 'audit:1.0') == 'herdr'
               and A.outer('#{mouse_any_flag}', 'audit:1.0') == '1', 'second client', 15)
    with_config('prefix = "ctrl+a"', 'prefix = "ctrl+y"')
    A.herdr('server', 'reload-config')
    time.sleep(1)
    second = prefix_creates_tab('C-y')
    A.keys('C-b', 'p', pause=0.8)
    first = prefix_creates_tab('C-y')
    restore_config()
    A.herdr('server', 'reload-config')
    time.sleep(1)
    first_back = prefix_creates_tab('C-a')
    A.keys('C-b', 'n', pause=0.8)
    second_back = prefix_creates_tab('C-a')
    A.keys('C-a', 'q', pause=1.2)                     # detach client #2
    A.keys('C-b', 'p', pause=0.8)
    expect(first and second and first_back and second_back, (first, second, first_back, second_back))
    return f'ctrl+y active in client#1={first}, client#2={second}; restored ctrl+a in both={first_back and second_back}'


@check('14 detach Ctrl+a q keeps every process; herdr reattaches to the same panes and PIDs')
def c14():
    pids0 = A.shell_pids()
    A.keys('C-a', 'q', pause=1.5)
    cmd = A.outer('#{pane_current_command}')
    running = 'status: running' in A.herdr('status', check=False).stdout
    alive = all(A.alive(v) for v in pids0.values())
    A.typ('herdr', pause=0.5)
    A.wait_for(lambda: A.outer('#{pane_current_command}') == 'herdr' and A.outer('#{mouse_any_flag}') == '1', 'reattach', 15)
    pids1 = A.shell_pids()
    expect(cmd == 'zsh' and running and alive and pids1 == pids0, (cmd, running, alive, pids1 == pids0))
    return f'after C-a q outer pane={cmd}, server running={running}, {len(pids0)} shells alive={alive}; reattach same PIDs={pids1 == pids0}'


@check('15 close: x and X close immediately (busy pane too); Shift+d asks; Esc x2 back; Enter closes')
def c15():
    A.keys('C-a', '%', pause=0.8)
    p = A.snap()['focused_pane_id']
    A.typ('sleep 300', pause=0.8)
    job = A.wait_for(lambda: next((x['pid'] for x in A.proc_info(p)['foreground_processes'] if x['name'] == 'sleep'), None),
                     'sleep in foreground', 15)
    A.keys('C-a', 'x', pause=1.2)
    pane_closed = p not in [x['pane_id'] for x in A.snap()['panes']] and not A.alive(job)
    A.keys('C-a', 'c', pause=0.8)
    A.keys('C-a', '%', pause=0.8)
    s = A.snap()
    tab = s['focused_tab_id']
    victims = [A.proc_info(x['pane_id'])['shell_pid'] for x in s['panes'] if x['tab_id'] == tab]
    A.keys('C-a', 'X', pause=1.2)
    tab_closed = tab not in [t['tab_id'] for t in A.snap()['tabs']] and not any(A.alive(v) for v in victims)
    A.keys('C-a', 'N', pause=1.0)
    s = A.snap()
    ws = s['focused_workspace_id']
    shells = [A.proc_info(x['pane_id'])['shell_pid'] for x in s['panes'] if x['workspace_id'] == ws]
    A.keys('C-a', 'D', pause=1.0)
    dialog = any('Close workspace?' in l for l in A.outer_pane_screen())
    A.keys('Esc', pause=1.5)
    kept = ws in [w['workspace_id'] for w in A.snap()['workspaces']]
    navigate = 'NAVIGATE' in A.outer_pane_screen()[-2]
    A.keys('Esc', pause=1.5)
    A.typ('echo WS2_SHELL_OK', pause=1.0)
    typing = 'WS2_SHELL_OK' in A.pane_text(A.snap()['focused_pane_id'], 3)
    A.keys('C-a', 'D', pause=1.0)
    A.keys('Enter', pause=1.5)
    ws_closed = ws not in [w['workspace_id'] for w in A.snap()['workspaces']] and not any(A.alive(v) for v in shells)
    expect(pane_closed and tab_closed and dialog and kept and navigate and typing and ws_closed,
           (pane_closed, tab_closed, dialog, kept, navigate, typing, ws_closed))
    return (f'x killed busy pane w/o prompt={pane_closed}; X closed tab+shells={tab_closed}; D dialog={dialog}; '
            f'Esc kept ws={kept} but left NAVIGATE mode={navigate}; 2nd Esc -> typing works={typing}; Enter closed ws+shells={ws_closed}')


@check('16 outer tmux: Ctrl+b works over Herdr; ordinary shells scroll in tmux copy mode at the configured step')
def c16():
    m = re.search(r'-N (\d+)', A.ta('list-keys', '-T', 'copy-mode-vi', 'WheelUpPane').stdout)
    step = int(m.group(1)) if m else 1
    wins = lambda: A.ta('list-windows', '-t', 'audit', '-F', '#{window_index}:#{window_active}').stdout.split()
    w = len(wins())
    A.keys('C-b', 'c', pause=1.5)
    created = len(wins()) == w + 1
    idx = [x.split(':')[0] for x in wins() if x.endswith(':1')][0]
    tgt = f'audit:{idx}.0'
    A.wait_for(lambda: A.PROMPT in A.ta('capture-pane', '-p', '-t', tgt).stdout, 'zsh in new outer window', 15)
    A.typ("clear; seq -f 'OUTER_%03g' 1 300", pause=1.2)
    A.wheel('up', 1, 60, 20)
    first = (A.outer('#{pane_in_mode}', tgt), A.outer('#{scroll_position}', tgt))
    A.wheel('up', 4, 60, 20)
    five = (A.outer('#{pane_in_mode}', tgt), A.outer('#{scroll_position}', tgt))
    A.wheel('down', 6, 60, 20)
    exited = A.outer('#{pane_in_mode}', tgt) == '0'
    A.keys('C-b', '0', pause=0.8)
    on_herdr = A.outer('#{window_active}', 'audit:0.0') == '1' and A.outer('#{mouse_any_flag}', 'audit:0.0') == '1'
    sp = A.ta('list-keys', '-T', 'prefix', 'C-b').stdout.strip()
    expect(created and first == ('1', '0') and five == ('1', str(4 * step)) and exited and on_herdr and 'send-prefix' in sp,
           (created, step, first, five, exited, on_herdr, sp))
    return (f'C-b c from Herdr created window={created}; step={step}; 1 notch -> (in_mode, lines)={first}; '
            f'5 notches -> {five}; wheel-down exits={exited}; C-b 0 back on Herdr={on_herdr}; {sp}')


@check('17 Codex launched directly in a Herdr pane is detected and cleared on exit')
def c17():
    if os.environ.get('AUDIT_SKIP_CODEX') == '1':
        return 'SKIPPED by AUDIT_SKIP_CODEX=1'
    A.keys('C-a', 'c', pause=0.8)
    p = A.snap()['focused_pane_id']
    A.typ('cd ~ && clear', pause=0.8)
    A.typ('codex', pause=1.0)
    t0 = time.monotonic()
    found = A.wait_for(lambda: [a for a in A.snap()['agents'] if a.get('pane_id') == p], 'codex detection', 60, 0.5)
    dt = time.monotonic() - t0
    time.sleep(4)
    state = [(a.get('agent'), a.get('agent_status')) for a in A.snap()['agents'] if a.get('pane_id') == p]
    procs = [x['pid'] for x in A.proc_info(p)['foreground_processes']]
    cleared = lambda: not [a for a in A.snap()['agents'] if a.get('pane_id') == p]
    A.keys('Esc', pause=0.8)             # dismiss a startup dialog (e.g. "update available") without choosing anything
    A.keys('C-c', pause=0.6)
    A.keys('C-c', pause=2.0)
    how = 'Ctrl+C x2'
    try:
        A.wait_for(cleared, 'codex cleared', 10)
    except AssertionError:
        A.typ('/exit', pause=0.5)        # Codex slash command; typ() presses Enter
        A.wait_for(cleared, 'codex cleared after /exit', 15)
        how = 'Ctrl+C x2 then /exit'
    gone = not any(A.alive(x) for x in procs)
    expect(found[0]['agent'] == 'codex' and gone, (found, gone))
    return f'detected as {found[0]["agent"]} after {dt:.1f}s, state {state}; {how} -> agent cleared, processes gone={gone}'


@check('18 help overlay lists the effective prefix')
def c18():
    A.keys('C-a', '?', pause=1.2)
    scr = A.outer_pane_screen()
    (A.OUT / 'help-overlay.txt').write_text('\n'.join(scr))
    A.keys('Esc', pause=1.0)
    A.keys('Esc', pause=1.0)
    line = next((l.strip() for l in scr if 'prefix mode' in l), '')
    expect('ctrl+a' in line, line)
    return line.split('│')[-2].strip() if '│' in line else line


@check('19 background agent finishing: delivery="herdr" shows an in-app toast; "system" shows no in-app toast')
def c19():
    delivery = config_value('delivery', 'off')
    ws1 = A.snap()['focused_workspace_id']
    A.keys('C-a', 'N', pause=1.2)
    s = A.snap()
    ws2, p2 = s['focused_workspace_id'], s['focused_pane_id']
    A.hj('workspace', 'focus', ws1)
    time.sleep(0.8)

    def finish_and_look():
        A.wait_for(lambda: not any('finished' in l for l in A.outer_pane_screen()), 'screen without toast', 30, 0.5)
        A.herdr('pane', 'report-agent', '--source', 'audit:toast', '--agent', 'claude', '--state', 'working', p2)
        time.sleep(1.5)
        A.herdr('pane', 'report-agent', '--source', 'audit:toast', '--agent', 'claude', '--state', 'idle', p2)
        end, seen = time.time() + 4, ''
        while time.time() < end and not seen:
            seen = next((l.split('│')[-2].strip() for l in A.outer_pane_screen() if 'finished' in l), '')
            time.sleep(0.2)
        return seen

    configured = finish_and_look()
    with_config(f'delivery = "{delivery}"', 'delivery = "system"')
    A.herdr('server', 'reload-config')
    time.sleep(1)
    system = finish_and_look()
    restore_config()
    A.herdr('server', 'reload-config')
    time.sleep(1)
    A.herdr('pane', 'release-agent', '--source', 'audit:toast', '--agent', 'claude', p2, check=False)
    A.herdr('workspace', 'close', ws2, check=False)
    expect(delivery == 'herdr' and configured and not system, (delivery, configured, system))
    return f'configured delivery={delivery} -> toast {configured!r}; delivery=system -> in-app toast seen={bool(system)}'


# --------------------------------------------------------------------------- main
def history_marks():
    return {m.decode(): REAL_HISTORY.read_bytes().count(m) for m in MARKERS} if REAL_HISTORY.exists() else {}


def main():
    if not sys.platform.startswith('linux'):
        sys.exit('run_checks.py needs Linux (/proc, tmux -L sockets)')
    A.prepare_root()            # refuses foreign directories and live leftovers
    A.OUT.mkdir(parents=True)
    A.ENV.update(A.make_env())
    before = A.live_fp()
    (A.OUT / 'live-before.json').write_text(json.dumps(before, indent=1))
    hist0 = history_marks()
    only = sys.argv[sys.argv.index('--only') + 1].split(',') if '--only' in sys.argv else None
    selected = [(n, f) for n, f in CHECKS
                if only is None or n.startswith('01 ') or any(n.startswith(o + ' ') for o in only)]
    try:
        for name, fn in selected:
            t0 = time.monotonic()
            try:
                ev = fn()
                status = 'skip' if str(ev).startswith('SKIPPED') else 'pass'
                RESULTS.append({'check': name, 'status': status, 'evidence': ev, 'secs': round(time.monotonic() - t0, 1)})
                print(f'{status.upper():<4} {name}\n     {ev}', flush=True)
            except Exception as e:  # keep going; record the failure
                RESULTS.append({'check': name, 'status': 'fail', 'error': f'{type(e).__name__}: {e}',
                                'secs': round(time.monotonic() - t0, 1)})
                print(f'FAIL {name}\n     {type(e).__name__}: {e}', flush=True)
                if name.startswith('01'):
                    break
            finally:
                # a failed check must not leave a mutated config behind for the next one
                if A.HCONF.exists() and A.sha(A.HCONF) != A.sha(A.REAL_HCONF):
                    restore_config()
                    A.herdr('server', 'reload-config', check=False)
                    RESULTS[-1]['config_restored_after_check'] = True
    finally:
        config_identical, artifacts_error = None, None
        try:
            config_identical = A.sha(A.HCONF) == A.sha(A.REAL_HCONF) if A.HCONF.exists() else None
            for log in (A.X / 'herdr').glob('*.log'):
                shutil.copy(log, A.OUT / log.name)
        except Exception as e:  # bookkeeping must never skip the teardown below
            artifacts_error = f'{type(e).__name__}: {e}'
        finally:
            killed = A.teardown()
        after = A.live_fp()
        (A.OUT / 'live-after.json').write_text(json.dumps(after, indent=1))
        hist1 = history_marks()

        def unchanged(key):          # None on either side = the live query failed: say so, do not claim preservation
            return 'unverifiable' if before[key] is None or after[key] is None else before[key] == after[key]

        tp_known = before['tmux_panes'] is not None and after['tmux_panes'] is not None
        cleanup = {
            'isolated_config_identical_to_active_at_end': config_identical,
            'artifacts_error': artifacts_error,
            'marked_processes_after_teardown': A.marked_pids(),
            'marked_processes_killed_by_teardown': killed,
            'live_herdr_panes_unchanged': unchanged('herdr_panes'),
            'live_tmux_clients_unchanged': unchanged('tmux_clients'),
            'live_tmux_panes_all_still_present': set(before['tmux_panes']) <= set(after['tmux_panes']) if tp_known else 'unverifiable',
            'live_tmux_panes_created_by_others_during_run': sorted(set(after['tmux_panes']) - set(before['tmux_panes'])) if tp_known else 'unverifiable',
            'real_zsh_history_marker_counts_unchanged': hist0 == hist1,
        }
        verdicts = [cleanup[k] for k in ('live_herdr_panes_unchanged', 'live_tmux_clients_unchanged',
                                         'live_tmux_panes_all_still_present', 'real_zsh_history_marker_counts_unchanged')]
        cleanup_ok = (config_identical is True and artifacts_error is None
                      and not cleanup['marked_processes_after_teardown'] and False not in verdicts)
        cleanup['unverifiable'] = [k for k, v in cleanup.items() if v == 'unverifiable']
        counts = {s: sum(r['status'] == s for r in RESULTS) for s in ('pass', 'fail', 'skip')}
        summary = {'passed': counts['pass'], 'failed': counts['fail'], 'skipped': counts['skip'],
                   'cleanup_ok': cleanup_ok, 'checks': RESULTS, 'cleanup': cleanup}
        (A.OUT / 'results.json').write_text(json.dumps(summary, indent=1))
        print(f"\n{counts['pass']} passed, {counts['fail']} failed, {counts['skip']} skipped; cleanup ok={cleanup_ok}")
        print('cleanup:', json.dumps(cleanup))
        print('results:', A.OUT / 'results.json')
    if counts['fail'] or not cleanup_ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
