#!/usr/bin/env bash
# Pull the garage from GitHub when it changed. Run by garage-update.timer every 10 minutes.
# Branch comes from /etc/garage-bot/branch (default main). Nothing happens when nothing changed.
set -euo pipefail
src=/opt/garage-bot/src
branch=$(cat /etc/garage-bot/branch 2>/dev/null || echo main)
[ -d "$src/.git" ] || exit 0
before=$(git -C "$src" rev-parse HEAD)
git -C "$src" fetch -q --depth 1 origin "$branch"
after=$(git -C "$src" rev-parse FETCH_HEAD)
[ "$before" = "$after" ] && exit 0
echo "garage: $before -> $after ($branch)"
umask 022
GARAGE_BRANCH="$branch" bash "$src/deploy/install.sh" | grep -E "health|env keys"
chmod -R u=rwX,go=rX "$src"
if ! cmp -s "$src/deploy/nginx-garage.conf" /etc/nginx/sites-available/garage; then
  install -o root -g root -m 0644 "$src/deploy/nginx-garage.conf" /etc/nginx/sites-available/garage && nginx -t -q && systemctl reload nginx
fi
if ! cmp -s "$src/deploy/garage-update.sh" /usr/local/sbin/garage-update; then
  install -o root -g root -m 0755 "$src/deploy/garage-update.sh" /usr/local/sbin/garage-update
fi
