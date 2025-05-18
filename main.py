import os
import discord
from discord.ext import commands

TOKEN   = os.getenv("DISCORD_TOKEN")         # keep it secret!
PHRASE  = "hello there"                      # phrase to watch for
EMOJI   = "👋"                                # reaction emoji

intents = discord.Intents.default()
intents.message_content = True               # must also be enabled in the portal

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message):
    if message.author.bot:                   # ignore other bots (and itself)
        return

    if PHRASE.lower() in message.content.lower():
        try:
            await message.add_reaction(EMOJI)
        except discord.Forbidden:
            print("Missing 'Add Reactions' permission!")
    await bot.process_commands(message)      # keep commands working

bot.run(TOKEN)
