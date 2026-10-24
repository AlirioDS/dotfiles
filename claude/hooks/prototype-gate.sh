#!/usr/bin/env bash
# PreToolUse(Edit|Write|MultiEdit): block edits to visual files until the branch journal registers a prototype.
# Fail-OPEN on missing journal / kill-switch / other repositories. No jq: python3 decodes the hook JSON
# (sed fallback when python3 is missing). ALWAYS exits 0.
set +e
[ "${ALTAIRUM_PROTOTYPE_GATE:-on}" = "off" ] && exit 0

# Altairum guard, same as journal-scaffold.sh: another repository on a branch with the same
# name must not inherit this gate through the shared journal directory.
case "$(git remote get-url origin 2>/dev/null)" in
  *AlirioDS/altairum|*AlirioDS/altairum.git) ;; *) exit 0 ;;
esac

input="$(cat)"
if command -v python3 >/dev/null 2>&1; then
  file="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    pass')"
else
  file="$(printf '%s' "$input" | tr '\n' ' ' | sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
fi
[ -z "$file" ] && exit 0

case "$file" in
  */app/views/*|app/views/*|*/app/javascript/*|app/javascript/*|*/app/assets/stylesheets/*|app/assets/stylesheets/*) ;;
  *) exit 0 ;;
esac

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
slug="$(printf '%s' "$branch" | sed 's#/#-#g; s#[^a-zA-Z0-9._-]#-#g')"
journal="${ALTAIRUM_JOURNAL_DIR:-$HOME/.claude/altairum-journals}/${slug}.md"
[ -f "$journal" ] || exit 0   # fail-open: scaffold hasn't run / pre-harness branch

proto="$(awk -F': *' '/^prototype:/{print $2; exit}' "$journal" | tr -d '[:space:]')"
[ -n "$proto" ] && exit 0     # registered (path or skip:...) -> allow

reason="This edits a screen ($file) but no prototype is registered for branch '$branch'. Make a prototype first (use /frontend-design, save to .prototypes/$slug/), then set prototype: <path> in the journal -- or prototype: skip: <reason> for a trivial diff."
printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$reason"
exit 0
