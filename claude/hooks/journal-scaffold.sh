#!/usr/bin/env bash
# SessionStart hook: scaffold a work-journal skeleton for a new feature/fix/hotfix/docs/chore branch.
# Idempotent; no-ops on trunk, existing journal, or outside Altairum. ALWAYS exits 0. Emits no stdout.
set +e
JOURNAL_DIR="${ALTAIRUM_JOURNAL_DIR:-$HOME/.claude/altairum-journals}"

case "$(git remote get-url origin 2>/dev/null)" in
  *AlirioDS/altairum|*AlirioDS/altairum.git) ;; *) exit 0 ;;
esac

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
case "$branch" in feature/*|fix/*|hotfix/*|docs/*|chore/*) ;; *) exit 0 ;; esac

slug="$(printf '%s' "$branch" | sed 's#/#-#g; s#[^a-zA-Z0-9._-]#-#g')"
journal="$JOURNAL_DIR/${slug}.md"
[ -f "$journal" ] && exit 0

mkdir -p "$JOURNAL_DIR"
today="$(date +%F)"
cat > "$journal" <<EOF
---
branch: $branch
status: in_progress
updated: $today
next: "TBD — set with /save"
prototype:
gates:                  # hash each gate last PASSED at (blank = never ran; n/a = not applicable; waived: <reason>)
  simplify:
  ci_check:
  code_review:
  e2e_claude:
  e2e_user:
goal: "TBD"
---
# ${branch}

## Goal
TBD

## Decisions locked
-

## Done ✅

## In progress 🔨

## Left ⬜

## ▶ NEXT ACTION
TBD

## Blockers
- none
EOF
exit 0
