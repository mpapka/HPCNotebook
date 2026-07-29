#!/usr/bin/env bash
# ============================================================================
# publish.sh — release lab notebook(s) to students, in one step.
#
# Does BOTH halves of a weekly rollout:
#   1. Copies the named notebook(s) + current labHelpers.py onto the `release`
#      branch (what nbgitpuller pulls into each student's ~/HPCNotebook).
#   2. Flips `published: true` on the matching course-site lab card and pushes
#      the site, so the Labs page lists only labs that are actually available.
#
# The .md docs, this script, and unreleased labs never touch `release`, so
# students only ever get what you have published.
#
#   ./publish.sh lab01                 # accepts lab01, lab01SerialBaseline, or a filename
#   ./publish.sh lab01 lab02           # several at once
#   ./publish.sh --list                # show what is currently on release
#
# Develop/test on `main` (test agents test main). A dedicated worktree
# (../HPCNotebook-release) is used so your main checkout is never disturbed.
# Course-site checkout defaults to ../UIC_Course_Website; override with
# COURSE_SITE_DIR. If the site is absent, the card step is skipped.
# ============================================================================
set -euo pipefail
REPO="$(git -C "$(dirname "$(readlink -f "$0")")" rev-parse --show-toplevel)"
WT="${REPO}-release"
SITE="${COURSE_SITE_DIR:-$(dirname "$REPO")/UIC_Course_Website}"

git -C "$REPO" fetch -q origin release 2>/dev/null || true
if ! git -C "$REPO" worktree list --porcelain | grep -qx "worktree $WT"; then
  git -C "$REPO" worktree add -q "$WT" release 2>/dev/null \
    || git -C "$REPO" worktree add -q -B release "$WT" origin/release 2>/dev/null \
    || {
         # First-ever release: create an orphan release branch with just labHelpers.py
         git -C "$REPO" worktree add -q --detach "$WT"
         git -C "$WT" checkout -q --orphan release
         git -C "$WT" rm -rfq . 2>/dev/null || true
       }
fi
git -C "$WT" checkout -q release 2>/dev/null || true
git -C "$WT" reset -q --hard origin/release 2>/dev/null || true
git -C "$WT" clean -fdq            # worktree == release exactly; no stray untracked files

if [ "${1:-}" = "--list" ]; then
  echo "On release now (students get these):"; git -C "$WT" ls-files; exit 0
fi
[ "$#" -ge 1 ] || { echo "usage: $0 <lab> [lab ...]   e.g.  $0 lab01"; exit 1; }

# --- 1. put the notebook(s) + current toolkit on the release branch ---
git -C "$WT" checkout main -- labHelpers.py
files=()
for lab in "$@"; do
  f="$(git -C "$REPO" ls-files "${lab}*.ipynb" | head -1)"
  [ -n "$f" ] || { echo "no notebook on main matches '$lab'"; exit 1; }
  git -C "$WT" checkout main -- "$f"
  files+=("$f"); echo "  + $f"
done
git -C "$WT" add -- labHelpers.py "${files[@]}"   # explicit: never sweep in stray files
if git -C "$WT" diff --cached --quiet; then
  echo "release already current for: $*"
else
  git -C "$WT" commit -q -m "release: publish $*"
  git -C "$WT" push -q origin release
  echo "published to release: $*"
fi

# --- 2. reveal the matching site card(s) so the Labs page lists only released labs ---
if [ -d "$SITE/_labs" ]; then
  changed=0
  for f in "${files[@]}"; do
    card="$(grep -rl "file: \"$f\"" "$SITE/_labs" 2>/dev/null | head -1)"
    [ -n "$card" ] || { echo "  (no site card references $f)"; continue; }
    if grep -q '^published:' "$card"; then sed -i 's/^published:.*/published: true/' "$card"
    else sed -i '/^file:/a published: true' "$card"; fi
    echo "  revealed card: $(basename "$card")"
  done
  if ! git -C "$SITE" diff --quiet -- _labs; then
    git -C "$SITE" add _labs
    git -C "$SITE" commit -q -m "Labs: reveal card(s) for $*"
    echo "  pushing site (builds + deploys via pre-push hook) ..."
    git -C "$SITE" push 2>&1 | grep -vE 'dependabot|vulnerabilit|^remote:( |$)' | tail -4 || true
  else
    echo "  site cards already current."
  fi
else
  echo "  (course site not at $SITE; skipped card reveal -- set COURSE_SITE_DIR)"
fi
echo "done. students get it on their next Launch (nbgitpuller fast-forwards)."
