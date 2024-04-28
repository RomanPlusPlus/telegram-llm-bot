import os
from ai_wrapper import ask_gpt_single_message
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)


# Retrieve token from environment variable
TOKEN = os.getenv("TELEGRAM_LLM_BOT_TOKEN")
if not TOKEN:
    raise ValueError(
        "No token provided. Set the TELEGRAM_BOT_TOKEN environment variable."
    )


allowed_ids_str = os.getenv("ALLOWED_USER_IDS")
# Convert the string of comma-separated integers to a list of integers
ALLOWED_USER_IDS = [int(user_id.strip()) for user_id in allowed_ids_str.split(",")]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("In the start function...")

    user = update.effective_user

    if True:
        keyboard = [
            [InlineKeyboardButton("Start", callback_data="start_game")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        welcome_message = f"Hello {user.first_name}, ich bin dein hilfreicher Assistent! Clicke 'Start'"
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=welcome_message,
            reply_markup=reply_markup,
        )


async def start_new_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = "Wie kann ich dir helfen?"
    if update.message:
        await update.message.reply_text(text)
    else:
        await update.callback_query.edit_message_text(text)


async def start_game_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    await start_new_game(update, context)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text

    user_id = update.effective_user.id

    if user_id in ALLOWED_USER_IDS:
        # await update.message.reply_text(f"Du hast gesendet: {text}")
        sys_msg = "Du bist ein hilfreicher Assistent."
        answer = ask_gpt_single_message(text, sys_msg, max_length=500)
        await update.message.reply_text(answer)
    else:
        text = f"Eh? Du hast doch keine Berechtigung. Deine user_id ist {user_id}."
        await update.message.reply_text(text)


async def restrict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Keine Berechtigung für user_id {user_id}.",
    )


def main():
    app = Application.builder().token(TOKEN).build()

    """Restrict fhs bot to the specified user_id.
    NOTE: this should be always the first handler, to prevent the bot from responding to unauthorized users.
    """
    restrict_handler = MessageHandler(~filters.User(ALLOWED_USER_IDS), restrict)
    app.add_handler(restrict_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(start_game_callback, pattern="^start_game$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
