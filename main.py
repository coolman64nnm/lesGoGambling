import discord
from discord.ext import commands
import os

# 👇 enable all intents you need
intents = discord.Intents.default()
intents.message_content = True  # required to read messages
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong! 🏓")

bot.run(os.getenv("TOKEN"))
