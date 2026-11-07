#!/usr/bin/env bash
# Public page: nginx on 127.0.0.1:8080 serving /opt/garage-bot/src/public, plus the tunnel
# ingress for jerrekts-garage.adsuaracloud.com. Run as root inside the garage container,
# after install.sh. Safe to run again.
set -euo pipefail
host=jerrekts-garage.adsuaracloud.com
src=/opt/garage-bot/src
cfg=/etc/cloudflared/config.yml

[ -d "$src/public" ] || { echo "no $src/public: run install.sh first (branch with the public/ folder)"; exit 1; }
command -v nginx >/dev/null || { apt-get -qq update && DEBIAN_FRONTEND=noninteractive apt-get -qq install -y nginx-light; }

install -o root -g root -m 0644 "$src/deploy/nginx-garage.conf" /etc/nginx/sites-available/garage
ln -sfn /etc/nginx/sites-available/garage /etc/nginx/sites-enabled/garage
rm -f /etc/nginx/sites-enabled/default
nginx -t -q
systemctl enable -q nginx
systemctl restart nginx

if [ -f "$cfg" ] && ! grep -q "hostname: $host" "$cfg"; then
  cp -a "$cfg" "$cfg.bak.$(date +%s)"
  # insert the new hostname above the catch-all 404 rule
  awk -v h="$host" '/service: http_status:404/ && !done {print "  - hostname: " h; print "    service: http://127.0.0.1:8080"; done=1} {print}' "$cfg" > "$cfg.new"
  mv "$cfg.new" "$cfg"; chmod 600 "$cfg"
  cloudflared tunnel ingress validate
  systemctl restart cloudflared
fi

# auto-update timer: pulls from GitHub when the branch moved
install -o root -g root -m 0755 "$src/deploy/garage-update.sh" /usr/local/sbin/garage-update
install -o root -g root -m 0644 "$src/deploy/garage-update.service" /etc/systemd/system/garage-update.service
install -o root -g root -m 0644 "$src/deploy/garage-update.timer" /etc/systemd/system/garage-update.timer
[ -f /etc/garage-bot/branch ] || echo main > /etc/garage-bot/branch
systemctl daemon-reload
systemctl enable -q --now garage-update.timer

sleep 1
echo "auto-update: $(systemctl is-active garage-update.timer) every 10 min, branch $(cat /etc/garage-bot/branch)"
echo "local page: $(curl -s -o /dev/null -w '%{http_code}' -H "Host: $host" 127.0.0.1:8080/)"
echo "local api:  $(curl -s -H "Host: $host" 127.0.0.1:8080/api/public | head -c 80)"
echo "ingress:    $(grep -c "hostname: $host" "$cfg" 2>/dev/null || echo 0) rule(s) for $host"
echo "DNS: if $host is not routed yet, run (then delete the cert):"
echo "  cloudflared tunnel login && cloudflared tunnel route dns garage $host && rm -f /root/.cloudflared/cert.pem"
