import os
import logging
from flask import Flask, request
from telegram import Update, ParseMode
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext
)
from prettytable import PrettyTable

# =============================
# CONFIGURATION
# =============================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_URL = os.environ.get("RENDER_URL")  # e.g. https://colorelephantbot-1t4s.onrender.com
PORT = int(os.environ.get("PORT", 8443))

# =============================
# LOGGING
# =============================
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================
# FLASK APP
# =============================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is running and healthy."

@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    """Receive updates from Telegram via webhook."""
    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher.process_update(update)
    return "ok", 200

# =============================
# BOT LOGIC
# =============================
user_state = {}  # track waiting users

def start(update: Update, context: CallbackContext):
    """Ask user to enter balance."""
    user_id = update.effective_user.id
    user_state[user_id] = "WAITING_FOR_BALANCE"
    update.message.reply_text("💰 Please enter your *current balance* (numbers only):", parse_mode=ParseMode.MARKDOWN)
    logger.info(f"/start from {user_id}")

def handle_message(update: Update, context: CallbackContext):
    """Handle user balance input and table generation."""
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_state.get(user_id) != "WAITING_FOR_BALANCE":
        update.message.reply_text("Send /start to begin.")
        return

    # Validate numeric input
    if not text.replace('.', '', 1).isdigit():
        update.message.reply_text("❌ Kindly enter *numbers only.*", parse_mode=ParseMode.MARKDOWN)
        return

    balance = float(text)
    user_state.pop(user_id, None)

    # ===== CASE I =====
    case1_percentages = [10, 10, 15, 30, 55]
    case1_results = [
        "If win, follow Case I",
        "If win session ends, If lost next round",
        "If win session ends, If lost next round",
        "If win session ends, If lost next round",
        "Last round, 99% win possibility"
    ]

    case1_table = PrettyTable()
    case1_table.field_names = ["Round", "Amount", "Result"]
    for i, p in enumerate(case1_percentages, start=1):
        amt = round(balance * p / 100, 2)
        case1_table.add_row([f"Round {i}", f"{amt}", case1_results[i - 1]])

    # ===== CASE II =====
    case2_percentages = [10, 25, 65]
    case2_results = [
        "If lost, use Case II",
        "If win session ends, If lost next round",
        "Last round, 99% win possibility"
    ]

    case2_table = PrettyTable()
    case2_table.field_names = ["Round", "Amount", "Result"]
    for i, p in enumerate(case2_percentages, start=1):
        amt = round(balance * p / 100, 2)
        case2_table.add_row([f"Round {i}", f"{amt}", case2_results[i - 1]])

    # Combine tables in one message
    response = f"📊 *Case I*\n```\n{case1_table}\n```\n📉 *Case II*\n```\n{case2_table}\n```"
    update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

# =============================
# TELEGRAM INITIALIZATION
# =============================
updater = Updater(BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# =============================
# MAIN
# =============================
if __name__ == "__main__":
    # Set webhook for Render
    webhook_url = f"{RENDER_URL}/{BOT_TOKEN}"
    updater.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook set to {webhook_url}")

    # Start Flask app
    app.run(host="0.0.0.0", port=PORT)