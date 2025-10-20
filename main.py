import os
import logging
from datetime import datetime
import pytz
from math import floor
from flask import Flask, jsonify
from threading import Thread
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ParseMode
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackQueryHandler,
    CallbackContext,
)
from telegram.error import TelegramError

# =============================
# CONFIGURATION
# =============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
TIMEZONE = pytz.timezone("Asia/Kolkata")
ACTIVE_HOURS = [13, 17, 21]
RULES_FILE = "rules.txt"
RENDER_URL = os.environ.get("RENDER_URL")

# =============================
# LOGGING SETUP
# =============================

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("TELEGRAM_BOT")

def log_event(event_type, user=None, details=""):
    """Write structured log lines."""
    if user:
        user_info = f"User {user.id} ({user.first_name})"
    else:
        user_info = "SYSTEM"
    logger.info(f"[{event_type}] {user_info} {details}")

# =============================
# FLASK APP (for Render + UptimeRobot)
# =============================

app = Flask('')

@app.route('/')
def home():
    log_event("PING", None, "Root endpoint hit.")
    return "Bot is running."

@app.route('/ping')
def ping():
    """For UptimeRobot health checks."""
    log_event("PING", None, "UptimeRobot health check ping received.")
    return jsonify(status="ok", message="Ping received. Bot alive."), 200

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# =============================
# HELPER FUNCTIONS
# =============================

def nearest_ten(value):
    return int(floor(value / 10) * 10)

def percent_of(balance, pct):
    return nearest_ten(balance * pct)

def load_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "Rules not found."

def _is_admin(user_id):
    if not ADMIN_ID:
        return False
    return str(user_id) == str(ADMIN_ID)

def is_effectively_active(update: Update, context: CallbackContext) -> bool:
    if context.user_data.get("override_session", False):
        return True
    now = datetime.now(TIMEZONE)
    return now.hour in ACTIVE_HOURS

def inactive_reply(update: Update, context: CallbackContext):
    msg = (
        "The bot is currently offline.\n\n"
        "It will be active at 1 PM, 5 PM, and 9 PM.\n\n"
        "If you wish to continue now, reply with /override (if permitted)."
    )
    context.user_data["awaiting_override"] = True
    update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
    log_event("INACTIVE", update.effective_user, "Bot inactive reply sent.")

# =============================
# GAME LOGIC
# =============================

def start_game_flow(update: Update, context: CallbackContext):
    context.user_data["Round"] = 1
    update.message.reply_text(
        "Game Started.\n\nPlease enter your Current Balance (e.g., 1000).",
        parse_mode=ParseMode.MARKDOWN
    )
    log_event("GAME", update.effective_user, "Game flow started.")

def start_game(update: Update, context: CallbackContext):
    log_event("COMMAND", update.effective_user, "/start")
    if not is_effectively_active(update, context):
        return inactive_reply(update, context)
    context.user_data.clear()
    start_game_flow(update, context)

def process_balance(update: Update, context: CallbackContext):
    log_event("MESSAGE", update.effective_user, f"Balance input: {update.message.text}")
    if not is_effectively_active(update, context):
        return inactive_reply(update, context)

    try:
        balance = float(update.message.text)
    except Exception:
        return update.message.reply_text("Please enter a valid number (e.g., 1000).")

    balance = nearest_ten(balance)
    context.user_data["Balance"] = balance
    investment = percent_of(balance, 0.10)
    context.user_data["Round 1"] = investment

    buttons = [
        [InlineKeyboardButton("Win", callback_data="r1_win"),
         InlineKeyboardButton("Lose", callback_data="r1_lose")]
    ]

    update.message.reply_text(
        f"Round 1: Place ₹{investment} (10% of ₹{balance}) on predicted color.\n\nRound 1 result?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def handle_result(update: Update, context: CallbackContext):
    query = update.callback_query
    log_event("CALLBACK", query.from_user, f"→ {query.data}")
    query.answer()
    data = query.data
    balance = context.user_data.get("Balance", 0)
    # Your original result logic here

def clear(update: Update, context: CallbackContext):
    log_event("COMMAND", update.effective_user, "/clear")
    context.user_data.clear()
    update.message.reply_text("Chat cleared. Use /start to start again.")

def rules(update: Update, context: CallbackContext):
    log_event("COMMAND", update.effective_user, "/rules")
    rules_text = load_rules()
    update.message.reply_text(f"Platform Rules:\n\n{rules_text}", parse_mode=ParseMode.MARKDOWN)

def commands_list(update: Update, context: CallbackContext):
    log_event("COMMAND", update.effective_user, "/commands")
    cmds = (
        "Available Commands:\n\n"
        "/start – Start predictions\n"
        "/clear – Reset chat\n"
        "/rules – Show rules\n"
        "/commands – List commands\n"
        "/override – Enable session override (if allowed)\n"
        "/reboot – Logout and start fresh"
    )
    update.message.reply_text(cmds, parse_mode=ParseMode.MARKDOWN)

def override_cmd(update: Update, context: CallbackContext):
    log_event("COMMAND", update.effective_user, "/override")
    user = update.effective_user
    awaiting = context.user_data.get("awaiting_override", False)

    if not awaiting:
        update.message.reply_text("You can only use /override after the bot offered it.")
        return

    if ADMIN_ID and not _is_admin(user.id):
        update.message.reply_text("You are not authorized to use /override.")
        return

    context.user_data["override_session"] = True
    context.user_data.pop("awaiting_override", None)
    update.message.reply_text("Override accepted. Starting game now...")
    start_game_flow(update, context)

def reboot(update: Update, context: CallbackContext):
    log_event("COMMAND", update.effective_user, "/reboot")
    context.user_data.clear()
    update.message.reply_text("Bot rebooted. Session cleared.\n\nUse /start to begin again.")

def unknown(update: Update, context: CallbackContext):
    log_event("COMMAND", update.effective_user, f"Unknown command: {update.message.text}")
    update.message.reply_text("Sorry, I am not programmed to answer this. Try /start or /commands.")

# =============================
# MAIN BOT LAUNCH (WEBHOOK MODE)
# =============================

def main():
    log_event("SYSTEM", None, "Bot startup initiated.")
    Thread(target=run_flask).start()

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_game))
    dp.add_handler(CommandHandler("clear", clear))
    dp.add_handler(CommandHandler("rules", rules))
    dp.add_handler(CommandHandler("commands", commands_list))
    dp.add_handler(CommandHandler("override", override_cmd))
    dp.add_handler(CommandHandler("reboot", reboot))
    dp.add_handler(CallbackQueryHandler(handle_result))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, process_balance))
    dp.add_handler(MessageHandler(Filters.command, unknown))

    # Set webhook for Render
    webhook_url = f"{RENDER_URL}/webhook/{BOT_TOKEN}"
    updater.bot.set_webhook(url=webhook_url)
    log_event("SYSTEM", None, f"Webhook set to {webhook_url}")

    updater.start_webhook(listen="0.0.0.0", port=8443, url_path=BOT_TOKEN)
    updater.idle()

if __name__ == "__main__":
    main()
