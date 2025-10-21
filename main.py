import os
import random
import asyncio
import aiosqlite
import discord
from discord.ext import commands

# --- CONFIG ---
DATABASE = "economy.db"
PREFIX = "!"
STARTING_BALANCE = 1000
DAILY_REWARD = 250
# 3 reels, emoji set:
REELS = ["🍒", "🍋", "🔔", "⭐", "7️⃣", "🍀"]
# Payout multipliers for different outcomes:
PAYOUTS = {
    "three_same": 5,     # three of the same -> 5x bet
    "two_same": 2,       # two same -> 2x bet
    "jackpot_777": 20,   # three 7️⃣ -> 20x bet
    "lucky_clover": 10   # three 🍀 -> 10x bet
}
# Admin role name for give command (change if you use different role)
ADMIN_ROLE = "Admin"

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)


# -------------------------
# Database helpers
# -------------------------
async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS users (
                   user_id INTEGER PRIMARY KEY,
                   balance INTEGER NOT NULL,
                   last_daily INTEGER
               )"""
        )
        await db.commit()

async def ensure_user(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO users (user_id, balance, last_daily) VALUES (?, ?, ?)",
                (user_id, STARTING_BALANCE, 0)
            )
            await db.commit()

async def get_balance(user_id: int) -> int:
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row:
            return row[0]
        return 0

async def add_balance(user_id: int, amount: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def set_balance(user_id: int, amount: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def get_last_daily(user_id: int) -> int:
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if row:
            return row[0] or 0
        return 0

async def set_last_daily(user_id: int, ts: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (ts, user_id))
        await db.commit()

async def top_balances(limit: int = 10):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,))
        rows = await cur.fetchall()
        return rows


# -------------------------
# Utility: slot logic
# -------------------------
def spin_reels():
    return [random.choice(REELS) for _ in range(3)]

def evaluate_spin(reels, bet):
    a, b, c = reels
    # jackpot 777
    if a == b == c == "7️⃣":
        return "jackpot_777", PAYOUTS["jackpot_777"] * bet
    # lucky clover
    if a == b == c == "🍀":
        return "lucky_clover", PAYOUTS["lucky_clover"] * bet
    # three same
    if a == b == c:
        return "three_same", PAYOUTS["three_same"] * bet
    # two same
    if a == b or a == c or b == c:
        re

