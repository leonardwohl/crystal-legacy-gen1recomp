#!/usr/bin/env bash
# Commit the regenerated mod feed(s) under site/ back to main (used by CI).
#   tools/commit_feed.sh "<commit message>"
set -euo pipefail
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add site
if git diff --cached --quiet; then
  echo "feed unchanged"
  exit 0
fi
git commit -q -m "$1"
# Another push may have landed meanwhile: replay this commit on top of it.
for attempt in 1 2 3; do
  if git pull -q --rebase origin main && git push -q origin HEAD:main; then
    echo "feed pushed"
    exit 0
  fi
  sleep $((attempt * 5))
done
echo "could not push the feed" >&2
exit 1
