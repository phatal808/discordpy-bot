#!/usr/bin/env python3
"""
Memento Mori Bot – slash-command driven reaction / reply trigger bot
────────────────────────────────────────────────────────────────────
• Per-guild trigger maps persist on a Railway **volume** mounted at `/data`.
• Admin-only management via slash commands gated by an **admin role** that
  each guild picks with `/setadminrole` (falls back to Manage Guild).
• Supports **one action per phrase** – either a reaction (Unicode or custom /
  external emoji) *or* a plain‑text reply.
• Soft cap of 100 triggers per guild.

REQUIRES
────────
Python ≥ 3.9  and  discord.py ≥ 2.4
Message Content Intent must be enabled in the Dev Portal **and** in code.

Railway setup
─────────────
$ railway volume create data 1GB          # one‑off, attaches at /data
$ export DISCORD_TOKEN=...               # or railway variables set
$ python mm.py                           # start command (same in deploy)
"""

from __future__ import annotations
import os
import json
import logging
import sys
from typing import Dict, Any

import discord
from discord.ext import commands
from discord import app_commands

# ─────────────────────────── Config ────────────────────────────
PHRASE_LIMIT = 100
DATA_DIR   = os.getenv("DATA_DIR", "/data")  # Railway volume mount point
DATA_FILE  = os.path.join(DATA_DIR, "triggers.json")

os.makedirs(DATA_DIR, exist_ok=True)            # first‑run volume

# ────────────────────────── Logging setup ─────────────────────
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logger = logging.getLogger("memento_mori")
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ──────────────────────── Persistence helpers ─────────────────

def load_data() -> Dict[str, Any]:
    if not os.path.isfile(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf‑8") as fp:
            return json.load(fp)
    except (IOError, json.JSONDecodeError):
        logger.warning("Could not read triggers.json – starting fresh")
        return {}

def save_data(data: Dict[str, Any]):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf‑8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

GUILD_DATA = load_data()  # guild_id:str → {admin_role:int|null, triggers:{}}

def get_guild_entry(guild: discord.Guild) -> Dict[str, Any]:
    gid = str(guild.id)
    if gid not in GUILD_DATA:
        GUILD_DATA[gid] = {"admin_role": None, "triggers": {}}
    return GUILD_DATA[gid]

# ─────────────────────────── Bot setup ─────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    sys.exit("❌  DISCORD_TOKEN environment variable is missing.")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, description="Memento Mori Bot")

# ───────────────────── Permission / role helpers ──────────────

def has_admin_role(inter: discord.Interaction) -> bool:
    entry   = get_guild_entry(inter.guild)
    role_id = entry.get("admin_role")
    if role_id:
        role = inter.guild.get_role(role_id)
        return role in inter.user.roles
    return inter.user.guild_permissions.manage_guild

admin_check = app_commands.check(lambda i: has_admin_role(i))

# ───────────────────────── Slash commands ─────────────────────

CHOICES_ACTION = [
    app_commands.Choice(name="reaction", value="reaction"),
    app_commands.Choice(name="reply",    value="reply"),
]

@app_commands.command(name="addtrigger", description="Add or update a trigger phrase → action")
@admin_check
@app_commands.describe(
    phrase="Text to look for (case‑insensitive)",
    action="Choose whether to react or reply",
    emoji="Emoji to react with (if action=reaction)",
    response="Reply text (if action=reply)",
)
@app_commands.choices(action=CHOICES_ACTION)
async def add_trigger(
    interaction: discord.Interaction,
    phrase: str,
    action: app_commands.Choice[str],
    emoji: discord.PartialEmoji | None = None,
    response: str | None = None,
):
    await interaction.response.defer(thinking=True, ephemeral=True)
    phrase = phrase.lower().strip()

    entry    = get_guild_entry(interaction.guild)
    triggers = entry["triggers"]

    act_val = action.value
    if act_val == "reaction" and emoji is None:
        return await interaction.followup.send("You must supply an emoji for a reaction trigger.")
    if act_val == "reply" and response is None:
        return await interaction.followup.send("You must supply response text for a reply trigger.")

    if phrase not in triggers and len(triggers) >= PHRASE_LIMIT:
        return await interaction.followup.send(f"Trigger limit ({PHRASE_LIMIT}) reached.")

    if act_val == "reaction":
        triggers[phrase] = {"type": "reaction", "emoji": str(emoji)}
    else:
        triggers[phrase] = {"type": "reply", "response": response}

    save_data(GUILD_DATA)
    await interaction.followup.send(f"✅  Trigger ‘{phrase}’ set to {act_val}.")

@app_commands.command(name="removetrigger", description="Delete a trigger phrase")
@admin_check
async def removetrigger(interaction: discord.Interaction, phrase: str):
    phrase = phrase.lower().strip()
    entry  = get_guild_entry(interaction.guild)
    removed = entry["triggers"].pop(phrase, None)
    if removed:
        save_data(GUILD_DATA)
        msg = f"🗑️  Trigger ‘{phrase}’ removed."
    else:
        msg = "That phrase was not registered."
    await interaction.response.send_message(msg, ephemeral=True)

@app_commands.command(name="listtriggers", description="List all trigger phrases in this server")
@admin_check
async def listtriggers(interaction: discord.Interaction):
    entry = get_guild_entry(interaction.guild)
    if not entry["triggers"]:
        return await interaction.response.send_message("No triggers set.", ephemeral=True)
    lines = [f"• **{p}** → {info['type']}" for p, info in entry["triggers"].items()]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@app_commands.command(name="setadminrole", description="Choose which role can manage triggers in this server")
@admin_check
async def setadminrole(interaction: discord.Interaction, role: discord.Role):
    entry = get_guild_entry(interaction.guild)
    entry["admin_role"] = role.id
    save_data(GUILD_DATA)
    await interaction.response.send_message(f"✅  Admin role set to {role.mention}.", ephemeral=True)

# Grouping for cleaner UI
cmd_group = app_commands.Group(name="trigger", description="Trigger management")
for _cmd in (add_trigger, removetrigger, listtriggers):
    cmd_group.add_command(_cmd)

bot.tree.add_command(cmd_group)
bot.tree.add_command(setadminrole)

# ─────────────────────── Message listener ─────────────────────
@bot.event
async def on_message(message: discord.Message):
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
                except discord.HTTPException as exc:
                    logger.warning(f"Failed to react: {exc}")
            elif info["type"] == "reply":
                await message.reply(info["response"], mention_author=False)
            break  # fire only first match

# ───────────────────────── Ready event ────────────────────────
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID {bot.user.id})")
    try:
        await bot.tree.sync()
        logger.info("Slash commands synced globally.")
    except Exception as exc:
        logger.error(f"Failed to sync commands: {exc}")

# ─────────────────────────── Run bot ──────────────────────────
if __name__ == "__main__":
    bot.run(TOKEN)
