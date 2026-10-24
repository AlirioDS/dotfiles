#!/usr/bin/env bash
# PreToolUse(Bash): the agent must never merge a PR or push to trunk.
# Human override: run '! gh pr merge ...' in your own shell (bypasses the AI tool layer).
# No jq: the hook JSON is decoded with python3 (a quoted command such as
# git push origin "HEAD:refs/heads/main" used to be cut at the first quote by the
# old sed extraction); sed stays as a last resort when python3 is missing. ALWAYS exits 0.
set +e
input="$(cat)"
if command -v python3 >/dev/null 2>&1; then
  cmd="$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    pass')"
else
  cmd="$(printf '%s' "$input" | tr '\n' ' ' | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
fi
[ -z "$cmd" ] && exit 0
deny(){ printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$1"; exit 0; }

case "$cmd" in
  *"gh pr merge"*) deny "The agent must not merge PRs. Merge on GitHub, or run '! gh pr merge ...' in your own shell (project rule: the human controls merges)." ;;
esac

case "$cmd" in
  *"git push"*)
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
    { [ "$branch" = "main" ] || [ "$branch" = "development" ]; } && deny "Refusing to push from trunk ($branch). Push a feature/fix/hotfix branch; trunk advances only via merged PRs."
    # Trunk as a push target: "main"/"development" as a whole word preceded by a space, ':' or '/'
    # (" main", ":main", "HEAD:main", "refs/heads/main", quoted forms) and followed by a space,
    # a quote, a shell separator or the end. "maintenance" and "development-preview" do not match.
    if [[ "$cmd" =~ (^|[[:space:]]|:|/|[\"\'])(main|development)([[:space:]]|[\"\']|\;|\&|\||$) ]]; then
      deny "Refusing to push directly to trunk (main/development). Open a PR instead."
    fi
    ;;
esac
exit 0
