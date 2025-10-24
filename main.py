import os
import logging
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from prettytable import PrettyTable

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app-name.onrender.com/webhook
PORT = int(os.environ.get("PORT", 5000))

# --- Flask app ---
flask_app = Flask(__name__)
telegram_app = None


# --- Telegram Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome! Please enter your *current balance:*",
        parse_mode="Markdown",
    )


async def handle_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user input (balance) and send calculation tables."""
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

        message = (
            f"💰 *Initial Balance:* {balance:.2f}\n\n"
            f"📊 *Case 1 (Win Scenario)*\n```\n{table1}\n```\n"
            f"📉 *Case 2 (Lose Scenario)*\n```\n{table2}\n```"
        )

        await update.message.reply_text(message, parse_mode="Markdown")

    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number for your balance.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧮 *Usage Guide:*\n"
        "1️⃣ Send /start to begin.\n"
        "2️⃣ Enter your current balance.\n"
        "3️⃣ The bot will show you two cases:\n"
        "   - Case 1 (Win scenario)\n"
        "   - Case 2 (Lose scenario)",
        parse_mode="Markdown",
    )


# --- Flask Routes ---
@flask_app.route("/", methods=["GET"])
def home():
    """Health check endpoint."""
    return "✅ Bot is running and healthy!", 200


@flask_app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)
    asyncio.get_event_loop().create_task(telegram_app.process_update(update))
    return '', 200

# --- Initialize Telegram Application ---
async def setup_bot():
    """Build bot app and set webhook."""
    global telegram_app

    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_balance))

    # --- Auto re-register webhook if needed ---
    webhook_info = await telegram_app.bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await telegram_app.bot.delete_webhook()
        await telegram_app.bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"✅ Webhook set to: {WEBHOOK_URL}")
    else:
        logger.info("🔄 Webhook already set correctly.")

    return telegram_app


if __name__ == "__main__":
    # Initialize bot and run Flask web server
    asyncio.get_event_loop().run_until_complete(setup_bot())
    flask_app.run(host="0.0.0.0", port=PORT)
