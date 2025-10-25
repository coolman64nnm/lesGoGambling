# main.py
import os
import random
import time
import asyncio
import aiosqlite
import discord
from discord.ext import commands

# -------------------------
# CONFIG
# -------------------------
DATABASE = "fishnuke.db"
PREFIX = "!"
TOKEN = os.getenv("TOKEN")  # set this in Railway/Env or hardcode for local testing
OWNER_ID = 123456789012345678  # replace with your numeric Discord ID
ADMIN_ROLE = "Admin"           # must exist in your server
STARTING_BALANCE = 500
DAILY_REWARD = 200
NUKE_PRICE = 500
NUKE_COOLDOWN = 60 * 60 * 6
MAX_CATCH = 6
SHOP = {
    "nuke": {"price": NUKE_PRICE, "desc": "Destroy other players' fish (in-game)"},
    "petfood": {"price": 50, "desc": "Feed your pet (+happiness)"},
    "rod": {"price": 300, "desc": "Upgrade rod for better fishing"}
}

# -------------------------
# Bot setup
# -------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# -------------------------
# DATABASE
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

async def ensure_user(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        if not await cur.fetchone():
            await db.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, STARTING_BALANCE))
            await db.execute("INSERT INTO fish (user_id) VALUES (?)", (user_id,))
            await db.execute("INSERT INTO cooldowns (user_id) VALUES (?)", (user_id,))
            await db.execute("INSERT OR IGNORE INTO pets (user_id) VALUES (?)", (user_id,))
            await db.commit()

# -------------------------
# UTILITY
# -------------------------
def fmt(num: int) -> str:
    return f"{num:,}"

def is_admin_role(member: discord.Member):
    if OWNER_ID and member.id == OWNER_ID:
        return True
    return any(r.name == ADMIN_ROLE for r in member.roles)

# -------------------------
# BALANCE / FISH / ITEMS helpers
# -------------------------
# Using async functions for DB operations (get/add/set balance, fish, items)

# BALANCE
async def get_balance(uid): 
    async with aiosqlite.connect(DATABASE) as db:
        row = await (await db.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))).fetchone()
        return int(row[0]) if row else 0
async def add_balance(uid, amount):
    await ensure_user(uid)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (int(amount), uid))
        await db.commit()
async def set_balance(uid, amount):
    await ensure_user(uid)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (max(0,int(amount)), uid))
        await db.commit()

# FISH
async def get_fish(uid):
    async with aiosqlite.connect(DATABASE) as db:
        row = await (await db.execute("SELECT fish_count FROM fish WHERE user_id = ?", (uid,))).fetchone()
        return int(row[0]) if row else 0
async def add_fish(uid, amount):
    await ensure_user(uid)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE fish SET fish_count = fish_count + ? WHERE user_id = ?", (int(amount), uid))
        await db.commit()
async def set_fish(uid, amount):
    await ensure_user(uid)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE fish SET fish_count = ? WHERE user_id = ?", (max(0,int(amount)), uid))
        await db.commit()

# ITEMS
async def get_item(uid, name):
    async with aiosqlite.connect(DATABASE) as db:
        row = await (await db.execute("SELECT amount FROM items WHERE user_id = ? AND item_name = ?", (uid,name))).fetchone()
        return int(row[0]) if row else 0
async def add_item(uid, name, amount):
    await ensure_user(uid)
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT amount FROM items WHERE user_id = ? AND item_name = ?", (uid,name))
        row = await cur.fetchone()
        if row:
            await db.execute("UPDATE items SET amount = amount + ? WHERE user_id=? AND item_name=?", (amount, uid, name))
        else:
            await db.execute("INSERT INTO items (user_id,item_name,amount) VALUES (?,?,?)", (uid,name,amount))
        await db.commit()
async def set_item(uid,name,amount):
    await ensure_user(uid)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("INSERT OR REPLACE INTO items (user_id,item_name,amount) VALUES (?,?,?)",(uid,name,max(0,int(amount))))
        await db.commit()

# COOLDOWNS
async def get_last_nuke(uid):
    async with aiosqlite.connect(DATABASE) as db:
        row = await (await db.execute("SELECT last_nuke FROM cooldowns WHERE user_id=?", (uid,))).fetchone()
        return int(row[0]) if row else 0
async def set_last_nuke(uid, ts):
    await ensure_user(uid)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE cooldowns SET last_nuke=? WHERE user_id=?", (ts,uid))
        await db.commit()
async def get_last_fish(uid):
    async with aiosqlite.connect(DATABASE) as db:
        row = await (await db.execute("SELECT last_fish FROM cooldowns WHERE user_id=?", (uid,))).fetchone()
        return int(row[0]) if row else 0
async def set_last_fish(uid, ts):
    await ensure_user(uid)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE cooldowns SET last_fish=? WHERE user_id=?", (ts,uid))
        await db.commit()

# PETS
async def get_pet(uid):
    await ensure_user(uid)
    async with aiosqlite.connect(DATABASE) as db:
        row = await (await db.execute("SELECT name,level,happiness,exp FROM pets WHERE user_id=?", (uid,))).fetchone()
        if row: return row
        return ("Lucky",1,100,0)
async def update_pet(uid, **kwargs):
    if not kwargs: return
    keys = ", ".join(f"{k}=?" for k in kwargs.keys())
    vals = list(kwargs.values()) + [uid]
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(f"UPDATE pets SET {keys} WHERE user_id=?", vals)
        await db.commit()

# LEADERBOARDS
async def top_fish(limit=10):
    async with aiosqlite.connect(DATABASE) as db:
        return await (await db.execute("SELECT user_id,fish_count FROM fish ORDER BY fish_count DESC LIMIT ?",(limit,))).fetchall()
async def top_balance(limit=10):
    async with aiosqlite.connect(DATABASE) as db:
        return await (await db.execute("SELECT user_id,balance FROM users ORDER BY balance DESC LIMIT ?",(limit,))).fetchall()

# -------------------------
# EVENTS
# -------------------------
@bot.event
async def on_ready():
    print(f"✅ FishNuke bot online as {bot.user}")
    await init_db()
    # create admin role if OWNER_ID exists and role missing
    if OWNER_ID:
        for guild in bot.guilds:
            member = guild.get_member(OWNER_ID)
            role = discord.utils.get(guild.roles,name=ADMIN_ROLE)
            if not role:
                role = await guild.create_role(name=ADMIN_ROLE,permissions=discord.Permissions(0))
            if member and role not in member.roles:
                await member.add_roles(role)
                print(f"Assigned {ADMIN_ROLE} to {member.display_name} in {guild.name}")

# -------------------------
# COMMANDS (BALANCE / DAILY / FISH)
# -------------------------
@bot.command()
async def balance(ctx, member: discord.Member=None):
    target = member or ctx.author
    await ensure_user(target.id)
    bal = await get_balance(target.id)
    await ctx.send(f"💰 {target.display_name} has **{fmt(bal)}** coins.")

@bot.command()
async def daily(ctx):
    await ensure_user(ctx.author.id)
    now = int(time.time())
    async with aiosqlite.connect(DATABASE) as db:
        row = await (await db.execute("SELECT last_daily FROM users WHERE user_id=?", (ctx.author.id,))).fetchone()
    last = int(row[0]) if row else 0
    if now - last < 86400:
        rem = 86400 - (now-last)
        await ctx.send(f"⏳ Already claimed daily. Try again in {rem//3600}h {(rem%3600)//60}m {rem%60}s")
        return
    await add_balance(ctx.author.id, DAILY_REWARD)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET last_daily=? WHERE user_id=?",(now,ctx.author.id))
        await db.commit()
    await ctx.send(f"✨ Claimed **{fmt(DAILY_REWARD)}** coins!")

@bot.command()
async def fish(ctx):
    await ensure_user(ctx.author.id)
    now = int(time.time())
    last = await get_last_fish(ctx.author.id)
    if now - last < 5:
        return await ctx.send("⏳ Slow down! Try again in a few seconds.")
    rod = await get_item(ctx.author.id,"rod")
    max_catch = MAX_CATCH + min(10, rod)
    caught = random.randint(1,max_catch)
    if random.random() < 0.05 + rod*0.01:
        bonus = random.randint(3,12)
        caught += bonus
        note = f" — huge catch! +{bonus}"
    else: note=""
    coins = caught * (random.randint(5,15)+rod)
    await add_fish(ctx.author.id, caught)
    await add_balance(ctx.author.id, coins)
    await set_last_fish(ctx.author.id, now)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET xp = xp + ? WHERE user_id=?",(caught*2,ctx.author.id))
        await db.commit()
    await ctx.send(f"🎣 {ctx.author.display_name} caught **{caught}** fish{note} and earned **{fmt(coins)}** coins!")

# -------------------------
# START BOT
# -------------------------
if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: TOKEN not set!")
    else:
        bot.run(TOKEN)
