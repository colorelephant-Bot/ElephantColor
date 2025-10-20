# main.py
import os
import logging
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
from math import floor
import pytz
import random
from typing import List
from datetime import datetime, date

# =============================
# CONFIGURATION
# =============================

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID")) if os.environ.get("ADMIN_ID") else None
RENDER_URL = os.environ.get("RENDER_URL")  # e.g. https://color-elephant.onrender.com
TIMEZONE = pytz.timezone("Asia/Kolkata")
RULES_FILE = "rules.txt"
BANNED_FILE = "banned_users.txt"
USERS_FILE = "users.txt"
AUTHORIZED_FILE = "authorized_users.txt"
PENDING_FILE = "pending_auth.txt"
REVOKED_FILE = "revoked_users.txt"

CASE1 = [10, 10, 15, 30, 50]
CASE2 = [10, 25, 65]
TAX_RATE = 0.10  # 10% tax on profit
LOG_LINES_TO_SHOW = 30

# runtime server state
SERVER_DOWN = False

# =============================
# AUTO FILE CREATION
# =============================
REQUIRED_FILES = [BANNED_FILE, USERS_FILE, AUTHORIZED_FILE, PENDING_FILE, REVOKED_FILE, "bot.log"]

for fname in REQUIRED_FILES:
    if not os.path.exists(fname):
        # create file
        with open(fname, "w", encoding="utf-8") as f:
            f.write("")

# =============================
# LOGGING SETUP
# =============================

logging.basicConfig(
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log", mode="a", encoding="utf-8")],
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def log_event(event_type, user, message):
    """Log formatted events for better tracking"""
    name = ""
    username = "NoUsername"
    uid = "Unknown"
    if user:
        name = f"{getattr(user, 'first_name', '') or ''} {getattr(user, 'last_name', '') or ''}".strip()
        username = f"@{user.username}" if getattr(user, "username", None) else "NoUsername"
        uid = getattr(user, "id", "Unknown")
    logger.info(f"[{event_type}] {message} | User: {username} ({uid}) - {name}")


# =============================
# FLASK APP (Webhook + Ping)
# =============================

app = Flask("")


@app.route("/")
def home():
    logger.info("[PING] Root endpoint hit.")
    return "Bot is running."


@app.route("/ping")
def ping():
    logger.info("[PING] /ping endpoint accessed.")
    return jsonify(status="ok", message="Ping received. Bot alive."), 200


# =============================
# FILE UTILITIES
# =============================

def load_banned():
    banned = set()
    if os.path.exists(BANNED_FILE):
        with open(BANNED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        banned.add(int(line))
                    except Exception:
                        continue
    return banned


def save_banned(banned_set):
    with open(BANNED_FILE, "w", encoding="utf-8") as f:
        for uid in sorted(banned_set):
            f.write(str(uid) + "\n")


def track_user(user):
    """Save user id + username to USERS_FILE for broadcast"""
    if not user:
        return
    uid = getattr(user, "id", None)
    username = getattr(user, "username", "") or ""
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
    existing[uid] = username
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        for k, v in existing.items():
            f.write(f"{k},{v}\n")


def load_tracked_users():
    users = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",", 1)
                try:
                    uid = int(parts[0])
                except Exception:
                    continue
                users[uid] = parts[1] if len(parts) > 1 else ""
    return users


def load_authorized():
    auth = set()
    if os.path.exists(AUTHORIZED_FILE):
        with open(AUTHORIZED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    auth.add(int(line))
                except Exception:
                    continue
    return auth


def save_authorized(auth_set):
    with open(AUTHORIZED_FILE, "w", encoding="utf-8") as f:
        for uid in sorted(auth_set):
            f.write(str(uid) + "\n")


def load_pending():
    pending = []
    if os.path.exists(PENDING_FILE):
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        # store as int if numeric else raw
                        pending.append(line)
                    except Exception:
                        continue
    return pending


def save_pending(pending_list):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        for entry in pending_list:
            f.write(str(entry) + "\n")


def load_revoked():
    # revoked file lines: uid,date_string (YYYY-MM-DD)
    revoked = {}
    if os.path.exists(REVOKED_FILE):
        with open(REVOKED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",", 1)
                try:
                    uid = int(parts[0])
                    dt = parts[1] if len(parts) > 1 else ""
                    revoked[uid] = dt
                except Exception:
                    continue
    return revoked


def save_revoked(revoked_dict):
    with open(REVOKED_FILE, "w", encoding="utf-8") as f:
        for uid, dt in revoked_dict.items():
            f.write(f"{uid},{dt}\n")


# initialize sets/dicts
BANNED_USERS = load_banned()
TRACKED_USERS = load_tracked_users()
AUTHORIZED_USERS = load_authorized()
PENDING_USERS = load_pending()
REVOKED_USERS = load_revoked()


# =============================
# UTILS
# =============================

def nearest_ten(value):
    return int(floor(value / 10) * 10)


def percent_of(balance, pct):
    return nearest_ten(balance * pct / 100)


def load_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return "Rules not found."


def _is_admin(user_id):
    if ADMIN_ID is None:
        return False
    try:
        return int(user_id) == int(ADMIN_ID)
    except Exception:
        return False


def is_authorized(user_id):
    # admin always authorized
    if _is_admin(user_id):
        return True
    try:
        return int(user_id) in AUTHORIZED_USERS
    except Exception:
        return False


def is_revoked_today(user_id):
    # rough day check: if revoked date == today => still in cooldown
    dt_str = REVOKED_USERS.get(int(user_id))
    if not dt_str:
        return False
    try:
        revoked_date = datetime.strptime(dt_str, "%Y-%m-%d").date()
        return revoked_date == date.today()
    except Exception:
        return False


def server_block_check(update, context):
    """Return True if requests should be blocked due to server down (only admin allowed)."""
    global SERVER_DOWN
    user = update.effective_user
    if SERVER_DOWN and not _is_admin(getattr(user, "id", None)):
        # non-admins receive shutdown message
        try:
            update.message.reply_text("Server Shutdown 🚫")
        except Exception:
            try:
                update.callback_query.message.reply_text("Server Shutdown 🚫")
            except Exception:
                pass
        return True
    return False


def reject_if_banned(update: Update, context: CallbackContext):
    user = update.effective_user
    if not user:
        return False
    # admin cannot be banned
    if _is_admin(getattr(user, "id", None)):
        return False
    if int(user.id) in BANNED_USERS:
        logger.info(f"[BLOCKED] Banned user {user.id}, trying to access.")
        try:
            update.message.reply_text("You are banned from using this bot.")
        except Exception:
            pass
        return True
    return False


def require_authorization(update, context):
    """
    Checks authorization for user. If not authorized, send 'No authorization' message and hint /authorize.
    Returns True if not authorized (i.e., should stop processing).
    """
    user = update.effective_user
    if not user:
        return True
    if _is_admin(user.id):
        return False
    # banned check
    if int(user.id) in BANNED_USERS:
        try:
            update.message.reply_text("You are banned from using this bot.")
        except Exception:
            pass
        return True
    # revoked today check
    if is_revoked_today(user.id):
        try:
            update.message.reply_text("⚠️ Your access has been revoked. You may re-apply after 12 hours.")
        except Exception:
            pass
        return True
    # authorized?
    if not is_authorized(user.id):
        try:
            update.message.reply_text(
                "❌ No authorization.\nAccess to Bot not possible.\nInitiate authorization request with /authorize."
            )
            # log attempted access
            log_event("AUTH_DENIED", user, "Attempted access without authorization")
        except Exception:
            pass
        return True
    return False


# =============================
# GAME LOGIC (original behavior preserved)
# =============================

def start_game_flow(update: Update, context: CallbackContext):
    context.user_data.clear()
    # compact keypad with multipliers to the right and Enter/Clear
    keyboard = [
        ["1", "2", "3", "10"],
        ["4", "5", "6", "100"],
        ["7", "8", "9", "1K"],
        ["0", "Clear", "Enter", "10K"],
    ]
    context.user_data["input_buffer"] = ""
    update.message.reply_text(
        "Game Started!\n\nPlease enter your Current Balance.\nYou can type manually or use the number pad below.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard, one_time_keyboard=False, resize_keyboard=True, input_field_placeholder="Enter or tap digits"
        ),
    )


def start_game(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    if server_block_check(update, context):
        return
    user = update.effective_user
    # authorization check
    if require_authorization(update, context):
        return
    track_user(user)
    log_event("COMMAND", user, "/start invoked")
    start_game_flow(update, context)


def process_balance(update: Update, context: CallbackContext):
    # This function handles keypad tokens and final entry via Enter button;
    # also handles manual typing
    if reject_if_banned(update, context):
        return
    if server_block_check(update, context):
        return

    user = update.effective_user
    text = update.message.text.strip()

    # if user is not authorized, block (unless admin)
    if not _is_admin(user.id) and not is_authorized(user.id):
        # allow only /authorize
        try:
            update.message.reply_text("❌ No authorization.\nAccess to Bot not possible.\nInitiate authorization request with /authorize.")
            log_event("AUTH_DENIED", user, "Attempted input without authorization")
        except Exception:
            pass
        return

    buf = context.user_data.get("input_buffer", "")

    token = text.upper()

    # Handle special tokens
    if token == "CLEAR":
        context.user_data["input_buffer"] = ""
        return update.message.reply_text("Buffer cleared. Enter digits.")
    if token == "ENTER":
        raw = context.user_data.get("input_buffer", "")
        if raw == "":
            return update.message.reply_text("Buffer empty. Type or tap digits first.")
        t = raw.upper()
        if t.endswith("K"):
            try:
                num = float(t[:-1])
                raw = str(int(num * 1000))
            except Exception:
                return update.message.reply_text("Invalid number in buffer.")
        if not raw.replace(".", "", 1).isdigit():
            return update.message.reply_text("Buffer doesn't contain a valid number.")
        try:
            balance = float(raw)
        except Exception:
            return update.message.reply_text("Invalid numeric value in buffer.")
    else:
        # map 1K/10K/10/100 tokens
        if token in {"1K", "10K"}:
            if token == "1K":
                if buf == "":
                    buf = "1000"
                else:
                    buf = buf + "000"
            else:
                if buf == "":
                    buf = "10000"
                else:
                    buf = buf + "0000"
            context.user_data["input_buffer"] = buf
            return update.message.reply_text(f"Buffer: {buf}")
        if token in {"10", "100"}:
            # append as digits
            buf = buf + token
            context.user_data["input_buffer"] = buf
            return update.message.reply_text(f"Buffer: {buf}")
        if token in {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            buf = buf + token
            context.user_data["input_buffer"] = buf
            return update.message.reply_text(f"Buffer: {buf}")

        # if user typed manual number (not tokens)
        txt = text.upper()
        if txt.endswith("K"):
            try:
                num = float(txt[:-1])
                txt = str(int(num * 1000))
            except Exception:
                return update.message.reply_text("Please enter a valid number (e.g., 1000).")
        if not txt.replace(".", "", 1).isdigit():
            return update.message.reply_text("Please enter a valid numeric balance (e.g., 1000).")
        try:
            balance = float(txt)
        except Exception:
            return update.message.reply_text("Please enter a valid number (e.g., 1000).")

    # final validation & start session
    balance = nearest_ten(balance)
    log_event("BALANCE", user, f"Entered balance: ₹{balance}")
    track_user(user)

    context.user_data["BaseBalance"] = balance
    context.user_data["Round"] = 1
    context.user_data["Path"] = None
    context.user_data["Wins"] = 0
    context.user_data["Losses"] = 0
    context.user_data["TotalPlaced"] = 0
    context.user_data["Profit"] = 0
    context.user_data["input_buffer"] = ""

    update.message.reply_text("Balance saved. Let's begin!", reply_markup=ReplyKeyboardRemove())

    investment = percent_of(balance, CASE1[0])
    context.user_data["TotalPlaced"] += investment
    update.message.reply_text(f"Round 1: Place ₹{investment} (10% of ₹{balance}).")
    buttons = [[InlineKeyboardButton("Win", callback_data="r1_win"), InlineKeyboardButton("Lose", callback_data="r1_lose")]]
    update.message.reply_text("Round 1 result?", reply_markup=InlineKeyboardMarkup(buttons))


# =============================
# Simulation & helper for estimate
# =============================

def simulate_session_profit_for_path(base_balance: int, outcomes: List[str]) -> int:
    """
    Simulate profit (after tax) for a given sequence of outcomes list like ['W','L','L'].
    Uses the same rules as the bot: base balance constant, CASE1/CASE2 for percentages,
    winning gives 2x the investment (profit = investment) taxed at TAX_RATE, losing subtracts investment.
    """
    profit = 0
    path = "case1" if outcomes[0] == "W" else "case2"
    percentages = CASE1 if path == "case1" else CASE2
    for i, res in enumerate(outcomes):
        round_no = i + 1
        if round_no > len(percentages):
            break
        pct = percentages[round_no - 1]
        invest = nearest_ten(base_balance * pct / 100)
        if res == "W":
            gross_profit = invest
            tax = gross_profit * TAX_RATE
            net = gross_profit - tax
            profit += net
            if round_no > 1:
                break
        else:
            profit -= invest
    profit = nearest_ten(profit)
    return int(profit)


def generate_possible_outcome_sequences():
    sequences = []

    def rec(seq):
        if len(seq) >= 1:
            last_round = len(seq)
            if seq[-1] == "W" and last_round > 1:
                sequences.append(seq.copy())
                return
        # Determine path by first result
        if len(seq) == 0:
            rec(seq + ["W"])
            rec(seq + ["L"])
            return
        path = "case1" if seq[0] == "W" else "case2"
        max_len = len(CASE1) if path == "case1" else len(CASE2)
        if len(seq) >= max_len:
            sequences.append(seq.copy())
            return
        rec(seq + ["W"])
        rec(seq + ["L"])

    rec([])
    seqs = [s for s in sequences if s]
    return seqs


def compute_all_session_profits(base_balance: int):
    seqs = generate_possible_outcome_sequences()
    profits = []
    for s in seqs:
        p = simulate_session_profit_for_path(base_balance, s)
        profits.append((s, p))
    return profits


def compute_weighted_daily_profit(base_balance: int):
    """Compute weighted daily profit using 80% worst + 20% average of other scenarios."""
    all_profits = compute_all_session_profits(base_balance)
    if not all_profits:
        return 0
    profits = [p for (_, p) in all_profits]
    if not profits:
        return 0
    worst = min(profits)
    others = [x for x in profits if x != worst]
    avg_others = sum(others) / len(others) if others else worst
    weighted = 0.8 * worst + 0.2 * avg_others
    return nearest_ten(weighted)


# =============================
# HANDLE RESULT (original logic preserved + summary + remark)
# =============================

def handle_result(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    if server_block_check(update, context):
        return

    query = update.callback_query
    query.answer()
    data = query.data
    user = update.effective_user
    track_user(user)

    # authorization check (non-admins must be authorized)
    if not _is_admin(user.id) and not is_authorized(user.id):
        try:
            query.message.reply_text("❌ No authorization.\nAccess to Bot not possible.\nInitiate authorization request with /authorize.")
            log_event("AUTH_DENIED", user, "Attempted result input without authorization")
        except Exception:
            pass
        return

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

    # build sequence list for remark
    seq_list = context.user_data.get("seq", [])
    seq_list.append("W" if data.endswith("_win") else "L")
    context.user_data["seq"] = seq_list
    seq_str = "".join(seq_list)

    # determine best/worst sequences for remark
    all_profits = compute_all_session_profits(base_balance)
    if all_profits:
        sorted_by_profit = sorted(all_profits, key=lambda x: x[1])
        worst_seq, worst_profit = sorted_by_profit[0]
        best_seq, best_profit = sorted_by_profit[-1]
        worst_seq_str = "".join(worst_seq)
        best_seq_str = "".join(best_seq)
    else:
        worst_seq_str = ""
        best_seq_str = ""

    if seq_str == worst_seq_str:
        remark = f"{seq_str} -> Worst possible scenario"
    elif seq_str == best_seq_str:
        remark = f"{seq_str} -> Best possible scenario"
    else:
        remark = f"{seq_str} -> Moderate performance"

    # End on WIN after round1 or max rounds reached
    if data.endswith("_win") and round_num > 1:
        profit_after_tax = nearest_ten(profit)
        updated_balance = nearest_ten(base_balance + profit_after_tax)
        msg = (
            "Session Summary:\n"
            f"Rounds Played: {round_num} ({wins} Won, {losses} Lost)\n"
            f"Amount Placed: ₹{context.user_data['TotalPlaced']}\n"
            f"Profit Made: ₹{nearest_ten(profit)}\n"
            f"Profit After Tax: ₹{nearest_ten(profit_after_tax)}\n"
            f"Balance After Session: ₹{nearest_ten(updated_balance)}\n\n"
            f"Outcome: {remark}\n\n"
            "Use /start to begin a new session."
        )
        query.message.reply_text(msg)
        log_event("SUMMARY", user, f"Profit ₹{profit_after_tax} | Balance ₹{updated_balance}")
        context.user_data.clear()
        return

    if round_num >= total_rounds:
        profit_after_tax = nearest_ten(profit)
        updated_balance = nearest_ten(base_balance + profit_after_tax)
        msg = (
            "Session Summary:\n"
            f"Rounds Played: {round_num} ({wins} Won, {losses} Lost)\n"
            f"Amount Placed: ₹{context.user_data['TotalPlaced']}\n"
            f"Profit Made: ₹{nearest_ten(profit)}\n"
            f"Profit After Tax: ₹{nearest_ten(profit_after_tax)}\n"
            f"Balance After Session: ₹{nearest_ten(updated_balance)}\n\n"
            f"Outcome: {remark}\n\n"
            "Use /start to begin a new session."
        )
        query.message.reply_text(msg)
        log_event("SUMMARY", user, f"Profit ₹{profit_after_tax} | Balance ₹{updated_balance}")
        context.user_data.clear()
        return

    # Next round
    next_round = round_num + 1
    context.user_data["Round"] = next_round
    next_percent = percentages[next_round - 1]
    invest_amount = percent_of(base_balance, next_percent)
    context.user_data["TotalPlaced"] += invest_amount

    query.message.reply_text(f"Round {next_round}: Place ₹{invest_amount} ({next_percent}% of ₹{base_balance}).")
    buttons = [[InlineKeyboardButton("Win", callback_data=f"r{next_round}_win"), InlineKeyboardButton("Lose", callback_data=f"r{next_round}_lose")]]
    query.message.reply_text(f"Round {next_round} result?", reply_markup=InlineKeyboardMarkup(buttons))


# =============================
# AUTHORIZATION: /authorize, admin notifications & handling
# =============================

def authorize_cmd(update: Update, context: CallbackContext):
    """User requests authorization"""
    user = update.effective_user
    if not user:
        return
    # Admin always authorized
    if _is_admin(user.id):
        update.message.reply_text("You are the admin and already have full access.")
        return
    # If banned
    if int(user.id) in BANNED_USERS:
        update.message.reply_text("You are banned from using this bot.")
        return
    # If already authorized
    if is_authorized(user.id):
        update.message.reply_text("You already have access.")
        return
    # If revoked today, deny re-apply
    if is_revoked_today(user.id):
        update.message.reply_text("⚠️ Your access has been revoked. You may re-apply after 12 hours.")
        return
    # Add to pending if not already
    pending = set(load_pending())
    if str(user.id) in pending:
        update.message.reply_text("Your authorization request is already in queue.")
        return
    pending.add(str(user.id))
    save_pending(list(pending))
    update.message.reply_text("📨 Request submitted and is in queue. Bot will notify you when access is granted.")
    # notify admin
    msg = f"New authorization request from @{user.username or 'NoUsername'} ({user.id})\nName: {user.first_name or ''} {user.last_name or ''}"
    log_event("AUTH_REQUEST", user, "New authorization request")
    # send admin inline approve/reject
    try:
        keyboard = [
            [InlineKeyboardButton("Approve", callback_data=f"auth_approve:{user.id}"), InlineKeyboardButton("Reject", callback_data=f"auth_reject:{user.id}")],
        ]
        # send to admin via bot (if admin id available)
        if ADMIN_ID:
            context.bot.send_message(chat_id=ADMIN_ID, text=msg, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Failed to notify admin about auth request: {e}")


def admin_approve_reject_handler(update: Update, context: CallbackContext):
    """Handle admin approve/reject clicks for auth requests"""
    query = update.callback_query
    query.answer()
    user = query.from_user
    if not _is_admin(user.id):
        query.message.reply_text("Not authorized.")
        return
    data = query.data  # format: auth_approve:<uid> or auth_reject:<uid>
    try:
        action, uid_str = data.split(":", 1)
        uid = int(uid_str)
    except Exception:
        query.message.reply_text("Invalid request.")
        return

    pending = set(load_pending())
    revoked = load_revoked()
    authorized = load_authorized()

    if action == "auth_approve":
        # remove from pending
        if str(uid) in pending:
            pending.remove(str(uid))
            save_pending(list(pending))
        authorized.add(uid)
        save_authorized(authorized)
        # notify user
        try:
            context.bot.send_message(chat_id=uid, text="✅ Authorization approved. You now have access to all bot commands.")
        except Exception:
            pass
        log_event("AUTH_APPROVE", user, f"Approved {uid}")
        query.message.reply_text(f"Approved {uid}.")
        return

    if action == "auth_reject":
        if str(uid) in pending:
            pending.remove(str(uid))
            save_pending(list(pending))
        # add to revoked with today's date as quick denial? We'll just notify user.
        try:
            context.bot.send_message(chat_id=uid, text="❌ Your authorization request has been denied.")
        except Exception:
            pass
        log_event("AUTH_REJECT", user, f"Rejected {uid}")
        query.message.reply_text(f"Rejected {uid}.")
        return


def admin_manage_authorizations_menu(update: Update, context: CallbackContext):
    user = update.effective_user
    if not _is_admin(user.id):
        update.message.reply_text("You are not authorized.")
        return
    buttons = [
        [InlineKeyboardButton("List authorized", callback_data="manage_list_auth")],
        [InlineKeyboardButton("List pending", callback_data="manage_list_pending")],
        [InlineKeyboardButton("Revoke user", callback_data="manage_revoke_user")],
    ]
    update.message.reply_text("Manage Authorizations:", reply_markup=InlineKeyboardMarkup(buttons))


def admin_manage_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    user = query.from_user
    if not _is_admin(user.id):
        query.message.reply_text("Not authorized.")
        return
    data = query.data

    if data == "manage_list_auth":
        auth = sorted(list(load_authorized()))
        if not auth:
            query.message.reply_text("No authorized users.")
            return
        lines = []
        for uid in auth[-30:]:
            lines.append(str(uid))
        query.message.reply_text("Authorized users (last 30):\n" + "\n".join(lines))
        return

    if data == "manage_list_pending":
        pend = load_pending()
        if not pend:
            query.message.reply_text("No pending requests.")
            return
        lines = []
        for p in pend[-30:]:
            lines.append(p)
        query.message.reply_text("Pending requests (IDs):\n" + "\n".join(lines))
        return

    if data == "manage_revoke_user":
        query.message.reply_text("Send user id to revoke access.")
        context.user_data["admin_action"] = "revoke_user"
        return


def admin_followup_authorization(update: Update, context: CallbackContext):
    user = update.effective_user
    if not _is_admin(user.id):
        return
    action = context.user_data.get("admin_action")
    if not action:
        return
    text = update.message.text.strip()
    if action == "revoke_user":
        try:
            uid = int(text.strip())
        except Exception:
            update.message.reply_text("Invalid id.")
            context.user_data.pop("admin_action", None)
            return
        auth = load_authorized()
        if uid in auth:
            auth.remove(uid)
            save_authorized(auth)
        # add to revoked with today's date
        revoked = load_revoked()
        revoked[uid] = date.today().strftime("%Y-%m-%d")
        save_revoked(revoked)
        # ensure not in pending
        pend = set(load_pending())
        if str(uid) in pend:
            pend.remove(str(uid))
            save_pending(list(pend))
        # log and notify
        log_event("AUTH_REVOKE", user, f"Revoked {uid}")
        try:
            context.bot.send_message(chat_id=uid, text="⚠️ Your access has been revoked. You may re-apply after 12 hours.")
        except Exception:
            pass
        update.message.reply_text(f"User {uid} revoked and put under cooldown.")
        context.user_data.pop("admin_action", None)
        return


# =============================
# ADMIN PORTAL (/roka) and other admin callbacks
# =============================

def admin_menu(update: Update, context: CallbackContext):
    user = update.effective_user
    if not _is_admin(user.id):
        update.message.reply_text("You are not authorized.")
        return
    # show inline admin options including auth management
    buttons = [
        [InlineKeyboardButton("Logs", callback_data="admin_logs"), InlineKeyboardButton("Shutdown", callback_data="admin_shutdown")],
        [InlineKeyboardButton("Reboot", callback_data="admin_reboot"), InlineKeyboardButton("Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("Ban user", callback_data="admin_ban"), InlineKeyboardButton("Unban user", callback_data="admin_unban")],
        [InlineKeyboardButton("List banned", callback_data="admin_list_banned"), InlineKeyboardButton("List users", callback_data="admin_list_users")],
        [InlineKeyboardButton("Warn user", callback_data="admin_warn"), InlineKeyboardButton("Manage Authorizations", callback_data="admin_manage_auth")],
    ]
    update.message.reply_text("Admin portal:", reply_markup=InlineKeyboardMarkup(buttons))


def admin_callback(update: Update, context: CallbackContext):
    global SERVER_DOWN
    query = update.callback_query
    query.answer()
    user = query.from_user
    if not _is_admin(user.id):
        query.message.reply_text("Not authorized.")
        return

    data = query.data

    if data == "admin_logs":
        try:
            with open("bot.log", "r", encoding="utf-8") as f:
                lines = f.readlines()[-LOG_LINES_TO_SHOW:]
            if not lines:
                query.message.reply_text("No logs found.")
                return
            text = "".join(lines[-LOG_LINES_TO_SHOW:])
            if len(text) > 3900:
                text = text[-3900:]
            query.message.reply_text("Last logs:\n```\n" + text + "\n```", parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            query.message.reply_text(f"Error reading logs: {e}")
        return

    if data == "admin_shutdown":
        SERVER_DOWN = True
        log_event("ADMIN", user, "Shutdown invoked")
        query.message.reply_text("Server Shutdown mode enabled. Bot will only reply 'Server Shutdown' to regular users.")
        return

    if data == "admin_reboot":
        SERVER_DOWN = True
        query.message.reply_text("Server rebooting. ColorElephant Bot will be soon up. Thank you for your patience.")
        log_event("ADMIN", user, "Reboot invoked")
        # simulate reboot toggle
        SERVER_DOWN = False
        query.message.reply_text("Server is back online.")
        return

    if data == "admin_broadcast":
        query.message.reply_text("Send the broadcast message now (it will be sent to all tracked users).")
        context.user_data["admin_action"] = "broadcast"
        return

    if data == "admin_ban":
        query.message.reply_text("Send user id or @username to ban.")
        context.user_data["admin_action"] = "ban"
        return

    if data == "admin_unban":
        query.message.reply_text("Send user id or @username to unban.")
        context.user_data["admin_action"] = "unban"
        return

    if data == "admin_list_banned":
        banned = sorted(list(BANNED_USERS))[-10:]
        if not banned:
            query.message.reply_text("No banned users.")
            return
        lines = [str(uid) for uid in banned]
        query.message.reply_text("Last 10 banned IDs:\n" + "\n".join(lines))
        return

    if data == "admin_list_users":
        users = load_tracked_users()
        if not users:
            query.message.reply_text("No tracked users yet.")
            return
        items = list(users.items())[-30:]
        lines = [f"{uid} — @{users[uid]}" for uid, _ in items]
        query.message.reply_text("Tracked users (last 30):\n" + "\n".join(lines))
        return

    if data == "admin_warn":
        query.message.reply_text("Send user id and warning message separated by a newline (user_id\\nmessage).")
        context.user_data["admin_action"] = "warn"
        return

    if data == "admin_manage_auth":
        admin_manage_authorizations_menu(update, context)
        return


def admin_manage_authorizations_menu(update: Update, context: CallbackContext):
    user = update.effective_user
    if not _is_admin(user.id):
        update.message.reply_text("Not authorized.")
        return
    buttons = [
        [InlineKeyboardButton("List authorized", callback_data="manage_list_auth")],
        [InlineKeyboardButton("List pending", callback_data="manage_list_pending")],
        [InlineKeyboardButton("Revoke user", callback_data="manage_revoke_user")],
    ]
    update.message.reply_text("Manage Authorizations:", reply_markup=InlineKeyboardMarkup(buttons))


def admin_followup_handler(update: Update, context: CallbackContext):
    # generic followups for broadcast, ban, unban, warn, etc.
    user = update.effective_user
    if not _is_admin(user.id):
        return
    action = context.user_data.get("admin_action")
    if not action:
        return
    text = update.message.text.strip()

    if action == "broadcast":
        msg = text
        users = load_tracked_users()
        success = 0
        for uid in users.keys():
            try:
                context.bot.send_message(chat_id=uid, text=f"ANNOUNCEMENT:\n\n{msg}")
                success += 1
            except Exception:
                continue
        update.message.reply_text(f"Broadcast sent to {success} users.")
        context.user_data.pop("admin_action", None)
        return

    if action == "ban":
        target = text.strip()
        if target.startswith("@"):
            try:
                chat = context.bot.get_chat(target)
                uid = chat.id
            except Exception:
                update.message.reply_text("Could not resolve username.")
                context.user_data.pop("admin_action", None)
                return
        else:
            try:
                uid = int(target)
            except Exception:
                update.message.reply_text("Invalid id.")
                context.user_data.pop("admin_action", None)
                return
        BANNED_USERS.add(uid)
        save_banned(BANNED_USERS)
        update.message.reply_text(f"Banned {uid}.")
        log_event("ADMIN", user, f"Banned {uid}")
        context.user_data.pop("admin_action", None)
        return

    if action == "unban":
        target = text.strip()
        try:
            uid = int(target) if not target.startswith("@") else context.bot.get_chat(target).id
        except Exception:
            update.message.reply_text("Invalid id or username.")
            context.user_data.pop("admin_action", None)
            return
        if uid in BANNED_USERS:
            BANNED_USERS.remove(uid)
            save_banned(BANNED_USERS)
            update.message.reply_text(f"Unbanned {uid}.")
            log_event("ADMIN", user, f"Unbanned {uid}")
        else:
            update.message.reply_text("User not banned.")
        context.user_data.pop("admin_action", None)
        return

    if action == "warn":
        parts = text.split("\n", 1)
        if len(parts) < 2:
            update.message.reply_text("Send in format: user_id\\nmessage")
            return
        try:
            uid = int(parts[0].strip())
            msg = parts[1].strip()
            context.bot.send_message(chat_id=uid, text=f"Warning:\n\n{msg}")
            update.message.reply_text(f"Warning sent to {uid}.")
            log_event("ADMIN", user, f"Warned {uid}")
        except Exception as e:
            update.message.reply_text(f"Failed to send warning: {e}")
        context.user_data.pop("admin_action", None)
        return


# =============================
# /logs (admin)
# =============================

def logs_cmd(update: Update, context: CallbackContext):
    user = update.effective_user
    if not _is_admin(user.id):
        update.message.reply_text("You are not authorized to view logs.")
        return
    try:
        with open("bot.log", "r", encoding="utf-8") as f:
            lines = f.readlines()[-LOG_LINES_TO_SHOW:]
        if not lines:
            update.message.reply_text("No logs found.")
            return
        log_text = "".join(lines[-LOG_LINES_TO_SHOW:])
        if len(log_text) > 3900:
            log_text = log_text[-3900:]
        update.message.reply_text("Last logs:\n```\n" + log_text + "\n```", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        update.message.reply_text(f"Error reading logs: {e}")


# =============================
# /estimate command
# =============================

def estimate_cmd(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    if server_block_check(update, context):
        return
    user = update.effective_user
    if require_authorization(update, context):
        return
    track_user(user)
    log_event("COMMAND", user, "/estimate invoked")

    args = context.args
    if args:
        try:
            bal = float(args[0])
        except Exception:
            return update.message.reply_text("Usage: /estimate [balance]")
    else:
        bal = context.user_data.get("BaseBalance")
        if not bal:
            return update.message.reply_text("No balance found in session. Provide balance like: /estimate 500")

    bal = nearest_ten(float(bal))
    daily = compute_weighted_daily_profit(bal)
    if daily == 0:
        return update.message.reply_text("Could not compute estimate (insufficient data).")

    # Simulate day-by-day compounding for 10/20/30 days
    def compound_days(start_balance, days):
        b = start_balance
        for _ in range(days):
            profit_today = compute_weighted_daily_profit(b)
            b = nearest_ten(b + profit_today)
        return b

    for d in (10, 20, 30):
        result = compound_days(bal, d)
        update.message.reply_text(f"Estimated balance after {d} days: ₹{result}")


# =============================
# Other commands: /clear, /rules, /commands
# =============================

def clear(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    if server_block_check(update, context):
        return
    user = update.effective_user
    if require_authorization(update, context):
        return
    log_event("COMMAND", user, "/clear invoked")
    context.user_data.clear()
    update.message.reply_text("Chat cleared. Use /start to start again.")


def rules(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    if server_block_check(update, context):
        return
    user = update.effective_user
    if require_authorization(update, context):
        return
    log_event("COMMAND", user, "/rules invoked")
    rules_text = load_rules()
    update.message.reply_text(f"Platform Rules:\n\n{rules_text}", parse_mode=ParseMode.MARKDOWN)


def commands_list(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    if server_block_check(update, context):
        return
    user = update.effective_user
    if require_authorization(update, context):
        return
    log_event("COMMAND", user, "/commands invoked")
    cmds = (
        "Available Commands:\n\n"
        "/start – Start predictions\n"
        "/clear – Reset chat\n"
        "/rules – Show rules\n"
        "/commands – List commands\n"
        "/estimate [balance] – Estimate growth (10/20/30 days)\n"
        "/authorize – Request access to bot\n"
    )
    update.message.reply_text(cmds, parse_mode=ParseMode.MARKDOWN)


def unknown(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return
    user = update.effective_user
    if server_block_check(update, context):
        return
    # for unknown, require authorization first
    if require_authorization(update, context):
        return
    log_event("UNKNOWN", user, f"Sent unknown command: {update.message.text}")
    update.message.reply_text("Sorry, I am not programmed to answer this. Try /start or /commands.")


# =============================
# Ban/unban direct commands (admin)
# =============================

def ban_cmd_direct(update: Update, context: CallbackContext):
    user = update.effective_user
    if not _is_admin(user.id):
        return
    if not context.args:
        update.message.reply_text("Usage: /ban <user_id>")
        return
    try:
        uid = int(context.args[0])
    except Exception:
        update.message.reply_text("Invalid id.")
        return
    BANNED_USERS.add(uid)
    save_banned(BANNED_USERS)
    log_event("ADMIN", user, f"Banned {uid}")
    update.message.reply_text(f"Banned {uid}")


def unban_cmd_direct(update: Update, context: CallbackContext):
    user = update.effective_user
    if not _is_admin(user.id):
        return
    if not context.args:
        update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        uid = int(context.args[0])
    except Exception:
        update.message.reply_text("Invalid id.")
        return
    if uid in BANNED_USERS:
        BANNED_USERS.remove(uid)
        save_banned(BANNED_USERS)
        log_event("ADMIN", user, f"Unbanned {uid}")
        update.message.reply_text(f"Unbanned {uid}")
    else:
        update.message.reply_text("User not banned.")


# =============================
# MAIN BOT LAUNCH (WEBHOOK)
# =============================

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Command handlers
    dp.add_handler(CommandHandler("start", start_game))
    dp.add_handler(CommandHandler("clear", clear))
    dp.add_handler(CommandHandler("rules", rules))
    dp.add_handler(CommandHandler("commands", commands_list))
    dp.add_handler(CommandHandler("logs", logs_cmd))
    dp.add_handler(CommandHandler("estimate", estimate_cmd))
    dp.add_handler(CommandHandler("authorize", authorize_cmd))
    dp.add_handler(CommandHandler("ban", ban_cmd_direct))
    dp.add_handler(CommandHandler("unban", unban_cmd_direct))
    dp.add_handler(CommandHandler("roka", admin_menu))

    # Callback handlers
    dp.add_handler(CallbackQueryHandler(admin_approve_reject_handler, pattern="^auth_"))
    dp.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    dp.add_handler(CallbackQueryHandler(admin_manage_callback, pattern="^manage_"))
    dp.add_handler(CallbackQueryHandler(handle_result, pattern="^r"))

    # Text handlers
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, process_balance))
    dp.add_handler(MessageHandler(Filters.command, unknown))

    # Admin followups
    dp.add_handler(MessageHandler(Filters.text & Filters.user(user_id=ADMIN_ID), admin_followup_handler))
    dp.add_handler(MessageHandler(Filters.text & Filters.user(user_id=ADMIN_ID), admin_followup_authorization))
    dp.add_handler(MessageHandler(Filters.text & Filters.user(user_id=ADMIN_ID), admin_followup_handler))

    # Flask webhook endpoint
    @app.route(f"/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        update = Update.de_json(request.get_json(force=True), updater.bot)
        dp.process_update(update)
        return "ok", 200

    # set webhook
    try:
        updater.bot.delete_webhook()
        updater.bot.set_webhook(f"{RENDER_URL}/{BOT_TOKEN}")
        logger.info(f"✅ Webhook set to {RENDER_URL}/{BOT_TOKEN}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")

    # run flask
    app.run(host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
