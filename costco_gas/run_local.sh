#!/bin/zsh
# Local launchd entry point. Pulls latest, runs the fetcher, commits + pushes
# any data changes. Mirrors the GitHub Actions job in pages.yml so the two can
# coexist (push-triggered deploy still happens on the GH side).
set -u

REPO="/Users/rradhakrishnan/projects/utils"
VENV_PY="$REPO/costco_gas/.venv/bin/python"
LOG="$HOME/Library/Logs/costco_gas.log"

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1

echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') ====="

# Make ssh-agent / Keychain SSH key available to git push under launchd.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export SSH_AUTH_SOCK="${SSH_AUTH_SOCK:-/private/tmp/com.apple.launchd.$(id -u)/Listeners}"

cd "$REPO" || { echo "cd failed"; exit 1; }

branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" != "main" ]]; then
  echo "Skip: not on main (current: $branch)"
  exit 0
fi

# Pull latest so the GH Actions hourly run doesn't conflict on push.
git pull --rebase --autostash || { echo "git pull failed"; exit 1; }

"$VENV_PY" costco_gas/fetch_data.py
fetch_rc=$?
if [[ $fetch_rc -ne 0 ]]; then
  echo "fetch_data.py exited $fetch_rc"
  exit $fetch_rc
fi

git add costco_gas/pwa/data costco_gas/zip_cache.json
if git diff --staged --quiet; then
  echo "No data changes to commit."
  exit 0
fi

git commit -m "chore(costco-gas): local snapshot $(date -u +%Y-%m-%dT%H:%MZ)" \
  && git push
