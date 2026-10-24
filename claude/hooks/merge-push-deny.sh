#!/usr/bin/env bash
# PreToolUse(Bash): the agent must never merge a PR or push to trunk.
# Human override: run '! gh pr merge ...' in your own shell (bypasses the AI tool layer).
# Pure bash (no jq). ALWAYS exits 0.
set +e
input="$(cat | tr '\n' ' ')"
cmd="$(printf '%s' "$input" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
[ -z "$cmd" ] && exit 0
deny(){ printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$1"; exit 0; }

case "$cmd" in
  *"gh pr merge"*) deny "The agent must not merge PRs. Merge on GitHub, or run '! gh pr merge ...' in your own shell (project rule: the human controls merges)." ;;
esac

case "$cmd" in
  *"git push"*)
    branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
    { [ "$branch" = "main" ] || [ "$branch" = "development" ]; } && deny "Refusing to push from trunk ($branch). Push a feature/fix/hotfix branch; trunk advances only via merged PRs."
    # Refspec targets match only at word end (":main"/":main <flags>") so
    # ":maintenance" / ":development-preview" stay allowed; refs/heads/ forms
    # are word-end anchored the same way (refs/heads/development-preview allowed).
    case "$cmd" in
      *" main"*|*" development"*|*:main|*":main "*|*:development|*":development "*|*refs/heads/main|*"refs/heads/main "*|*refs/heads/development|*"refs/heads/development "*)
        deny "Refusing to push directly to trunk (main/development). Open a PR instead." ;;
    esac
    ;;
esac
exit 0
