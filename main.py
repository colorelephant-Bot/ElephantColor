import os
import logging
from flask import Flask, jsonify, request
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
from math import floor
import pytz

# =============================
# CONFIGURATION
# =============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
RENDER_URL = os.environ.get("RENDER_URL")  # e.g. https://color-elephant.onrender.com
TIMEZONE = pytz.timezone("Asia/Kolkata")
RULES_FILE = "rules.txt"
BANNED_FILE = "banned_users.txt"

logging.basicConfig(
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log", mode="a", encoding="utf-8")],
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================
# FLASK APP (Webhook + Ping)
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

# =============================
# BAN SYSTEM
# =============================

def load_banned():
    banned = set()
    if os.path.exists(BANNED_FILE):
        with open(BANNED_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    banned.add(int(line.strip()))
    return banned

def save_banned(banned):
    with open(BANNED_FILE, 'w', encoding='utf-8') as f:
        for uid in sorted(banned):
            f.write(str(uid) + "\n")

BANNED_USERS = load_banned()

def is_banned(user_id):
    return int(user_id) in BANNED_USERS

def reject_if_banned(update: Update, context: CallbackContext):
    user = update.effective_user
    if user and is_banned(user.id):
        logger.info(f"Banned user {user.id}, trying to access.")
        return True
    return False

# =============================
# HELPER FUNCTIONS
# =============================

def nearest_ten(value):
    return int(floor(value / 10) * 10)

def percent_of(balance, pct):
    return nearest_ten(balance * pct / 100)

def load_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    return "Rules not found."

def _is_admin(user_id):
    return ADMIN_ID and str(user_id) == str(ADMIN_ID)

def is_effectively_active(update: Update, context: CallbackContext) -> bool:
    return True  # Always active 24/7

# =============================
# GAME LOGIC
# =============================

CASE1 = [10, 10, 15, 30, 50]  # Percentages for Win Path
CASE2 = [10, 25, 65]          # Percentages for Loss Path

def start_game_flow(update: Update, context: CallbackContext):
    context.user_data.clear()
    update.message.reply_text(
        "🎮 Game Started!\n\nPlease enter your Current Balance (e.g., 1000).",
        parse_mode=ParseMode.MARKDOWN
    )

def start_game(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    start_game_flow(update, context)

def process_balance(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return

    try:
        balance = float(update.message.text)
    except Exception:
        return update.message.reply_text("Please enter a valid number (e.g., 1000).")

    balance = nearest_ten(balance)
    context.user_data["BaseBalance"] = balance
    context.user_data["Round"] = 1
    context.user_data["Path"] = None  # Will be set after first round

    investment = percent_of(balance, CASE1[0])
    buttons = [[
        InlineKeyboardButton("Win", callback_data="r1_win"),
        InlineKeyboardButton("Lose", callback_data="r1_lose")
    ]]
    update.message.reply_text(
        f"Round 1: Place ₹{investment} (10% of ₹{balance}) on predicted color.\n\nRound 1 result?",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.MARKDOWN
    )

# =============================
# UPDATED HANDLE_RESULT (with Session Summary)
# =============================

def handle_result(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return

    query = update.callback_query
    query.answer()
    data = query.data

    base_balance = context.user_data.get("BaseBalance", 0)
    round_num = context.user_data.get("Round", 1)
    path = context.user_data.get("Path")

    if round_num == 1:
        if data.endswith("_win"):
            path = "case1"
        else:
            path = "case2"
        context.user_data["Path"] = path

    percentages = CASE1 if path == "case1" else CASE2
    total_rounds = len(percentages)

    # ✅ End on WIN (after Round 1)
    if data.endswith("_win") and round_num > 1:
        msg = (
            f"🎉 Congratulations! You won in Round {round_num}!\n\n"
            f"📊 Session Summary:\n"
            f"- Total Rounds Played: {round_num}\n"
            f"- Final Result: WIN\n"
            f"- Base Balance: ₹{base_balance}\n\n"
            f"Use /start to begin a new prediction session."
        )
        query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
        context.user_data.clear()
        return

    # ✅ End if all rounds exhausted
    if round_num >= total_rounds:
        msg = (
            f"🛑 Prediction session completed.\n\n"
            f"📊 Session Summary:\n"
            f"- Total Rounds Played: {round_num}\n"
            f"- Final Result: LOSS\n"
            f"- Base Balance: ₹{base_balance}\n\n"
            f"Use /start to begin a new session."
        )
        query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)
        context.user_data.clear()
        return

    # Proceed to next round
    next_round = round_num + 1
    context.user_data["Round"] = next_round
    next_percent = percentages[next_round - 1]
    invest_amount = percent_of(base_balance, next_percent)

    buttons = [[
        InlineKeyboardButton("Win", callback_data=f"r{next_round}_win"),
        InlineKeyboardButton("Lose", callback_data=f"r{next_round}_lose")
    ]]

    msg = (
        f"{'✅' if data.endswith('_win') else '❌'} Round {round_num} {'WIN' if data.endswith('_win') else 'LOSS'}\n"
        f"Base Balance: ₹{base_balance}\n\n"
        f"Round {next_round}: Place ₹{invest_amount} ({next_percent}% of ₹{base_balance})\n\n"
        f"Round {next_round} result?"
    )

    query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)

# =============================
# OTHER COMMANDS
# =============================

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
# MAIN BOT LAUNCH (WEBHOOK)
# =============================

def main():
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

    @app.route(f"/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        update = Update.de_json(request.get_json(force=True), updater.bot)
        dp.process_update(update)
        return "ok", 200

    updater.bot.delete_webhook()
    updater.bot.set_webhook(f"{RENDER_URL}/{BOT_TOKEN}")
    logger.info(f"✅ Webhook set to {RENDER_URL}/{BOT_TOKEN}")

    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()
