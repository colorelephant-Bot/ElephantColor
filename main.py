import os
import math
import time
import logging
import threading
import requests
from flask import Flask, request
from telegram import Update, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# =============================
# CONFIGURATION
# =============================
BOT_TOKEN  = os.environ.get("BOT_TOKEN")
RENDER_URL = os.environ.get("RENDER_URL")  # e.g. https://colorelephantbot.onrender.com
PORT       = int(os.environ.get("PORT", 8443))
PING_DELAY = 5  # seconds between pings

# =============================
# LOGGING
# =============================
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# =============================
# FLASK APP
# =============================
app = Flask(__name__)

@app.route("/")
def home():
    logger.info("[PING] Root endpoint hit.")
    return "✅ Bot is running and healthy."

@app.route("/" + BOT_TOKEN, methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher.process_update(update)
    return "ok", 200

# =============================
# HEALTH PINGER THREAD
# =============================
def ping_self():
    """Ping the bot every few seconds to keep it alive."""
    url = f"{RENDER_URL}/"
    while True:
        try:
            r = requests.get(url, timeout=4)
            if r.status_code == 200:
                logger.info(f"[HEALTH] Ping OK → {url}")
            else:
                logger.warning(f"[HEALTH] Ping failed ({r.status_code})")
        except Exception as e:
            logger.error(f"[HEALTH] Ping exception: {e}")
        time.sleep(PING_DELAY)

# =============================
# BOT LOGIC
# =============================
user_state = {}

def start(update: Update, context: CallbackContext):
    """Start command – ask user for balance."""
    user_id = update.effective_user.id
    user_state[user_id] = {"stage": "WAITING_FOR_BALANCE"}
    update.message.reply_text(
        "💰 Please enter your *current balance* (numbers only):",
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f"/start from {user_id}")

def reset(update: Update, context: CallbackContext):
    """Reset command – clears data and deletes recent messages."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        # Delete last 20 messages for a clean chat
        messages = context.bot.get_chat(chat_id).get_history(limit=20)
        for msg in messages:
            try:
                context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
            except Exception:
                pass  # Ignore if cannot delete a specific message

        # Clear session and cached data
        user_state.clear()
        context.bot_data.clear()
        context.user_data.clear()

        context.bot.send_message(chat_id, "♻️ All sessions and messages have been reset.\nYou can start again with /start.")
        logger.info(f"[RESET] User {user_id} reset session and chat.")
    except Exception as e:
        logger.error(f"[RESET ERROR] {e}")
        update.message.reply_text("⚠️ Unable to clear chat fully, but session reset successfully.")

def handle_message(update: Update, context: CallbackContext):
    """Handle balance input and show Case I & Case II directly."""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    state = user_state.get(user_id, {}).get("stage")

    if state == "WAITING_FOR_BALANCE":
        if not text.replace(".", "", 1).isdigit():
            update.message.reply_text("❌ Kindly enter *numbers only.*", parse_mode=ParseMode.MARKDOWN)
            return

        balance = float(text)
        user_state.pop(user_id, None)
        logger.info(f"[BALANCE INPUT] {user_id} entered balance {balance}")

        # Calculate amounts
        case1_perc = [10, 10, 15, 30, 55]
        case2_perc = [10, 25, 65]
        case1_amounts = [math.floor(balance * p / 100) for p in case1_perc]
        case2_amounts = [math.floor(balance * p / 100) for p in case2_perc]

        # Clean message
        message = (
            f"✅ *Your balance:* ₹{math.floor(balance)}\n\n"
            f"📊 *CASE I*\n"
            f"Round 1️⃣: ₹{case1_amounts[0]}\n"
            f"Round 2️⃣: ₹{case1_amounts[1]}\n"
            f"Round 3️⃣: ₹{case1_amounts[2]}\n"
            f"Round 4️⃣: ₹{case1_amounts[3]}\n"
            f"Round 5️⃣: ₹{case1_amounts[4]}\n\n"
            f"📉 *CASE II*\n"
            f"Round 1️⃣: ₹{case2_amounts[0]}\n"
            f"Round 2️⃣: ₹{case2_amounts[1]}\n"
            f"Round 3️⃣: ₹{case2_amounts[2]}\n\n"
            f"💡 All amounts are rounded down to the previous whole number."
        )
        update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        return

    update.message.reply_text("Send /start to begin or /reset to clear the chat.")

# =============================
# TELEGRAM INITIALIZATION
# =============================
updater = Updater(BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("reset", reset))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

# =============================
# MAIN
# =============================
if __name__ == "__main__":
    webhook_url = f"{RENDER_URL}/{BOT_TOKEN}"
    updater.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook set to {webhook_url}")

    threading.Thread(target=ping_self, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)