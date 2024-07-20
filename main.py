import os
from ai_providers.rate_limited_ai_wrapper import ask_gpt_multi_message
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)

"""
Note:
Currently, it's limiting the number of messages from the user by keeping only the last MAX_MESSAGES_NUM messages.
It was selected as the most user-friendly optiion, even if it's costlier.
Some possible alternative strategies:
- maybe detect a change of topic and reset the chat
- add the reset chat button
- reset after a night
--- save the ts of the latest msg
--- if the latest msg by the user was yesterday, and more than 5h elapsed, then reset

############################################################

TODO:
-implement Claude 3.5 Sonet (smarter, larger context window)

photo as an input

add optional logging, by user

"""


# Retrieve token from environment variable
TOKEN = os.getenv("TELEGRAM_LLM_BOT_TOKEN")
if not TOKEN:
    raise ValueError(
        "No token provided. Set the TELEGRAM_BOT_TOKEN environment variable."
    )


allowed_ids_str = os.getenv("ALLOWED_USER_IDS")

# Convert the string of comma-separated integers to a list of integers
ALLOWED_USER_IDS = [int(user_id.strip()) for user_id in allowed_ids_str.split(",")]

SYSTEM_MSG = """
Du bist ein hilfreicher Assistent.
Dies ist ein Instant-Messaging-Chat, also halten Sie Ihre Antworten kurz und präzise. Geben Sie aber eine ausführliche Antwort, wenn Sie dem Nutzer damit am besten helfen können. 
Zum Beispiel, wenn der Benutzer eine einfache Frage gestellt hat, ist eine kurze Antwort vorzuziehen. Wenn der Benutzer jedoch eine komplizierte E-Mail schreiben möchte, schreiben Sie sie vollständig. 
Oft ist es hilfreich, dem Benutzer Fragen zu stellen, um ihm einen maßgeschneiderten Rat zu geben oder das Thema zu vertiefen. 
Aber der Benutzer tippt nicht gerne, also versuchen Sie, unnötige Fragen zu vermeiden. Und es ist besser, eine Frage zu stellen, NACHDEM Sie dem Nutzer bereits geholfen haben, als eine Option zum Weitermachen. 
Verwenden Sie die Sprache des Benutzers, es sei denn, eine Aufgabe erfordert etwas anderes.
"""

MAX_MESSAGES_NUM = 50

MESSAGES_BY_USER = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("In the start function...")

    user = update.effective_user

    if True:
        keyboard = [[InlineKeyboardButton("Start", callback_data="start_game")]]
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
    user_id = update.effective_user.id

    if user_id in ALLOWED_USER_IDS:
        user_input = update.message.text

        if user_id in MESSAGES_BY_USER:
            MESSAGES_BY_USER[user_id].append(
                {"role": "user", "content": user_input},
            )

        else:  # the user posted his first message
            MESSAGES_BY_USER[user_id] = [
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user", "content": user_input},
            ]

        # answer = ask_gpt_single_message(user_input, SYSTEM_MSG, max_length=500)
        answer = ask_gpt_multi_message(MESSAGES_BY_USER[user_id], max_length=500)

        MESSAGES_BY_USER[user_id].append(
            {"role": "assistant", "content": answer},
        )

        # remove the oldest messages. We keep only the last MAX_MESSAGES_NUM messages
        if len(MESSAGES_BY_USER[user_id]) > MAX_MESSAGES_NUM:
            MESSAGES_BY_USER[user_id] = MESSAGES_BY_USER[user_id][-MAX_MESSAGES_NUM:]
            # attach the system message to the beginning
            MESSAGES_BY_USER[user_id].insert(0, {"role": "system", "content": SYSTEM_MSG})
        print(f"Messages length: {len(MESSAGES_BY_USER[user_id])}")

        await update.message.reply_text(answer)
    else:
        answer = f"Eh? Du hast doch keine Berechtigung. Deine user_id ist {user_id}."
        print(answer)
        await update.message.reply_text(answer)


async def restrict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = f"Keine Berechtigung für user_id {user_id}."
    print(text)
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
