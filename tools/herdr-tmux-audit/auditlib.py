#!/usr/bin/env python3
"""Isolated Herdr/tmux audit harness.

Chain under test (all private to SP, nothing touches the live servers):

    harness tmux (-L harness)  = synthetic outer terminal (Windows Terminal stand-in)
      └─ tmux client, TERM=xterm-256color
         └─ audit tmux (-L audit, config = the real ~/.tmux.conf, read-only)
            └─ zsh (real ~/.zshrc) → herdr (config = byte-identical copy of the real config)
               └─ zsh panes (real ~/.zshrc)

Input enters exactly like terminal input: bytes are written to the synthetic
terminal's pty with `send-keys -H`. Raw terminal output is logged with
`pipe-pane -O`, so OSC 52 can be decoded where Windows Terminal would see it.

Isolation: TMUX_TMPDIR, XDG_CONFIG_HOME and HERDR_CONFIG_PATH point into the
audit root (SP); every HERDR_*/TMUX* variable inherited from a live Herdr pane is
removed. Every spawned process carries AUDIT_RUN_ID so teardown can find
leftovers without ever matching a live process.

Environment knobs:
  HERDR_AUDIT_ROOT    audit root; default: a new temp dir. Keep it short: Unix
                      socket paths under it must stay within 107 characters.
                      Set it to reuse one root across the step-by-step CLI below.
  HERDR_AUDIT_PROMPT  text that marks a ready zsh prompt (default: the
                      robbyrussell arrow).
"""
import base64
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid
from pathlib import Path

SP = Path(os.environ.get('HERDR_AUDIT_ROOT') or tempfile.mkdtemp(prefix='herdr-audit.'))
PROMPT = os.environ.get('HERDR_AUDIT_PROMPT', '➜')
X = SP / 'x'                      # XDG_CONFIG_HOME for the isolated Herdr
T = SP / 't'                      # TMUX_TMPDIR for every isolated tmux server
HCONF = X / 'herdr' / 'config.toml'
OUT = SP / 'run'
RAW = OUT / 'terminal-output.bin'
HARNESS_CONF = SP / 'harness.tmux.conf'
RUN_ID_FILE = SP / 'run-id'
HOME = Path.home()
REAL_HCONF = HOME / '.config/herdr/config.toml'
REAL_TMUX_CONF = HOME / '.tmux.conf'
HERDR = shutil.which('herdr') or str(HOME / '.local/bin/herdr')
ZSH = shutil.which('zsh') or '/usr/bin/zsh'
MARKER = SP / '.herdr-audit-root'   # proves this directory was created by the harness
COLS, ROWS = 140, 45

STRIP_PREFIXES = ('HERDR_', 'HC_', 'TMUX', 'CLAUDE', 'TERM_PROGRAM')
STRIP_EXACT = {'NO_TMUX', 'COLORTERM'}


def run_id():
    SP.mkdir(parents=True, exist_ok=True)
    if not RUN_ID_FILE.exists():
        RUN_ID_FILE.write_text(uuid.uuid4().hex)
    return RUN_ID_FILE.read_text().strip()


def make_env():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(STRIP_PREFIXES) and k not in STRIP_EXACT}
    env.update(
        TMUX_TMPDIR=str(T),
        XDG_CONFIG_HOME=str(X),
        XDG_STATE_HOME=str(SP / 'state'),   # Herdr keeps agent-detection/client state here
        XDG_CACHE_HOME=str(SP / 'cache'),
        XDG_DATA_HOME=str(SP / 'data'),
        HERDR_CONFIG_PATH=str(HCONF),
        TERM='xterm-256color',
        SHELL=ZSH,
        HISTFILE=str(SP / 'zsh_history.test'),
        SSH_AUTH_SOCK=os.path.realpath(os.environ.get('SSH_AUTH_SOCK', '/nonexistent')),
        NO_SSH_AGENT='1',   # a test shell must never start or adopt the real shared agent
        AUDIT_RUN_ID=run_id(),
    )
    return env


ENV = make_env()


def sh(args, check=True, timeout=20, env=None):
    r = subprocess.run(args, env=env or ENV, text=True, capture_output=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f'{args!r} -> {r.returncode}: {r.stderr.strip()} {r.stdout.strip()}')
    return r


def ta(*a, check=True):
    return sh(['tmux', '-L', 'audit', *a], check=check)


def th(*a, check=True):
    return sh(['tmux', '-L', 'harness', '-f', str(HARNESS_CONF), *a], check=check)


def herdr(*a, check=True, timeout=20):
    return sh([HERDR, *a], check=check, timeout=timeout)


def hj(*a, timeout=20):
    d = json.loads(herdr(*a, timeout=timeout).stdout)
    if 'error' in d:
        raise RuntimeError(d['error'])
    return d['result']


def snap():
    return hj('api', 'snapshot')['snapshot']


def wait_for(pred, what, timeout=15, interval=0.15):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        try:
            last = pred()
            if last:
                return last
        except (RuntimeError, KeyError, ValueError, IndexError, StopIteration) as exc:
            last = f'{type(exc).__name__}: {exc}'
        time.sleep(interval)
    raise AssertionError(f'timeout waiting for {what}; last={last!r}')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- input
KEYS = {
    'C-a': b'\x01', 'C-b': b'\x02', 'C-c': b'\x03', 'C-d': b'\x04', 'C-u': b'\x15', 'C-y': b'\x19',
    'Enter': b'\r', 'Esc': b'\x1b', 'Tab': b'\t', 'Space': b' ', 'BSpace': b'\x7f',
    'Left': b'\x1b[D', 'Right': b'\x1b[C', 'Up': b'\x1b[A', 'Down': b'\x1b[B',
    'PgUp': b'\x1b[5~', 'PgDn': b'\x1b[6~',
}


def inject(data, pause=0.25):
    """Write raw bytes to the synthetic terminal's input (one write per call)."""
    th('send-keys', '-t', 'h:0.0', '-H', *[f'{b:02x}' for b in data])
    time.sleep(pause)


def keys(*names, pause=0.35, gap=0.12):
    for n in names:
        inject(KEYS.get(n, n.encode()), pause=gap)
    time.sleep(pause)


def typ(text, enter=True, pause=0.35):
    inject(text.encode() + (b'\r' if enter else b''), pause=pause)


def mouse(code, x, y, release=False, pause=0.06):
    inject(f'\x1b[<{code};{x};{y}{"m" if release else "M"}'.encode(), pause=pause)


def wheel(direction, n, x, y):
    for _ in range(n):
        mouse(64 if direction == 'up' else 65, x, y, pause=0.08)
    time.sleep(0.3)


def drag(x1, y1, x2, y2):
    mouse(0, x1, y1)
    for x in range(x1 + 1, x2 + 1):
        mouse(32, x, y2, pause=0.03)
    mouse(0, x2, y2, release=True, pause=0.4)


# ---------------------------------------------------------------- output
def term_screen():
    """What the synthetic outer terminal shows (incl. the audit tmux status line)."""
    return th('capture-pane', '-p', '-t', 'h:0.0').stdout.split('\n')


def outer_pane_screen(target='audit:0.0'):
    return ta('capture-pane', '-p', '-t', target).stdout.split('\n')


def _cells(s):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else (0 if unicodedata.combining(c) else 1) for c in s)


def find_on_terminal(token):
    """1-based (x, y) terminal cell of the first occurrence of token."""
    for r, line in enumerate(term_screen()):
        i = line.find(token)
        if i >= 0:
            return _cells(line[:i]) + 1, r + 1
    return None


def raw():
    return RAW.read_bytes() if RAW.exists() else b''


OSC52 = re.compile(rb'\x1b\]52;([^;\x07\x1b]*);([A-Za-z0-9+/=]*)(?:\x07|\x1b\\)')


def osc52_since(offset=0):
    return [(m.group(1).decode(), base64.b64decode(m.group(2)).decode('utf-8', 'replace'))
            for m in OSC52.finditer(raw()[offset:])]


def outer(fmt, target='audit:0.0'):
    return ta('display-message', '-p', '-t', target, fmt).stdout.strip()


# ---------------------------------------------------------------- herdr helpers
def pane(pane_id):
    return next(p for p in snap()['panes'] if p['pane_id'] == pane_id)


def proc_info(pane_id):
    return hj('pane', 'process-info', '--pane', pane_id)['process_info']


def shell_pids():
    return {p['pane_id']: proc_info(p['pane_id'])['shell_pid'] for p in snap()['panes']}


def proc_env(pid):
    return dict(e.split(b'=', 1) for e in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in e)


def alive(pid):
    try:
        os.kill(pid, 0)
        return Path(f'/proc/{pid}/stat').read_text().split()[2] != 'Z'
    except (ProcessLookupError, FileNotFoundError):
        return False


def pane_text(pane_id, lines=60):
    return herdr('pane', 'read', pane_id, '--lines', str(lines)).stdout


# ---------------------------------------------------------------- live fingerprint (read-only)
def live_fp():
    """Fingerprint of the LIVE servers, read-only. A list is an observation ([] = server confirmed
    absent); None means the query itself failed (permissions, connection) and is unverifiable."""
    real = dict(os.environ)
    real.pop('TMUX_TMPDIR', None)

    def tmux_q(*args):
        r = subprocess.run(['tmux', *args], env=real, text=True, capture_output=True)
        if r.returncode == 0:
            return sorted(x for x in r.stdout.split('\n') if x)
        return [] if 'no server running' in r.stderr else None

    try:
        r = subprocess.run([HERDR, 'pane', 'list'], env=real, text=True, capture_output=True)
        hp = json.loads(r.stdout)
        if 'error' in hp:
            herdr_panes = [] if 'not running' in json.dumps(hp['error']).replace('_', ' ') else None
        else:
            herdr_panes = sorted((p['pane_id'], p['terminal_id']) for p in hp['result']['panes'])
    except (ValueError, KeyError, TypeError, OSError):
        herdr_panes = None
    return {
        'tmux_panes': tmux_q('list-panes', '-a', '-F', '#{session_name}:#{window_index}.#{pane_index} #{pane_pid}'),
        'tmux_clients': tmux_q('list-clients', '-F', '#{client_tty} #{client_pid} #{session_name}'),
        'herdr_panes': herdr_panes,
    }


# ---------------------------------------------------------------- lifecycle
def under_root(path):
    root = os.path.realpath(SP)
    return os.path.commonpath([root, os.path.realpath(path)]) == root


def isolated_socket():
    """The Herdr socket the isolated env resolves to, or None when it is not under SP."""
    st = herdr('status', check=False).stdout
    m = re.search(r'socket: (\S+)', st)
    return m.group(1) if m and under_root(m.group(1)) else None


def assert_isolated():
    st = herdr('status', check=False).stdout
    m = re.search(r'socket: (\S+)', st)
    if not m or not under_root(m.group(1)):
        raise SystemExit(f'REFUSING: isolated env resolves Herdr socket {m.group(1) if m else "<none>"} outside {SP}')
    return st


def prepare_root():
    """Make SP safe to (re)use: refuse foreign directories and live leftovers, then clear our own state."""
    SP.mkdir(parents=True, exist_ok=True)
    entries = {p.name for p in SP.iterdir()} - {RUN_ID_FILE.name}
    if not MARKER.exists() and entries:
        raise SystemExit(f'REFUSING: {SP} is not empty and was not created by this harness (no {MARKER.name})')
    if MARKER.exists():
        left = [p for p in marked_pids() if alive(p)]
        servers = [n for n in ('audit', 'harness', 'default') if sh(['tmux', '-L', n, 'has-session'], check=False).returncode == 0]
        if left or servers:
            raise SystemExit(f'REFUSING: a previous run is still alive (pids {left}, tmux {servers}); run `auditlib.py teardown` first')
    for d in (X, T, OUT, SP / 'state', SP / 'cache', SP / 'data'):
        shutil.rmtree(d, ignore_errors=True)
    for f in (RUN_ID_FILE, SP / 'zsh_history.test', HARNESS_CONF):
        f.unlink(missing_ok=True)
    MARKER.write_text('created by herdr-tmux-audit; safe to delete\n')


def setup():
    longest = X / 'herdr' / 'herdr-client.sock'
    if len(str(longest)) > (107 if sys.platform.startswith('linux') else 103):  # sun_path minus NUL
        raise SystemExit(f'audit root too long for Unix sockets ({len(str(longest))} chars): set a shorter HERDR_AUDIT_ROOT')
    for d in (X / 'herdr', T, OUT):
        d.mkdir(parents=True, exist_ok=True)
    os.chmod(T, 0o700)
    if sh(['tmux', '-L', 'audit', 'has-session'], check=False).returncode == 0:
        raise SystemExit('audit tmux already running; run teardown first')
    shutil.copyfile(REAL_HCONF, HCONF)
    assert sha(HCONF) == sha(REAL_HCONF)
    HARNESS_CONF.write_text('set -g status off\nset -s escape-time 0\nset -s set-clipboard on\n')
    RAW.write_bytes(b'')
    pre = assert_isolated()
    if 'status: running' in pre:
        raise SystemExit('an isolated Herdr server is already running; run teardown first')
    ta('-f', str(REAL_TMUX_CONF), 'new-session', '-d', '-s', 'audit', '-x', str(COLS), '-y', str(ROWS))
    th('new-session', '-d', '-s', 'h', '-x', str(COLS), '-y', str(ROWS),
       'sleep 0.5; exec env -u TMUX -u TMUX_PANE TERM=xterm-256color tmux -L audit attach -t audit')
    th('pipe-pane', '-O', '-t', 'h:0.0', f"cat >> '{RAW}'")
    wait_for(lambda: ta('list-clients', '-F', '#{client_tty}').stdout.strip(), 'synthetic client attach')
    wait_for(lambda: PROMPT in ta('capture-pane', '-p', '-t', 'audit:0.0').stdout, 'zsh prompt in outer tmux', 20)
    typ('herdr')
    wait_for(lambda: snap()['panes'], 'isolated Herdr API', 20)
    wait_for(lambda: outer('#{mouse_any_flag}') == '1', 'Herdr requesting mouse events')
    post = assert_isolated()
    return pre, post


def marked_pids():
    rid = f'AUDIT_RUN_ID={run_id()}'.encode()
    pids = []
    for p in Path('/proc').iterdir():
        if p.name.isdigit() and int(p.name) != os.getpid():
            try:
                if rid in (p / 'environ').read_bytes().split(b'\0'):
                    pids.append(int(p.name))
            except (PermissionError, FileNotFoundError, ProcessLookupError):
                pass
    return pids


def teardown():
    # Only stop a Herdr server whose socket is inside SP; never one the env resolved elsewhere.
    if isolated_socket():
        herdr('server', 'stop', check=False)
    for name in ('audit', 'harness', 'default', 'inner'):
        if under_root(T):
            sh(['tmux', '-L', name, 'kill-server'], check=False)
    time.sleep(1)
    left = marked_pids()
    for pid in left:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(0.5)
    for pid in marked_pids():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return left


# ---------------------------------------------------------------- CLI for step-by-step exploration
def main(argv):
    cmd, *rest = argv or ['help']
    if cmd == 'setup':
        prepare_root()
        pre, post = setup()
        print(post)
    elif cmd == 'teardown':
        print('leftover marked pids killed:', teardown(), '| remaining:', marked_pids())
    elif cmd == 'keys':
        keys(*rest)
    elif cmd == 'type':
        typ(rest[0], enter=(len(rest) < 2 or rest[1] != 'noenter'))
    elif cmd == 'screen':
        print('\n'.join(term_screen() if (rest or ['term'])[0] == 'term' else outer_pane_screen()))
    elif cmd == 'snap':
        print(json.dumps(snap(), indent=1))
    elif cmd == 'herdr':
        print(herdr(*rest, check=False).stdout)
    elif cmd == 'ta':
        r = ta(*rest, check=False)
        print(r.stdout, r.stderr)
    elif cmd == 'osc52':
        print(osc52_since(int(rest[0]) if rest else 0))
    elif cmd == 'rawlen':
        print(len(raw()))
    elif cmd == 'wheel':
        wheel(rest[0], int(rest[1]), int(rest[2]), int(rest[3]))
    elif cmd == 'drag':
        drag(*map(int, rest))
    elif cmd == 'find':
        print(find_on_terminal(rest[0]))
    elif cmd == 'livefp':
        print(json.dumps(live_fp(), indent=1))
    elif cmd == 'pids':
        print(json.dumps({k: [v, alive(v)] for k, v in shell_pids().items()}))
    elif cmd == 'marked':
        print(marked_pids())
    else:
        print(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
