#!/usr/bin/env python3
"""Register the /garage slash commands with Discord, once (again if they change).

Run on your own machine, not the server. The bot token is used for this one
call and never stored:

  DISCORD_APP_ID=... DISCORD_GUILD_ID=... DISCORD_BOT_TOKEN=... python3 register_commands.py

Reset the token in the developer portal afterwards.
"""
import os
import sys

import httpx

CAR = {"name": "car", "description": "Car id from /garage cars, like e36", "type": 3, "required": True, "max_length": 40}
MILES = {"name": "miles", "description": "Odometer reading", "type": 4, "required": False, "min_value": 0, "max_value": 2000000}
DATE = {"name": "date", "description": "YYYY-MM-DD, today if empty", "type": 3, "required": False, "max_length": 10}
TYPES = [{"name": n, "value": n} for n in ("preventive", "corrective", "diagnostic", "upgrade")]
SYSTEMS = [{"name": n, "value": n} for n in ("engine", "cooling", "drivetrain", "suspension", "steering", "brakes", "tires", "body", "electrical", "other")]

SUB = 1
COMMAND = {
    "name": "garage", "description": "Jerrekt's Garage: log work and see what's due",
    "options": [
        {"type": SUB, "name": "cars", "description": "Your cars and what's overdue"},
        {"type": SUB, "name": "addcar", "description": "Add a car (pending until approved)", "options": [
            {"name": "name", "description": "Like 2008 Civic Si", "type": 3, "required": True, "max_length": 60},
            {"name": "chassis", "description": "Short id, like e36 or civic", "type": 3, "required": False, "max_length": 20},
            {"name": "year", "description": "Model year", "type": 4, "required": False, "min_value": 1950, "max_value": 2100},
            {**MILES, "description": "Current odometer"}]},
        {"type": SUB, "name": "odo", "description": "Update the odometer", "options": [CAR, {**MILES, "required": True}, DATE]},
        {"type": SUB, "name": "log", "description": "Log work you did", "options": [
            CAR, {"name": "job", "description": "What you did, like Oil change 5W-40", "type": 3, "required": True, "max_length": 120},
            MILES, DATE,
            {"name": "type", "description": "Kind of work", "type": 3, "required": False, "choices": TYPES},
            {"name": "system", "description": "Which system", "type": 3, "required": False, "choices": SYSTEMS},
            {"name": "parts", "description": "Parts used, free text", "type": 3, "required": False, "max_length": 300}]},
        {"type": SUB, "name": "due", "description": "What's due on a car", "options": [CAR]},
        {"type": SUB, "name": "parts", "description": "FCP parts kit for a job", "options": [
            {"name": "job", "description": "Kit id, like valve-cover", "type": 3, "required": True, "max_length": 40}]},
        {"type": SUB, "name": "approve", "description": "Owner only: approve a pending car", "options": [CAR]},
        {"type": SUB, "name": "reject", "description": "Owner only: reject a pending car", "options": [CAR]},
        {"type": SUB, "name": "public", "description": "Owner only: show or hide a car on the public page", "options": [
            CAR, {"name": "show", "description": "Show it", "type": 5, "required": True}]},
        {"type": SUB, "name": "remove", "description": "Delete a car and its whole log", "options": [CAR]},
    ],
}


def main():
    app_id, guild, token = (os.environ.get(k, "").strip() for k in ("DISCORD_APP_ID", "DISCORD_GUILD_ID", "DISCORD_BOT_TOKEN"))
    if not (app_id and guild and token):
        sys.exit("Set DISCORD_APP_ID, DISCORD_GUILD_ID and DISCORD_BOT_TOKEN.")
    url = f"https://discord.com/api/v10/applications/{app_id}/guilds/{guild}/commands"
    r = httpx.put(url, json=[COMMAND], headers={"Authorization": f"Bot {token}",
                  "User-Agent": "DiscordBot (https://github.com/jerrekt/Jerrekts-Garage, 1.0)"}, timeout=20)
    r.raise_for_status()
    print("Registered:", ", ".join("/garage " + o["name"] for o in COMMAND["options"]))


if __name__ == "__main__":
    main()
