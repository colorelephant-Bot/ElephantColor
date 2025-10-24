import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from prettytable import PrettyTable
from flask import Flask, request

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- Environment Variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app-name.onrender.com/webhook

# --- Flask App for Render Ping + Webhook endpoint ---
flask_app = Flask(__name__)
telegram_app = None  # will hold Application instance


# --- Telegram Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Please enter your current balance:")


async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        balance = float(update.message.text)

        # Case 1 (Win Scenario)
        case1 = [10, 10, 15, 30, 55]
        table1 = PrettyTable(["Round", "Percentage", "Amount"])
        for i, p in enumerate(case1, start=1):
            table1.add_row([i, f"{p}%", f"{(balance * p / 100):.2f}"])

        # Case 2 (Lose Scenario)
        case2 = [10, 25, 65]
        table2 = PrettyTable(["Round", "Percentage", "Amount"])
        for i, p in enumerate(case2, start=1):
            table2.add_row([i, f"{p}%", f"{(balance * p / 100):.2f}"])

        msg = (
            f"💰 *Initial Balance:* {balance:.2f}\n\n"
            f"📊 *Case 1 (Win Scenario)*\n```\n{table1}\n```\n"
            f"📉 *Case 2 (Lose Scenario)*\n```\n{table2}\n```"
        )

        await update.message.reply_text(msg, parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number for your balance.")


# --- Flask Routes ---
@flask_app.route("/", methods=["GET"])
def home():
    return "Bot is alive!", 200


@flask_app.route("/webhook", methods=["POST"])
def webhook():
    if telegram_app:
        update = Update.de_json(request.get_json(force=True), telegram_app.bot)
        telegram_app.update_queue.put_nowait(update)
    return "ok", 200


# --- Main Entry ---
async def setup_telegram():
    global telegram_app
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_balance))

    # Set webhook
    await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
    logging.info(f"Webhook set to {WEBHOOK_URL}")


if __name__ == "__main__":
    import asyncio

    # Start Telegram bot asynchronously
    asyncio.get_event_loop().run_until_complete(setup_telegram())

    # Run Flask app (Render uses this as web server)
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
