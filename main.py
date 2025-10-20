def handle_result(update: Update, context: CallbackContext):
    if reject_if_banned(update, context):
        return

    query = update.callback_query
    query.answer()
    data = query.data

    base_balance = context.user_data.get("BaseBalance", 0)
    round_num = context.user_data.get("Round", 1)
    path = context.user_data.get("Path")
    total_placed = context.user_data.get("TotalPlaced", 0)
    profit = context.user_data.get("Profit", 0)
    wins = context.user_data.get("Wins", 0)
    losses = context.user_data.get("Losses", 0)

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
        # Gross profit = (2x investment) - investment = investment
        gross_profit = investment
        tax = gross_profit * 0.10
        net_profit = gross_profit - tax
        profit += net_profit
        context.user_data["Profit"] = profit
    else:
        losses += 1
        context.user_data["Losses"] = losses
        profit -= investment
        context.user_data["Profit"] = profit

    # --- End on WIN (after Round 1) ---
    if data.endswith("_win") and round_num > 1:
        profit_after_tax = profit
        updated_balance = base_balance + profit_after_tax
        msg = (
            f"Congratulations! You won in Round {round_num}!\n\n"
            f"Session Summary:\n"
            f"Rounds Played: {round_num} ({wins} Won, {losses} Lost)\n"
            f"Amount Placed: ₹{context.user_data['TotalPlaced']}\n"
            f"Profit Made: ₹{round(profit, 2)}\n"
            f"Profit After Tax: ₹{round(profit_after_tax, 2)}\n"
            f"Balance After Session: ₹{round(updated_balance, 2)}\n\n"
            f"Use /start to begin a new prediction session."
        )
        query.message.reply_text(msg)
        context.user_data.clear()
        return

    # --- End if all rounds exhausted ---
    if round_num >= total_rounds:
        profit_after_tax = profit
        updated_balance = base_balance + profit_after_tax
        msg = (
            f"Prediction session completed.\n\n"
            f"Session Summary:\n"
            f"Rounds Played: {round_num} ({wins} Won, {losses} Lost)\n"
            f"Amount Placed: ₹{context.user_data['TotalPlaced']}\n"
            f"Profit Made: ₹{round(profit, 2)}\n"
            f"Profit After Tax: ₹{round(profit_after_tax, 2)}\n"
            f"Balance After Session: ₹{round(updated_balance, 2)}\n\n"
            f"Use /start to begin a new session."
        )
        query.message.reply_text(msg)
        context.user_data.clear()
        return

    # --- Proceed to next round ---
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
