# Deploying the garage bot

Runs as a third bot in the shared bots container on Kratos (CT 160), next to
the Bricked and Waymo claim bots, with the same isolation:

| Per bot | Garage |
|---|---|
| Linux user (no login) | `bot-garage` |
| Code (root-owned, read-only to the bot) | `/opt/garage-bot/src` (this repo) |
| Data (only the bot can write) | `/var/lib/garage-bot/garage.db` |
| Secrets (root-only, 0600) | `/etc/garage-bot/bot.env` |
| Service | `garage-bot.service` |
| Port, localhost only | `127.0.0.1:8703` |
| Public hostname | `garage-api.adsuaracloud.com` via the container's `bots` tunnel |

The Bricked-Sorting repo's `deploy/bots/add-bot.sh` makes the user and folders.

## Install (inside CT 160, as root)
    bash install.sh            # idempotent: clone or pull, venv, unit, env skeleton, start, health

## Then, by hand
1. `/etc/garage-bot/bot.env`: fill from `bot.env.example` (nano, never paste secrets into chat).
   `GARAGE_SITE_TOKEN`: `openssl rand -hex 32`.
2. Discord: Developer Portal, New Application "Jerrekt's Garage". Public key into `bot.env`,
   restart, then set the Interactions Endpoint URL to `https://garage-api.adsuaracloud.com/discord/interactions`.
   Install in the server with the `applications.commands` scope. A webhook in the feed channel into `bot.env`.
3. Register the commands once from your PC: `bot/register_commands.py` (token used once, then reset).
4. Tunnel: add to `/etc/cloudflared/config.yml`
       - hostname: garage-api.adsuaracloud.com
         service: http://127.0.0.1:8703
   above the 404 line, `cloudflared tunnel ingress validate`, restart cloudflared, then the DNS route
   (`cloudflared tunnel login`, `cloudflared tunnel route dns bots garage-api.adsuaracloud.com`, delete the cert again).

## Updating
    cd /opt/garage-bot/src && git pull --ff-only
    /opt/garage-bot/venv/bin/python -m py_compile bot/app.py && systemctl restart garage-bot

## Off switch
`systemctl stop garage-bot`. Discord commands then fail with an error; nothing else is affected.
