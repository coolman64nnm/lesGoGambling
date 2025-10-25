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

# BALANCE helpers
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
    amount = int(max(0, amount))
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

# FISH helpers
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

# ITEMS helpers
async def get_item(user_id: int, item_name: str) -> int:
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT amount FROM items WHERE user_id = ? AND item_name = ?", (user_id, item_name))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

async def add_item(user_id: int, item_name: str, amount: int):
    await ensure_user(user_id)
    amount = int(amount)
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT amount FROM items WHERE user_id = ? AND item_name = ?", (user_id, item_name))
        row = await cur.fetchone()
        if row:
            await db.execute("UPDATE items SET amount = amount + ? WHERE user_id = ? AND item_name = ?",
                             (amount, user_id, item_name))
        else:
            await db.execute("INSERT INTO items (user_id, item_name, amount) VALUES (?, ?, ?)",
                             (user_id, item_name, amount))
        await db.commit()

async def set_item(user_id: int, item_name: str, amount: int):
    await ensure_user(user_id)
    amount = max(0, int(amount))
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("INSERT OR REPLACE INTO items (user_id, item_name, amount) VALUES (?, ?, ?)",
                         (user_id, item_name, amount))
        await db.commit()

# COOLDOWN helpers
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

async def get_last_fish(user_id: int) -> int:
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT last_fish FROM cooldowns WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

async def set_last_fish(user_id: int, ts: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE cooldowns SET last_fish = ? WHERE user_id = ?", (int(ts), user_id))
        await db.commit()

# PET helpers
async def get_pet(user_id: int):
    await ensure_user(user_id)
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT name, level, happiness, exp FROM pets WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return ("Lucky", 1, 100, 0)
        return (row[0], int(row[1]), int(row[2]), int(row[3]))

async def update_pet(user_id: int, **kwargs):
    if not kwargs:
        return
    keys = ", ".join(f"{k} = ?" for k in kwargs.keys())
    vals = list(kwargs.values()) + [user_id]
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(f"UPDATE pets SET {keys} WHERE user_id = ?", vals)
        await db.commit()

# LEADERBOARD
async def top_fish(limit: int = 10):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT user_id, fish_count FROM fish ORDER BY fish_count DESC LIMIT ?", (limit,))
        return await cur.fetchall()

async def top_balance(limit: int = 10):
    async with aiosqlite.connect(DATABASE) as db:
        cur = await db.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,))
        return await cur.fetchall()

# -------------------------
# Utility
# -------------------------
def is_admin_role(member: discord.Member):
    if OWNER_ID and member.id == OWNER_ID:
        return True
    return any(r.name == ADMIN_ROLE for r in member.roles)

def fmt(num: int) -> str:
    return f"{num:,}"

# -------------------------
# Bot events
# -------------------------
@bot.event
async def on_ready():
    print(f"✅ FishNuke bot online as {bot.user} (id: {bot.user.id})")
    await init_db()
    # auto-create admin role and assign to OWNER_ID if provided and present in guilds
    if OWNER_ID:
        for guild in bot.guilds:
            member = guild.get_member(OWNER_ID)
            if member:
                role = discord.utils.get(guild.roles, name=ADMIN_ROLE)
                if not role:
                    try:
                        role = await guild.create_role(name=ADMIN_ROLE, permissions=discord.Permissions(permissions=0))
                        print(f"Created role {ADMIN_ROLE} in guild {guild.name}")
                    except Exception:
                        role = discord.utils.get(guild.roles, name=ADMIN_ROLE)
                if role and role not in member.roles:
                    try:
                        await member.add_roles(role)
                        print(f"Assigned {ADMIN_ROLE} to {member.display_name} in {guild.name}")
                    except Exception as e:
                        print("Could not assign role (missing Manage Roles):", e)

# -------------------------
# Commands: economy & basic
# -------------------------
@bot.command(name="balance")
async def cmd_balance(ctx, member: discord.Member = None):
    target = member or ctx.author
    await ensure_user(target.id)
    bal = await get_balance(target.id)
    await ctx.send(f"💰 {target.display_name} has **{fmt(bal)}** coins.")

@bot.command(name="daily")
async def cmd_daily(ctx):
    await ensure_user(ctx.author.id)
    now = int(time.time())
    # check last_daily
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
    await ctx.send(f"✨ You claimed **{fmt(DAILY_REWARD)}** coins!")

# -------------------------
# Commands: fishing
# -------------------------
@bot.command(name="fish")
async def cmd_fish(ctx):
    await ensure_user(ctx.author.id)
    now = int(time.time())
    last = await get_last_fish(ctx.author.id)
    # small per-user cooldown (enforced in DB to be robust)
    if now - last < 5:  # 5s minimal server-side safety
        return await ctx.send("⏳ Slow down! Try again in a few seconds.")
    # chance to yield better catch based on rod level (item 'rod' amount)
    rod_level = await get_item(ctx.author.id, "rod")
    # rod_level >0 reduces chance of tiny catches and increases max
    max_catch = MAX_CATCH + min(10, rod_level)
    caught = random.randint(1, max_catch)
    # rare big catch
    if random.random() < 0.05 + (rod_level * 0.01):
        bonus = random.randint(3, 12)
        caught += bonus
        note = f" — huge catch! +{bonus}"
    else:
        note = ""
    # reward coins for fish: 1 fish = random 5-15 coins (scale with rod)
    coin_per_fish = random.randint(5, 15) + rod_level
    coins = caught * coin_per_fish
    await add_fish(ctx.author.id, caught)
    await add_balance(ctx.author.id, coins)
    await set_last_fish(ctx.author.id, now)
    # xp gain
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (caught * 2, ctx.author.id))
        await db.commit()
    await ctx.send(f"🎣 {ctx.author.display_name} caught **{caught}** fish{note} and earned **{fmt(coins)}** coins!")

# -------------------------
# ITEMS: shop/buy/inventory
# -------------------------
@bot.command(name="shop")
async def cmd_shop(ctx):
    desc = ""
    for k, v in SHOP.items():
        desc += f"**{k}** — {v['price']} coins — {v['desc']}\n"
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
    cost = SHOP[item]["price"] * amount
    bal = await get_balance(ctx.author.id)
    if cost > bal:
        return await ctx.send(f"💸 You need {fmt(cost)} coins but you only have {fmt(bal)}.")
    await add_balance(ctx.author.id, -cost)
    if item == "rod":
        # rods are stackable: each increases rod_level
        await add_item(ctx.author.id, "rod", amount)
    else:
        await add_item(ctx.author.id, item, amount)
    await ctx.send(f"✅ You bought {amount} x **{item}** for {fmt(cost)} coins.")

@bot.command(name="inventory")
async def cmd_inventory(ctx, member: discord.Member = None):
    target = member or ctx.author
    await ensure_user(target.id)
    fish = await get_fish(target.id)
    nukes = await get_item(target.id, "nuke")
    rod_level = await get_item(target.id, "rod")
    petfood = await get_item(target.id, "petfood")
    bal = await get_balance(target.id)
    embed = discord.Embed(title=f"📦 {target.display_name}'s Inventory", color=0x88FF88)
    embed.add_field(name="Coins", value=fmt(bal), inline=True)
    embed.add_field(name="Fish", value=fmt(fish), inline=True)
    embed.add_field(name="Nukes", value=fmt(nukes), inline=True)
    embed.add_field(name="Rods (level)", value=fmt(rod_level), inline=True)
    embed.add_field(name="Pet Food", value=fmt(petfood), inline=True)
    await ctx.send(embed=embed)

# -------------------------
# Command: nuke (safe in-game)
# -------------------------
@bot.command(name="nuke")
@commands.cooldown(1, NUKE_COOLDOWN, commands.BucketType.user)
async def cmd_nuke(ctx, target: discord.Member = None):
    # If no target, make it an area nuke gamble on self
    await ensure_user(ctx.author.id)
    if target is None:
        # gamble nuke: pay coins to "detonate" for random big reward or loss
        bal = await get_balance(ctx.author.id)
        cost = NUKE_PRICE
        if bal < cost and not is_admin_role(ctx.author):
            return await ctx.send(f"💸 You need {fmt(cost)} coins to detonate a nuke (you have {fmt(bal)}).")
        # admin bypass
        if not is_admin_role(ctx.author):
            await add_balance(ctx.author.id, -cost)
        # big random outcome
        roll = random.random()
        if roll < 0.5:
            # bad: lose some fish & coins
            lost = max(1, int((await get_fish(ctx.author.id)) * random.uniform(0.1, 0.5)))
            await set_fish(ctx.author.id, max(0, await get_fish(ctx.author.id) - lost))
            lost_coins = int(cost * 0.8)
            await add_balance(ctx.author.id, -lost_coins)
            await ctx.send(f"💥 You detonated your own nuke and it backfired! Lost **{fmt(lost)}** fish and **{fmt(lost_coins)}** coins.")
        else:
            # good: huge reward
            gain = cost * random.randint(2, 8)
            await add_balance(ctx.author.id, gain)
            await ctx.send(f"💣 You detonated a glorious nuke and gained **{fmt(gain)}** coins!")
        await set_last_nuke(ctx.author.id, int(time.time()))
        return

    # target provided: consume a nuke item (if not admin)
    if target.id == ctx.author.id:
        return await ctx.send("❌ You can't nuke yourself (target your own detonate without a target by using `!nuke`).")
    await ensure_user(target.id)
    nukes = await get_item(ctx.author.id, "nuke")
    if nukes <= 0 and not is_admin_role(ctx.author):
        return await ctx.send("💥 You don't have any nukes. Buy one with `!buy nuke`.")
    # consume nuke
    if not is_admin_role(ctx.author):
        await add_item(ctx.author.id, "nuke", -1)
    # calc damage
    target_fish = await get_fish(target.id)
    if target_fish <= 0:
        return await ctx.send("🫥 Target has no fish to nuke.")
    pct = random.randint(10, 60)  # percent destroyed
    destroyed = max(1, (target_fish * pct) // 100)
    salvage = max(0, (destroyed * 30) // 100)  # attacker gets 30% of destroyed as fish
    new_target = max(0, target_fish - destroyed)
    await set_fish(target.id, new_target)
    await add_fish(ctx.author.id, salvage)
    # optional coin salvage
    coin_salvage = int(salvage * random.randint(5, 12))
    await add_balance(ctx.author.id, coin_salvage)
    await set_last_nuke(ctx.author.id, int(time.time()))
    embed = discord.Embed(title="💥 FISH NUKE!", color=0xFF4444)
    embed.add_field(name="Attacker", value=ctx.author.display_name, inline=True)
    embed.add_field(name="Target", value=target.display_name, inline=True)
    embed.add_field(name="Destroyed", value=f"{fmt(destroyed)} fish ({pct}%)", inline=False)
    embed.add_field(name="Salvaged Fish", value=f"{fmt(salvage)} fish", inline=True)
    embed.add_field(name="Salvaged Coins", value=f"{fmt(coin_salvage)} coins", inline=True)
    await ctx.send(embed=embed)

@cmd_nuke.error
async def cmd_nuke_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        remaining = int(error.retry_after)
        hrs = remaining // 3600
        mins = (remaining % 3600) // 60
        secs = remaining % 60
        await ctx.send(f"⏳ Nuke cooldown. Try again in {hrs}h {mins}m {secs}s.")
    else:
        raise error

# -------------------------
# PET commands
# -------------------------
@bot.command(name="pet")
async def cmd_pet(ctx):
    await ensure_user(ctx.author.id)
    name, level, happiness, exp = await get_pet(ctx.author.id)
    await ctx.send(f"🐾 {ctx.author.display_name}'s pet **{name}** — Level {level}\n💖 Happiness: {happiness}/100 • EXP: {exp}")

@bot.command(name="adopt")
async def cmd_adopt(ctx, *, name: str = "Lucky"):
    await ensure_user(ctx.author.id)
    await update_pet(ctx.author.id, name=name[:32], level=1, happiness=100, exp=0)
    await ctx.send(f"🎉 You adopted a new pet named **{name[:32]}**!")

@bot.command(name="feedpet")
async def cmd_feedpet(ctx, amount: int = 1):
    if amount <= 0:
        return await ctx.send("Amount must be positive.")
    await ensure_user(ctx.author.id)
    food = await get_item(ctx.author.id, "petfood")
    if food < amount:
        return await ctx.send(f"🍪 You don't have that much pet food (you have {fmt(food)}).")
    await add_item(ctx.author.id, "petfood", -amount)
    name, level, happiness, exp = await get_pet(ctx.author.id)
    new_hap = min(100, happiness + 10 * amount)
    await update_pet(ctx.author.id, happiness=new_hap)
    await ctx.send(f"🧁 You fed **{name}**. Happiness is now {new_hap}/100.")

@bot.command(name="renamepet")
async def cmd_renamepet(ctx, *, new_name: str):
    await ensure_user(ctx.author.id)
    await update_pet(ctx.author.id, name=new_name[:32])
    await ctx.send(f"✏️ Pet renamed to **{new_name[:32]}**.")

@bot.command(name="playpet")
async def cmd_playpet(ctx):
    await ensure_user(ctx.author.id)
    name, level, happiness, exp = await get_pet(ctx.author.id)
    if happiness < 20:
        return await ctx.send(f"😢 {name} is too sad to play. Feed them first.")
    gain_exp = random.randint(5, 20)
    new_exp = exp + gain_exp
    new_hap = max(0, happiness - random.randint(5, 15))
    new_level = level
    # level-up threshold
    if new_exp >= (level * 100):
        new_exp -= level * 100
        new_level = level + 1
    await update_pet(ctx.author.id, exp=new_exp, happiness=new_hap, level=new_level)
    await ctx.send(f"🎾 You played with **{name}**. +{gain_exp} EXP. Level: {new_level}. Happiness: {new_hap}/100")

# -------------------------
# ADMIN tools
# -------------------------
@bot.command(name="give")
@commands.has_role(ADMIN_ROLE)
async def cmd_give(ctx, member: discord.Member, amount: int):
    if amount == 0:
        return await ctx.send("Amount cannot be zero.")
    await ensure_user(member.id)
    await add_balance(member.id, amount)
    await ctx.send(f"✅ Gave {member.display_name} **{fmt(amount)}** coins.")

@cmd_give.error
async def cmd_give_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        # allow OWNER_ID bypass
        if OWNER_ID and ctx.author.id == OWNER_ID:
            return
        return await ctx.send("❌ You don't have permission to use this command.")
    else:
        raise error

@bot.command(name="setbalance")
@commands.has_role(ADMIN_ROLE)
async def cmd_setbalance(ctx, member: discord.Member, amount: int):
    if amount < 0:
        return await ctx.send("Balance cannot be negative.")
    await set_balance(member.id, amount)
    await ctx.send(f"✅ Set {member.display_name}'s balance to **{fmt(amount)}** coins.")

@cmd_setbalance.error
async def cmd_setbalance_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        if OWNER_ID and ctx.author.id == OWNER_ID:
            return
        return await ctx.send("❌ You don't have permission to use this command.")
    else:
        raise error

# -------------------------
# Leaderboards
# -------------------------
@bot.command(name="leaderboard")
async def cmd_leaderboard(ctx):
    b_rows = await top_balance(10)
    f_rows = await top_fish(10)
    desc_b = ""
    desc_f = ""
    pos = 1
    for uid, bal in b_rows:
        member = ctx.guild.get_member(uid)
        name = member.display_name if member else f"<@{uid}>"
        desc_b += f"**{pos}.** {name} — {fmt(bal)} coins\n"
        pos += 1
    pos = 1
    for uid, fish_count in f_rows:
        member = ctx.guild.get_member(uid)
        name = member.display_name if member else f"<@{uid}>"
        desc_f += f"**{pos}.** {name} — {fmt(fish_count)} fish\n"
        pos += 1
    embed = discord.Embed(title="🏆 Leaderboards", color=0xFFD700)
    embed.add_field(name="Top Coins", value=desc_b or "No data", inline=True)
    embed.add_field(name="Top Fish", value=desc_f or "No data", inline=True)
    await ctx.send(embed=embed)

# -------------------------
# Error handlers & safety
# -------------------------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return  # ignore unknown commands
    # default fallback: print and inform
    print("Command error:", error)
    await ctx.send(f"❌ Error: {str(error)}")

# -------------------------
# Start bot
# -------------------------
if __name__ == "__main__":
    if not TOKEN:
        print("ERROR: TOKEN environment variable not set. Set TOKEN before running.")
    else:
        bot.run(TOKEN)
