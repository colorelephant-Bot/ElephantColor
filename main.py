import os
import logging
from threading import Thread
from flask import Flask, jsonify
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext
)

# =============================
# CONFIGURATION
# =============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_URL = os.environ.get("RENDER_URL")  # Example: https://your-app-name.onrender.com

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
    return "✅ Bot is running and healthy."

@app.route('/ping')
def ping():
    """For UptimeRobot health checks."""
    logger.info("[PING] UptimeRobot ping received.")
    return jsonify(status="ok", message="Bot alive"), 200


def run_flask():
    """Run Flask app in a separate thread for Render deployment."""
    app.run(host='0.0.0.0', port=8080)

# =============================
# BOT COMMANDS
# =============================

def start(update: Update, context: CallbackContext):
    """Respond to /start command."""
    user = update.effective_user
    logger.info(f"[COMMAND] /start by {user.first_name} ({user.id})")
    update.message.reply_text(
        "👋 Hello! I’m alive and working through webhook.\n\n"
        "Send /start anytime to test bot connectivity.",
        parse_mode=ParseMode.MARKDOWN
    )

def clear(update: Update, context: CallbackContext):
    """Optional reset command."""
    context.user_data.clear()
    logger.info(f"[COMMAND] /clear by {update.effective_user.id}")
    update.message.reply_text("✅ Chat data cleared.")


# =============================
# MAIN BOT (Webhook Mode)
# =============================

def main():
    logger.info("[SYSTEM] Bot startup initiated.")
    Thread(target=run_flask).start()

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Register commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("clear", clear))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, start))

    # Set webhook for Render
    webhook_url = f"{RENDER_URL}/webhook/{BOT_TOKEN}"
    updater.bot.set_webhook(url=webhook_url)
    logger.info(f"[SYSTEM] Webhook set to {webhook_url}")

    # Start webhook listener (port 8443)
    updater.start_webhook(listen="0.0.0.0", port=8443, url_path=BOT_TOKEN)
    updater.idle()


if __name__ == "__main__":
    main()
