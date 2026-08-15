import logging
import os
import sys
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

log = logging.getLogger("bot")

TOKEN = os.environ.get("DISCORD_TOKEN")

if not TOKEN:
    log.error("DISCORD_TOKEN is not set in Railway Variables.")
    sys.exit(1)

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


@bot.command()
async def ping(ctx):
    await ctx.send(f"pong ({bot.latency * 1000:.0f} ms)")


@bot.command()
async def hello(ctx):
    await ctx.send("Choo choo! 🚅")


@bot.command()
async def remind(
    ctx,
    member: discord.Member = None,
    time: str = None,
    *message
):
    if member is None or time is None or not message:
        await ctx.send(
            "❌ გამოყენება:\n"
            "`!remind @კლიენტი 20:00 2000-ის გადახდა`"
        )
        return

    try:
        datetime.strptime(time, "%H:%M")
    except ValueError:
        await ctx.send(
            "❌ დრო უნდა იყოს HH:MM ფორმატში. მაგალითად: `20:00`"
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
        f"✅ **Reminder შექმნილია!**\n"
        f"👤 კლიენტი: {member.mention}\n"
        f"⏰ დრო: **{time}**\n"
        f"📝 ტექსტი: **{' '.join(message)}**\n"
        f"🔁 ყოველდღე"
    )


@bot.command()
async def reminders(ctx):
    if not reminders:
        await ctx.send("📭 აქტიური Reminders არ გაქვს.")
        return

    text = "📋 **აქტიური Reminders:**\n\n"

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
            "❌ გამოიყენე: `!cancel 1`"
        )
        return

    for reminder in reminders:
        if reminder["id"] == reminder_id:
            reminders.remove(reminder)
            save_reminders()

            await ctx.send(
                f"🗑️ Reminder **#{reminder_id}** გაუქმებულია."
            )
            return

    await ctx.send("❌ ასეთი Reminder ვერ მოიძებნა.")


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
                            f"⏰ **Reminder**\n"
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
