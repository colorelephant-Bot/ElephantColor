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

# =============================
# CONFIGURATION
# =============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
TIMEZONE = pytz.timezone("Asia/Kolkata")
ACTIVE_HOURS = [13, 17, 21]
RULES_FILE = "rules.txt"
BANNED_FILE = "banned_users.txt"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================
# KEEP ALIVE (Flask server + UptimeRobot)
# =============================

app = Flask('')

@app.route('/')
def home():
    logger.info("[PING] Root endpoint hit.")
    return "Bot is running."

@app.route('/ping')
def ping():
    logger.info("[PING] /ping endpoint accessed.")
    return jsonify(status="ok", message="Ping received. Bot alive."), 200

def keep_alive():
    def run():
        app.run(host='0.0.0.0', port=8080)
    t = Thread(target=run)
    t.start()

# =============================
# BAN SYSTEM
# =============================

def load_banned():
    banned = set()
    if os.path.exists(BANNED_FILE):
        with open(BANNED_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        banned.add(int(line))
                    except ValueError:
                        continue
    return banned

def save_banned(banned_set):
    with open(BANNED_FILE, 'w', encoding='utf-8') as f:
        for uid in sorted(banned_set):
            f.write(str(uid) + "\n")

BANNED_USERS = load_banned()

def is_banned(user_id):
    try:
        return int(user_id) in BANNED_USERS
    except Exception:
        return False

def ban_user_by_id(user_id, admin_id):
    BANNED_USERS.add(int(user_id))
    save_banned(BANNED_USERS)
    logger.info(f"User {user_id} banned by admin {admin_id}.")

def unban_user_by_id(user_id, admin_id):
    uid = int(user_id)
    if uid in BANNED_USERS:
        BANNED_USERS.remove(uid)
        save_banned(BANNED_USERS)
        logger.info(f"User {user_id} unbanned by admin {admin_id}.")

def reject_if_banned(update: Update, context: CallbackContext):
    user = update.effective_user
    if not user:
        return False
    if is_banned(user.id):
        logger.info(f"Banned user {user.id}, trying to access.")
        return True
    return False

def resolve_username_to_id(bot, username):
    u = username.lstrip('@')
    try:
        chat = bot.get_chat(u)
        return chat.id
    except Exception:
        return None

def ban_cmd(update: Update, context: CallbackContext):
    if not ADMIN_ID or str(update.effective_user.id) != str(ADMIN_ID):
        return
    if not context.args:
        update.message.reply_text("Usage: /ban <user_id|@username>")
        return
    target = context.args[0]
    target_id = None
    if target.isdigit() or (target.startswith('-') and target[1:].isdigit()):
        target_id = int(target)
    else:
        target_id = resolve_username_to_id(context.bot, target)
    if not target_id:
        update.message.reply_text("Could not resolve user.")
        return
    ban_user_by_id(target_id, update.effective_user.id)
    update.message.reply_text(f"User {target_id} has been banned.")

def unban_cmd(update: Update, context: CallbackContext):
    if not ADMIN_ID or str(update.effective_user.id) != str(ADMIN_ID):
        return
    if not context.args:
        update.message.reply_text("Usage: /unban <user_id|@username>")
        return
    target = context.args[0]
    target_id = None
    if target.isdigit() or (target.startswith('-') and target[1:].isdigit()):
        target_id = int(target)
    else:
        target_id = resolve_username_to_id(context.bot, target)
    if not target_id:
        update.message.reply_text("Could not resolve user.")
        return
    unban_user_by_id(target_id, update.effective_user.id)
    update.message.reply_text(f"User {target_id} has been unbanned.")

# =============================
# HELPER FUNCTIONS
# =============================

def nearest_ten(value):
    return int(floor(value / 10) * 10)

def percent_of(balance, pct):
    return nearest_ten(balance * pct)

def load_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, 'r', encoding='utf-8') as f:
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

# =============================
# GAME LOGIC
# =============================

def start_game_flow(update: Update, context: CallbackContext):
    context.user_data["Round"] = 1
    update.message.reply_text(
        "Game Started.\n\nPlease enter your Current Balance (e.g., 1000).",
        parse_mode=ParseMode.MARKDOWN
    )

def start_game(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    if not is_effectively_active(update, context):
        return inactive_reply(update, context)
    context.user_data.clear()
    start_game_flow(update, context)

def process_balance(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
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
    buttons = [[InlineKeyboardButton("Win", callback_data="r1_win"), InlineKeyboardButton("Lose", callback_data="r1_lose")]]
    update.message.reply_text(
        f"Round 1: Place ₹{investment} (10% of ₹{balance}) on predicted color.\n\nRound 1 result?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def handle_result(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    query = update.callback_query
    query.answer()
    data = query.data
    balance = context.user_data.get("Balance", 0)
    # (rest of handle_result logic unchanged)

def clear(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    context.user_data.clear()
    update.message.reply_text("Chat cleared. Use /start to start again.")

def rules(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    rules_text = load_rules()
    update.message.reply_text(f"Platform Rules:\n\n{rules_text}", parse_mode=ParseMode.MARKDOWN)

def commands_list(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
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

def unknown(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    update.message.reply_text("Sorry, I am not programmed to answer this. Try /start or /commands.")

def override_cmd(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
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
    if reject_if_banned(update, context):
        return
    context.user_data.clear()
    update.message.reply_text("Bot rebooted. Session cleared.\n\nUse /start to begin again.")

# =============================
# MAIN BOT LAUNCH
# =============================

def main():
    keep_alive()
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("ban", ban_cmd))
    dp.add_handler(CommandHandler("unban", unban_cmd))
    dp.add_handler(CommandHandler("start", start_game))
    dp.add_handler(CommandHandler("clear", clear))
    dp.add_handler(CommandHandler("rules", rules))
    dp.add_handler(CommandHandler("commands", commands_list))
    dp.add_handler(CommandHandler("override", override_cmd))
    dp.add_handler(CommandHandler("reboot", reboot))
    dp.add_handler(CallbackQueryHandler(handle_result))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, process_balance))
    dp.add_handler(MessageHandler(Filters.command, unknown))
    updater.start_polling()
    logger.info("✅ Bot is live and monitored via Flask + UptimeRobot.")
    updater.idle()

if __name__ == "__main__":
    main()
