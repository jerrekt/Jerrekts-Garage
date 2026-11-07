#!/usr/bin/env bash
# Install or update the garage bot inside the garage container (CT 170). Run as root there.
# Safe to run again: it pulls, reinstalls requirements, and restarts.
set -euo pipefail
name=garage-bot
user=bot-garage
repo=https://github.com/jerrekt/Jerrekts-Garage
branch="${GARAGE_BRANCH:-main}"

id -u "$user" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$user"
install -d -o root -g root -m 0755 "/opt/$name"
install -d -o "$user" -g "$user" -m 0700 "/var/lib/$name"
install -d -o root -g root -m 0700 "/etc/$name"
[ -f "/etc/$name/bot.env" ] || install -o root -g root -m 0600 /dev/null "/etc/$name/bot.env"

if [ -d "/opt/$name/src/.git" ]; then
  git -C "/opt/$name/src" fetch -q --depth 1 origin "$branch"
  git -C "/opt/$name/src" checkout -q -B "$branch" FETCH_HEAD
else
  git clone -q --depth 1 -b "$branch" "$repo" "/opt/$name/src"
fi
[ -x "/opt/$name/venv/bin/pip" ] || python3 -m venv "/opt/$name/venv"
"/opt/$name/venv/bin/pip" install -q -r "/opt/$name/src/bot/requirements.txt"
"/opt/$name/venv/bin/python" -m py_compile "/opt/$name/src/bot/app.py"

install -o root -g root -m 0644 "/opt/$name/src/deploy/$name.service" "/etc/systemd/system/$name.service"
systemctl daemon-reload
systemctl enable -q "$name"
systemctl restart "$name"
sleep 2
echo "health: $(curl -s 127.0.0.1:8703/health || echo FAILED)"
systemctl --no-pager --lines=5 status "$name" | sed -n '1,8p'
echo "env keys set: $(grep -c '=.' /etc/$name/bot.env || true) (fill /etc/$name/bot.env from deploy/bot.env.example)"
