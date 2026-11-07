# Deploying the garage

Everything lives in its own container on Kratos (CT 170 "garage", unprivileged, firewalled),
with the same isolation pattern as the Bricked and Waymo bots:

| Piece | Where |
|---|---|
| Linux user (no login) | `bot-garage` |
| Code (root-owned, read-only to the bot) | `/opt/garage-bot/src` (this repo) |
| Data (only the bot can write) | `/var/lib/garage-bot/garage.db` |
| Secrets (root-only, 0600) | `/etc/garage-bot/bot.env` |
| Bot service | `garage-bot.service`, `127.0.0.1:8703` |
| Site | nginx-light, `127.0.0.1:8080`, serves `public/` and proxies `/api/*` and `/auth/*` to the bot |
| Tunnel `garage` | `jerrekts-garage.adsuaracloud.com` → 8080 (the site), `garage-api.adsuaracloud.com` → 8703 (Discord interactions only) |

One URL for everyone: the public bays need no sign-in; "Sign in with Discord" unlocks your cars.

## Install (inside the container, as root)
    GARAGE_BRANCH=main bash install.sh      # bot: clone or pull, venv, unit, env skeleton, start, health
    bash install-site.sh                    # nginx + tunnel ingress for the site

## Then, by hand
1. `/etc/garage-bot/bot.env`: fill from `bot.env.example` (type secrets in the terminal, never paste them into chat).
   `GARAGE_SITE_TOKEN`: `openssl rand -hex 32`.
2. Discord Developer Portal, application "Jerrekt's Garage":
   - General Information: Public Key → `DISCORD_PUBLIC_KEY`; Interactions Endpoint URL
     `https://garage-api.adsuaracloud.com/discord/interactions` (saves only if the key is right and the bot is up).
   - Installation: Guild install with the `applications.commands` scope; open the install link, add to the server.
   - OAuth2: Client ID → `DISCORD_CLIENT_ID`, Reset Secret → `DISCORD_CLIENT_SECRET`,
     Redirect `https://jerrekts-garage.adsuaracloud.com/auth/callback`.
   - A webhook in the feed channel → `DISCORD_WEBHOOK_URL`.
3. Register the slash commands once, from the container (it has Python and httpx; the bot token is used once, then reset in the portal):
       export DISCORD_APP_ID=<app id> DISCORD_GUILD_ID=<server id>; read -r -s -p "Bot token: " DISCORD_BOT_TOKEN; echo; export DISCORD_BOT_TOKEN
       /opt/garage-bot/venv/bin/python /opt/garage-bot/src/bot/register_commands.py; unset DISCORD_BOT_TOKEN
4. DNS for a new hostname on the tunnel: `cloudflared tunnel login && cloudflared tunnel route dns garage <host>` then `rm -f /root/.cloudflared/cert.pem`.
5. Service logs from the vault: `bot/import_log.py` (see its docstring); idempotent.

## Updating
Automatic: `garage-update.timer` checks GitHub every 10 minutes and, when the branch in
`/etc/garage-bot/branch` (default `main`) moved, pulls, reinstalls requirements, restarts the
bot and reloads nginx if its config changed. Push to that branch and wait ten minutes.
By hand, same thing now: `garage-update` (or `GARAGE_BRANCH=main bash /opt/garage-bot/src/deploy/install.sh`).

Never run these with `umask 077` set in the shell: the checkout inherits it and nginx answers 403. Fix: `chmod -R u=rwX,go=rX /opt/garage-bot/src`.

## Off switch
`systemctl stop garage-bot`: Discord commands fail with an error, the site shows the public bays only. `systemctl stop nginx`: site down, bot still answers Discord.
