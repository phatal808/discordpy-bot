#!/usr/bin/env python3
"""
Memento Mori Bot – slash‑command driven reaction / reply trigger bot
────────────────────────────────────────────────────────────────────
This version fixes the slash‑command parameter definition so Discord can
extract choices correctly.

• Per‑guild trigger maps stored in `/data/triggers.json` (Railway volume)
• Admin‑only slash commands (`/trigger …`, `/setadminrole`)
• One action per phrase: *reaction* (emoji) **or** *reply* (text)
"""
from __future__ import annotations
import os, json, logging, sys
from typing import Dict, Any

import discord
from discord.ext import commands
from discord import app_commands

PHRASE_LIMIT = 100
DATA_DIR = os.getenv("DATA_DIR", "/data")
DATA_FILE = os.path.join(DATA_DIR, "triggers.json")
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("memento_mori")

# ───────────────── Persistence ─────────────────

def load_data() -> Dict[str, Any]:
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        logger.warning("triggers.json corrupt – starting fresh")
        return {}

def save_data(data: Dict[str, Any]):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

GUILD_DATA = load_data()

def get_entry(guild: discord.Guild) -> Dict[str, Any]:
    gid = str(guild.id)
    if gid not in GUILD_DATA:
        GUILD_DATA[gid] = {"admin_role": None, "triggers": {}}
    return GUILD_DATA[gid]

# ───────────────── Bot setup ─────────────────
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    sys.exit("❌ DISCORD_TOKEN missing")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, description="Memento Mori Bot")

# ───────────── Permission helper ────────────

def has_admin(i: discord.Interaction) -> bool:
    entry = get_entry(i.guild)
    rid = entry.get("admin_role")
    if rid:
        role = i.guild.get_role(rid)
        return role in i.user.roles
    return i.user.guild_permissions.manage_guild

admin_check = app_commands.check(has_admin)

# ────────────── Slash commands ──────────────
CHOICES = [
    app_commands.Choice(name="reaction", value="reaction"),
    app_commands.Choice(name="reply", value="reply"),
]

@app_commands.command(name="addtrigger", description="Add/overwrite a trigger")
@admin_check
@app_commands.describe(
    phrase="Text to watch for (case‑insensitive)",
    action="Select reaction or reply",
    emoji="Emoji if action=reaction",
    response="Reply text if action=reply",
)
@app_commands.choices(action=CHOICES)
async def addtrigger(
    interaction: discord.Interaction,
    phrase: str,
    action: app_commands.Choice[str],  # <-- FIXED: Choice type
    emoji: discord.PartialEmoji | None = None,
    response: str | None = None,
):
    await interaction.response.defer(thinking=True, ephemeral=True)
    phrase = phrase.lower().strip()
    act = action.value  # now get value

    entry = get_entry(interaction.guild)
    triggers = entry["triggers"]

    if act == "reaction" and emoji is None:
        return await interaction.followup.send("You must supply an emoji.")
    if act == "reply" and response is None:
        return await interaction.followup.send("You must supply reply text.")
    if phrase not in triggers and len(triggers) >= PHRASE_LIMIT:
        return await interaction.followup.send(f"Trigger limit {PHRASE_LIMIT} reached.")

    triggers[phrase] = {
        "type": act,
        "emoji": str(emoji) if act == "reaction" else None,
        "response": response if act == "reply" else None,
    }
    save_data(GUILD_DATA)
    await interaction.followup.send(f"✅ ‘{phrase}’ now triggers {act}.")

@app_commands.command(name="removetrigger", description="Remove a trigger")
@admin_check
async def removetrigger(interaction: discord.Interaction, phrase: str):
    phrase = phrase.lower().strip()
    entry = get_entry(interaction.guild)
    removed = entry["triggers"].pop(phrase, None)
    save_data(GUILD_DATA)
    msg = "Removed." if removed else "Phrase not found."
    await interaction.response.send_message(msg, ephemeral=True)

@app_commands.command(name="listtriggers", description="List triggers in this guild")
@admin_check
async def listtriggers(interaction: discord.Interaction):
    entry = get_entry(interaction.guild)
    if not entry["triggers"]:
        return await interaction.response.send_message("No triggers set.", ephemeral=True)
    lines = [f"• **{p}** → {info['type']}" for p, info in entry["triggers"].items()]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@app_commands.command(name="setadminrole", description="Set role allowed to manage triggers")
@admin_check
async def setadminrole(interaction: discord.Interaction, role: discord.Role):
    entry = get_entry(interaction.guild)
    entry["admin_role"] = role.id
    save_data(GUILD_DATA)
    await interaction.response.send_message(f"Admin role set to {role.mention}", ephemeral=True)

# group
grp = app_commands.Group(name="trigger", description="Trigger management")
for cmd in (addtrigger, removetrigger, listtriggers):
    grp.add_command(cmd)

bot.tree.add_command(grp)
bot.tree.add_command(setadminrole)

# ─────────── Message listener ────────────
@bot.event
async def on_message(msg: discord.Message):
    if msg.author.bot or msg.guild is None:
        return
    entry = get_entry(msg.guild)
    if not entry["triggers"]:
        return
    content = msg.content.lower()
    for phrase, info in entry["triggers"].items():
        if phrase in content:
            if info["type"] == "reaction":
                try:
                    await msg.add_reaction(info["emoji"])
                except discord.HTTPException as e:
                    logger.warning(f"React failed: {e}")
            else:
                await msg.reply(info["response"], mention_author=False)
            break

# ───────────── Ready event ───────────────
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} ({bot.user.id})")
    await bot.tree.sync()
    logger.info("Slash commands synced.")

if __name__ == "__main__":
    bot.run(TOKEN)
