# main.py
import os
import random
import time
import asyncio
import aiosqlite
import discord
from discord.ext import commands

# -------------------------
# CONFIG - edit as needed
# -------------------------
DATABASE = "fishnuke.db"
PREFIX = "!"
STARTING_BALANCE = 500
DAILY_REWARD = 200
NUKE_PRICE = 500           # coins per nuke
NUKE_COOLDOWN = 60 * 60 * 6  # 6 hours per user (seconds)
MAX_CATCH = 6              # max fish you can catch per !fish
ADMIN_ROLE = "Admin"       # role name for admin commands
BOT_INTENTS = discord.Intents.default()
BOT_INTENTS.message_content = True
BOT_INTENTS.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=BOT_INTENTS)

# -------------------------
# DATABASE helpers
# -------------------------
async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                last_daily INTEGER DEFAULT 0
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
                last_nuke INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def ensure_user(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        if not await cur.fetchone():
            await db.execute("INSERT INTO users (user_id, balance, last_daily) VALUES (?, ?, 0)",
                             (user_id, STARTING_BALANCE))
            await db.execute("INSERT INTO fish (user_id, fish_count) VALUES (?, 0)", (user_id,))
            await db.execute("INSERT INTO cooldowns (user_id, last_nuke) VALUES (?, 0)", (user_id,))
            await db.commit()

# balance helpers
async def get_balance(user_id: int) -> int:
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

async def add_balance(user_id: int, amount: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (int(amount), user_id))
        await db.commit()

async def set_balance(user_id: int, amount: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (int(amount), user_id))
        await db.commit()

# fish helpers
async def get_fish(user_id: int) -> int:
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT fish_count FROM fish WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

async def add_fish(user_id: int, amount: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE fish SET fish_count = fish_count + ? WHERE user_id = ?", (int(amount), user_id))
        await db.commit()

async def set_fish(user_id: int, amount: int):
    await ensure_user(user_id)
    amount = max(0, int(amount))
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE fish SET fish_count = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

# items helpers
async def get_item(user_id: int, item_name: str) -> int:
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT amount FROM items WHERE user_id = ? AND item_name = ?", (user_id, item_name))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

async def add_item(user_id: int, item_name: str, amount: int):
    await ensure_user(user_id)
    current = await get_item(user_id, item_name)
    async with aiosqlite.connect(DATABASE) as db:
        if current == 0:
            await db.execute("INSERT OR REPLACE INTO items (user_id, item_name, amount) VALUES (?, ?, ?)",
                             (user_id, item_name, int(amount)))
        else:
            await db.execute("UPDATE items SET amount = amount + ? WHERE user_id = ? AND item_name = ?",
                             (int(amount), user_id, item_name))
        await db.commit()

async def set_item(user_id: int, item_name: str, amount: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("INSERT OR REPLACE INTO items (user_id, item_name, amount) VALUES (?, ?, ?)",
                         (user_id, item_name, int(amount)))
        await db.commit()

# cooldown helpers
async def get_last_nuke(user_id: int) -> int:
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT last_nuke FROM cooldowns WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

async def set_last_nuke(user_id: int, ts: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE cooldowns SET last_nuke = ? WHERE user_id = ?", (int(ts), user_id))
        await db.commit()

# leaderboard helpers
async def top_fish(limit: int = 10):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT user_id, fish_count FROM fish ORDER BY fish_count DESC LIMIT ?", (limit,))
        rows = await cur.fetchall()
        return rows

# -------------------------
# BOT EVENTS
# -------------------------
@bot.event
async def on_ready():
    print(f"✅ FishNuke bot online as {bot.user} (id: {bot.user.id})")
    await init_db()

# -------------------------
# COMMANDS
# -------------------------
@bot.command(name="balance")
async def cmd_balance(ctx, member: discord.Member = None):
    target = member or ctx.author
    await ensure_user(target.id)
    bal = await get_balance(target.id)
    await ctx.send(f"💰 {target.display_name} has **{bal:,}** coins.")

@bot.command(name="daily")
async def cmd_daily(ctx):
    await ensure_user(ctx.author.id)
    now = int(time.time())
    last = await get_balance_last_daily(ctx.author.id) if False else None  # replaced by get_last_daily below
    # we'll store last_daily in users table; reuse functions
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT last_daily FROM users WHERE user_id = ?", (ctx.author.id,))
        row = await cur.fetchone()
        last = int(row[0]) if row and row[0] else 0

    if now - last < 86400:
        remaining = 86400 - (now - last)
        hrs = remaining // 3600
        mins = (remaining % 3600) // 60
        secs = remaining % 60
        return await ctx.send(f"⏳ You've already claimed daily. Try again in {hrs}h {mins}m {secs}s.")
    await add_balance(ctx.author.id, DAILY_REWARD)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (now, ctx.author.id))
        await db.commit()
    await ctx.send(f"✨ You claimed **{DAILY_REWARD:,}** coins!")

@bot.command(name="fish")
@commands.cooldown(1, 15, commands.BucketType.user)  # 15s cooldown per user
async def cmd_fish(ctx):
    await ensure_user(ctx.author.id)
    caught = random.randint(1, MAX_CATCH)
    # chance for rare big catch
    if random.random() < 0.05:
        bonus = random.randint(5, 15)
        caught += bonus
        note = f" — huge catch! +{bonus}"
    else:
        note = ""
    await add_fish(ctx.author.id, caught)
    await ctx.send(f"🎣 {ctx.author.display_name} caught **{caught}** fish{note}!")

@cmd_fish.error
async def cmd_fish_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ You're fishing too fast. Try again in {error.retry_after:.0f}s.")

@bot.command(name="inventory")
async def cmd_inventory(ctx, member: discord.Member = None):
    target = member or ctx.author
    await ensure_user(target.id)
    fish = await get_fish(target.id)
    nu
