import os, json, time, traceback
from datetime import datetime
from math import floor
import pytz
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, jsonify, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler, CallbackContext

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CREATOR_ID = int(os.environ.get("CREATOR_ID")) if os.environ.get("CREATOR_ID") else None
RENDER_URL = os.environ.get("RENDER_URL")
TIMEZONE = pytz.timezone("Asia/Kolkata")

LOGS_DIR = "logs"
SYSTEM_STATE_FILE = "system_state.json"
RULES_FILE = "rules.txt"
AUTHORIZED_USERS_FILE = "authorized_users.json"
SENT_MESSAGES_FILE = "sent_messages.json"

CASE1 = [10, 10, 15, 30, 50]
CASE2 = [10, 25, 65]
TAX_RATE = 0.10

os.makedirs(LOGS_DIR, exist_ok=True)
if not os.path.exists(RULES_FILE):
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        f.write("Platform rules not defined yet.\n")
if not os.path.exists(SYSTEM_STATE_FILE):
    with open(SYSTEM_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"maintenance": False, "last_reboot": None, "uptime_start": datetime.now().isoformat()}, f)
if not os.path.exists(AUTHORIZED_USERS_FILE):
    with open(AUTHORIZED_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)
if not os.path.exists(SENT_MESSAGES_FILE):
    with open(SENT_MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

def _cleanup_old_logs():
    try:
        now = datetime.now()
        for fname in os.listdir(LOGS_DIR):
            if fname.startswith("bot_") and fname.endswith(".log"):
                path = os.path.join(LOGS_DIR, fname)
                try:
                    date_part = fname[4:-4]
                    file_date = datetime.strptime(date_part, "%Y-%m-%d")
                    if (now - file_date).total_seconds() > 86400:
                        os.remove(path)
                except Exception:
                    mtime = datetime.fromtimestamp(os.path.getmtime(path))
                    if (now - mtime).total_seconds() > 86400:
                        os.remove(path)
    except Exception:
        pass

_cleanup_old_logs()
TODAY = datetime.now().strftime("%Y-%m-%d")
LOG_PATH = os.path.join(LOGS_DIR, f"bot_{TODAY}.log")
logger = logging.getLogger("ColorElephantBot")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh); logger.addHandler(ch)

def log_event(category: str, user=None, details: str = ""):
    uname = "NoUsername"; uid = "N/A"
    if user:
        try:
            uname = getattr(user, "username", None) or getattr(user, "first_name", "") or "NoUsername"
            uid = getattr(user, "id", "N/A")
        except Exception:
            pass
    msg = f"[{category}] {details} | User: @{uname} ({uid})"
    logger.info(msg)

app = Flask(__name__)
@app.route("/")
def root():
    log_event("SYSTEM", None, "Root endpoint hit")
    return "Color Elephant Bot is running."
@app.route("/ping")
def ping():
    log_event("SYSTEM", None, "/ping received")
    return jsonify(status="ok", message="Ping received. Bot alive."), 200

def load_system_state():
    try:
        with open(SYSTEM_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        s = {"maintenance": False, "last_reboot": None, "uptime_start": datetime.now().isoformat()}
        with open(SYSTEM_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f)
        return s

def save_system_state(state: dict):
    try:
        with open(SYSTEM_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        log_event("SYSTEM", None, "Failed to save system state")

def nearest_ten(value):
    try:
        return int(floor(float(value) / 10) * 10)
    except Exception:
        return 0

def percent_of(balance, pct):
    return nearest_ten(balance * pct / 100)

def load_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            txt = f.read().strip()
            return txt if txt else "No rules defined."
    return "Rules not found."

def load_users():
    try:
        with open(AUTHORIZED_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        with open(AUTHORIZED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}

def save_users(data):
    try:
        with open(AUTHORIZED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log_event("SYSTEM", None, f"save_users error: {e}")

def update_user_record(user):
    if not user: return
    data = load_users()
    uid = str(user.id)
    now = datetime.now().isoformat()
    entry = data.get(uid, {})
    entry["username"] = user.username or entry.get("username","")
    entry["first_name"] = user.first_name or entry.get("first_name","")
    entry["banned"] = entry.get("banned", False)
    entry["last_active"] = now
    data[uid] = entry
    save_users(data)
    log_event("USERS", user, "User recorded")

def is_user_banned(user_id):
    data = load_users()
    return str(user_id) in data and data[str(user_id)].get("banned", False)

def load_sent_messages():
    try:
        with open(SENT_MESSAGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        with open(SENT_MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
        return {}

def save_sent_messages(data):
    try:
        with open(SENT_MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log_event("SYSTEM", None, f"save_sent_messages error: {e}")

def record_sent_message(chat_id, msg_id):
    data = load_sent_messages()
    sid = str(chat_id)
    data.setdefault(sid, [])
    if msg_id not in data[sid]:
        data[sid].append(msg_id)
    save_sent_messages(data)

def clear_sent_messages_for_chat(chat_id):
    data = load_sent_messages()
    sid = str(chat_id)
    if sid in data:
        data[sid] = []
        save_sent_messages(data)

def is_creator(user):
    try:
        return CREATOR_ID and user and int(user.id) == int(CREATOR_ID)
    except Exception:
        return False

def in_maintenance():
    state = load_system_state()
    return bool(state.get("maintenance", False))

def notify_creator(bot, text):
    try:
        if CREATOR_ID:
            bot.send_message(chat_id=int(CREATOR_ID), text=text)
            log_event("SYSTEM", None, f"Creator notified: {text}")
    except Exception:
        log_event("SYSTEM", None, f"Notify creator failed: {text}")

def keypad_markup():
    kb = [
        [InlineKeyboardButton("1", callback_data="num_1"), InlineKeyboardButton("2", callback_data="num_2"), InlineKeyboardButton("3", callback_data="num_3"), InlineKeyboardButton("x10", callback_data="mul_10")],
        [InlineKeyboardButton("4", callback_data="num_4"), InlineKeyboardButton("5", callback_data="num_5"), InlineKeyboardButton("6", callback_data="num_6"), InlineKeyboardButton("x100", callback_data="mul_100")],
        [InlineKeyboardButton("7", callback_data="num_7"), InlineKeyboardButton("8", callback_data="num_8"), InlineKeyboardButton("9", callback_data="num_9"), InlineKeyboardButton("x1K", callback_data="mul_1000")],
        [InlineKeyboardButton("0", callback_data="num_0"), InlineKeyboardButton("Clear", callback_data="clr"), InlineKeyboardButton("Enter", callback_data="enter"), InlineKeyboardButton("x10K", callback_data="mul_10000")],
    ]
    return InlineKeyboardMarkup(kb)

def simulate_session_profit_for_path(base_balance: int, outcomes):
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
            gross_profit = invest
            tax = gross_profit * TAX_RATE
            net = gross_profit - tax
            profit += net
            if round_no > 1:
                break
        else:
            profit -= invest
    return int(nearest_ten(profit))

def generate_possible_sequences():
    seqs = []
    def rec(seq):
        if seq and seq[-1] == "W" and len(seq) > 1:
            seqs.append(seq.copy()); return
        if not seq:
            rec(["W"]); rec(["L"]); return
        path = "case1" if seq[0] == "W" else "case2"
        max_len = len(CASE1) if path == "case1" else len(CASE2)
        if len(seq) >= max_len:
            seqs.append(seq.copy()); return
        rec(seq+["W"]); rec(seq+["L"])
    rec([])
    unique=[]; seen=set()
    for s in seqs:
        k="".join(s)
        if k not in seen:
            seen.add(k); unique.append(s)
    return unique

def compute_all_session_profits(base_balance):
    seqs = generate_possible_sequences()
    out=[]
    for s in seqs:
        p=simulate_session_profit_for_path(base_balance, s)
        out.append((s,p))
    return out

def worst_session_profit(base_balance:int)->int:
    pairs = compute_all_session_profits(base_balance)
    if not pairs: return 0
    profits=[int(p) for (_,p) in pairs]
    return nearest_ten(min(profits)) if profits else 0

def estimate_compound_worst(base_balance:int, days:int, sessions_per_day:int=3):
    b = nearest_ten(base_balance)
    history=[]
    for d in range(1, days+1):
        day_record={"day":d,"start_balance":b,"session_profits":[],"end_balance":None}
        for s in range(sessions_per_day):
            profit = worst_session_profit(b)
            profit = nearest_ten(profit)
            day_record["session_profits"].append(int(profit))
            b = nearest_ten(b + profit)
        day_record["end_balance"]=b
        history.append(day_record)
    return b, history

def send_and_record(context: CallbackContext, chat_id: int, text: str, reply_markup=None, parse_mode=None):
    try:
        if parse_mode:
            msg = context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        else:
            msg = context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        record_sent_message(chat_id, msg.message_id)
        return msg
    except Exception:
        try:
            msg = context.bot.send_message(chat_id=chat_id, text=text)
            record_sent_message(chat_id, msg.message_id)
            return msg
        except Exception as e:
            log_event("SYSTEM", None, f"send_and_record failed: {e}")
            return None

def start_game_with_balance(update_or_query, context: CallbackContext, balance: float):
    try:
        if isinstance(update_or_query, Update):
            chat_id = update_or_query.effective_chat.id
            user = update_or_query.effective_user
        else:
            chat_id = update_or_query.message.chat_id
            user = update_or_query.from_user
        context.user_data["BaseBalance"]=balance
        context.user_data["Round"]=1
        context.user_data["Path"]=None
        context.user_data["Wins"]=0; context.user_data["Losses"]=0
        context.user_data["TotalPlaced"]=0; context.user_data["Profit"]=0; context.user_data["seq"]=[]
        invest = percent_of(balance, CASE1[0])
        context.user_data["TotalPlaced"] += invest
        send_and_record(context, chat_id, f"Round 1: Place ₹{invest} (10% of ₹{balance}).")
        buttons=[[InlineKeyboardButton("Win", callback_data="r1_win"), InlineKeyboardButton("Lose", callback_data="r1_lose")]]
        send_and_record(context, chat_id, "Round 1 result?", reply_markup=InlineKeyboardMarkup(buttons))
        log_event("GAME", user, f"Started game with balance {balance}")
    except Exception as e:
        log_event("SYSTEM", None, f"start_game error: {e}"); traceback.print_exc()

def handle_result(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    user = query.from_user
    if is_user_banned(user.id) and not is_creator(user):
        try: query.message.reply_text("⚠️ Access denied. You are banned from using this bot.")
        except: pass
        log_event("BLOCKED", user, "Attempted callback while banned"); return
    log_event("GAME", user, f"Result callback {query.data}")
    data = query.data
    base_balance = context.user_data.get("BaseBalance",0)
    round_no = context.user_data.get("Round",1)
    path = context.user_data.get("Path")
    total_placed = context.user_data.get("TotalPlaced",0)
    profit = context.user_data.get("Profit",0)
    wins = context.user_data.get("Wins",0)
    losses = context.user_data.get("Losses",0)
    seq = context.user_data.get("seq",[])
    is_win = data.endswith("_win"); label = "W" if is_win else "L"
    if round_no == 1:
        path = "case1" if is_win else "case2"; context.user_data["Path"]=path
    percentages = CASE1 if path=="case1" else CASE2
    max_rounds = len(percentages)
    invest = percent_of(base_balance, percentages[round_no-1])
    context.user_data["TotalPlaced"] = total_placed + invest
    if is_win:
        wins += 1
        gross_profit = invest; tax = gross_profit * TAX_RATE; net = gross_profit - tax
        profit += net; context.user_data["Profit"] = nearest_ten(profit); context.user_data["Wins"]=wins
    else:
        losses += 1; profit -= invest; context.user_data["Profit"]=nearest_ten(profit); context.user_data["Losses"]=losses
    seq.append(label); context.user_data["seq"]=seq
    all_profits = compute_all_session_profits(base_balance)
    if all_profits:
        sorted_by = sorted(all_profits, key=lambda x: x[1])
        worst_seq = "".join(sorted_by[0][0]); best_seq = "".join(sorted_by[-1][0])
    else:
        worst_seq = ""; best_seq = ""
    current_seq_str = "".join(seq)
    if current_seq_str == worst_seq:
        remark = f"{current_seq_str} -> Worst possible scenario"
    elif current_seq_str == best_seq:
        remark = f"{current_seq_str} -> Best possible scenario"
    else:
        remark = f"{current_seq_str} -> Moderate performance"
    ended = False
    if is_win and round_no > 1: ended = True
    if round_no >= max_rounds: ended = True
    if ended:
        total_rounds_played = round_no
        total_placed = context.user_data.get("TotalPlaced",0)
        total_profit = context.user_data.get("Profit",0)
        profit_after_tax = nearest_ten(total_profit)
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
        send_and_record(context, query.message.chat_id, summary)
        log_event("SUMMARY", user, f"Rounds:{total_rounds_played} Profit:{profit_after_tax} Balance:{updated_balance}")
        context.user_data.clear(); return
    next_round = round_no + 1; context.user_data["Round"] = next_round
    next_pct = percentages[next_round - 1]; next_invest = percent_of(base_balance, next_pct)
    context.user_data["TotalPlaced"] += next_invest
    send_and_record(context, query.message.chat_id, f"Round {next_round}: Place ₹{next_invest} ({next_pct}% of ₹{base_balance}).")
    buttons = [[InlineKeyboardButton("Win", callback_data=f"r{next_round}_win"), InlineKeyboardButton("Lose", callback_data=f"r{next_round}_lose")]]
    send_and_record(context, query.message.chat_id, f"Round {next_round} result?", reply_markup=InlineKeyboardMarkup(buttons))

def handle_keypad(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    user = query.from_user
    if is_user_banned(user.id) and not is_creator(user):
        try: query.message.reply_text("⚠️ Access denied. You are banned from using this bot.")
        except: pass
        log_event("BLOCKED", user, "Attempted keypad while banned"); return
    data = query.data; buffer = context.user_data.get("buffer","0")
    if data.startswith("num_"):
        d = data.split("_",1)[1]; buffer = d if buffer=="0" else buffer + d
    elif data.startswith("mul_"):
        try:
            mult = int(data.split("_",1)[1]); val = int(buffer) if buffer.isdigit() else 0; buffer = str(val * mult)
        except Exception:
            buffer = "0"
    elif data == "clr":
        buffer = "0"
    elif data == "enter":
        try:
            val = int(buffer) if buffer.isdigit() else float(buffer)
            val = float(val)
        except Exception:
            try: query.message.edit_text("⚠️ Please enter a valid numeric value.", reply_markup=query.message.reply_markup)
            except: pass
            context.user_data["buffer"]=buffer; return
        balance = nearest_ten(val); expect = context.user_data.get("expect_balance_for")
        try: query.message.edit_text(f"Balance confirmed: ₹{balance}")
        except: pass
        context.user_data["buffer"]="0"; context.user_data["expect_balance_for"]=None
        if expect == "start":
            start_game_with_balance(query, context, balance); return
        if expect == "estimate":
            ask_estimate_days_from_query(query, context, balance); return
        try: query.message.reply_text("No active request. Use /start or /estimate.")
        except: pass
        return
    context.user_data["buffer"]=buffer
    try:
        query.message.edit_text(f"💰 Current Input: `{buffer}`", reply_markup=query.message.reply_markup, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass

def cmd_start(update: Update, context: CallbackContext):
    user = update.effective_user
    update_user_record(user)
    if is_user_banned(user.id) and not is_creator(user):
        update.message.reply_text("⚠️ Access denied. You are banned from using this bot."); log_event("BLOCKED", user, "start"); return
    if in_maintenance() and not is_creator(user):
        update.message.reply_text("🚧 Down for maintenance. Please try again later."); return
    log_event("COMMAND", user, "/start")
    context.user_data["buffer"]="0"; context.user_data["expect_balance_for"]="start"
    msg = update.message.reply_text("💰 Please enter your current balance (press Enter when done).", reply_markup=keypad_markup())
    try: record_sent_message(update.effective_chat.id, msg.message_id)
    except: pass

def cmd_estimate(update: Update, context: CallbackContext):
    user = update.effective_user
    update_user_record(user)
    if is_user_banned(user.id) and not is_creator(user):
        update.message.reply_text("⚠️ Access denied. You are banned from using this bot."); log_event("BLOCKED", user, "estimate"); return
    if in_maintenance() and not is_creator(user):
        update.message.reply_text("🚧 Down for maintenance. Please try again later."); return
    log_event("COMMAND", user, "/estimate")
    context.user_data["buffer"]="0"; context.user_data["expect_balance_for"]="estimate"
    msg = update.message.reply_text("💰 Please enter your current balance for estimation (press Enter when done).", reply_markup=keypad_markup())
    try: record_sent_message(update.effective_chat.id, msg.message_id)
    except: pass

def ask_estimate_days_from_query(query, context, base_balance: float):
    buttons = [
        [InlineKeyboardButton("10 Days", callback_data="est_10"), InlineKeyboardButton("20 Days", callback_data="est_20")],
        [InlineKeyboardButton("30 Days", callback_data="est_30"), InlineKeyboardButton("60 Days", callback_data="est_60")],
        [InlineKeyboardButton("90 Days", callback_data="est_90")],
    ]
    try:
        msg = query.message.reply_text("📆 Select the number of days for estimation:", reply_markup=InlineKeyboardMarkup(buttons))
        record_sent_message(query.message.chat_id, msg.message_id)
    except:
        pass
    context.user_data["estimate_balance"]=base_balance

def handle_estimate_days(update: Update, context: CallbackContext):
    query = update.callback_query; query.answer()
    user = query.from_user
    if is_user_banned(user.id) and not is_creator(user):
        try: query.message.reply_text("⚠️ Access denied. You are banned from using this bot.")
        except: pass
        log_event("BLOCKED", user, "estimate_days"); return
    if in_maintenance() and not is_creator(user):
        query.message.reply_text("🚧 Down for maintenance. Please try again later."); return
    data = query.data
    if not data.startswith("est_"): return
    days = int(data.split("_",1)[1]); base = context.user_data.get("estimate_balance")
    if base is None:
        query.message.reply_text("No balance found for estimation. Use /estimate to start again."); return
    log_event("GAME", user, f"Estimate for {days} days, base ₹{base}")
    final_balance, hist = estimate_compound_worst(base, days, sessions_per_day=3)
    d1 = hist[0] if hist else {}
    msg = f"Estimate for {days} days (worst-case sessions, 3/day)\nStart Balance: ₹{base}\nEnd Balance: ₹{final_balance}\n"
    if d1:
        msg += f"Day 1: start ₹{d1['start_balance']} -> sessions {d1['session_profits']} -> end ₹{d1['end_balance']}"
    m = query.message.reply_text(msg); record_sent_message(query.message.chat_id, m.message_id)

def cmd_rules(update: Update, context: CallbackContext):
    user = update.effective_user; update_user_record(user)
    if is_user_banned(user.id) and not is_creator(user):
        update.message.reply_text("⚠️ Access denied. You are banned from using this bot."); log_event("BLOCKED", user, "rules"); return
    if in_maintenance() and not is_creator(user):
        update.message.reply_text("🚧 Down for maintenance. Please try again later."); return
    log_event("COMMAND", user, "/rules")
    m = update.message.reply_text(f"📜 Platform Rules:\n\n{load_rules()}", parse_mode=ParseMode.MARKDOWN)
    record_sent_message(update.effective_chat.id, m.message_id)

def cmd_commands(update: Update, context: CallbackContext):
    user = update.effective_user; update_user_record(user)
    if is_user_banned(user.id) and not is_creator(user):
        update.message.reply_text("⚠️ Access denied. You are banned from using this bot"); log_event("BLOCKED", user, "commands"); return
    if in_maintenance() and not is_creator(user):
        update.message.reply_text("🚧 Down for maintenance. Please try again later."); return
    log_event("COMMAND", user, "/commands")
    msg = ("📜 Available Commands:\n\n/start — Start a new session\n/estimate — Estimate future profits\n/rules — Show platform rules\n/commands — This command list\n/reset — Clear your session/chat")
    m = update.message.reply_text(msg); record_sent_message(update.effective_chat.id, m.message_id)

def cmd_reset(update: Update, context: CallbackContext):
    user = update.effective_user; update_user_record(user)
    if is_user_banned(user.id) and not is_creator(user):
        update.message.reply_text("⚠️ Access denied. You are banned from using this bot"); log_event("BLOCKED", user, "reset"); return
    if in_maintenance() and not is_creator(user):
        update.message.reply_text("🚧 Down for maintenance. Please try again later"); return
    log_event("COMMAND", user, "/reset")
    chat_id = update.effective_chat.id
    data = load_sent_messages()
    sent_ids = data.get(str(chat_id), [])
    deleted = 0
    for mid in list(sent_ids):
        try:
            context.bot.delete_message(chat_id=chat_id, message_id=mid); deleted += 1
        except Exception:
            pass
    data[str(chat_id)] = []
    save_sent_messages(data)
    context.user_data.clear()
    m = update.message.reply_text(f"♻️ Session cleared. {deleted} messages deleted.")
    try: record_sent_message(chat_id, m.message_id)
    except: pass
    log_event("SYSTEM", user, f"Reset performed. Deleted {deleted} messages.")

def cmd_roka(update: Update, context: CallbackContext):
    user = update.effective_user; update_user_record(user)
    log_event("COMMAND", user, "/roka")
    if is_creator(user):
        msg = ("🧠 Creator Access Granted\n\nCommands:\n• /down — Put bot Down for maintenance\n• /restart — Restart bot (keep data)\n• /reboot — Full reboot (clear all data)\n• /status — Show system status\n• /logs — Show latest 30 log entries\n• /userlist — Show last 10 users\n• /ban <id> — Ban user\n• /unban <id> — Unban user\n• /banned — Show banned users")
        m = update.message.reply_text(msg); record_sent_message(update.effective_chat.id, m.message_id); log_event("CREATOR", user, "/roka success")
    else:
        update.message.reply_text("❌ Unauthorized command"); log_event("CREATOR", user, "/roka failed")

def cmd_down(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_creator(user):
        update.message.reply_text("❌ Unauthorized"); log_event("CREATOR", user, "/down unauthorized"); return
    state = load_system_state(); state["maintenance"]=True; save_system_state(state)
    m = update.message.reply_text("🚧 Bot is now Down for maintenance"); record_sent_message(update.effective_chat.id, m.message_id)
    log_event("CREATOR", user, "Set bot Down"); notify_creator(context.bot, "🚧 Bot set Down for maintenance by Creator.")

def cmd_restart(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_creator(user):
        update.message.reply_text("❌ Unauthorized"); log_event("CREATOR", user, "/restart unauthorized"); return
    state = load_system_state(); state["maintenance"]=False; state["last_reboot"]=datetime.now().isoformat(); save_system_state(state)
    m = update.message.reply_text("🔄 Restarting bot... Please wait.\nColorElephant Bot will be live again shortly. ✨"); record_sent_message(update.effective_chat.id, m.message_id)
    log_event("CREATOR", user, "Restart invoked"); notify_creator(context.bot, "🔄 Bot restart requested by Creator.")

def cmd_reboot(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_creator(user):
        update.message.reply_text("❌ Unauthorized"); log_event("CREATOR", user, "/reboot unauthorized"); return
    m = update.message.reply_text("⚙️ System rebooting... All session data will be cleared."); record_sent_message(update.effective_chat.id, m.message_id)
    log_event("CREATOR", user, "Reboot invoked"); notify_creator(context.bot, "⚙️ System reboot requested by Creator.")
    try:
        dp = context.dispatcher
        if hasattr(dp, "user_data"): dp.user_data.clear()
        if hasattr(dp, "chat_data"): dp.chat_data.clear()
        users_file = os.path.join(LOGS_DIR, "users.txt")
        try:
            if os.path.exists(users_file): os.remove(users_file)
        except: pass
        state = {"maintenance": False, "last_reboot": datetime.now().isoformat(), "uptime_start": datetime.now().isoformat()}
        save_system_state(state)
        save_sent_messages({})
        save_users({})
    except Exception as e:
        log_event("SYSTEM", None, f"Reboot error: {e}")
    notify_creator(context.bot, "✅ Reboot complete. Bot is live"); log_event("CREATOR", user, "Reboot complete")

def cmd_status(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_creator(user):
        update.message.reply_text("❌ Unauthorized"); return
    state = load_system_state(); maintenance = state.get("maintenance", False)
    last_reboot = state.get("last_reboot"); uptime_start = state.get("uptime_start")
    users_file = os.path.join(LOGS_DIR, "users.txt"); users_count=0
    try:
        if os.path.exists(users_file):
            with open(users_file,"r",encoding="utf-8") as f: users_count = len([l for l in f.read().splitlines() if l.strip()])
    except: users_count=0
    msg = f"System Status:\n• Maintenance: {'ON' if maintenance else 'OFF'}\n• Last Reboot: {last_reboot}\n• Uptime Start: {uptime_start}\n• Known Users: {users_count}"
    m = update.message.reply_text(msg); record_sent_message(update.effective_chat.id, m.message_id)

def cmd_logs(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_creator(user):
        update.message.reply_text("❌ Unauthorized"); log_event("CREATOR", user, "/logs unauthorized"); return
    try:
        files = sorted([os.path.join(LOGS_DIR, f) for f in os.listdir(LOGS_DIR) if f.endswith(".log")])
        if not files:
            update.message.reply_text("No logs available"); return
        lines=[]
        for path in reversed(files):
            with open(path,"r",encoding="utf-8") as f:
                lines.extend(f.read().splitlines())
            if len(lines)>=30: break
        last30 = "\n".join(lines[-30:]) if lines else ""
        if not last30: update.message.reply_text("No logs found"); return
        if len(last30)>3900: last30 = last30[-3900:]
        m = update.message.reply_text("Last logs:\n```\n"+last30+"\n```", parse_mode=ParseMode.MARKDOWN); record_sent_message(update.effective_chat.id, m.message_id)
    except Exception as e:
        update.message.reply_text(f"Error reading logs: {e}"); log_event("SYSTEM", None, f"/logs error: {e}")

def cmd_userlist(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_creator(user):
        update.message.reply_text("❌ Unauthorized"); return
    data = load_users()
    items = list(data.items())[-10:]
    msg = "👥 Last 10 Users:\n"
    for uid, info in reversed(items):
        status = "❌ Banned" if info.get("banned") else "✅ Active"
        uname = ("@" + info.get("username")) if info.get("username") else info.get("first_name","")
        msg += f"\n• {uname} — {status}\n  ID: {uid}\n"
    m = update.message.reply_text(msg); record_sent_message(update.effective_chat.id, m.message_id)

def cmd_banned(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_creator(user):
        update.message.reply_text("❌ Unauthorized"); return
    data = load_users()
    banned = [f"{v.get('first_name','')} (ID: {k})" for k,v in data.items() if v.get("banned")]
    if not banned:
        update.message.reply_text("✅ No users are currently banned")
    else:
        msg = "🚫 Banned Users:\n" + "\n".join(banned); m = update.message.reply_text(msg); record_sent_message(update.effective_chat.id, m.message_id)

def cmd_ban(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_creator(user):
        update.message.reply_text("❌ Unauthorized"); return
    if not context.args:
        update.message.reply_text("Usage: /ban <user_id>"); return
    uid = str(context.args[0])
    if uid == str(CREATOR_ID):
        update.message.reply_text("⚠️ Creator cannot be banned"); return
    data = load_users()
    if uid in data:
        data[uid]["banned"]=True; save_users(data)
        update.message.reply_text(f"🚫 User {uid} banned"); log_event("CREATOR", user, f"Banned {uid}")
    else:
        update.message.reply_text("User not found in records")

def cmd_unban(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_creator(user):
        update.message.reply_text("❌ Unauthorized"); return
    if not context.args:
        update.message.reply_text("Usage: /unban <user_id)"); return
    uid = str(context.args[0]); data = load_users()
    if uid in data:
        data[uid]["banned"]=False; save_users(data)
        update.message.reply_text(f"✅ User {uid} unbanned"); log_event("CREATOR", user, f"Unbanned {uid}")
    else:
        update.message.reply_text("User not found in records")

def unknown_handler(update: Update, context: CallbackContext):
    user = update.effective_user
    txt = update.message.text if update.message else ""
    if txt and txt.startswith("/"):
        update_user_record(user)
        if is_user_banned(user.id) and not is_creator(user):
            update.message.reply_text("⚠️ Access denied. You are banned from using this bot"); log_event("BLOCKED", user, "unknown command"); return
        if in_maintenance() and not is_creator(user):
            update.message.reply_text("🚧 Down for maintenance. Please try again later"); return
        update.message.reply_text("❌ Invalid command. Use /commands to see available options"); log_event("COMMAND", user, f"Invalid: {txt}")
    else:
        update.message.reply_text("❌ Invalid command. Use /commands to see available options")

def build_dispatcher_and_start():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set. Exiting"); return None, None
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CommandHandler("estimate", cmd_estimate))
    dp.add_handler(CommandHandler("rules", cmd_rules))
    dp.add_handler(CommandHandler("commands", cmd_commands))
    dp.add_handler(CommandHandler("reset", cmd_reset))
    dp.add_handler(CommandHandler("roka", cmd_roka))
    dp.add_handler(CommandHandler("down", cmd_down))
    dp.add_handler(CommandHandler("restart", cmd_restart))
    dp.add_handler(CommandHandler("reboot", cmd_reboot))
    dp.add_handler(CommandHandler("status", cmd_status))
    dp.add_handler(CommandHandler("logs", cmd_logs))
    dp.add_handler(CommandHandler("userlist", cmd_userlist))
    dp.add_handler(CommandHandler("banned", cmd_banned))
    dp.add_handler(CommandHandler("ban", cmd_ban, pass_args=True))
    dp.add_handler(CommandHandler("unban", cmd_unban, pass_args=True))
    dp.add_handler(CallbackQueryHandler(handle_keypad, pattern="^(num_|mul_|clr|enter)"))
    dp.add_handler(CallbackQueryHandler(handle_estimate_days, pattern="^est_"))
    dp.add_handler(CallbackQueryHandler(handle_result, pattern="^r"))
    dp.add_handler(MessageHandler(Filters.command, unknown_handler))
    @app.route(f"/{BOT_TOKEN}", methods=["POST"])
    def webhook():
        try:
            data = request.get_json(force=True)
            upd = Update.de_json(data, updater.bot)
            dp.process_update(upd)
        except Exception as e:
            log_event("SYSTEM", None, f"Webhook process error: {e}")
        return "ok", 200
    try:
        if RENDER_URL:
            wh = f"{RENDER_URL.rstrip('/')}/{BOT_TOKEN}"
            updater.bot.set_webhook(wh); log_event("SYSTEM", None, f"Webhook set to {wh}")
        else:
            log_event("SYSTEM", None, "RENDER_URL not set; webhook not configured")
    except Exception as e:
        log_event("SYSTEM", None, f"Failed to set webhook: {e}")
    return updater, dp

def main():
    updater, dp = build_dispatcher_and_start()
    if not updater:
        return
    state = load_system_state()
    if not state.get("uptime_start"):
        state["uptime_start"] = datetime.now().isoformat(); save_system_state(state)
    if state.get("maintenance"):
        notify_creator(updater.bot, "🚧 Bot started in Down (maintenance) mode")
    else:
        notify_creator(updater.bot, "✅ Bot started and is live")
    app.run(host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()