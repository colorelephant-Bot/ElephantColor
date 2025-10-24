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

# (all internal logic unchanged)
# ...
# keep everything as in your code above
# ...

def build_dispatcher_and_start():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN not set. Exiting"); return None, None
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # ✅ Removed /start and /estimate
    # dp.add_handler(CommandHandler("start", cmd_start))
    # dp.add_handler(CommandHandler("estimate", cmd_estimate))

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