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
RENDER_URL = os.getenv("RENDER_URL")  # e.g. https://colorelephantbot-1t4s.onrender.com
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
# FLASK SETUP
# =============================
flask_app = Flask(__name__)
telegram_app = None  # will hold the Telegram bot instance


@flask_app.route("/")
def home():
    """Root endpoint for Render health check."""
    logger.info("[PING] Root endpoint hit.")
    return "✅ Bot is running and healthy."


@flask_app.route("/ping")
def ping():
    """UptimeRobot or manual health check."""
    return jsonify(status="ok", message="Bot alive"), 200


@flask_app.route("/webhook", methods=["POST"])
def webhook():
    """Synchronous Flask route that runs async Telegram handler."""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, telegram_app.bot)
        asyncio.run(telegram_app.process_update(update))
    except Exception as e:
        logger.error(f"[ERROR] Exception in webhook handler: {e}", exc_info=True)
    return "", 200


# =============================
# TELEGRAM HANDLERS
# =============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Respond to /start command."""
    user = update.effective_user
    logger.info(f"[COMMAND] /start by {user.first_name} ({user.id})")
    await update.message.reply_text(
        "👋 Hello! The bot is live and working via webhook.\n\n"
        "Send /start anytime to test connectivity."
    )


# =============================
# TELEGRAM INITIALIZATION
# =============================
async def setup_telegram():
    """Initialize Telegram bot and set webhook."""
    global telegram_app
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))

    webhook_url = f"{RENDER_URL}/webhook"
    info = await telegram_app.bot.get_webhook_info()

    if info.url != webhook_url:
        logger.info(f"[SYSTEM] Setting webhook to {webhook_url}")
        await telegram_app.bot.delete_webhook()
        await telegram_app.bot.set_webhook(url=webhook_url)
    else:
        logger.info(f"[SYSTEM] Webhook already set to {webhook_url}")

    logger.info("✅ Telegram bot setup complete.")


# =============================
# MAIN ENTRY POINT
# =============================
if __name__ == "__main__":
    logger.info("[SYSTEM] Starting bot setup...")

    try:
        asyncio.get_event_loop().run_until_complete(setup_telegram())
        logger.info("[SYSTEM] Webhook and bot initialized successfully.")
    except Exception as e:
        logger.error(f"[FATAL] Bot setup failed: {e}", exc_info=True)

    # Always start Flask, even if setup fails
    logger.info(f"[SYSTEM] Starting Flask server on port {PORT} ...")
    flask_app.run(host="0.0.0.0", port=PORT)
