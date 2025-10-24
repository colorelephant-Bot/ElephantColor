import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# =============================
# CONFIGURATION
# =============================
BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_URL = os.getenv("RENDER_URL")  # Example: https://colorelephantbot-1t4s.onrender.com
PORT = int(os.environ.get("PORT", "8080"))

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
flask_app = Flask(__name__)
telegram_app = None  # Telegram app instance


@flask_app.route("/")
def home():
    """Render health check."""
    return "✅ Bot is running and healthy."


@flask_app.route("/ping")
def ping():
    """UptimeRobot check."""
    return jsonify(status="ok", message="Bot alive"), 200


@flask_app.route("/webhook", methods=["POST"])
def webhook():
    """Sync Flask route to handle Telegram updates."""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, telegram_app.bot)
        asyncio.run(process_telegram_update(update))
    except Exception as e:
        logger.error(f"[ERROR] Exception in webhook handler: {e}", exc_info=True)
    return "", 200


# =============================
# TELEGRAM COMMAND HANDLERS
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to /start."""
    user = update.effective_user
    logger.info(f"[COMMAND] /start by {user.first_name} ({user.id})")
    await update.message.reply_text(
        "👋 Hello! The bot is live and connected via webhook.\n\n"
        "Send /start anytime to test connectivity."
    )


# =============================
# TELEGRAM SETUP
# =============================
async def setup_telegram():
    """Initialize bot and set webhook."""
    global telegram_app
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))

    await telegram_app.initialize()

    webhook_url = f"{RENDER_URL}/webhook"
    info = await telegram_app.bot.get_webhook_info()

    if info.url != webhook_url:
        logger.info(f"[SYSTEM] Setting webhook to {webhook_url}")
        await telegram_app.bot.delete_webhook()
        await telegram_app.bot.set_webhook(url=webhook_url)
    else:
        logger.info(f"[SYSTEM] Webhook already set to {webhook_url}")

    logger.info("✅ Telegram bot setup complete.")


async def process_telegram_update(update: Update):
    """Process incoming Telegram update safely."""
    if not telegram_app.running:
        await telegram_app.initialize()
    await telegram_app.process_update(update)


# =============================
# MAIN ENTRY POINT
# =============================
if __name__ == "__main__":
    logger.info("[SYSTEM] Starting bot setup...")

    try:
        asyncio.get_event_loop().run_until_complete(setup_telegram())
        logger.info("[SYSTEM] Bot setup completed successfully.")
    except Exception as e:
        logger.error(f"[FATAL] Bot setup failed: {e}", exc_info=True)
        logger.warning("[WARNING] Continuing to start Flask even though Telegram setup failed.")

    logger.info(f"[SYSTEM] Starting Flask server on port {PORT} ...")
    try:
        flask_app.run(host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.error(f"[FATAL] Flask failed to start: {e}", exc_info=True)
