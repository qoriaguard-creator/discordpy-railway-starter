import logging
import os
import sys
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands
import google.generativeai as genai

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

log = logging.getLogger("bot")

TOKEN = os.environ.get("DISCORD_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
OPERATOR_CHANNEL_ID = int(os.environ.get("OPERATOR_CHANNEL_ID", "0"))

if not TOKEN:
    log.error("DISCORD_TOKEN is not set in Railway Variables.")
    sys.exit(1)

# Configure Gemini safely
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = genai.GenerativeModel('models/gemini-1.5-flash')
else:
    log.warning("GEMINI_API_KEY is missing. AI features will be disabled.")
    ai_model = None

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

REMINDERS_FILE = "reminders.json"
TIMEZONE = ZoneInfo("Asia/Tbilisi")


def load_reminders():
    if not os.path.exists(REMINDERS_FILE):
        return []

    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return []


def save_reminders():
    with open(REMINDERS_FILE, "w", encoding="utf-8") as file:
        json.dump(reminders, file, ensure_ascii=False, indent=2)


reminders = load_reminders()


@bot.event
async def on_ready():
    log.info("Logged in as %s", bot.user)

    if not hasattr(bot, "reminder_task"):
        bot.reminder_task = asyncio.create_task(reminder_loop())


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # AI Support in Operator Channel (if configured and not a command)
    if ai_model and OPERATOR_CHANNEL_ID and message.channel.id == OPERATOR_CHANNEL_ID and not message.content.startswith("!"):
        async with message.channel.typing():
            try:
                response = ai_model.generate_content(message.content)
                await message.reply(response.text)
            except Exception as e:
                log.error(f"AI Error: {e}")
                await message.reply(f"AI Error Details: {e}")

    await bot.process_commands(message)


@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! ({bot.latency * 1000:.0f} ms)")


@bot.command()
async def hello(ctx):
    await ctx.send("Ple- Please... Do Something")


@bot.command()
async def remind(
    ctx,
    member: discord.Member = None,
    time: str = None,
    *message
):
    if member is None or time is None or not message:
        await ctx.send(
            "❌ **Usage:**\n"
            "`!remind @client 20:00 Your reminder message here`"
        )
        return

    try:
        datetime.strptime(time, "%H:%M")
    except ValueError:
        await ctx.send(
            "❌ Time must be in `HH:MM` format. Example: `20:00`"
        )
        return

    reminder = {
        "id": max([r["id"] for r in reminders], default=0) + 1,
        "user_id": member.id,
        "time": time,
        "message": " ".join(message),
        "last_sent": None
    }

    reminders.append(reminder)
    save_reminders()

    await ctx.send(
        f"✅ **Reminder successfully created!**\n"
        f"👤 Client: {member.mention}\n"
        f"⏰ Time: **{time}**\n"
        f"📝 Message: **{' '.join(message)}**\n"
        f"🔁 Repeats daily"
    )


@bot.command(name="reminders")
async def list_reminders(ctx):
    if not reminders:
        await ctx.send("📭 You have no active reminders.")
        return

    text = "📋 **Active Reminders:**\n\n"

    for reminder in reminders:
        text += (
            f"**#{reminder['id']}** — <@{reminder['user_id']}>\n"
            f"⏰ {reminder['time']}\n"
            f"📝 {reminder['message']}\n\n"
        )

    await ctx.send(text)


@bot.command()
async def cancel(ctx, reminder_id: int = None):
    if reminder_id is None:
        await ctx.send(
            "❌ **Usage:** `!cancel [reminder_id]` (Example: `!cancel 1`)"
        )
        return

    for reminder in reminders:
        if reminder["id"] == reminder_id:
            reminders.remove(reminder)
            save_reminders()

            await ctx.send(
                f"🗑️ Reminder **#{reminder_id}** has been cancelled."
            )
            return

    await ctx.send("❌ Reminder with such ID was not found.")


async def reminder_loop():
    await bot.wait_until_ready()

    while not bot.is_closed():
        now = datetime.now(TIMEZONE)
        current_time = now.strftime("%H:%M")
        today = now.strftime("%Y-%m-%d")

        changed = False

        for reminder in reminders:
            if reminder["time"] == current_time:
                if reminder["last_sent"] != today:
                    try:
                        user = await bot.fetch_user(reminder["user_id"])

                        await user.send(
                            f"⏰ **Reminder Notification**\n"
                            f"📝 {reminder['message']}"
                        )

                        reminder["last_sent"] = today
                        changed = True

                    except Exception as e:
                        log.error(
                            "Could not send reminder #%s: %s",
                            reminder["id"],
                            e
                        )

        if changed:
            save_reminders()

        await asyncio.sleep(30)


bot.run(TOKEN)
    
