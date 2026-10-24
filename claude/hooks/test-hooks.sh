#!/usr/bin/env bash
# Self-test for the custom Claude Code hooks in this directory. Runs in throwaway git repos
# under a temp dir; never touches your real journals (ALTAIRUM_JOURNAL_DIR is overridden).
#   bash ~/.claude/hooks/test-hooks.sh
set -u
HOOKS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export ALTAIRUM_JOURNAL_DIR="$TMP/journals"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
export GIT_AUTHOR_NAME=test GIT_AUTHOR_EMAIL=test@example.com GIT_COMMITTER_NAME=test GIT_COMMITTER_EMAIL=test@example.com
pass=0; fail=0
ok()   { pass=$((pass+1)); printf 'PASS %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf 'FAIL %s\n     got: %s\n' "$1" "$2"; }

json() { python3 -c 'import json,sys; print(json.dumps({"tool_name": sys.argv[1], "tool_input": json.loads(sys.argv[2])}))' "$1" "$2"; }
decision() {  # decision <hook> <tool> <tool_input json>  -> "deny" | "allow"
  json "$2" "$3" > "$TMP/input.json"          # a file, not a pipe: hooks may exit before reading stdin
  out="$(bash "$HOOKS/$1" < "$TMP/input.json")"
  case "$out" in *'"permissionDecision":"deny"'*) echo deny ;; *) echo allow ;; esac
}
expect() {    # expect <deny|allow> <label> <hook> <tool> <tool_input json>
  got="$(decision "$3" "$4" "$5")"
  [ "$got" = "$1" ] && ok "$2" || bad "$2" "$got"
}

mkrepo() {    # mkrepo <dir> <origin-url> <branch>
  git init -q -b main "$1" && git -C "$1" remote add origin "$2" && git -C "$1" commit -q --allow-empty -m init \
    && git -C "$1" checkout -q -b "$3" || { echo "test setup failed for $1" >&2; exit 2; }
}
mkrepo "$TMP/altairum" "git@github.com:AlirioDS/altairum.git" "feature/ui+copy"
mkrepo "$TMP/other"    "git@github.com:someone/other-rails-app.git" "feature/ui+copy"

echo "--- merge-push-deny.sh (feature branch)"
cd "$TMP/altairum"
expect allow "push a feature branch"                   merge-push-deny.sh Bash '{"command":"git push origin feature/ui+copy"}'
expect deny  "push main"                               merge-push-deny.sh Bash '{"command":"git push origin main"}'
expect deny  "push quoted refspec to main"             merge-push-deny.sh Bash '{"command":"git push origin \"HEAD:refs/heads/main\""}'
expect deny  "push HEAD:development"                   merge-push-deny.sh Bash '{"command":"git push origin HEAD:development"}'
expect deny  "push -u origin main && more"             merge-push-deny.sh Bash '{"command":"git push -u origin main && echo done"}'
expect allow "push maintenance (not main)"             merge-push-deny.sh Bash '{"command":"git push origin maintenance"}'
expect allow "push development-preview (not trunk)"    merge-push-deny.sh Bash '{"command":"git push origin development-preview"}'
expect allow "push feature/main-page"                  merge-push-deny.sh Bash '{"command":"git push origin feature/main-page"}'
expect deny  "gh pr merge"                             merge-push-deny.sh Bash '{"command":"gh pr merge 42 --squash"}'
expect allow "unrelated command"                       merge-push-deny.sh Bash '{"command":"ls -la"}'
expect allow "multi-line command without push"         merge-push-deny.sh Bash '{"command":"echo a\necho main"}'
git checkout -q main
expect deny  "any push from trunk branch"              merge-push-deny.sh Bash '{"command":"git push"}'
git checkout -q "feature/ui+copy"

echo "--- journal-scaffold.sh / journal-surface.sh / prototype-gate.sh"
cd "$TMP/other"
bash "$HOOKS/journal-scaffold.sh" </dev/null >/dev/null
[ -z "$(ls -A "$ALTAIRUM_JOURNAL_DIR" 2>/dev/null)" ] && ok "scaffold ignores a non-Altairum repo" || bad "scaffold ignores a non-Altairum repo" "$(ls "$ALTAIRUM_JOURNAL_DIR")"

cd "$TMP/altairum"
bash "$HOOKS/journal-scaffold.sh" </dev/null >/dev/null
[ -f "$ALTAIRUM_JOURNAL_DIR/feature-ui-copy.md" ] && ok "scaffold writes the sanitized slug feature-ui-copy.md" || bad "scaffold slug" "$(ls "$ALTAIRUM_JOURNAL_DIR")"

# the Altairum journal now exists for this branch name: another repo on the same branch must not inherit its gate
cd "$TMP/other"
expect allow "gate ignores a non-Altairum repo on the same branch name" prototype-gate.sh Edit '{"file_path":"app/views/home/index.html.erb"}'
cd "$TMP/altairum"
surf="$(bash "$HOOKS/journal-surface.sh" </dev/null)"
case "$surf" in *"Active journal: feature/ui+copy"*) ok "surface finds the journal through the same slug" ;; *) bad "surface finds the journal" "$surf" ;; esac
expect deny  "gate denies a view edit without a prototype"  prototype-gate.sh Edit '{"file_path":"app/views/home/index.html.erb"}'
expect allow "gate ignores non-visual files"                prototype-gate.sh Edit '{"file_path":"app/models/user.rb"}'
sed -i 's|^prototype:.*|prototype: skip: trivial copy change|' "$ALTAIRUM_JOURNAL_DIR/feature-ui-copy.md"
expect allow "gate allows once prototype: skip is set"      prototype-gate.sh Edit '{"file_path":"app/views/home/index.html.erb"}'
ALTAIRUM_PROTOTYPE_GATE=off expect allow "gate kill-switch" prototype-gate.sh Edit '{"file_path":"app/views/home/index.html.erb"}'

echo; echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
