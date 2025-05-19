#!/usr/bin/env python3
"""
Memento Mori Bot – slash-command driven reaction / reply trigger bot
────────────────────────────────────────────────────────────────────
• Per-guild trigger maps persist on a Railway **volume** mounted at `/data`.
• Admin-only management via slash commands gated by an **admin role** that
  each guild picks with `/setadminrole` (falls back to Manage Guild).
• Supports **one action per phrase** – either a reaction (Unicode or custom /
  external emoji) *or* a plain-text reply.
• Soft cap of 100 triggers per guild.

REQUIRES
────────
Python ≥ 3.9  and  discord.py ≥ 2.4
Message Content Intent must be enabled in the Dev Portal **and** in code.

Railway setup
─────────────
$ railway volume create data 1GB          # one-off, attaches at /data
$ export DISCORD_TOKEN=...               # or railway variables set
$ python mm.py                           # start command (same in deploy)
"""

from __future__ import annotations
import os
import json
import asyncio
import logging
import sys
from typing import Dict, Any

import discord
from discord.ext import commands
from discord import app_commands

# ----- Configurable constants -----
PHRASE_LIMIT = 100
DATA_DIR = os.getenv("DATA_DIR", "/data")  # Railway volume mount point
DATA_FILE = os.path.join(DATA_DIR, "triggers.json")

# Ensure data directory exists (Railway volume is empty on first run)
os.makedirs(DATA_DIR, exist_ok=True)

# Logging – send INFO to stdout so Railway doesn’t colour them red
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logger = logging.getLogger("memento_mori")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def load_data() -> Dict[str, Any]:
    if not os.path.isfile(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except (IOError, json.JSONDecodeError):
        logger.warning("Could not read triggers.json – starting fresh")
        return {}

def save_data(data: Dict[str, Any]):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

# In-memory cache populated at startup
GUILD_DATA = load_data()  # guild_id:str → {admin_role:int|null, triggers:{} }

def get_guild_entry(guild: discord.Guild) -> Dict[str, Any]:
    gid = str(guild.id)
    if gid not in GUILD_DATA:
        GUILD_DATA[gid] = {"admin_role": None, "triggers": {}}
    return GUILD_DATA[gid]

# ----- Bot setup -----
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    sys.exit("❌  DISCORD_TOKEN environment variable is missing.")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, description="Memento Mori Bot")

def has_admin_role(interaction: discord.Interaction) -> bool:
    entry = get_guild_entry(interaction.guild)
    role_id = entry.get("admin_role")
    if role_id:
        role = interaction.guild.get_role(role_id)
        return role in interaction.user.roles
    # Fallback – users with Manage Guild permission can manage triggers
    return interaction.user.guild_permissions.manage_guild

admin_check = app_commands.check(lambda i: has_admin_role(i))

# ───────────────────────────── Slash commands ──────────────────────────────

class TriggerAction(app_commands.Choice[str]):
    CHOICES = [
        app_commands.Choice(name="reaction", value="reaction"),
        app_commands.Choice(name="reply", value="reply"),
    ]

@app_commands.command(name="addtrigger", description="Add or update a trigger phrase → action")
@admin_check
aasync def add_trigger(
    interaction: discord.Interaction,
    phrase: str,
    action: app_commands.Choice[str, TriggerAction] | str,
    emoji: discord.PartialEmoji | None = None,
    response: str | None = None,
):
    """Register or overwrite a trigger. One action per phrase.
    • When *action* is **reaction** you must supply *emoji*.
    • When *action* is **reply** you must supply *response*.
    """
    await interaction.response.defer(thinking=True)
    phrase = phrase.lower().strip()
    entry = get_guild_entry(interaction.guild)
    triggers = entry["triggers"]

    if action == "reaction" and emoji is None:
        return await interaction.followup.send("You must supply an emoji for a reaction trigger.", ephemeral=True)
    if action == "reply" and response is None:
        return await interaction.followup.send("You must supply response text for a reply trigger.", ephemeral=True)

    if phrase not in triggers and len(triggers) >= PHRASE_LIMIT:
        return await interaction.followup.send(f"Trigger limit ({PHRASE_LIMIT}) reached.", ephemeral=True)

    if action == "reaction":
        triggers[phrase] = {"type": "reaction", "emoji": str(emoji)}
    else:
        triggers[phrase] = {"type": "reply", "response": response}

    save_data(GUILD_DATA)
    await interaction.followup.send(f"✅  Trigger for ‘{phrase}’ set to {action}.", ephemeral=True)

@app_commands.command(name="removetrigger", description="Delete a trigger phrase")
@admin_check
aasync def remove_trigger(interaction: discord.Interaction, phrase: str):
    phrase = phrase.lower().strip()
    entry = get_guild_entry(interaction.guild)
    removed = entry["triggers"].pop(phrase, None)
    if removed:
        save_data(GUILD_DATA)
        msg = f"🗑️  Trigger ‘{phrase}’ removed."
    else:
        msg = "That phrase was not registered."
    await interaction.response.send_message(msg, ephemeral=True)

@app_commands.command(name="listtriggers", description="List all trigger phrases in this server")
@admin_check
aasync def list_triggers(interaction: discord.Interaction):
    entry = get_guild_entry(interaction.guild)
    if not entry["triggers"]:
        return await interaction.response.send_message("No triggers set.", ephemeral=True)
    lines = [
        f"• **{p}** → {info['type']}" for p, info in entry["triggers"].items()
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@app_commands.command(name="setadminrole", description="Choose which role can manage triggers in this server")
@admin_check
aasync def set_admin_role(interaction: discord.Interaction, role: discord.Role):
    entry = get_guild_entry(interaction.guild)
    entry["admin_role"] = role.id
    save_data(GUILD_DATA)
    await interaction.response.send_message(f"✅  Admin role set to {role.mention}.", ephemeral=True)

# Register the commands in a CommandTree group for cleaner Discord UI
command_group = app_commands.Group(name="trigger", description="Trigger management")
for cmd in (add_trigger, remove_trigger, list_triggers):
    command_group.add_command(cmd)

bot.tree.add_command(command_group)
bot.tree.add_command(set_admin_role)

# ----- Message listener -----
@bot.event
aasync def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    entry = get_guild_entry(message.guild)
    if not entry["triggers"]:
        return
    content = message.content.lower()
    for phrase, info in entry["triggers"].items():
        if phrase in content:
            if info["type"] == "reaction":
                try:
                    await message.add_reaction(info["emoji"])
                except discord.HTTPException as e:
                    logger.warning(f"Failed to react: {e}")
            elif info["type"] == "reply":
                await message.reply(info["response"], mention_author=False)
            break  # only first matching trigger fires

# ----- Ready / sync slash commands -----
@bot.event
aasync def on_ready():
    logger.info(f"Logged in as {bot.user} (ID {bot.user.id})")
    try:
        await bot.tree.sync()
        logger.info("Slash commands synced globally.")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")

# Run the bot
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
