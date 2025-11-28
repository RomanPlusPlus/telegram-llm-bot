import os
from ai_providers.rate_limited_ai_wrapper import (
    PROVIDER_FROM_ENV,
    ask_gpt_multi_message,
)
from plugins import config_plugins
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from PIL import Image
import io
from utils.images import openai_requirements_image_resize, encode_image_to_data_url
from config import MAX_IMAGES_PER_MESSAGE
from utils.images import openai_requirements_image_resize, encode_image_to_data_url
from config import MAX_IMAGES_PER_MESSAGE
import importlib.util
import sys

# Dynamic Plugin Loading
PLUGINS = []
PLUGINS_DIR = os.path.join(os.path.dirname(__file__), "plugins")

def load_plugins():
    global PLUGINS
    PLUGINS = []
    if not os.path.exists(PLUGINS_DIR):
        print(f"Plugins directory not found: {PLUGINS_DIR}")
        return

    for plugin_name in os.listdir(PLUGINS_DIR):
        plugin_path = os.path.join(PLUGINS_DIR, plugin_name)
        if os.path.isdir(plugin_path):
            # Check if plugin is enabled in config
            if not config_plugins.is_plugin_enabled(plugin_name):
                print(f"Plugin {plugin_name} is disabled in config.")
                continue
                
            main_py = os.path.join(plugin_path, "main.py")
            if os.path.exists(main_py):
                try:
                    spec = importlib.util.spec_from_file_location(f"plugins.{plugin_name}", main_py)
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[f"plugins.{plugin_name}"] = module
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, "is_plugin_applicable") and hasattr(module, "process_messages"):
                        PLUGINS.append(module)
                        print(f"Loaded plugin: {plugin_name}")
                    else:
                        print(f"Plugin {plugin_name} missing required functions.")
                except Exception as e:
                    print(f"Error loading plugin {plugin_name}: {e}")

load_plugins()

"""
Note:
Currently, it's limiting the number of messages from the user by keeping only the last MAX_MESSAGES_NUM messages.
It was selected as the most user-friendly option, even if it's costlier.
Some possible alternative strategies:
- maybe detect a change of topic and reset the chat
- add the reset chat button
- reset after a night
--- save the ts of the latest msg
--- if the latest msg by the user was yesterday, and more than 5h elapsed, then reset

"""


PROVIDER_INDICATORS = {  # the indicators are case-insensitive
    "openai": ["o:", "о:"],  # Russian and Latin
    "anthropic": ["a:", "а:", "c:", "с:"],  # Russian and Latin
}  # if the user message starts with any of the indicators, use the provider

SELECTED_PROVIDER = None

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
Sie sind ein hilfreicher Assistent.
Dies ist ein Instant-Messaging-Chat, also halten Sie Ihre Antworten kurz und präzise. Geben Sie aber eine ausführliche Antwort, wenn Sie dem Nutzer damit am besten helfen können. 
Zum Beispiel, wenn der Benutzer eine einfache Frage gestellt hat, ist eine kurze Antwort vorzuziehen. Wenn der Benutzer jedoch eine komplizierte E-Mail schreiben möchte, schreiben Sie sie vollständig. 
Oft ist es hilfreich, dem Benutzer Fragen zu stellen, um ihm einen maßgeschneiderten Rat zu geben oder das Thema zu vertiefen. 
Aber der Benutzer tippt nicht gerne, also versuchen Sie, unnötige Fragen zu vermeiden. Und es ist besser, eine Frage zu stellen, NACHDEM Sie dem Nutzer bereits geholfen haben, als eine Option zum Weitermachen. 
Verwenden Sie die Sprache des Benutzers, es sei denn, eine Aufgabe erfordert etwas anderes.
"""

MAX_MESSAGES_NUM = 100
MAX_IMAGE_SIZE_MB = 30

MESSAGES_BY_USER = {}

def is_file_too_large(file_size_bytes: int | None, max_size_mb: int) -> bool:
    try:
        return isinstance(file_size_bytes, int) and file_size_bytes > max_size_mb * 1024 * 1024
    except Exception:
        return False


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


async def plugins_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the status of all plugins."""
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text(f"No permission. Your user_id is {user_id}.")
        return
    
    status = config_plugins.get_plugin_status()
    message = "**Plugin Status:**\n\n"
    for plugin_name, enabled in status.items():
        status_emoji = "✅" if enabled else "❌"
        message += f"{status_emoji} `{plugin_name}`: {'Enabled' if enabled else 'Disabled'}\n"
    
    await update.message.reply_text(message, parse_mode="Markdown")


async def enable_plugin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enable a specific plugin."""
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text(f"No permission. Your user_id is {user_id}.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /enable_plugin <plugin_name>")
        return
    
    plugin_name = context.args[0]
    if config_plugins.enable_plugin(plugin_name):
        load_plugins()  # Reload plugins
        await update.message.reply_text(f"✅ Plugin `{plugin_name}` enabled.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Plugin `{plugin_name}` not found.", parse_mode="Markdown")


async def disable_plugin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Disable a specific plugin."""
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text(f"No permission. Your user_id is {user_id}.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /disable_plugin <plugin_name>")
        return
    
    plugin_name = context.args[0]
    if config_plugins.disable_plugin(plugin_name):
        load_plugins()  # Reload plugins
        await update.message.reply_text(f"❌ Plugin `{plugin_name}` disabled.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ Plugin `{plugin_name}` not found.", parse_mode="Markdown")


async def enable_all_plugins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Enable all plugins."""
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text(f"No permission. Your user_id is {user_id}.")
        return
    
    config_plugins.enable_all_plugins()
    load_plugins()  # Reload plugins
    await update.message.reply_text("✅ All plugins enabled.")


async def disable_all_plugins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Disable all plugins."""
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text(f"No permission. Your user_id is {user_id}.")
        return
    
    config_plugins.disable_all_plugins()
    load_plugins()  # Reload plugins
    await update.message.reply_text("❌ All plugins disabled.")


def update_provider_from_user_input(user_input):
    switch7 = False
    report = ""
    for provider, indicators in PROVIDER_INDICATORS.items():
        for indicator in indicators:
            if user_input.lower().startswith(indicator):
                global SELECTED_PROVIDER
                if provider != SELECTED_PROVIDER:
                    switch7 = True
                    if SELECTED_PROVIDER is None:
                        SELECTED_PROVIDER = PROVIDER_FROM_ENV
                    report = f"{SELECTED_PROVIDER} -> {provider}"
                    print(report)
                SELECTED_PROVIDER = provider
                return switch7, report
    return switch7, report


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("In the handle_message function...")
    user_id = update.effective_user.id

    if user_id in ALLOWED_USER_IDS:
        user_input = update.message.text
        user_input = user_input.strip()
        print(f"User input: {user_input}")

        # get the provider from the user input
        switch7, report = update_provider_from_user_input(user_input)
        if switch7:
            await update.message.reply_text(report)

        # remove the provider indicator from the start of the message, but only from the start
        for provider, indicators in PROVIDER_INDICATORS.items():
            for indicator in indicators:
                if user_input.lower().startswith(indicator):
                    user_input = user_input[len(indicator) :].strip()

        # Plugin processing
        # Create a temporary message list to pass to plugins
        # We need to construct it as if it was in the history, but it's just the current message for now
        # Actually, plugins might need history? The spec says `is_plugin_applicable(messages)`.
        # So we should pass the current history + the new message?
        # But we haven't appended the new message to history yet.
        # Let's construct a temporary list.
        
        temp_messages = []
        if user_id in MESSAGES_BY_USER:
            temp_messages = MESSAGES_BY_USER[user_id].copy()
        
        # Append current message
        temp_messages.append({"role": "user", "content": user_input})
        
        plugin_processed = False
        user_input_to_process = user_input
        
        for plugin in PLUGINS:
            try:
                # Pass the selected provider to the plugin
                # The provider might be None if not set yet, defaulting to env
                current_provider = SELECTED_PROVIDER if SELECTED_PROVIDER else PROVIDER_FROM_ENV
                
                if plugin.is_plugin_applicable(temp_messages, current_provider):
                    print(f"Plugin {plugin.__name__} triggered.")
                    # process_messages modifies the messages list in place or returns it?
                    # The spec says "Modifies the messages accordingly".
                    # Let's assume it modifies the last message content if needed.
                    # We should pass a copy or the actual list?
                    # If we pass temp_messages, we can check if the last message content changed.
                    
                    # We need to be careful. If we pass temp_messages and it modifies it, 
                    # we extract the content from the last message.
                    
                    # we extract the content from the last message.
                    
                    updated_messages = plugin.process_messages(temp_messages, current_provider)
                    if updated_messages:
                        last_msg = updated_messages[-1]
                        if last_msg["content"] != user_input:
                            user_input_to_process = last_msg["content"]
                            plugin_processed = True
                            await update.message.reply_text(f"Processed by plugin: {plugin.__name__.split('.')[-1]}")
                            break # Stop after first plugin triggers?
            except Exception as e:
                print(f"Error executing plugin {plugin.__name__}: {e}")

        # If no plugin processed it, user_input_to_process remains user_input

        if user_id in MESSAGES_BY_USER:
            MESSAGES_BY_USER[user_id].append(
                {"role": "user", "content": user_input_to_process},
            )

        else:  # the user posted his first message
            MESSAGES_BY_USER[user_id] = [
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user", "content": user_input_to_process},
            ]

        # answer = ask_gpt_single_message(user_input, SYSTEM_MSG, max_length=500)
        answer = ask_gpt_multi_message(
            MESSAGES_BY_USER[user_id],
            max_length=500,
            user_defined_provider=SELECTED_PROVIDER,
        )

        MESSAGES_BY_USER[user_id].append(
            {"role": "assistant", "content": answer},
        )

        # remove the oldest messages. We keep only the last MAX_MESSAGES_NUM messages
        if len(MESSAGES_BY_USER[user_id]) > MAX_MESSAGES_NUM:
            MESSAGES_BY_USER[user_id] = MESSAGES_BY_USER[user_id][-MAX_MESSAGES_NUM:]
            # attach the system message to the beginning
            MESSAGES_BY_USER[user_id].insert(
                0, {"role": "system", "content": SYSTEM_MSG}
            )
        print(f"Messages length: {len(MESSAGES_BY_USER[user_id])}")

        await update.message.reply_text(answer)
    else:
        answer = f"Eh? Du hast doch keine Berechtigung. Deine user_id ist {user_id}."
        print(answer)
        await update.message.reply_text(answer)


async def handle_photo_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("In the handle_photo_message function...")
    user_id = update.effective_user.id

    if user_id in ALLOWED_USER_IDS:
        try:
            # Reject media groups (albums) when only 1 image per message is allowed
            if update.message.media_group_id is not None and MAX_IMAGES_PER_MESSAGE == 1:
                msg = f"Too many images in one message (album). Allowed: {MAX_IMAGES_PER_MESSAGE}."
                print(msg)
                await update.message.reply_text(msg)
                return
            photos = update.message.photo
            if not photos:
                await update.message.reply_text("got an image")
                return
            # Debug: Telegram PhotoSize reported size
            reported_photo_size = getattr(photos[-1], "file_size", None)
            print(f"DEBUG(photo): PhotoSize.file_size={reported_photo_size} bytes")
            # Pre-check size (Telegram photo sizes are server-compressed, so we also check post-download size below)
            if is_file_too_large(getattr(photos[-1], "file_size", None), MAX_IMAGE_SIZE_MB):
                msg = f"File size exceeds the maximum limit of {MAX_IMAGE_SIZE_MB}MB. Please send a smaller image."
                print(msg)
                await update.message.reply_text(msg)
                return

            file_id = photos[-1].file_id
            file = await context.bot.get_file(file_id)
            # Debug: Telegram File reported size
            reported_file_size = getattr(file, "file_size", None)
            print(f"DEBUG(photo): File.file_size={reported_file_size} bytes")
            if is_file_too_large(getattr(file, "file_size", None), MAX_IMAGE_SIZE_MB):
                msg = f"File size exceeds the maximum limit of {MAX_IMAGE_SIZE_MB}MB. Please send a smaller image."
                print(msg)
                await update.message.reply_text(msg)
                return

            bio = io.BytesIO()
            await file.download_to_memory(out=bio)
            # Post-download size check (definitive)
            bytes_len = bio.getbuffer().nbytes
            print(f"DEBUG(photo): downloaded bytes_len={bytes_len} bytes (~{bytes_len/1024/1024:.2f} MB)")
            if is_file_too_large(bytes_len, MAX_IMAGE_SIZE_MB):
                msg = f"File size exceeds the maximum limit of {MAX_IMAGE_SIZE_MB}MB. Please send a smaller image."
                print(msg)
                await update.message.reply_text(msg)
                return
            bio.seek(0)
            img = Image.open(bio)
            w, h = img.size
            print(f"DEBUG(photo): original downloaded image size={w}x{h}")

            # Resize to OpenAI requirements and encode
            img_resized = openai_requirements_image_resize(img)
            rw, rh = img_resized.size
            print(f"DEBUG(photo): resized image size={rw}x{rh}")
            data_url = encode_image_to_data_url(img_resized, fmt="JPEG")

            image_content = {"type": "image_url", "image_url": {"url": data_url}}
            content_parts = []
            if isinstance(update.message.caption, str) and len(update.message.caption.strip()) > 0:
                print(f"DEBUG(photo): caption_len={len(update.message.caption.strip())}")
                content_parts.append({"type": "text", "text": update.message.caption.strip()})
            content_parts.append(image_content)

            user_input = update.message.caption or ""
            
            # Provider update logic
            switch7, report = update_provider_from_user_input(user_input)
            if switch7:
                await update.message.reply_text(report)
            
            # Strip indicator
            for provider, indicators in PROVIDER_INDICATORS.items():
                for indicator in indicators:
                    if user_input.lower().startswith(indicator):
                        user_input = user_input[len(indicator) :].strip()

            # Temp messages for plugins
            temp_messages = []
            if user_id in MESSAGES_BY_USER:
                temp_messages = MESSAGES_BY_USER[user_id].copy()
            
            temp_messages.append({"role": "user", "content": content_parts})
            
            plugin_processed = False
            current_provider = SELECTED_PROVIDER if SELECTED_PROVIDER else PROVIDER_FROM_ENV
            final_messages = temp_messages # Default
            
            for plugin in PLUGINS:
                try:
                    if plugin.is_plugin_applicable(temp_messages, current_provider):
                        print(f"Plugin {plugin.__name__} triggered.")
                        updated_messages = plugin.process_messages(temp_messages, current_provider)
                        if updated_messages:
                            final_messages = updated_messages
                            plugin_processed = True
                            await update.message.reply_text(f"Processed by plugin: {plugin.__name__.split('.')[-1]}")
                            break 
                except Exception as e:
                    print(f"Error executing plugin {plugin.__name__}: {e}")

            if user_id in MESSAGES_BY_USER:
                MESSAGES_BY_USER[user_id].append(final_messages[-1])
            else:
                MESSAGES_BY_USER[user_id] = [
                    {"role": "system", "content": SYSTEM_MSG},
                    final_messages[-1],
                ]

            answer = ask_gpt_multi_message(
                MESSAGES_BY_USER[user_id],
                max_length=500,
                user_defined_provider=SELECTED_PROVIDER,
            )

            MESSAGES_BY_USER[user_id].append({"role": "assistant", "content": answer})
            if len(MESSAGES_BY_USER[user_id]) > MAX_MESSAGES_NUM:
                MESSAGES_BY_USER[user_id] = MESSAGES_BY_USER[user_id][-MAX_MESSAGES_NUM:]
                MESSAGES_BY_USER[user_id].insert(0, {"role": "system", "content": SYSTEM_MSG})

            await update.message.reply_text(answer)
        except Exception as e:
            print(f"Error handling photo: {e}")
            await update.message.reply_text("Sorry, failed to process the image.")
    else:
        answer = f"Eh? Du hast doch keine Berechtigung. Deine user_id ist {user_id}."
        print(answer)
        await update.message.reply_text(answer)

async def handle_image_document_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("In the handle_image_document_message function...")
    user_id = update.effective_user.id

    if user_id in ALLOWED_USER_IDS:
        try:
            # Reject media groups (albums) for documents as well when limit is 1
            if update.message.media_group_id is not None and MAX_IMAGES_PER_MESSAGE == 1:
                msg = f"Too many images in one message (album). Allowed: {MAX_IMAGES_PER_MESSAGE}."
                print(msg)
                await update.message.reply_text(msg)
                return
            doc = update.message.document
            if not doc or not isinstance(doc.mime_type, str) or not doc.mime_type.startswith("image/"):
                return
            print(f"DEBUG(doc): name={getattr(doc, 'file_name', None)}, mime={doc.mime_type}, file_size={getattr(doc, 'file_size', None)} bytes")
            # Pre-check size on the document (original size preserved for documents)
            if is_file_too_large(getattr(doc, "file_size", None), MAX_IMAGE_SIZE_MB):
                msg = f"File size exceeds the maximum limit of {MAX_IMAGE_SIZE_MB}MB. Please send a smaller image."
                print(msg)
                await update.message.reply_text(msg)
                return

            file = await context.bot.get_file(doc.file_id)
            print(f"DEBUG(doc): File.file_size={getattr(file, 'file_size', None)} bytes")
            if is_file_too_large(getattr(file, "file_size", None), MAX_IMAGE_SIZE_MB):
                msg = f"File size exceeds the maximum limit of {MAX_IMAGE_SIZE_MB}MB. Please send a smaller image."
                print(msg)
                await update.message.reply_text(msg)
                return

            bio = io.BytesIO()
            await file.download_to_memory(out=bio)
            bytes_len = bio.getbuffer().nbytes
            print(f"DEBUG(doc): downloaded bytes_len={bytes_len} bytes (~{bytes_len/1024/1024:.2f} MB)")
            if is_file_too_large(bytes_len, MAX_IMAGE_SIZE_MB):
                msg = f"File size exceeds the maximum limit of {MAX_IMAGE_SIZE_MB}MB. Please send a smaller image."
                print(msg)
                await update.message.reply_text(msg)
                return
            bio.seek(0)
            img = Image.open(bio)
            w, h = img.size
            print(f"DEBUG(doc): original downloaded image size={w}x{h}")

            img_resized = openai_requirements_image_resize(img)
            rw, rh = img_resized.size
            print(f"DEBUG(doc): resized image size={rw}x{rh}")
            # Preserve format when reasonable, default to JPEG
            fmt = "JPEG"
            if isinstance(doc.mime_type, str) and "png" in doc.mime_type:
                fmt = "PNG"
            data_url = encode_image_to_data_url(img_resized, fmt=fmt)

            image_content = {"type": "image_url", "image_url": {"url": data_url}}
            content_parts = []
            if isinstance(update.message.caption, str) and len(update.message.caption.strip()) > 0:
                print(f"DEBUG(doc): caption_len={len(update.message.caption.strip())}")
                content_parts.append({"type": "text", "text": update.message.caption.strip()})
            content_parts.append(image_content)

            if user_id in MESSAGES_BY_USER:
                MESSAGES_BY_USER[user_id].append({"role": "user", "content": content_parts})
            else:
                MESSAGES_BY_USER[user_id] = [
                    {"role": "system", "content": SYSTEM_MSG},
                    {"role": "user", "content": content_parts},
                ]

            answer = ask_gpt_multi_message(
                MESSAGES_BY_USER[user_id],
                max_length=500,
                user_defined_provider=SELECTED_PROVIDER,
            )

            MESSAGES_BY_USER[user_id].append({"role": "assistant", "content": answer})
            if len(MESSAGES_BY_USER[user_id]) > MAX_MESSAGES_NUM:
                MESSAGES_BY_USER[user_id] = MESSAGES_BY_USER[user_id][-MAX_MESSAGES_NUM:]
                MESSAGES_BY_USER[user_id].insert(0, {"role": "system", "content": SYSTEM_MSG})

            await update.message.reply_text(answer)
        except Exception as e:
            print(f"Error handling image document: {e}")
            await update.message.reply_text("Sorry, failed to process the image document.")
    else:
        answer = f"Eh? Du hast doch keine Berechtigung. Deine user_id ist {user_id}."
        print(answer)
        await update.message.reply_text(answer)


async def handle_video_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("In the handle_video_message function...")
    user_id = update.effective_user.id

    if user_id in ALLOWED_USER_IDS:
        try:
            video = update.message.video
            if not video:
                return
            
            print(f"DEBUG(video): file_id={video.file_id}, mime={video.mime_type}, size={video.file_size}")
            
            video_content = {
                "type": "video", 
                "file_id": video.file_id,
                "mime_type": video.mime_type,
                "file_size": video.file_size,
                "file_name": getattr(video, "file_name", "video.mp4")
            }
            
            content_parts = []
            if isinstance(update.message.caption, str) and len(update.message.caption.strip()) > 0:
                content_parts.append({"type": "text", "text": update.message.caption.strip()})
            content_parts.append(video_content)
            
            user_input = update.message.caption or ""
            
            # Provider update logic
            switch7, report = update_provider_from_user_input(user_input)
            if switch7:
                await update.message.reply_text(report)
            
            # Strip indicator
            for provider, indicators in PROVIDER_INDICATORS.items():
                for indicator in indicators:
                    if user_input.lower().startswith(indicator):
                        user_input = user_input[len(indicator) :].strip()

            # Temp messages for plugins
            temp_messages = []
            if user_id in MESSAGES_BY_USER:
                temp_messages = MESSAGES_BY_USER[user_id].copy()
            
            temp_messages.append({"role": "user", "content": content_parts})
            
            plugin_processed = False
            current_provider = SELECTED_PROVIDER if SELECTED_PROVIDER else PROVIDER_FROM_ENV
            final_messages = temp_messages # Default
            
            for plugin in PLUGINS:
                try:
                    if plugin.is_plugin_applicable(temp_messages, current_provider):
                        print(f"Plugin {plugin.__name__} triggered.")
                        updated_messages = plugin.process_messages(temp_messages, current_provider)
                        if updated_messages:
                            final_messages = updated_messages
                            plugin_processed = True
                            await update.message.reply_text(f"Processed by plugin: {plugin.__name__.split('.')[-1]}")
                            break 
                except Exception as e:
                    print(f"Error executing plugin {plugin.__name__}: {e}")
            
            if user_id in MESSAGES_BY_USER:
                MESSAGES_BY_USER[user_id].append(final_messages[-1])
            else:
                MESSAGES_BY_USER[user_id] = [
                    {"role": "system", "content": SYSTEM_MSG},
                    final_messages[-1],
                ]

            answer = ask_gpt_multi_message(
                MESSAGES_BY_USER[user_id],
                max_length=500,
                user_defined_provider=SELECTED_PROVIDER,
            )

            MESSAGES_BY_USER[user_id].append({"role": "assistant", "content": answer})
            if len(MESSAGES_BY_USER[user_id]) > MAX_MESSAGES_NUM:
                MESSAGES_BY_USER[user_id] = MESSAGES_BY_USER[user_id][-MAX_MESSAGES_NUM:]
                MESSAGES_BY_USER[user_id].insert(0, {"role": "system", "content": SYSTEM_MSG})

            await update.message.reply_text(answer)

        except Exception as e:
            print(f"Error handling video: {e}")
            await update.message.reply_text("Sorry, failed to process the video.")
    else:
        answer = f"Eh? Du hast doch keine Berechtigung. Deine user_id ist {user_id}."
        print(answer)
        await update.message.reply_text(answer)


async def handle_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("In the handle_audio_message function...")
    user_id = update.effective_user.id

    if user_id in ALLOWED_USER_IDS:
        try:
            audio = update.message.audio or update.message.voice
            if not audio:
                return
            
            # Determine type
            msg_type = "audio" if update.message.audio else "voice"
            
            print(f"DEBUG({msg_type}): file_id={audio.file_id}, mime={audio.mime_type}, size={audio.file_size}")
            
            audio_content = {
                "type": msg_type, 
                "file_id": audio.file_id,
                "mime_type": audio.mime_type,
                "file_size": audio.file_size,
                "file_name": getattr(audio, "file_name", "audio.mp3")
            }
            
            content_parts = []
            if isinstance(update.message.caption, str) and len(update.message.caption.strip()) > 0:
                content_parts.append({"type": "text", "text": update.message.caption.strip()})
            content_parts.append(audio_content)
            
            user_input = update.message.caption or ""
            
            # Provider update logic
            switch7, report = update_provider_from_user_input(user_input)
            if switch7:
                await update.message.reply_text(report)
            
            # Strip indicator
            for provider, indicators in PROVIDER_INDICATORS.items():
                for indicator in indicators:
                    if user_input.lower().startswith(indicator):
                        user_input = user_input[len(indicator) :].strip()

            # Temp messages for plugins
            temp_messages = []
            if user_id in MESSAGES_BY_USER:
                temp_messages = MESSAGES_BY_USER[user_id].copy()
            
            temp_messages.append({"role": "user", "content": content_parts})
            
            plugin_processed = False
            current_provider = SELECTED_PROVIDER if SELECTED_PROVIDER else PROVIDER_FROM_ENV
            final_messages = temp_messages # Default
            
            for plugin in PLUGINS:
                try:
                    if plugin.is_plugin_applicable(temp_messages, current_provider):
                        print(f"Plugin {plugin.__name__} triggered.")
                        updated_messages = plugin.process_messages(temp_messages, current_provider)
                        if updated_messages:
                            final_messages = updated_messages
                            plugin_processed = True
                            await update.message.reply_text(f"Processed by plugin: {plugin.__name__.split('.')[-1]}")
                            break 
                except Exception as e:
                    print(f"Error executing plugin {plugin.__name__}: {e}")
            
            if user_id in MESSAGES_BY_USER:
                MESSAGES_BY_USER[user_id].append(final_messages[-1])
            else:
                MESSAGES_BY_USER[user_id] = [
                    {"role": "system", "content": SYSTEM_MSG},
                    final_messages[-1],
                ]

            answer = ask_gpt_multi_message(
                MESSAGES_BY_USER[user_id],
                max_length=500,
                user_defined_provider=SELECTED_PROVIDER,
            )

            MESSAGES_BY_USER[user_id].append({"role": "assistant", "content": answer})
            if len(MESSAGES_BY_USER[user_id]) > MAX_MESSAGES_NUM:
                MESSAGES_BY_USER[user_id] = MESSAGES_BY_USER[user_id][-MAX_MESSAGES_NUM:]
                MESSAGES_BY_USER[user_id].insert(0, {"role": "system", "content": SYSTEM_MSG})

            await update.message.reply_text(answer)

        except Exception as e:
            print(f"Error handling audio: {e}")
            await update.message.reply_text("Sorry, failed to process the audio.")
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
    print("In the main function...")
    app = Application.builder().token(TOKEN).build()

    """Restrict fhs bot to the specified user_id.
    NOTE: this should be always the first handler, to prevent the bot from responding to unauthorized users.
    """
    restrict_handler = MessageHandler(~filters.User(ALLOWED_USER_IDS), restrict)
    app.add_handler(restrict_handler)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("plugins", plugins_status))
    app.add_handler(CommandHandler("enable_plugin", enable_plugin_cmd))
    app.add_handler(CommandHandler("disable_plugin", disable_plugin_cmd))
    app.add_handler(CommandHandler("enable_all_plugins", enable_all_plugins_cmd))
    app.add_handler(CommandHandler("disable_all_plugins", disable_all_plugins_cmd))
    app.add_handler(CallbackQueryHandler(start_game_callback, pattern="^start_game$"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_message))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video_message))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE, handle_audio_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_image_document_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    main()
