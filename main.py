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

async def ensure_user(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        if not await cur.fetchone():
            await db.execute("INSERT INTO users (user_id, balance, last_daily, xp) VALUES (?, ?, 0, 0)",
                             (user_id, STARTING_BALANCE))
            await db.execute("INSERT INTO fish (user_id, fish_count) VALUES (?, 0)", (user_id,))
            await db.execute("INSERT INTO cooldowns (user_id, last_nuke, last_fish) VALUES (?, 0, 0)", (user_id,))
            await db.execute("INSERT OR IGNORE INTO pets (user_id, name, level, happiness, exp) VALUES (?, 'Lucky', 1, 100, 0)",
                             (user_id,))
            await db.commit()

#
