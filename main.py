import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

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
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("TELEGRAM_BOT")

# =============================
# FLASK APP
# =============================
app = Flask(__name__)

@app.route("/")
def home():
    logger.info("[PING] Root endpoint hit.")
    return "✅ Bot is running and healthy."

@app.route("/ping")
def ping():
    return {"status": "ok", "message": "Bot alive"}, 200

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    """Handle incoming Telegram updates."""
    update = Update.de_json(request.get_json(force=True), updater.bot)
    dispatcher.process_update(update)
    return "ok", 200

# =============================
# TELEGRAM HANDLERS
# =============================
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    logger.info(f"[COMMAND] /start by {user.first_name} ({user.id})")
    update.message.reply_text(
        "👋 Hello! The bot is live and working via webhook.\n\n"
        "Send /start anytime to test connectivity."
    )

def echo(update: Update, context: CallbackContext):
    """Echo any text message."""
    update.message.reply_text(update.message.text)

# =============================
# TELEGRAM INITIALIZATION
# =============================
updater = Updater(token=BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher

# Register commands and handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

# =============================
# WEBHOOK SETUP
# =============================
webhook_url = f"{RENDER_URL}/{BOT_TOKEN}"

# Start webhook
updater.start_webhook(listen="0.0.0.0", port=PORT, url_path=BOT_TOKEN)
updater.bot.set_webhook(webhook_url)
logger.info(f"[SYSTEM] Webhook set to {webhook_url}")

# =============================
# FLASK SERVER START
# =============================
if __name__ == "__main__":
    logger.info(f"[SYSTEM] Starting Flask server on port {PORT} ...")
    app.run(host="0.0.0.0", port=PORT)
