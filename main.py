import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext
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
# TELEGRAM HANDLERS
# =============================
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    logger.info(f"/start from {user.first_name} ({user.id})")
    update.message.reply_text(
        "👋 Hello! I'm alive and running via webhook.\n\n"
        "Send /start anytime to test connectivity."
    )

# =============================
# TELEGRAM INITIALIZATION
# =============================
updater = Updater(BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, start))

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
