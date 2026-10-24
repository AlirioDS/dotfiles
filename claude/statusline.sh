#!/usr/bin/env bash
# ~/.claude/statusline.sh
# Claude Code status line — cyberpunk neon edition (responsive 1-or-2 lines)

input=$(cat)

# ─── Cyberpunk neon palette (256-color) ───
NEON_YELLOW='\033[38;5;226m'   # #FCEE0A — labels
HOT_PINK='\033[38;5;198m'      # #FF003C — values
NEON_CYAN='\033[38;5;51m'      # #00F0FF — separators / model
NEON_MAGENTA='\033[38;5;201m'  # #FF00FF — branch / vim
NEON_GREEN='\033[38;5;46m'     # matrix green — low ctx
NEON_ORANGE='\033[38;5;208m'   # warning amber
NEON_RED='\033[38;5;196m'      # critical
DIM='\033[2m'
BOLD='\033[1m'
RESET='\033[0m'

# ─── Parse JSON via Python (single process) ───
parsed=$(python3 -c '
import json, sys
d = json.loads(sys.stdin.read() or "{}")

def g(*path):
    cur = d
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return ""
        cur = cur[k]
    return "" if cur is None else str(cur)

print(g("workspace", "current_dir") or g("cwd"))
print(g("model", "display_name"))
print(g("context_window", "used_percentage"))
print(g("vim", "mode"))
print(g("output_style", "name"))
print(g("terminal", "width"))
print(g("cost", "total_cost_usd"))
' <<< "$input")

{ IFS= read -r cwd
  IFS= read -r model
  IFS= read -r used_pct
  IFS= read -r vim_mode
  IFS= read -r style_name
  IFS= read -r term_width
  IFS= read -r session_cost
} <<< "$parsed"

# ─── Detect terminal width (JSON → COLUMNS → stty → tput → 80) ───
tw=0
[ -n "$term_width" ] && [ "$term_width" -gt 0 ] 2>/dev/null && tw="$term_width"
[ "$tw" -le 0 ] && [ -n "$COLUMNS" ] && [ "$COLUMNS" -gt 0 ] 2>/dev/null && tw="$COLUMNS"
[ "$tw" -le 0 ] && tw=$( (stty size </dev/tty | awk '{print $2}') 2>/dev/null )
[ -z "$tw" ] || [ "$tw" -le 0 ] 2>/dev/null && tw=$(tput cols 2>/dev/null)
[ -z "$tw" ] || [ "$tw" -le 0 ] 2>/dev/null && tw=80
budget=$((tw - 2))   # margin for UI chrome

# ─── Working dir + git ───
[ -z "$cwd" ] && cwd="$(pwd)"
display_dir="${cwd/#$HOME/\~}"
dir_base=$(basename "$display_dir")

branch=""
if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  branch=$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null \
           || git -C "$cwd" rev-parse --short HEAD 2>/dev/null)
fi

# ─── Model variants ───
model_short="${model#Claude }"

# ─── Context % integer (used) + bar color ───
pct_int=""
[ -n "$used_pct" ] && pct_int=$(awk -v p="$used_pct" 'BEGIN { printf "%d", p + 0.5 }')

ctx_color="$DIM"
if [ -n "$used_pct" ]; then
  if   awk -v p="$used_pct" 'BEGIN { exit !(p < 50) }';  then ctx_color="$NEON_GREEN"
  elif awk -v p="$used_pct" 'BEGIN { exit !(p < 80) }';  then ctx_color="$NEON_YELLOW"
  elif awk -v p="$used_pct" 'BEGIN { exit !(p < 95) }';  then ctx_color="$NEON_ORANGE"
  else                                                        ctx_color="$NEON_RED"
  fi
fi

# ─── Bar renderers ───
render_bar() {
  local total="$1" pct="$2"
  local filled empty
  filled=$(awk -v p="$pct" -v t="$total" 'BEGIN { f = int(p*t/100 + 0.5); if (f<0) f=0; if (f>t) f=t; print f }')
  empty=$((total - filled))
  printf "%b" "$ctx_color"
  for ((i=0; i<filled; i++)); do printf "▰"; done
  printf "%b" "$DIM"
  for ((i=0; i<empty; i++));  do printf "▱"; done
  printf "%b" "$RESET"
}
plain_bar() {
  local total="$1"
  local s=""
  for ((i=0; i<total; i++)); do s="${s}▰"; done
  printf '%s' "$s"
}

# ─── Usage tracking via ccusage daily (cached, background refresh) ───
# Pinned: an unpinned `npx -y ccusage` would download and run whatever is latest on every refresh.
CCUSAGE_VERSION=20.0.43
# Per-user private directory (XDG_RUNTIME_DIR is 0700) instead of a predictable shared /tmp path.
USAGE_DIR="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}"
USAGE_CACHE="${USAGE_DIR%/}/claude-statusline-usage-${USER}.json"
USAGE_TTL=30  # seconds
TODAY=$(date +%Y%m%d)

cache_age=999999
if [ -f "$USAGE_CACHE" ]; then
  cache_mtime=$(stat -c %Y "$USAGE_CACHE" 2>/dev/null || stat -f %m "$USAGE_CACHE" 2>/dev/null || echo 0)
  cache_age=$(( $(date +%s) - cache_mtime ))
fi

# Refresh in background if missing or stale (don't block status line).
# flock -n: several agents rendering status lines at once share one refresh instead of racing.
if [ "$cache_age" -gt "$USAGE_TTL" ]; then
  ( flock -n 9 || exit 0
    npx -y "ccusage@${CCUSAGE_VERSION}" daily --json --since "$TODAY" >"${USAGE_CACHE}.tmp" 2>/dev/null \
    && mv "${USAGE_CACHE}.tmp" "$USAGE_CACHE" ) 9>"${USAGE_CACHE}.lock" >/dev/null 2>&1 </dev/null &
  disown 2>/dev/null
fi

# Read today's totals + sonnet from cache
today_total=""
sonnet_total=""
if [ -f "$USAGE_CACHE" ]; then
  read -r today_total sonnet_total < <(python3 -c '
import json
try:
    with open("'"$USAGE_CACHE"'") as f:
        d = json.load(f)
    total = d.get("totals", {}).get("totalCost", 0) or 0
    sonnet = 0
    daily = d.get("daily", [])
    if daily:
        for b in daily[0].get("modelBreakdowns", []):
            if "sonnet" in b.get("modelName", "").lower():
                sonnet += b.get("cost", 0) or 0
    print(f"{total:.2f}", f"{sonnet:.2f}")
except Exception:
    print("", "")
' 2>/dev/null)
fi

# Format session cost (current session $)
session_str=""
if [ -n "$session_cost" ]; then
  session_str=$(awk -v c="$session_cost" 'BEGIN { printf "%.2f", c }')
fi

SEP_C=" ${NEON_CYAN}▮${RESET} "
SEP_P=" ▮ "

# ─── Location segment builders (tier 1 = richest, 4 = leanest) ───
loc_plain() {
  local s
  case "$1" in
    1) s="DIR ${display_dir}"
       [ -n "$branch" ] && s="${s}${SEP_P}GIT ❯ ${branch}" ;;
    2) s="${display_dir}"
       [ -n "$branch" ] && s="${s}${SEP_P}❯ ${branch}" ;;
    3) s="${dir_base}"
       [ -n "$branch" ] && s="${s}${SEP_P}❯ ${branch}" ;;
    4) s="${dir_base}" ;;
  esac
  printf '%s' "$s"
}
loc_color() {
  local s
  case "$1" in
    1) s="${NEON_YELLOW}${BOLD}DIR${RESET} ${HOT_PINK}${display_dir}${RESET}"
       [ -n "$branch" ] && s="${s}${SEP_C}${NEON_YELLOW}${BOLD}GIT${RESET} ${NEON_MAGENTA}❯ ${branch}${RESET}" ;;
    2) s="${HOT_PINK}${display_dir}${RESET}"
       [ -n "$branch" ] && s="${s}${SEP_C}${NEON_MAGENTA}❯ ${branch}${RESET}" ;;
    3) s="${HOT_PINK}${dir_base}${RESET}"
       [ -n "$branch" ] && s="${s}${SEP_C}${NEON_MAGENTA}❯ ${branch}${RESET}" ;;
    4) s="${HOT_PINK}${dir_base}${RESET}" ;;
  esac
  printf '%b' "$s"
}

# ─── AI/CTX segment builders (tier 1 = richest, 5 = leanest) ───
ai_plain() {
  local s=""
  case "$1" in
    1) [ -n "$model" ] && s="AI ${model}"
       [ -n "$pct_int" ] && { [ -n "$s" ] && s="${s}${SEP_P}"; s="${s}CTX $(plain_bar 10) ${pct_int}%"; } ;;
    2) [ -n "$model" ] && s="${model}"
       [ -n "$pct_int" ] && { [ -n "$s" ] && s="${s}${SEP_P}"; s="${s}$(plain_bar 10) ${pct_int}%"; } ;;
    3) [ -n "$model_short" ] && s="${model_short}"
       [ -n "$pct_int" ] && { [ -n "$s" ] && s="${s}${SEP_P}"; s="${s}$(plain_bar 8) ${pct_int}%"; } ;;
    4) [ -n "$model_short" ] && s="${model_short}"
       [ -n "$pct_int" ] && { [ -n "$s" ] && s="${s}${SEP_P}"; s="${s}$(plain_bar 5) ${pct_int}%"; } ;;
    5) [ -n "$model_short" ] && s="${model_short}"
       [ -n "$pct_int" ] && { [ -n "$s" ] && s="${s} "; s="${s}${pct_int}%"; } ;;
  esac
  printf '%s' "$s"
}
ai_color() {
  local s=""
  case "$1" in
    1) [ -n "$model" ] && s="${NEON_YELLOW}${BOLD}AI${RESET} ${NEON_CYAN}${model}${RESET}"
       [ -n "$pct_int" ] && { [ -n "$s" ] && s="${s}${SEP_C}"; s="${s}${NEON_YELLOW}${BOLD}CTX${RESET} $(render_bar 10 "$used_pct") ${HOT_PINK}${pct_int}%${RESET}"; } ;;
    2) [ -n "$model" ] && s="${NEON_CYAN}${model}${RESET}"
       [ -n "$pct_int" ] && { [ -n "$s" ] && s="${s}${SEP_C}"; s="${s}$(render_bar 10 "$used_pct") ${HOT_PINK}${pct_int}%${RESET}"; } ;;
    3) [ -n "$model_short" ] && s="${NEON_CYAN}${model_short}${RESET}"
       [ -n "$pct_int" ] && { [ -n "$s" ] && s="${s}${SEP_C}"; s="${s}$(render_bar 8 "$used_pct") ${HOT_PINK}${pct_int}%${RESET}"; } ;;
    4) [ -n "$model_short" ] && s="${NEON_CYAN}${model_short}${RESET}"
       [ -n "$pct_int" ] && { [ -n "$s" ] && s="${s}${SEP_C}"; s="${s}$(render_bar 5 "$used_pct") ${HOT_PINK}${pct_int}%${RESET}"; } ;;
    5) [ -n "$model_short" ] && s="${NEON_CYAN}${model_short}${RESET}"
       [ -n "$pct_int" ] && { [ -n "$s" ] && s="${s} "; s="${s}${ctx_color}${BOLD}${pct_int}%${RESET}"; } ;;
  esac
  printf '%b' "$s"
}

# ─── Usage segment builders (tier 1 richest, 3 leanest) ───
# Shows: SES $X (session) ▮ TODAY $X (all models today) ▮ SONNET $X (sonnet today)
usage_plain() {
  local s=""
  case "$1" in
    1) [ -n "$session_str"  ] && s="SES \$${session_str}"
       [ -n "$today_total"  ] && { [ -n "$s" ] && s="${s}${SEP_P}"; s="${s}TODAY \$${today_total}"; }
       [ -n "$sonnet_total" ] && { [ -n "$s" ] && s="${s}${SEP_P}"; s="${s}SONNET \$${sonnet_total}"; }
       ;;
    2) [ -n "$session_str"  ] && s="\$${session_str} ses"
       [ -n "$today_total"  ] && { [ -n "$s" ] && s="${s}${SEP_P}"; s="${s}\$${today_total} all"; }
       [ -n "$sonnet_total" ] && { [ -n "$s" ] && s="${s}${SEP_P}"; s="${s}\$${sonnet_total} sn"; }
       ;;
    3) [ -n "$session_str"  ] && s="\$${session_str}"
       [ -n "$today_total"  ] && { [ -n "$s" ] && s="${s}/"; s="${s}\$${today_total}"; }
       [ -n "$sonnet_total" ] && { [ -n "$s" ] && s="${s}/"; s="${s}\$${sonnet_total}"; }
       ;;
  esac
  printf '%s' "$s"
}
usage_color() {
  local s=""
  case "$1" in
    1) [ -n "$session_str"  ] && s="${NEON_YELLOW}${BOLD}SES${RESET} ${NEON_GREEN}\$${session_str}${RESET}"
       [ -n "$today_total"  ] && { [ -n "$s" ] && s="${s}${SEP_C}"; s="${s}${NEON_YELLOW}${BOLD}TODAY${RESET} ${HOT_PINK}\$${today_total}${RESET}"; }
       [ -n "$sonnet_total" ] && { [ -n "$s" ] && s="${s}${SEP_C}"; s="${s}${NEON_YELLOW}${BOLD}SONNET${RESET} ${NEON_CYAN}\$${sonnet_total}${RESET}"; }
       ;;
    2) [ -n "$session_str"  ] && s="${NEON_GREEN}\$${session_str}${RESET}${DIM} ses${RESET}"
       [ -n "$today_total"  ] && { [ -n "$s" ] && s="${s}${SEP_C}"; s="${s}${HOT_PINK}\$${today_total}${RESET}${DIM} all${RESET}"; }
       [ -n "$sonnet_total" ] && { [ -n "$s" ] && s="${s}${SEP_C}"; s="${s}${NEON_CYAN}\$${sonnet_total}${RESET}${DIM} sn${RESET}"; }
       ;;
    3) [ -n "$session_str"  ] && s="${NEON_GREEN}\$${session_str}${RESET}"
       [ -n "$today_total"  ] && { [ -n "$s" ] && s="${s}${DIM}/${RESET}"; s="${s}${HOT_PINK}\$${today_total}${RESET}"; }
       [ -n "$sonnet_total" ] && { [ -n "$s" ] && s="${s}${DIM}/${RESET}"; s="${s}${NEON_CYAN}\$${sonnet_total}${RESET}"; }
       ;;
  esac
  printf '%b' "$s"
}

join_plain() {  # $1 loc, $2 ai
  if [ -n "$1" ] && [ -n "$2" ]; then printf '%s%s%s' "$1" "$SEP_P" "$2"
  else printf '%s%s' "$1" "$2"; fi
}
join_color() {
  if [ -n "$1" ] && [ -n "$2" ]; then printf '%b%s%b' "$1" "$SEP_C" "$2"
  else printf '%b%b' "$1" "$2"; fi
}

# Has any usage data?
has_usage=0
[ -n "$session_str" ] || [ -n "$today_total" ] || [ -n "$sonnet_total" ] && has_usage=1

# ─── Line 1 (location + AI/CTX) ───
full_plain=$(join_plain "$(loc_plain 1)" "$(ai_plain 1)")

line1_color=""
if [ "${#full_plain}" -le "$budget" ]; then
  line1_color=$(join_color "$(loc_color 1)" "$(ai_color 1)")
  line1_extra=""
else
  lt=4
  for t in 1 2 3 4; do
    lp=$(loc_plain $t); [ "${#lp}" -le "$budget" ] && { lt=$t; break; }
  done
  at=5
  for t in 1 2 3 4 5; do
    ap=$(ai_plain $t); [ "${#ap}" -le "$budget" ] && { at=$t; break; }
  done
  line1_color=$(loc_color $lt)
  line1_extra=$(ai_color $at)
fi

# ─── Line 2 (usage — only if data available) ───
line2_color=""
if [ "$has_usage" -eq 1 ]; then
  ut=3
  for t in 1 2 3; do
    up=$(usage_plain $t); [ "${#up}" -le "$budget" ] && { ut=$t; break; }
  done
  line2_color=$(usage_color $ut)
fi

# ─── Final output ───
if [ -n "$line1_extra" ]; then
  # location + AI/CTX split into 2 lines already
  if [ -n "$line2_color" ]; then
    printf "%b\n%b\n%b" "$line1_color" "$line1_extra" "$line2_color"
  else
    printf "%b\n%b" "$line1_color" "$line1_extra"
  fi
else
  # location + AI/CTX on 1 line
  if [ -n "$line2_color" ]; then
    printf "%b\n%b" "$line1_color" "$line2_color"
  else
    printf "%b" "$line1_color"
  fi
fi
