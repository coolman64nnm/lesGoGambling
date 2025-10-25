# main.py
import os
import random
import time
import asyncio
import aiosqlite
import discord
from discord.ext import commands

# -------------------------
# CONFIG - edit before deploy
# -------------------------
DATABASE = "fishnuke.db"
PREFIX = "!"
TOKEN = os.getenv("TOKEN")  # must set in Railway/Env
OWNER_ID = None  # set to your Discord numeric ID (e.g. 123456789012345678) if you want auto-admin
ADMIN_ROLE = "777"  # role name used to detect admins
STARTING_BALANCE = 500
DAILY_REWARD = 200
NUKE_PRICE = 500               # coins
NUKE_COOLDOWN = 60 * 60 * 6    # 6 hours
MAX_CATCH = 6
SHOP = {
    "nuke": {"price": NUKE_PRICE, "desc": "Destroy other players' fish (in-game)"},
    "petfood": {"price": 50, "desc": "Feed your pet (+happiness)"},
    "rod": {"price": 300, "desc": "Upgrade rod for better fishing (reduces cooldowns / improves catch)"}
}
BOT_INTENTS = discord.Intents.default()
BOT_INTENTS.message_content = True
BOT_INTENTS.members = True

# -------------------------
# Bot setup
# -------------------------
bot = commands.Bot(command_prefix=PREFIX, intents=BOT_INTENTS)

# -------------------------
# DATABASE: init + helpers
# -------------------------
async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                last_daily INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fish (
                user_id INTEGER PRIMARY KEY,
                fish_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS items (
                user_id INTEGER,
                item_name TEXT,
                amount INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, item_name)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cooldowns (
                user_id INTEGER PRIMARY KEY,
                last_nuke INTEGER DEFAULT 0,
                last_fish INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS pets (
                user_id INTEGER PRIMARY KEY,
                name TEXT DEFAULT 'Lucky',
                level INTEGER DEFAULT 1,
                happiness INTEGER DEFAULT 100,
                exp INTEGER DEFAULT 0
            )
        """)
        await db.commit()

# ... other database helpers remain unchanged ...

# -------------------------
# ITEMS: shop/buy/inventory
# -------------------------
@bot.command(name="shop")
async def cmd_shop(ctx):
    desc = ""
    user_rod_level = await get_item(ctx.author.id, "rod")
    for k, v in SHOP.items():
        if k == "rod":
            price = int(v['price'] * (1.2 ** user_rod_level))
        else:
            price = v['price']
        desc += f"**{k}** — {price} coins — {v['desc']}\n"
    embed = discord.Embed(title="🛒 Shop", description=desc, color=0x00CCFF)
    await ctx.send(embed=embed)

@bot.command(name="buy")
async def cmd_buy(ctx, item: str, amount: int = 1):
    item = item.lower()
    if item not in SHOP:
        return await ctx.send("Unknown item. Use `!shop` to view items.")
    if amount <= 0:
        return await ctx.send("Amount must be positive.")
    await ensure_user(ctx.author.id)

    if item == "rod":
        current_level = await get_item(ctx.author.id, "rod")
        cost = 0
        for i in range(amount):
            cost += int(SHOP["rod"]["price"] * (1.2 ** (current_level + i)))
    else:
        cost = SHOP[item]["price"] * amount

    bal = await get_balance(ctx.author.id)
    if cost > bal:
        return await ctx.send(f"💸 You need {fmt(cost)} coins but you only have {fmt(bal)}.")

    await add_balance(ctx.author.id, -cost)

    if item == "rod":
        await add_item(ctx.author.id, "rod", amount)
    else:
        await add_item(ctx.author.id, item, amount)

    await ctx.send(f"✅ You bought {amount} x **{item}** for {fmt(cost)} coins.")

# ... rest of commands and bot code remain unchanged ...
