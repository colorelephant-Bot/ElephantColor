# main.py
# -----------------------------------------------------------------------------
# COLOR ELEPHANT BOT - main.py
# Final production-ready version (per user requirements)
# -----------------------------------------------------------------------------

# ------------------------------
# IMPORTS & CONFIG
# ------------------------------
import os
import logging
from math import floor
from datetime import datetime, date
import pytz
from flask import Flask, jsonify, request
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    ParseMode,
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
# 🔒 LOGGING SYSTEM (PERMANENT SECTION — DO NOT MODIFY)
# =============================
# This section is intentionally self-contained and should remain unchanged.
# It provides structured logging to console + file with categories:
# [SYSTEM], [USERS], [COMMAND], [GAME], [SUMMARY], [CREATOR]
LOG_FILE = "bot.log"

def setup_logging():
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    logger = logging.getLogger("ColorElephantBot")
    logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers if module reloaded
    if not logger.handlers:
        fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter(fmt))
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter(fmt))
        logger.addHandler(fh)
        logger.addHandler(ch)
    return logger

logger = setup_logging()

def log_event(category: str, user=None, details: str = ""):
    """
    Unified logging function.
    category: one of SYSTEM, USERS, COMMAND, GAME, SUMMARY, CREATOR
    user: Telegram user object (or None)
    details: descriptive string
    """
    uname = "Unknown"
    uid = "N/A"
    if user:
        uname = getattr(user, "username", None) or f"{getattr(user, 'first_name', '')}".strip() or "NoUsername"
        uid = getattr(user, "id", "N/A")
    message = f"[{category}] {details} | User: @{uname} ({uid})"
    # Route by category
    if category.upper() == "SYSTEM":
        logger.info(message)
    elif category.upper() == "USERS":
        logger.info(message)
    elif category.upper() == "COMMAND":
        logger.info(message)
    elif category.upper() == "GAME":
        logger.info(message)
    elif category.upper() == "SUMMARY":
        logger.info(message)
    elif category.upper() == "CREATOR":
        logger.info(message)
    else:
        logger.info(f"[OTHER] {details} | User: @{uname} ({uid})")

# End of logging section
# =============================

# ------------------------------
# Constants & Environment
# ------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CREATOR_ID = int(os.environ.get("CREATOR_ID")) if os.environ.get("CREATOR_ID") else None
RENDER_URL = os.environ.get("RENDER_URL")  # e.g. https://your-app.onrender.com

TIMEZONE = pytz.timezone("Asia/Kolkata")
RULES_FILE = "rules.txt"
USERS_FILE = "users.txt"

# Game configuration (unchanged logic)
CASE1 = [10, 10, 15, 30, 50]
CASE2 = [10, 25, 65]
TAX_RATE = 0.10  # 10% tax on profit

# Ensure essential files exist
for fname in (RULES_FILE, USERS_FILE, LOG_FILE):
    if not os.path.exists(fname):
        with open(fname, "w", encoding="utf-8") as f:
            f.write("")

# ------------------------------
# FLASK APP (for Render webhook + UptimeRobot)
# ------------------------------
app = Flask(__name__)

@app.route("/")
def root():
    log_event("SYSTEM", None, "Root endpoint hit.")
    return "ColorElephant Bot is running."

@app.route("/ping")
def ping():
    log_event("SYSTEM", None, "/ping received.")
    return jsonify(status="ok", message="Ping received. Bot alive."), 200

# ------------------------------
# Utilities
# ------------------------------
def nearest_ten(value):
    try:
        return int(floor(float(value) / 10) * 10)
    except Exception:
        return 0

def percent_of(balance, pct):
    """Return nearest ten of (balance * pct/100)"""
    try:
        return nearest_ten(balance * pct / 100)
    except Exception:
        return 0

def load_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            txt = f.read().strip()
            return txt if txt else "No rules defined."
    return "Rules not found."

def track_user(user):
    """Record user id and username in USERS_FILE (one per line: id,username)"""
    if not user:
        return
    uid = getattr(user, "id", None)
    uname = getattr(user, "username", "") or ""
    if uid is None:
        return
    existing = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",", 1)
                try:
                    existing[int(parts[0])] = parts[1] if len(parts) > 1 else ""
                except Exception:
                    continue
    existing[uid] = uname
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        for k, v in existing.items():
            f.write(f"{k},{v}\n")
    log_event("USERS", user, "Tracked user.")

# ------------------------------
# GAME LOGIC & HANDLERS (preserve original logic)
# ------------------------------

def start_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    track_user(user)
    log_event("COMMAND", user, "/start invoked")
    start_game_flow(update, context)

def start_game_flow(update: Update, context: CallbackContext):
    # Reset user_data for new session
    context.user_data.clear()
    context.user_data["input_buffer"] = ""
    # Numeric keypad: digits on left, multipliers on right
    keyboard = [
        ["1", "2", "3", "10"],
        ["4", "5", "6", "100"],
        ["7", "8", "9", "1K"],
        ["0", "Clear", "Enter", "10K"],
    ]
    update.message.reply_text(
        "Game Started.\n\nPlease enter your Current Balance (e.g., 1000).\nYou can type a number or use the keypad below. Press Enter when ready.",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False),
    )

def reset(update: Update, context: CallbackContext):
    user = update.effective_user
    chat_id = update.effective_chat.id
    log_event("COMMAND", user, "/reset invoked")

    sent_messages = context.user_data.get("sent_messages", [])
    deleted_count = 0

    # Try deleting all stored bot messages for this chat
    for mid in sent_messages:
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=mid)
            deleted_count += 1
        except Exception:
            continue

    # Delete the user's command message too (optional, cleaner)
    try:
        context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

    # Clear all session data
    context.user_data.clear()
    context.chat_data.clear()

    # Log and confirm
    log_event("SYSTEM", user, f"Session reset. Deleted {deleted_count} messages.")
    update.message.reply_text(
        f"♻️ Session cleared. {deleted_count} previous messages deleted.\n"
        "You can start a new one anytime with /start."
    )


def process_balance(update: Update, context: CallbackContext):
    """
    Handles keypad tokens and manual numeric input.
    - Buffer behavior: digits and multiplier tokens append to buffer (and echo)
    - Clear resets buffer
    - Enter finalizes buffer and starts session
    - Manual numbers are accepted immediately as final when not a keypad token
    """
    user = update.effective_user
    text = update.message.text.strip()
    log_event("COMMAND", user, f"Text received: {text}")

    buf = context.user_data.get("input_buffer", "")

    token = text.upper()

    # keypad tokens that append to buffer
    if token in {"0","1","2","3","4","5","6","7","8","9"}:
        buf += token
        context.user_data["input_buffer"] = buf
        update.message.reply_text(f"Buffer: {buf}")
        return

    if token in {"10", "100"}:
        buf += token
        context.user_data["input_buffer"] = buf
        update.message.reply_text(f"Buffer: {buf}")
        return

    if token == "1K":
        if buf == "":
            buf = "1000"
        else:
            buf = buf + "000"
        context.user_data["input_buffer"] = buf
        update.message.reply_text(f"Buffer: {buf}")
        return

    if token == "10K":
        if buf == "":
            buf = "10000"
        else:
            buf = buf + "0000"
        context.user_data["input_buffer"] = buf
        update.message.reply_text(f"Buffer: {buf}")
        return

    if token == "CLEAR":
        context.user_data["input_buffer"] = ""
        update.message.reply_text("Buffer cleared. Enter digits.")
        return

    if token == "ENTER":
        raw = context.user_data.get("input_buffer", "")
        if raw == "":
            update.message.reply_text("Buffer empty. Type or tap digits first.")
            return
        final_txt = raw.upper()
        if final_txt.endswith("K"):
            try:
                num = float(final_txt[:-1])
                final_txt = str(int(num * 1000))
            except Exception:
                update.message.reply_text("Invalid number in buffer.")
                return
        if not final_txt.replace(".", "", 1).isdigit():
            update.message.reply_text("Buffer doesn't contain a valid number.")
            return
        try:
            balance = float(final_txt)
        except Exception:
            update.message.reply_text("Invalid numeric value.")
            return
        # proceed to start session
    else:
        # If the user typed a manual number (not a keypad token)
        txt = text.upper()
        # allow suffix K (e.g., 1K)
        if txt.endswith("K"):
            try:
                num = float(txt[:-1])
                txt = str(int(num * 1000))
            except Exception:
                update.message.reply_text("Please enter a valid number (e.g., 1000).")
                return
        if not txt.replace(".", "", 1).isdigit():
            update.message.reply_text("Please enter a valid numeric balance (e.g., 1000).")
            return
        try:
            balance = float(txt)
        except Exception:
            update.message.reply_text("Please enter a valid number (e.g., 1000).")
            return

    # Now we have 'balance' finalized
    balance = nearest_ten(balance)
    log_event("GAME", user, f"Balance entered: ₹{balance}")
    track_user(user)

    # initialize session state
    context.user_data["BaseBalance"] = balance
    context.user_data["Round"] = 1
    context.user_data["Path"] = None
    context.user_data["Wins"] = 0
    context.user_data["Losses"] = 0
    context.user_data["TotalPlaced"] = 0
    context.user_data["Profit"] = 0
    context.user_data["seq"] = []
    context.user_data["input_buffer"] = ""

    # remove keypad
    update.message.reply_text("Balance saved. Let's begin!", reply_markup=ReplyKeyboardRemove())

    # Round 1 investment (always 10% of base)
    investment = percent_of(balance, CASE1[0])
    context.user_data["TotalPlaced"] += investment
    update.message.reply_text(f"Round 1: Place ₹{investment} (10% of ₹{balance}).")
    buttons = [[InlineKeyboardButton("Win", callback_data="r1_win"), InlineKeyboardButton("Lose", callback_data="r1_lose")]]
    update.message.reply_text("Round 1 result?", reply_markup=InlineKeyboardMarkup(buttons))

# ------------------------------
# Simulation helpers for summary & estimate
# ------------------------------
def simulate_session_profit_for_path(base_balance: int, outcomes):
    """
    Simulate profit for a given sequence of 'W'/'L' outcomes
    - base balance remains constant
    - CASE chosen by first round (W => CASE1, L => CASE2)
    - win => gain equal to investment (gross), taxed 10% on the profit portion
    - lose => investment is lost
    - stop rules: if a win occurs after round1, stop (session ends). Max rounds per case apply.
    Returns integer profit (rounded to nearest ten).
    """
    profit = 0
    if not outcomes:
        return 0
    path = "case1" if outcomes[0] == "W" else "case2"
    percentages = CASE1 if path == "case1" else CASE2
    for i, res in enumerate(outcomes):
        round_no = i + 1
        if round_no > len(percentages):
            break
        pct = percentages[round_no - 1]
        invest = percent_of(base_balance, pct)
        if res == "W":
            gross_profit = invest  # you get invested amount as profit (receive 2x investment but profit = investment)
            tax = gross_profit * TAX_RATE
            net_profit = gross_profit - tax
            profit += net_profit
            if round_no > 1:
                break
        else:
            profit -= invest
    profit = nearest_ten(profit)
    return int(profit)

def generate_possible_sequences():
    """
    Generate all possible outcome sequences respecting stop rules and max lengths.
    """
    sequences = []

    def rec(seq):
        # If sequence ended with W after round>1, it's terminal
        if seq and seq[-1] == "W" and len(seq) > 1:
            sequences.append(seq.copy())
            return
        if not seq:
            # first round can be W or L
            rec(["W"])
            rec(["L"])
            return
        path = "case1" if seq[0] == "W" else "case2"
        max_len = len(CASE1) if path == "case1" else len(CASE2)
        if len(seq) >= max_len:
            sequences.append(seq.copy())
            return
        # continue sequences
        rec(seq + ["W"])
        rec(seq + ["L"])

    rec([])
    # dedupe (shouldn't be necessary)
    unique = []
    seen = set()
    for s in sequences:
        key = "".join(s)
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique

def compute_all_session_profits(base_balance):
    seqs = generate_possible_sequences()
    out = []
    for s in seqs:
        p = simulate_session_profit_for_path(base_balance, s)
        out.append((s, p))
    return out

def compute_weighted_daily_profit(base_balance):
    """
    Weighted daily profit: 80% of worst-case profit + 20% average of other scenarios.
    Returns nearest ten integer.
    """
    all_profits = [p for (_, p) in compute_all_session_profits(base_balance)]
    if not all_profits:
        return 0
    worst = min(all_profits)
    others = [x for x in all_profits if x != worst]
    avg_others = int(sum(others) / len(others)) if others else worst
    weighted = 0.8 * worst + 0.2 * avg_others
    return nearest_ten(weighted)

# ------------------------------
# Handle round results & session progression
# ------------------------------
def handle_result(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user = update.effective_user
    log_event("GAME", user, f"Callback {query.data}")

    # load session
    base_balance = context.user_data.get("BaseBalance", 0)
    round_no = context.user_data.get("Round", 1)
    path = context.user_data.get("Path")
    total_placed = context.user_data.get("TotalPlaced", 0)
    profit = context.user_data.get("Profit", 0)
    wins = context.user_data.get("Wins", 0)
    losses = context.user_data.get("Losses", 0)
    seq = context.user_data.get("seq", [])

    data = query.data  # e.g., r1_win or r2_lose
    is_win = data.endswith("_win")
    result_label = "W" if is_win else "L"

    # Determine path if first round
    if round_no == 1:
        path = "case1" if is_win else "case2"
        context.user_data["Path"] = path

    percentages = CASE1 if path == "case1" else CASE2
    max_rounds = len(percentages)

    invest = percent_of(base_balance, percentages[round_no - 1])
    context.user_data["TotalPlaced"] = total_placed + invest

    if is_win:
        wins += 1
        gross_profit = invest  # profit equals investment
        tax = gross_profit * TAX_RATE
        net_profit = gross_profit - tax
        profit += net_profit
        context.user_data["Profit"] = nearest_ten(profit)
        context.user_data["Wins"] = wins
    else:
        losses += 1
        profit -= invest
        context.user_data["Profit"] = nearest_ten(profit)
        context.user_data["Losses"] = losses

    seq.append(result_label)
    context.user_data["seq"] = seq

    # Compute best/worst sequences for remark
    all_profits = compute_all_session_profits(base_balance)
    if all_profits:
        sorted_by = sorted(all_profits, key=lambda x: x[1])
        worst_seq = "".join(sorted_by[0][0])
        best_seq = "".join(sorted_by[-1][0])
    else:
        worst_seq = ""
        best_seq = ""

    current_seq_str = "".join(seq)
    if current_seq_str == worst_seq:
        remark = f"{current_seq_str} -> Worst possible scenario"
    elif current_seq_str == best_seq:
        remark = f"{current_seq_str} -> Best possible scenario"
    else:
        remark = f"{current_seq_str} -> Moderate performance"

    # End conditions:
    # - If win after round 1 (i.e., round_no > 1 and current is win) -> end
    # - OR if reached max rounds for this case -> end
    ended = False
    if is_win and round_no > 1:
        ended = True
    if round_no >= max_rounds:
        ended = True

    if ended:
        # finalize session summary
        total_rounds_played = round_no
        total_placed = context.user_data.get("TotalPlaced", 0)
        total_profit = context.user_data.get("Profit", 0)
        profit_after_tax = nearest_ten(total_profit)  # profit already net-of-tax where wins occurred
        updated_balance = nearest_ten(base_balance + profit_after_tax)

        summary = (
            "Session Summary:\n"
            f"Rounds Played: {total_rounds_played} ({wins} Won, {losses} Lost)\n"
            f"Amount Placed: ₹{total_placed}\n"
            f"Profit Made: ₹{nearest_ten(total_profit)}\n"
            f"Profit After Tax: ₹{profit_after_tax}\n"
            f"Balance After Session: ₹{updated_balance}\n\n"
            f"Outcome: {remark}\n\n"
            "Use /start to begin a new session."
        )
        query.message.reply_text(summary)
        log_event("SUMMARY", user, f"Rounds:{total_rounds_played} Profit:{profit_after_tax} Balance:{updated_balance}")
        # clear session
        context.user_data.clear()
        return

    # Otherwise go to next round
    next_round = round_no + 1
    context.user_data["Round"] = next_round
    next_pct = percentages[next_round - 1]
    next_invest = percent_of(base_balance, next_pct)
    context.user_data["TotalPlaced"] += next_invest

    query.message.reply_text(f"Round {next_round}: Place ₹{next_invest} ({next_pct}% of ₹{base_balance}).")
    buttons = [
        [InlineKeyboardButton("Win", callback_data=f"r{next_round}_win"), InlineKeyboardButton("Lose", callback_data=f"r{next_round}_lose")]
    ]
    query.message.reply_text(f"Round {next_round} result?", reply_markup=InlineKeyboardMarkup(buttons))

# ------------------------------
# Estimation command (/estimate)
# ------------------------------
def estimate_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    log_event("COMMAND", user, "/estimate invoked")
    # use base balance from args or session
    args = context.args
    if args:
        try:
            bal = float(args[0])
        except Exception:
            return update.message.reply_text("Usage: /estimate [balance]")
    else:
        bal = context.user_data.get("BaseBalance")
        if not bal:
            return update.message.reply_text("No balance found in session. Provide: /estimate 500")

    bal = nearest_ten(float(bal))

    # compute daily weighted profit
    daily = compute_weighted_daily_profit(bal)
    if daily == 0:
        return update.message.reply_text("Could not compute estimate (insufficient data).")

    # compound day-by-day
    def compound(start, days):
        b = start
        for _ in range(days):
            p = compute_weighted_daily_profit(b)
            b = nearest_ten(b + p)
        return b

    res10 = compound(bal, 10)
    res20 = compound(bal, 20)
    res30 = compound(bal, 30)

    update.message.reply_text(f"Estimated balance after 10 days: ₹{res10}")
    update.message.reply_text(f"Estimated balance after 20 days: ₹{res20}")
    update.message.reply_text(f"Estimated balance after 30 days: ₹{res30}")

# ------------------------------
# /rules and /commands
# ------------------------------
def rules_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    log_event("COMMAND", user, "/rules invoked")
    rules_text = load_rules()
    update.message.reply_text(f"Platform Rules:\n\n{rules_text}", parse_mode=ParseMode.MARKDOWN)

def commands_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    log_event("COMMAND", user, "/commands invoked")
    cmds = (
        "Available Commands:\n\n"
        "/start – Start predictions\n"
        "/reset – Reset session\n"
        "/rules – Show rules\n"
        "/commands – List commands\n"
        "/estimate [balance] – Estimate growth (10/20/30 days)\n"
    )
    update.message.reply_text(cmds, parse_mode=ParseMode.MARKDOWN)

# ------------------------------
# Creator login (/roka) and /logs (creator-only)
# ------------------------------
def roka_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    log_event("COMMAND", user, "/roka invoked")
    if CREATOR_ID and user.id == int(CREATOR_ID):
        update.message.reply_text("🧠 Creator access verified. Welcome, Roka.")
        log_event("CREATOR", user, "/roka success")
    else:
        update.message.reply_text("❌ Unauthorized command.")
        log_event("CREATOR", user, "/roka failed - unauthorized")

def logs_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    log_event("COMMAND", user, "/logs invoked")
    if not (CREATOR_ID and user.id == int(CREATOR_ID)):
        update.message.reply_text("You are not authorized to view logs.")
        log_event("CREATOR", user, "/logs access denied")
        return
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-30:]
        if not lines:
            update.message.reply_text("No logs found.")
            return
        text = "".join(lines[-30:])
        if len(text) > 3900:
            text = text[-3900:]
        update.message.reply_text("Last logs:\n```\n" + text + "\n```", parse_mode=ParseMode.MARKDOWN)
        log_event("CREATOR", user, "/logs displayed")
    except Exception as e:
        update.message.reply_text(f"Error reading logs: {e}")
        log_event("SYSTEM", user, f"/logs error: {e}")

# ------------------------------
# Unknown handler
# ------------------------------
def unknown_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    log_event("COMMAND", user, f"Unknown or unsupported: {update.message.text}")
    update.message.reply_text("Sorry, I am not programmed to answer this. Try /start or /commands.")

# ------------------------------
# MAIN - setup handlers and webhook
# ------------------------------
def main():
    # Basic validation
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set in environment.")
        return
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # User commands
    dp.add_handler(CommandHandler("start", start_cmd))
    dp.add_handler(CommandHandler("reset", reset_cmd))
    dp.add_handler(CommandHandler("estimate", estimate_cmd))
    dp.add_handler(CommandHandler("rules", rules_cmd))
    dp.add_handler(CommandHandler("commands", commands_cmd))

    # Creator commands
    dp.add_handler(CommandHandler("roka", roka_cmd))
    dp.add_handler(CommandHandler("logs", logs_cmd))

    # Callbacks for round results
    dp.add_handler(CallbackQueryHandler(handle_result, pattern="^r"))

    # Message handlers
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, process_balance))
    dp.add_handler(MessageHandler(Filters.command, unknown_cmd))

    # Flask webhook endpoint
    @app.route(f"/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        data = request.get_json(force=True)
        update = Update.de_json(data, updater.bot)
        dp.process_update(update)
        return "ok", 200

    # Set webhook for Render
    try:
        updater.bot.delete_webhook()
    except Exception:
        pass
    try:
        if not RENDER_URL:
            logger.warning("RENDER_URL not set; webhook won't be configured automatically.")
            log_event("SYSTEM", None, "RENDER_URL not set - webhook not configured.")
        else:
            wh = f"{RENDER_URL.rstrip('/')}/{BOT_TOKEN}"
            updater.bot.set_webhook(wh)
            log_event("SYSTEM", None, f"Webhook set to {wh}")
    except Exception as e:
        log_event("SYSTEM", None, f"Failed to set webhook: {e}")

    # Run Flask app (this will keep the process alive on Render)
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()