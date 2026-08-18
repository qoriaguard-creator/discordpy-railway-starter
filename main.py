import logging
import os
import sys
import json
import asyncio
import platform
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

TIMEZONE = ZoneInfo("Asia/Tbilisi")
BOT_START_TIME = datetime.now(TIMEZONE)
CURRENCY_SYMBOL = "₾"  # ლარი / ეკონომიკური ნიშანი


# --- DATABASE LOADERS & SAVERS ---

def load_json_file(filename: str) -> dict | list:
    """Universal loader for JSON storage files with safe fallbacks."""
    if not os.path.exists(filename):
        return {} if filename == ECONOMY_FILE else []
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Error loading {filename}: {e}")
        return {} if filename == ECONOMY_FILE else []


def save_json_file(filename: str, data):
    """Universal saver for JSON storage files."""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.error(f"Error saving {filename}: {e}")


reminders = load_json_file(REMINDERS_FILE)
economy_data = load_json_file(ECONOMY_FILE)  # Format: {str(user_id): {"balance": 100, "last_daily": "YYYY-MM-DD", "last_work": timestamp}}
expenses_data = load_json_file(EXPENSES_FILE)  # Format: {str(user_id): [{"category": "Food", "amount": 25, "date": "..."}]}


def save_reminders_data():
    save_json_file(REMINDERS_FILE, reminders)
    save_json_file(BACKUP_FILE, reminders)

def save_economy_data():
    save_json_file(ECONOMY_FILE, economy_data)

def save_expenses_data():
    save_json_file(EXPENSES_FILE, expenses_data)


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
        description="List of all available reminder and financial commands:",
        color=discord.Color.purple(),
        timestamp=datetime.now(TIMEZONE)
    )
    
    embed.add_field(name="⏰ Reminders", value="`!remind @user HH:MM msg`\n`!reminders`\n`!cancel [ID]`", inline=False)
    embed.add_field(name="💰 Economy & Money", value="`!balance` | `!bal`\n`!daily`\n`!work`\n`!pay @user amount`\n`!leaderboard` | `!rich`", inline=False)
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
        description=f"Active system currency symbol: **{CURRENCY_SYMBOL}**\nUse `!balance` to check your funds, `!work` to earn money, and `!daily` to claim daily rewards.",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)


# --- 10 NEW ECONOMY & MONEY COMMANDS ---

@bot.command(name="balance", aliases=["bal"])
async def balance_command(ctx, member: discord.Member = None):
    """1. Checks balance for yourself or another user."""
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
    """2. Claims daily free bonus money."""
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
    """3. Works to earn money (with cooldown check)."""
    acc = get_user_account(ctx.author.id)
    current_timestamp = int(datetime.now().timestamp())
    cooldown = 3600  # 1 hour cooldown

    if current_timestamp - acc["last_work"] < cooldown:
        remaining = int((cooldown - (current_timestamp - acc["last_work"])) / 60)
        await ctx.send(f"⏳ You are tired! You can work again in **{remaining} minutes**.")
        return

    import random
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
    """4. Transfers money from your account to another user."""
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
    """5. Displays top 10 richest users on the server."""
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
    """6. Admin command to add money to user account."""
    if member is None or amount is None or amount <= 0:
        await ctx.send("❌ **Usage:** `!addmoney @user amount`")
        return

    acc = get_user_account(member.id)
    acc["balance"] += amount
    save_economy_data()

    await ctx.send(f"✅ Added **{amount:.2f} {CURRENCY_SYMBOL}** to {member.mention}'s account. New balance: **{acc['balance']:.2f} {CURRENCY_SYMBOL}**.")


@bot.command(name="removemoney")
@commands.has_permissions(administrator=True)
async def removemoney_command(ctx, member: discord.Member = None, amount: float = None):
    """7. Admin command to remove money from user account."""
    if member is None or amount is None or amount <= 0:
        await ctx.send("❌ **Usage:** `!removemoney @user amount`")
        return

    acc = get_user_account(member.id)
    acc["balance"] = max(0.0, acc["balance"] - amount)
    save_economy_data()

    await ctx.send(f"✅ Removed **{amount:.2f} {CURRENCY_SYMBOL}** from {member.mention}'s account. New balance: **{acc['balance']:.2f} {CURRENCY_SYMBOL}**.")


@bot.command(name="expense")
async def expense_command(ctx, category: str = None, amount: float = None):
    """8. Records a personal expense item."""
    if category is None or amount is None or amount <= 0:
        await ctx.send("❌ **Usage:** `!expense [category] [amount]` (e.g., `!expense Food 15.50`)")
        return

    uid = str(ctx.author.id)
    if uid not in expenses_data:
        expenses_data[uid] = []

    expense_entry = {
        "category": category,
        "amount": amount,
        "date": datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M")
    }

    expenses_data[uid].append(expense_entry)
    save_expenses_data()

    await ctx.send(f"📝 Recorded expense: **{category}** — **{amount:.2f} {CURRENCY_SYMBOL}**.")


@bot.command(name="expenses")
async def expenses_command(ctx):
    """9. Lists your recorded expenses."""
    uid = str(ctx.author.id)
    user_expenses = expenses_data.get(uid, [])

    if not user_expenses:
        await ctx.send("📭 You have no recorded expenses.")
        return

    embed = discord.Embed(title=f"📊 Expenses for {ctx.author.display_name}", color=discord.Color.red())
    total = 0.0
    desc = ""

    for exp in user_expenses[-10:]:  # Last 10 expenses
        desc += f"• **{exp['category']}**: {exp['amount']:.2f} {CURRENCY_SYMBOL} *({exp['date']})*\n"
        total += exp["amount"]

    embed.description = desc
    embed.set_footer(text=f"Total Tracked Expenses: {total:.2f} {CURRENCY_SYMBOL}")
    await ctx.send(embed=embed)


@bot.command(name="resetexpenses")
async def resetexpenses_command(ctx):
    """10. Clears all your recorded personal expenses."""
    uid = str(ctx.author.id)
    if uid in expenses_data:
        expenses_data[uid] = []
        save_expenses_data()
        await ctx.send("🗑️ Your personal expense registry has been cleared.")
    else:
        await ctx.send("📭 You don't have any recorded expenses.")


# --- REMINDER COMMANDS ---

@bot.command(name="remind")
async def remind_command(ctx, member: discord.Member = None, time_str: str = None, *, message: str = None):
    if member is None or time_str is None or not message:
        await ctx.send("❌ **Usage:** `!remind @user 14:30 Your message here`")
        return

    try:
        parsed_time = datetime.strptime(time_str, "%H:%M")
        formatted_time = parsed_time.strftime("%H:%M")
    except ValueError:
        await ctx.send("❌ Error: Time must follow `HH:MM` format.")
        return

    new_id = max([r["id"] for r in reminders], default=0) + 1
    reminder_entry = {
        "id": new_id,
        "user_id": member.id,
        "time": formatted_time,
        "message": message,
        "last_sent": None
    }

    reminders.append(reminder_entry)
    save_reminders_data()

    view = ReminderInteractiveView(new_id)
    embed = discord.Embed(title="✅ Reminder Created", color=discord.Color.teal())
    embed.add_field(name="ID", value=f"#{new_id}", inline=True)
    embed.add_field(name="User", value=member.mention, inline=True)
    embed.add_field(name="Time", value=formatted_time, inline=True)
    embed.add_field(name="Message", value=message, inline=False)
    await ctx.send(embed=embed, view=view)


@bot.command(name="reminders")
async def list_reminders_command(ctx):
    if not reminders:
        await ctx.send("📭 No active reminders.")
        return

    await ctx.send(f"📋 **Active Reminders ({len(reminders)}):**")
    for reminder in reminders:
        view = ReminderInteractiveView(reminder["id"])
        embed = discord.Embed(title=f"Reminder ID #{reminder['id']}", color=discord.Color.blurple())
        embed.add_field(name="User", value=f"<@{reminder['user_id']}>", inline=True)
        embed.add_field(name="Time", value=reminder['time'], inline=True)
        embed.add_field(name="Message", value=reminder['message'], inline=False)
        await ctx.send(embed=embed, view=view)


@bot.command(name="cancel")
async def cancel_command(ctx, reminder_id: int = None):
    if reminder_id is None:
        await ctx.send("❌ **Usage:** `!cancel [reminder_id]`")
        return

    global reminders
    initial_count = len(reminders)
    reminders = [r for r in reminders if r["id"] != reminder_id]

    if len(reminders) < initial_count:
        save_reminders_data()
        await ctx.send(f"🗑️ Reminder **#{reminder_id}** cancelled successfully.")
    else:
        await ctx.send(f"❌ Reminder ID **#{reminder_id}** not found.")


# 9. Execute Bot Instance
if __name__ == "__main__":
    bot.run(TOKEN)
    
