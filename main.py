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
