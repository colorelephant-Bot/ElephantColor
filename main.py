import os
import logging
from threading import Thread
from flask import Flask, jsonify
from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
)

# =============================
# CONFIGURATION
# =============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_URL = os.environ.get("RENDER_URL")  # e.g. https://your-app-name.onrender.com

# =============================
# LOGGING SETUP
# =============================

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("TELEGRAM_BOT")

# =============================
# FLASK APP (for Render + UptimeRobot)
# =============================

app = Flask(__name__)

@app.route('/')
def home():
    logger.info("[PING] Root endpoint hit.")
    return "✅ Bot is running."

@app.route('/ping')
def ping():
    """For UptimeRobot health checks."""
    logger.info("[PING] UptimeRobot ping received.")
    return jsonify(status="ok", message="Bot alive"), 200


def run_flask():
    """Run Flask app in a separate thread."""
    app.run(host='0.0.0.0', port=8080)

# =============================
# BOT COMMANDS
# =============================

def start(update: Update, context: CallbackContext):
    """Respond to /start command."""
    user = update.effective_user
    logger.info(f"[COMMAND] /start by {user.first_name} ({user.id})")
    update.message.reply_text(
        "👋 Hello! The bot is live and working via webhook.\n\n"
        "Send /start anytime to check connectivity."
    )

# =============================
# MAIN FUNCTION (Webhook Mode)
# =============================

def main():
    logger.info("[SYSTEM] Bot starting up...")

    # Start Flask server for Render and uptime pings
    Thread(target=run_flask).start()

    # Initialize Updater and Dispatcher
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Add only /start command
    dp.add_handler(CommandHandler("start", start))

    # Set webhook for Telegram → Render
    webhook_url = f"{RENDER_URL}/webhook/{BOT_TOKEN}"
    updater.bot.set_webhook(url=webhook_url)
    logger.info(f"[SYSTEM] Webhook set to {webhook_url}")

    # Start webhook listener (port 8443)
    updater.start_webhook(listen="0.0.0.0", port=8443, url_path=BOT_TOKEN)
    updater.idle()


if __name__ == "__main__":
    main()
