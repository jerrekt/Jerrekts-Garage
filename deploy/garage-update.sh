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
# service logs in data/logs/*.json: import the ones that changed (idempotent, only replaces imported rows)
admin=$(sed -n 's/^GARAGE_ADMIN_ID=//p' /etc/garage-bot/bot.env); aname=$(sed -n 's/^GARAGE_ADMIN_NAME=//p' /etc/garage-bot/bot.env)
install -d -o bot-garage -g bot-garage -m 0700 /var/lib/garage-bot/imported
for f in "$src"/data/logs/*.json; do
  [ -f "$f" ] || continue
  sum=$(sha256sum "$f" | cut -c1-16); mark="/var/lib/garage-bot/imported/$(basename "$f" .json).sha"
  [ "$(cat "$mark" 2>/dev/null)" = "$sum" ] && continue
  runuser -u bot-garage -- env GARAGE_DB=/var/lib/garage-bot/garage.db "/opt/garage-bot/venv/bin/python" "$src/bot/import_log.py" "$f" --owner-id "$admin" --owner-name "${aname:-Jerrekt}" | head -1 \
    && echo "$sum" | runuser -u bot-garage -- tee "$mark" >/dev/null
done
if ! cmp -s "$src/deploy/nginx-garage.conf" /etc/nginx/sites-available/garage; then
  install -o root -g root -m 0644 "$src/deploy/nginx-garage.conf" /etc/nginx/sites-available/garage && nginx -t -q && systemctl reload nginx
fi
if ! cmp -s "$src/deploy/garage-update.sh" /usr/local/sbin/garage-update; then
  install -o root -g root -m 0755 "$src/deploy/garage-update.sh" /usr/local/sbin/garage-update
fi
