import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
RENDER_URL = os.getenv("RENDER_URL")
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("TELEGRAM_BOT")

flask_app = Flask(__name__)
telegram_app = None


@flask_app.route("/")
def home():
    return "✅ Bot is running and healthy."


@flask_app.route("/ping")
def ping():
    return jsonify(status="ok", message="Bot alive"), 200


@flask_app.route("/webhook", methods=["POST"])
async def webhook():
    data = await request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return "", 200


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! The bot is live and working via webhook.\n\n"
        "Send /start anytime to test connectivity."
    )


async def setup_telegram():
    global telegram_app
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))

    webhook_url = f"{RENDER_URL}/webhook"
    info = await telegram_app.bot.get_webhook_info()
    if info.url != webhook_url:
        logger.info(f"Setting webhook to {webhook_url}")
        await telegram_app.bot.delete_webhook()
        await telegram_app.bot.set_webhook(url=webhook_url)
    else:
        logger.info(f"Webhook already set to {webhook_url}")

    logger.info("✅ Telegram bot setup complete.")


if __name__ == "__main__":
    logger.info("Starting bot...")
    asyncio.get_event_loop().run_until_complete(setup_telegram())
    flask_app.run(host="0.0.0.0", port=PORT)
