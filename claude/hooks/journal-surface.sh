#!/usr/bin/env bash
# SessionStart hook: surface the current branch's work-journal header into context.
# Safe by design: no-ops outside Altairum, on trunk/detached branches, or with no journal.
# ALWAYS exits 0 — a failing SessionStart hook must never break session start.
set +e

JOURNAL_DIR="${ALTAIRUM_JOURNAL_DIR:-$HOME/.claude/altairum-journals}"

# 1. Altairum guard — origin remote must reference AlirioDS/altairum
case "$(git remote get-url origin 2>/dev/null)" in
  *AlirioDS/altairum|*AlirioDS/altairum.git) ;;
  *) exit 0 ;;
esac

# 2. Current branch — skip trunk & detached HEAD
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
case "$branch" in
  ""|HEAD|development|main) exit 0 ;;
esac

# 3. Locate journal (same slug rule as journal-scaffold.sh and prototype-gate.sh:
#    '/' -> '-', then every other character outside [a-zA-Z0-9._-] -> '-')
slug="$(printf '%s' "$branch" | sed 's#/#-#g; s#[^a-zA-Z0-9._-]#-#g')"
journal="$JOURNAL_DIR/${slug}.md"
[ -f "$journal" ] || exit 0

# 4. Read ONLY the YAML header (between the first two '---' lines)
header="$(awk '/^---[[:space:]]*$/{c++; next} c==1{print} c>=2{exit}' "$journal")"
field() { printf '%s\n' "$header" | sed -n "s/^$1:[[:space:]]*//p" | head -1; }
status="$(field status)"; updated="$(field updated)"
next="$(field next)"; next="${next%\"}"; next="${next#\"}"

# 5. Emit a compact factual block (stdout reaches the model for SessionStart)
printf 'Active journal: %s (%s, updated %s).\n' "$branch" "${status:-unknown}" "${updated:-?}"
[ -n "$next" ] && printf 'Next action: %s\n' "$next"
printf 'Run /pickup for the full journal.\n'
exit 0
