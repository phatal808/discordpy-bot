"""
Animated-emoji reaction bot
——————————————
• Listens for a trigger phrase (case-insensitive).
• Reacts with an animated **external** emoji (<a:name:id>).
• Exits early if DISCORD_TOKEN is missing.
"""

import os, sys, discord
from discord.ext import commands

# ---------- CONFIG ----------------------------------------------------------
PHRASE        = "memento mori"                 # trigger phrase
EMOJI_ID      = 1367615846259621908            # ✨ replace with your ID
EMOJI_NAME    = "MM"                  # ✨ replace with your name
EMOJI         = discord.PartialEmoji(
                   id=EMOJI_ID, 
                   name=EMOJI_NAME, 
                   animated=True
                )
# ---------------------------------------------------------------------------

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    sys.exit("❌  DISCORD_TOKEN environment variable is missing.")

intents = discord.Intents.default()
intents.message_content = True                # also enable in Dev Portal!

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    # Sanity-check: can the bot *see* that emoji somewhere?
    if not bot.get_emoji(EMOJI_ID):
        print("⚠️  Warning: bot cannot find that emoji in any shared guild.")
        print("   Make sure the bot is in the server that hosts the emoji.")
    print(f"✅  Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return                                  # ignore bots & itself

    if PHRASE.lower() in message.content.lower():
        try:
            await message.add_reaction(EMOJI)
        except discord.Forbidden:
            # Missing “Add Reactions” or “Use External Emoji” in this guild
            print(f"🚫  No permission to use external emoji in {message.guild}")
        except discord.HTTPException as e:
            # Bad emoji ID or other request error
            print(f"🚫  Failed to add reaction: {e}")

    await bot.process_commands(message)         # keep other commands working

# Run the bot (blocking)
bot.run(TOKEN)
