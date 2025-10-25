import os
import math
import time
import logging
import threading
import requests
from flask import Flask, request
from telegram import Update, ParseMode
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext
)
from prettytable import PrettyTable

# =============================
# CONFIGURATION
# =============================
BOT_TOKEN   = os.environ.get("BOT_TOKEN")
RENDER_URL  = os.environ.get("RENDER_URL")  # e.g. https://colorelephantbot.onrender.com
PORT        = int(os.environ.get("PORT", 8443))
PING_DELAY  = 5     # seconds between pings

# =============================
# LOGGING
# =============================
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),   # full persistent log
        logging.StreamHandler()           # still echo to console
    ]
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
    """Receive updates from Telegram via webhook."""
    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher.process_update(update)
    return "ok", 200

# =============================
# HEALTH PINGER THREAD
# =============================
def ping_self():
    """Continuously ping the bot every 5 seconds and log results."""
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
    user_id = update.effective_user.id
    user_state[user_id] = "WAITING_FOR_BALANCE"
    update.message.reply_text(
        "💰 Please enter your *current balance* (numbers only):",
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info(f"/start from {user_id}")

def handle_message(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_state.get(user_id) != "WAITING_FOR_BALANCE":
        update.message.reply_text("Send /start to begin.")
        return

    if not text.replace(".", "", 1).isdigit():
        update.message.reply_text(
            "❌ Kindly enter *numbers only.*", parse_mode=ParseMode.MARKDOWN
        )
        return

    balance = float(text)
    user_state.pop(user_id, None)

    # ---- CASE I ----
    c1_perc = [10, 10, 15, 30, 55]
    c1_res  = [
        "If win, follow Case I",
        "If win session ends, If lost next round",
        "If win session ends, If lost next round",
        "If win session ends, If lost next round",
        "Last round, 99% win possibility",
    ]
    c1_tbl = PrettyTable(["Round", "Amount", "Result"])
    c1_tbl.align, c1_tbl.border = "l", True
    for i, p in enumerate(c1_perc, 1):
        amt = math.floor(balance * p / 100)
        c1_tbl.add_row([f"Round {i}", amt, c1_res[i-1]])

    # ---- CASE II ----
    c2_perc = [10, 25, 65]
    c2_res  = [
        "If lost, use Case II",
        "If win session ends, If lost next round",
        "Last round, 99% win possibility",
    ]
    c2_tbl = PrettyTable(["Round", "Amount", "Result"])
    c2_tbl.align, c2_tbl.border = "l", True
    for i, p in enumerate(c2_perc, 1):
        amt = math.floor(balance * p / 100)
        c2_tbl.add_row([f"Round {i}", amt, c2_res[i-1]])

    def format_table(title, table):
        border = "═" * (len(title) + 4)
        return f"╔{border}╗\n║  *{title}*  ║\n╚{border}╝\n```\n{table}\n```"

    msg = (
        f"📊 {format_table('CASE I', c1_tbl)}\n\n"
        f"📉 {format_table('CASE II', c2_tbl)}\n\n"
        f"💡 *All amounts are rounded down to the previous whole number.*"
    )
    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    logger.info(f"[BALANCE] {user_id} → {balance}")

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
    webhook_url = f"{RENDER_URL}/{BOT_TOKEN}"
    updater.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook set to {webhook_url}")

    # Start background pinger
    threading.Thread(target=ping_self, daemon=True).start()

    # Start Flask app
    app.run(host="0.0.0.0", port=PORT)