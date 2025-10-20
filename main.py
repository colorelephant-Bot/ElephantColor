import os
import logging
from flask import Flask, jsonify, request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
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
RENDER_URL = os.environ.get("RENDER_URL")  # Example: https://color-elephant.onrender.com
TIMEZONE = pytz.timezone("Asia/Kolkata")
RULES_FILE = "rules.txt"
BANNED_FILE = "banned_users.txt"

CASE1 = [10, 10, 15, 30, 50]
CASE2 = [10, 25, 65]
TAX_RATE = 0.10  # 10% tax on profit

# =============================
# LOGGING SETUP
# =============================

logging.basicConfig(
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log", mode="a", encoding="utf-8")],
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def log_event(event_type, user, message):
    """Log formatted events for better tracking"""
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    username = f"@{user.username}" if user.username else "NoUsername"
    uid = user.id if user else "Unknown"
    logger.info(f"[{event_type}] {message} | User: {username} ({uid}) - {name}")

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
        logger.info(f"[BLOCKED] Banned user {user.id}, trying to access.")
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

def start_game_flow(update: Update, context: CallbackContext):
    context.user_data.clear()
    keyboard = [
        ["1", "2", "3", "10"],
        ["4", "5", "6", "100"],
        ["7", "8", "9", "1K"],
        ["0", "10K"]
    ]
    update.message.reply_text(
        "🎮 Game Started!\n\nPlease enter your Current Balance.\n"
        "You can type manually or use the number pad below 👇",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="Enter or tap digits"
        )
    )

def start_game(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    user = update.effective_user
    log_event("COMMAND", user, "/start invoked")
    start_game_flow(update, context)

def process_balance(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return

    user = update.effective_user
    text = update.message.text.strip().upper()

    # Convert shorthand like 1K = 1000, 10K = 10000
    if text.endswith("K"):
        try:
            num = float(text[:-1])
            text = str(int(num * 1000))
        except Exception:
            update.message.reply_text("Please enter a valid number (e.g., 1000).")
            return

    # Check numeric validity
    if not text.replace('.', '', 1).isdigit():
        update.message.reply_text("Please enter a valid numeric balance (e.g., 1000).")
        return

    try:
        balance = float(text)
    except Exception:
        return update.message.reply_text("Please enter a valid number (e.g., 1000).")

    balance = nearest_ten(balance)
    log_event("BALANCE", user, f"Entered balance: ₹{balance}")

    context.user_data["BaseBalance"] = balance
    context.user_data["Round"] = 1
    context.user_data["Path"] = None
    context.user_data["Wins"] = 0
    context.user_data["Losses"] = 0
    context.user_data["TotalPlaced"] = 0
    context.user_data["Profit"] = 0

    update.message.reply_text("Balance saved. Let's begin!", reply_markup=ReplyKeyboardRemove())

    investment = percent_of(balance, CASE1[0])
    context.user_data["TotalPlaced"] += investment
    update.message.reply_text(f"Round 1: Place ₹{investment} (10% of ₹{balance}).")
    buttons = [
        [InlineKeyboardButton("Win", callback_data="r1_win"), InlineKeyboardButton("Lose", callback_data="r1_lose")]
    ]
    update.message.reply_text("Round 1 result?", reply_markup=InlineKeyboardMarkup(buttons))

# =============================
# HANDLE RESULT (Tax + Logging)
# =============================

def handle_result(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return

    query = update.callback_query
    query.answer()
    data = query.data
    user = update.effective_user

    base_balance = context.user_data.get("BaseBalance", 0)
    round_num = context.user_data.get("Round", 1)
    path = context.user_data.get("Path")
    total_placed = context.user_data.get("TotalPlaced", 0)
    profit = context.user_data.get("Profit", 0)
    wins = context.user_data.get("Wins", 0)
    losses = context.user_data.get("Losses", 0)

    result_text = "Win" if data.endswith("_win") else "Lose"
    log_event("ROUND", user, f"Round {round_num} result: {result_text}")

    if round_num == 1:
        path = "case1" if data.endswith("_win") else "case2"
        context.user_data["Path"] = path

    percentages = CASE1 if path == "case1" else CASE2
    total_rounds = len(percentages)

    investment = percent_of(base_balance, percentages[round_num - 1])
    context.user_data["TotalPlaced"] = total_placed + investment

    if data.endswith("_win"):
        wins += 1
        context.user_data["Wins"] = wins
        gross_profit = investment
        tax = gross_profit * TAX_RATE
        net_profit = gross_profit - tax
        profit += net_profit
        context.user_data["Profit"] = nearest_ten(profit)
    else:
        losses += 1
        context.user_data["Losses"] = losses
        profit -= investment
        context.user_data["Profit"] = nearest_ten(profit)

    # --- End conditions ---
    if data.endswith("_win") and round_num > 1 or round_num >= total_rounds:
        profit_after_tax = nearest_ten(profit)
        updated_balance = nearest_ten(base_balance + profit_after_tax)
        msg = (
            f"Session Summary:\n"
            f"Rounds Played: {round_num} ({wins} Won, {losses} Lost)\n"
            f"Amount Placed: ₹{context.user_data['TotalPlaced']}\n"
            f"Profit Made: ₹{nearest_ten(profit)}\n"
            f"Profit After Tax: ₹{nearest_ten(profit_after_tax)}\n"
            f"Balance After Session: ₹{nearest_ten(updated_balance)}\n\n"
            f"Use /start to begin a new session."
        )
        query.message.reply_text(msg)
        log_event("SUMMARY", user, f"Profit ₹{profit_after_tax} | Balance ₹{updated_balance}")
        context.user_data.clear()
        return

    # --- Next Round ---
    next_round = round_num + 1
    context.user_data["Round"] = next_round
    next_percent = percentages[next_round - 1]
    invest_amount = percent_of(base_balance, next_percent)
    context.user_data["TotalPlaced"] += invest_amount

    query.message.reply_text(f"Round {next_round}: Place ₹{invest_amount} ({next_percent}% of ₹{base_balance}).")
    buttons = [
        [InlineKeyboardButton("Win", callback_data=f"r{next_round}_win"),
         InlineKeyboardButton("Lose", callback_data=f"r{next_round}_lose")]
    ]
    query.message.reply_text(f"Round {next_round} result?", reply_markup=InlineKeyboardMarkup(buttons))

# =============================
# ADMIN LOG VIEW (/logs)
# =============================

def logs_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    if not _is_admin(user.id):
        update.message.reply_text("You are not authorized to view logs.")
        return
    try:
        with open("bot.log", "r", encoding="utf-8") as f:
            lines = f.readlines()[-30:]
        if not lines:
            update.message.reply_text("No logs found.")
            return
        log_text = "".join(lines[-30:])
        if len(log_text) > 3900:
            log_text = log_text[-3900:]
        update.message.reply_text(
            "🧾 *Last 30 Log Entries:*\n\n```\n" + log_text + "\n```",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        update.message.reply_text(f"Error reading logs: {e}")

# =============================
# OTHER COMMANDS
# =============================

def clear(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    user = update.effective_user
    log_event("COMMAND", user, "/clear invoked")
    context.user_data.clear()
    update.message.reply_text("Chat cleared. Use /start to start again.")

def rules(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    user = update.effective_user
    log_event("COMMAND", user, "/rules invoked")
    rules_text = load_rules()
    update.message.reply_text(f"Platform Rules:\n\n{rules_text}", parse_mode=ParseMode.MARKDOWN)

def commands_list(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    user = update.effective_user
    log_event("COMMAND", user, "/commands invoked")
    cmds = (
        "Available Commands:\n\n"
        "/start – Start predictions\n"
        "/clear – Reset chat\n"
        "/rules – Show rules\n"
        "/commands – List commands\n"
        "/override – Enable session override (if allowed)\n"
        "/reboot – Logout and start fresh\n"
        "/logs – Show recent activity logs (Admin only)"
    )
    update.message.reply_text(cmds, parse_mode=ParseMode.MARKDOWN)

def override_cmd(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    user = update.effective_user
    log_event("COMMAND", user, "/override invoked")
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
    user = update.effective_user
    log_event("COMMAND", user, "/reboot invoked")
    context.user_data.clear()
    update.message.reply_text("Bot rebooted. Session cleared.\n\nUse /start to begin again.")

def unknown(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    user = update.effective_user
    log_event("UNKNOWN", user, f"Sent unknown command: {update.message.text}")
    update.message.reply_text("Sorry, I am not programmed to answer this. Try /start or /commands.")

# =============================
# MAIN BOT LAUNCH
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
    dp.add_handler(CommandHandler("logs", logs_cmd))
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