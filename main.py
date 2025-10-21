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
        return "two_same", PAYOUTS["two_same"] * bet
    # nothing
    return "none", 0


# -------------------------
# Events & commands
# -------------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await init_db()

@bot.command(name="balance", help="Show your fake-currency balance")
async def balance_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    await ensure_user(target.id)
    bal = await get_balance(target.id)
    await ctx.send(f"💰 {target.display_name} has **{bal:,}** coins.")

@bot.command(name="give", help="(Admin) Give coins to a user for testing")
@commands.has_role(ADMIN_ROLE)
async def give_cmd(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        return await ctx.send("Amount must be positive.")
    await ensure_user(member.id)
    await add_balance(member.id, amount)
    await ctx.send(f"✅ Gave **{amount:,}** coins to {member.display_name}.")

@give_cmd.error
async def give_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You don't have permission to use this command.")
    else:
        raise error

@bot.command(name="daily", help=f"Claim daily reward of {DAILY_REWARD} coins")
async def daily_cmd(ctx):
    await ensure_user(ctx.author.id)
    import time
    now = int(time.time())
    last = await get_last_daily(ctx.author.id)
    # 24 hours = 86400 seconds
    if now - last < 86400:
        remaining = 86400 - (now - last)
        hrs = remaining // 3600
        mins = (remaining % 3600) // 60
        secs = remaining % 60
        return await ctx.send(f"⏳ You already claimed daily. Try again in {hrs}h {mins}m {secs}s.")
    await add_balance(ctx.author.id, DAILY_REWARD)
    await set_last_daily(ctx.author.id, now)
    await ctx.send(f"✨ You claimed **{DAILY_REWARD:,}** coins! Use `!balance` to check your total.")

@bot.command(name="leaderboard", help="Show top balances")
async def leaderboard_cmd(ctx):
    rows = await top_balances(10)
    if not rows:
        return await ctx.send("No data yet.")
    description = ""
    pos = 1
    for user_id, bal in rows:
        member = ctx.guild.get_member(user_id)
        name = member.display_name if member else f"<@{user_id}>"
        description += f"**{pos}.** {name} — {bal:,}\n"
        pos += 1
    embed = discord.Embed(title="🏆 Leaderboard", description=description, color=0xFFD700)
    await ctx.send(embed=embed)

@bot.command(name="slots", help="Play slot machine. Usage: !slots <bet>")
async def slots_cmd(ctx, bet: int):
    if bet <= 0:
        return await ctx.send("Bet must be a positive whole number.")
    await ensure_user(ctx.author.id)
    bal = await get_balance(ctx.author.id)
    if bet > bal:
        return await ctx.send("You don't have enough coins to bet that much.")
    # deduct bet immediately
    await add_balance(ctx.author.id, -bet)

    # spin animation (text-based)
    message = await ctx.send("Spinning... 🎰")
    # small "animation"
    for _ in range(3):
        interim = " | ".join([random.choice(REELS) for _ in range(3)])
        await message.edit(content=f"Spinning... {interim}")
        await asyncio.sleep(0.6)

    reels = spin_reels()
    outcome, payout = evaluate_spin(reels, bet)

    # payout
    if payout > 0:
        await add_balance(ctx.author.id, payout)
        result_text = f"🎉 **You won {payout:,} coins!** ({outcome})"
    else:
        result_text = "😢 No win this time. Better luck next spin!"

    final = f"{' | '.join(reels)}\n{result_text}\nYour balance: **{(await get_balance(ctx.author.id)):,}**"
    await message.edit(content=final)

# Keep commands working with any on_message handlers if added later
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

# -------------------------
# Start bot
# -------------------------
if __name__ == "__main__":
    token = os.getenv("TOKEN")
    if not token:
        print("ERROR: TOKEN environment variable not set.")
    else:
        bot.run(token)
