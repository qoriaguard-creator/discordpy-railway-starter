import logging
import os
import sys
import json
import asyncio
import platform
import random
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks

# 1. Advanced Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s -> %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

log = logging.getLogger("EnterpriseBot")

# 2. Environment Variables Validation
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    log.critical("FATAL ERROR: DISCORD_TOKEN environment variable is missing!")
    sys.exit(1)

# 3. Discord Intents Setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# 4. Global Constants & Storage Paths
REMINDERS_FILE = "reminders.json"
BACKUP_FILE = "reminders_backup.json"
ECONOMY_FILE = "economy.json"
EXPENSES_FILE = "expenses.json"
INVESTMENTS_FILE = "investments.json"

TIMEZONE = ZoneInfo("Asia/Tbilisi")
BOT_START_TIME = datetime.now(TIMEZONE)
CURRENCY_SYMBOL = "₾"  # ლარი / ეკონომიკური ნიშანი


# --- DATABASE LOADERS & SAVERS ---

def load_json_file(filename: str) -> dict | list:
    """Universal loader for JSON storage files with safe fallbacks."""
    if not os.path.exists(filename):
        return {} if filename in [ECONOMY_FILE, INVESTMENTS_FILE] else []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Error loading {filename}: {e}")
        return {} if filename in [ECONOMY_FILE, INVESTMENTS_FILE] else []


def save_json_file(filename: str, data):
    """Universal saver for JSON storage files."""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Error saving {filename}: {e}")


reminders = load_json_file(REMINDERS_FILE)
economy_data = load_json_file(ECONOMY_FILE)      # Format: {str(user_id): {"balance": 100, "last_daily": "...", "last_work": ...}}
expenses_data = load_json_file(EXPENSES_FILE)    # Format: {str(user_id): [{"category": "...", "amount": 25, "date": "..."}]}
investments_data = load_json_file(INVESTMENTS_FILE) # Format: {str(user_id): [{"id": 1, "asset": "crypto", "amount": 100, "end_time": timestamp}]}


def save_reminders_data():
    save_json_file(REMINDERS_FILE, reminders)
    save_json_file(BACKUP_FILE, reminders)

def save_economy_data():
    save_json_file(ECONOMY_FILE, economy_data)

def save_expenses_data():
    save_json_file(EXPENSES_FILE, expenses_data)

def save_investments_data():
    save_json_file(INVESTMENTS_FILE, investments_data)


def get_user_account(user_id: int) -> dict:
    """Ensures user has an economy account initialized."""
    uid = str(user_id)
    if uid not in economy_data:
        economy_data[uid] = {"balance": 0.0, "last_daily": "", "last_work": 0}
        save_economy_data()
    return economy_data[uid]


# 5. Interactive UI Components (Buttons)
class ReminderInteractiveView(discord.ui.View):
    def __init__(self, reminder_id: int):
        super().__init__(timeout=None)
        self.reminder_id = reminder_id

    @discord.ui.button(label="🗑️ Delete Reminder", style=discord.ButtonStyle.danger)
    async def delete_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        global reminders
        initial_count = len(reminders)
        reminders = [r for r in reminders if r["id"] != self.reminder_id]

        if len(reminders) < initial_count:
            save_reminders_data()
            embed = discord.Embed(
                title="🗑️ Reminder Deleted",
                description=f"Reminder **#{self.reminder_id}** was successfully removed.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            for child in self.children:
                child.disabled = True
            try:
                await interaction.message.edit(view=self)
            except Exception:
                pass
        else:
            await interaction.response.send_message(
                "❌ This reminder has already been deleted or does not exist.",
                ephemeral=True
            )


# 6. Bot Lifecycle Events
@bot.event
async def on_ready():
    log.info("--------------------------------------------------")
    log.info(f"Logged in successfully as: {bot.user.name} (ID: {bot.user.id})")
    log.info(f"Active Timezone: {TIMEZONE}")
    log.info(f"Loaded reminders: {len(reminders)} | Economy accounts: {len(economy_data)}")
    log.info("--------------------------------------------------")
    
    if not status_rotator.is_running():
        status_rotator.start()
    if not reminder_loop_task.is_running():
        reminder_loop_task.start()


# 7. Background Tasks
@tasks.loop(minutes=5)
async def status_rotator():
    try:
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(reminders)} reminders | !helpbot"
        )
        await bot.change_presence(activity=activity)
    except Exception as e:
        log.error(f"Status rotator error: {e}")

@status_rotator.before_loop
async def before_status_rotator():
    await bot.wait_until_ready()


@tasks.loop(seconds=30)
async def reminder_loop_task():
    try:
        now = datetime.now(TIMEZONE)
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        data_changed = False

        for reminder in reminders:
            if reminder["time"] == current_time:
                if reminder["last_sent"] != today:
                    try:
                        user = await bot.fetch_user(reminder["user_id"])
                        if user:
                            embed = discord.Embed(
                                title="⏰ Automated Reminder Alert",
                                description=reminder['message'],
                                color=discord.Color.orange(),
                                timestamp=now
                            )
                            await user.send(embed=embed)
                        reminder["last_sent"] = today
                        data_changed = True
                    except Exception as err:
                        log.error(f"Failed to deliver reminder #{reminder['id']}: {err}")

        if data_changed:
            save_reminders_data()
    except Exception as e:
        log.error(f"Reminder loop error: {e}")

@reminder_loop_task.before_loop
async def before_reminder_loop():
    await bot.wait_until_ready()


# 8. Help & System Commands
@bot.command(name="helpbot")
async def helpbot_command(ctx):
    """Displays comprehensive interactive command documentation."""
    embed = discord.Embed(
        title="🤖 Enterprise Bot - Help Panel",
        description="List of all available reminder, financial, and investment commands:",
        color=discord.Color.purple(),
        timestamp=datetime.now(TIMEZONE)
    )
    
    embed.add_field(name="⏰ Reminders", value="`!remind @user HH:MM msg`\n`!reminders`\n`!cancel [ID]`", inline=False)
    embed.add_field(name="💰 Economy & Money", value="`!balance` | `!bal`\n`!daily`\n`!work`\n`!pay @user amount`\n`!leaderboard` | `!rich`", inline=False)
    embed.add_field(name="📈 Investments (NEW)", value="`!invest_types`\n`!invest [asset] [amount]`\n`!investments`\n`!claim [ID]`", inline=False)
    embed.add_field(name="📊 Expenses Tracker", value="`!expense [category] [amount]`\n`!expenses`", inline=False)
    embed.add_field(name="🛠️ System", value="`!ping` | `!sysinfo` | `!currency`", inline=False)
    
    await ctx.send(embed=embed)


@bot.command(name="ping")
async def ping_command(ctx):
    latency_ms = round(bot.latency * 1000)
    await ctx.send(embed=discord.Embed(title="🏓 Pong!", description=f"Latency: **{latency_ms} ms**", color=discord.Color.green()))


@bot.command(name="sysinfo")
async def sysinfo_command(ctx):
    now = datetime.now(TIMEZONE)
    uptime = now - BOT_START_TIME
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    embed = discord.Embed(title="📊 System Diagnostics", color=discord.Color.blue())
    embed.add_field(name="Uptime", value=f"{hours}h {minutes}m {seconds}s", inline=False)
    embed.add_field(name="Active Reminders", value=str(len(reminders)), inline=True)
    embed.add_field(name="Economy Accounts", value=str(len(economy_data)), inline=True)
    embed.add_field(name="Python / OS", value=f"{platform.python_version()} / {platform.system()}", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="currency")
async def currency_command(ctx):
    embed = discord.Embed(
        title="💱 Currency Information",
        description=f"Active system currency symbol: **{CURRENCY_SYMBOL}**\nUse `!balance` to check your funds, `!work` to earn money, and `!invest` to grow capital.",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)


# --- ECONOMY & MONEY COMMANDS ---

@bot.command(name="balance", aliases=["bal"])
async def balance_command(ctx, member: discord.Member = None):
    target = member or ctx.author
    acc = get_user_account(target.id)
    
    embed = discord.Embed(
        title=f"💼 Balance for {target.display_name}",
        description=f"Current Funds: **{acc['balance']:.2f} {CURRENCY_SYMBOL}**",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)


@bot.command(name="daily")
async def daily_command(ctx):
    acc = get_user_account(ctx.author.id)
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")

    if acc["last_daily"] == today:
        await ctx.send("⏳ You have already claimed your daily bonus today! Come back tomorrow.")
        return

    bonus = 50.0
    acc["balance"] += bonus
    acc["last_daily"] = today
    save_economy_data()

    embed = discord.Embed(
        title="🎁 Daily Bonus Claimed!",
        description=f"You received **{bonus} {CURRENCY_SYMBOL}**!\nNew Balance: **{acc['balance']:.2f} {CURRENCY_SYMBOL}**",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)


@bot.command(name="work")
async def work_command(ctx):
    acc = get_user_account(ctx.author.id)
    current_timestamp = int(datetime.now().timestamp())
    cooldown = 3600  # 1 hour cooldown

    if current_timestamp - acc["last_work"] < cooldown:
        remaining = int((cooldown - (current_timestamp - acc["last_work"])) / 60)
        await ctx.send(f"⏳ You are tired! You can work again in **{remaining} minutes**.")
        return

    earned = round(random.uniform(10.0, 35.0), 2)
    acc["balance"] += earned
    acc["last_work"] = current_timestamp
    save_economy_data()

    embed = discord.Embed(
        title="🛠️ Job Completed",
        description=f"You worked hard and earned **{earned} {CURRENCY_SYMBOL}**!\nNew Balance: **{acc['balance']:.2f} {CURRENCY_SYMBOL}**",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)


@bot.command(name="pay")
async def pay_command(ctx, member: discord.Member = None, amount: float = None):
    if member is None or amount is None or amount <= 0:
        await ctx.send("❌ **Usage:** `!pay @user amount` (e.g., `!pay @John 25`)")
        return

    if member.id == ctx.author.id:
        await ctx.send("❌ You cannot send money to yourself.")
        return

    sender_acc = get_user_account(ctx.author.id)
    if sender_acc["balance"] < amount:
        await ctx.send(f"❌ Insufficient funds! Your balance is **{sender_acc['balance']:.2f} {CURRENCY_SYMBOL}**.")
        return

    receiver_acc = get_user_account(member.id)
    sender_acc["balance"] -= amount
    receiver_acc["balance"] += amount
    save_economy_data()

    embed = discord.Embed(
        title="💸 Money Transfer Successful",
        description=f"Successfully transferred **{amount:.2f} {CURRENCY_SYMBOL}** to {member.mention}.",
        color=discord.Color.teal()
    )
    await ctx.send(embed=embed)


@bot.command(name="leaderboard", aliases=["rich"])
async def leaderboard_command(ctx):
    if not economy_data:
        await ctx.send("📭 Economy registry is empty.")
        return

    sorted_users = sorted(economy_data.items(), key=lambda x: x[1]["balance"], reverse=True)[:10]
    embed = discord.Embed(title="🏆 Server Wealth Leaderboard (Top 10)", color=discord.Color.gold())
    
    desc = ""
    for idx, (uid, data) in enumerate(sorted_users, 1):
        user = ctx.guild.get_member(int(uid))
        name = user.display_name if user else f"User ID: {uid}"
        desc += f"**{idx}.** {name} — **{data['balance']:.2f} {CURRENCY_SYMBOL}**\n"

    embed.description = desc
    await ctx.send(embed=embed)


@bot.command(name="addmoney")
@commands.has_permissions(administrator=True)
async def addmoney_command(ctx, member: discord.Member = None, amount: float = None):
    if member is None or amount is None or amount <= 0:
        await ctx.send("❌ **Usage:** `!addmoney @user amount`")
        return

    acc = get_user_account(member.id)
    acc["balance"] += amount
    save_economy_data()
    await ctx.send(f"✅ Added **{amount:.2f} {CURRENCY_SYMBOL}** to {member.mention}'s account.")


@bot.command(name="removemoney")
@commands.has_permissions(administrator=True)
async def removemoney_command(ctx, member: discord.Member = None, amount: float = None):
    if member is None or amount is None or amount <= 0:
        await ctx.send("❌ **Usage:** `!removemoney @user amount`")
        return

    acc = get_user_account(member.id)
    acc["balance"] = max(0.0, acc["balance"] - amount)
    save_economy_data()
    await ctx.send(f"✅ Removed **{amount:.2f} {CURRENCY_SYMBOL}** from {member.mention}'s account.")


# --- 📈 NEW INVESTMENT SYSTEM COMMANDS ---

# Available investment tiers configuration
INVESTMENT_TIERS = {
    "deposit": {"name": "Safe Deposit (უსაფრთხო)", "min": 50, "duration": 300, "return_min": 1.05, "return_max": 1.15},  # 5 mins for testing (or scale up)
    "startup": {"name": "Startup Business (სტარტაპი)", "min": 200, "duration": 600, "return_min": 0.85, "return_max": 1.40},
    "crypto":  {"name": "Crypto Exchange (კრიპტო ბირჟა)", "min": 500, "duration": 900, "return_min": 0.50, "return_max": 2.00}
}

@bot.command(name="invest_types")
async def invest_types_command(ctx):
    """Shows available investment types and risks."""
    embed = discord.Embed(title="📈 Available Investment Portfolios", color=discord.Color.blue())
    for key, info in INVESTMENT_TIERS.items():
        embed.add_field(
            name=f"`{key}` — {info['name']}",
            value=f"• Min Amount: **{info['min']} {CURRENCY_SYMBOL}**\n• Lock Duration: **{info['duration']//60} mins**\n• Potential Return: **{int((info['return_min']-1)*100)}% to {int((info['return_max']-1)*100)}%**",
            inline=False
        )
    await ctx.send(embed=embed)


@bot.command(name="invest")
async def invest_command(ctx, asset: str = None, amount: float = None):
    """Invests money into a selected financial portfolio."""
    if not asset or not amount or amount <= 0:
        await ctx.send("❌ **Usage:** `!invest [asset] [amount]`\n*Example:* `!invest crypto 500`\n*Tip:* Use `!invest_types` to view portfolios.")
        return

    asset = asset.lower()
    if asset not in INVESTMENT_TIERS:
        await ctx.send("❌ Invalid asset type! Type `!invest_types` to see valid options.")
        return

    tier = INVESTMENT_TIERS[asset]
    if amount < tier["min"]:
        await ctx.send(f"❌ Minimum investment for **{tier['name']}** is **{tier['min']} {CURRENCY_SYMBOL}**.")
        return

    acc = get_user_account(ctx.author.id)
    if acc["balance"] < amount:
        await ctx.send(f"❌ Insufficient funds! You have **{acc['balance']:.2f} {CURRENCY_SYMBOL}**.")
        return

    # Deduct funds from balance
    acc["balance"] -= amount
    save_economy_data()

    uid = str(ctx.author.id)
    if uid not in investments_data:
        investments_data[uid] = []

    # Generate unique investment ID
    all_inv_ids = [inv["id"] for user_invs in investments_data.values() for inv in user_invs]
    new_inv_id = max(all_inv_ids, default=0) + 1

    current_timestamp = int(datetime.now(TIMEZONE).timestamp())
    end_time = current_timestamp + tier["duration"]

    investment_entry = {
        "id": new_inv_id,
        "asset": asset,
        "amount": amount,
        "end_time": end_time
    }

    investments_data[uid].append(investment_entry)
    save_investments_data()

    embed = discord.Embed(
        title="📈 Investment Successfully Placed!",
        description=f"You invested **{amount:.2f} {CURRENCY_SYMBOL}** into **{tier['name']}**.",
        color=discord.Color.green()
    )
    embed.add_field(name="Investment ID", value=f"#{new_inv_id}", inline=True)
    embed.add_field(name="Maturity Time", value=f"<t:{end_time}:R>", inline=True)
    await ctx.send(embed=embed)


@bot.command(name="investments")
async def investments_command(ctx):
    """Lists your active investments and statuses."""
    uid = str(ctx.author.id)
    user_investments = investments_data.get(uid, [])

    if not user_investments:
        await ctx.send("📭 You have no active investments. Use `!invest` to start.")
        return

    current_timestamp = int(datetime.now(TIMEZONE).timestamp())
    embed = discord.Embed(title=f"📈 Active Investments for {ctx.author.display_name}", color=discord.Color.purple())
    
    for inv in user_investments:
        tier_info = INVESTMENT_TIERS.get(inv["asset"], {"name": inv["asset"]})
        ready = current_timestamp >= inv["end_time"]
        status_text = "✅ **Ready to Claim!** (`!claim " + str(inv["id"]) + "`)" if ready else f"⏳ Maturity: <t:{inv['end_time']}:R>"
        
        embed.add_field(
            name=f"ID #{inv['id']} | {tier_info['name']}",
            value=f"Amount: **{inv['amount']:.2f} {CURRENCY_SYMBOL}**\nStatus: {status_text}",
            inline=False
        )
    await ctx.send(embed=embed)


@bot.command(name="claim")
async def claim_command(ctx, investment_id: int = None):
    """Claims returns from a matured investment."""
    if investment_id is None:
        await ctx.send("❌ **Usage:** `!claim [investment_id]`")
        return

    uid = str(ctx.author.id)
    user_investments = investments_data.get(uid, [])

    target_inv = None
    for inv in user_investments:
        if inv["id"] == investment_id:
            target_inv = inv
            break

    if not target_inv:
        await ctx.send(f"❌ Investment ID **#{investment_id}** not found in your portfolio.")
        return

    current_timestamp = int(datetime.now(TIMEZONE).timestamp())
    if current_timestamp < target_inv["end_time"]:
        await ctx.send(f"⏳ This investment has not matured yet! Ready <t:{target_inv['end_time']}:R>.")
        return

    # Remove investment from active list
    user_investments = [inv for inv in user_investments if inv["id"] != investment_id]
    investments_data[uid] = user_investments
    save_investments_data()

    # Calculate payout
    tier = INVESTMENT_TIERS[target_inv["asset"]]
    multiplier = random.uniform(tier["return_min"], tier["return_max"])
    payout = round(target_inv["amount"] * multiplier, 2)
    profit = round(payout - target_inv["amount"], 2)

    acc = get_user_account(ctx.author.id)
    acc["balance"] += payout
    save_economy_data()

    color = discord.Color.green() if profit >= 0 else discord.Color.red()
    embed = discord.Embed(title="📊 Investment Matured & Claimed", color=color)
    embed.add_field(name="Initial Capital", value=f"{target_inv['amount']:.2f} {CURRENCY_SYMBOL}", inline=True)
    embed.add_field(name="Final Payout", value=f"{payout:.2f} {CURRENCY_SYMBOL}", inline=True)
    embed.add_fiel
