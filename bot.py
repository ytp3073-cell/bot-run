# filename: tg_file_host_bot.py
# Python 3.9+ (recommend 3.10/3.11)
# Libraries required:
# pip install python-telegram-bot==20.8 flask python-multipart

import os
import threading
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, send_from_directory, abort
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ---------------- CONFIG ----------------
BOT_TOKEN = "8419880200:AAG5OpgB0BG7FOpN-XrUu_7y3hGJKmWimI4"
# Telegram numeric user id of owner (int). Replace with your telegram user id.
OWNER_ID = 7652176329
# Owner username for contact button (without @). If you want phone-contact features, implement separately.
OWNER_USERNAME = "ownerusername"

# Where uploads will be stored
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Host config for serving files
WEB_HOST = "0.0.0.0"
WEB_PORT = 8178  # change if occupied
BASE_URL = f"http://YOUR_SERVER_IP_OR_DOMAIN:{WEB_PORT}"  # change to your public IP/domain

# ----------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Simple metadata store in-memory (persist as JSON if needed)
# Structure: filename -> {uploader_id, original_name, saved_at}
METADATA = {}

# Flask app to serve files
flask_app = Flask(__name__)

@flask_app.route("/files/<path:filename>", methods=["GET"])
def serve_file(filename):
    # basic check - prevent path traversal
    safe_path = UPLOAD_DIR.joinpath(filename)
    try:
        safe_path.resolve(strict=True)
    except FileNotFoundError:
        abort(404)
    # ensure file is inside UPLOAD_DIR
    if UPLOAD_DIR not in safe_path.parents and safe_path != UPLOAD_DIR:
        abort(403)
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


def run_flask():
    # start flask in a background thread
    flask_app.run(host=WEB_HOST, port=WEB_PORT, threaded=True)


# Helper to create unique filename
def make_saved_filename(original_name: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    safe = original_name.replace(" ", "_")
    return f"{ts}__{safe}"


# Handlers for Telegram bot
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "File Host Bot ready.\n\n"
        "Commands:\n"
        "/upload - send a file directly (or just send document)\n"
        "/files - list all hosted files\n"
        "/myfiles - list your uploads\n        "
        "/owner - owner panel (only owner)\n\n"
        "Also use the Contact Owner button below."
    )
    kb = [
        [InlineKeyboardButton("Contact Owner", url=f"https://t.me/{OWNER_USERNAME}")],
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


# When user sends document/file
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user
    doc = msg.document or msg.effective_attachment
    if doc is None:
        await msg.reply_text("Koi document detect nahi hua. File bhejein (as document).")
        return

    orig_name = doc.file_name or "unknown"
    saved_name = make_saved_filename(orig_name)
    dest_path = UPLOAD_DIR / saved_name

    # download file
    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(custom_path=str(dest_path))

    # record metadata
    METADATA[saved_name] = {
        "uploader_id": user.id,
        "uploader_username": user.username or "",
        "original_name": orig_name,
        "saved_at": datetime.utcnow().isoformat(),
        "size": doc.file_size or 0,
    }

    file_url = f"{BASE_URL}/files/{saved_name}"
    text = f"✅ File saved as `{orig_name}`\n🔗 Public link: {file_url}"
    kb = [
        [InlineKeyboardButton("Open link", url=file_url)],
        [InlineKeyboardButton("Contact Owner", url=f"https://t.me/{OWNER_USERNAME}")],
    ]
    await msg.reply_markdown_v2(text, reply_markup=InlineKeyboardMarkup(kb))


async def list_files_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not METADATA:
        await update.message.reply_text("Koi file hosted nahi hai abhi.")
        return
    lines = []
    keyboard = []
    for saved_name, md in list(METADATA.items()):
        name = md["original_name"]
        uploader = md["uploader_username"] or str(md["uploader_id"])
        file_url = f"{BASE_URL}/files/{saved_name}"
        # each file as separate button row
        keyboard.append([InlineKeyboardButton(f"{name} ({uploader})", url=file_url)])
    # If caller is owner, add owner panel button
    if update.effective_user.id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("Open Owner Panel", callback_data="owner_panel")])
    await update.message.reply_text("Hosted files:", reply_markup=InlineKeyboardMarkup(keyboard))


async def myfiles_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_files = [(s, m) for s, m in METADATA.items() if m["uploader_id"] == uid]
    if not user_files:
        await update.message.reply_text("Aapne abhi tak koi file upload nahi ki.")
        return
    keyboard = []
    for saved_name, md in user_files:
        name = md["original_name"]
        file_url = f"{BASE_URL}/files/{saved_name}"
        keyboard.append([InlineKeyboardButton(name, url=file_url)])
    await update.message.reply_text("Aapki files:", reply_markup=InlineKeyboardMarkup(keyboard))


# Owner-only panel via command
async def owner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != OWNER_ID:
        await update.message.reply_text("Ye command sirf owner ke liye hai.")
        return
    # show control buttons
    keyboard = [
        [InlineKeyboardButton("List all files (manage)", callback_data="owner_manage_files")],
        [InlineKeyboardButton("Shutdown bot (not implemented here)", callback_data="owner_shutdown")],
    ]
    await update.message.reply_text("Owner Panel:", reply_markup=InlineKeyboardMarkup(keyboard))


# CallbackQuery handler for inline buttons
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "owner_panel":
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return
        # show owner manage files
        await owner_cmd(update, context)
        return

    if data == "owner_manage_files":
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return
        if not METADATA:
            await query.edit_message_text("No files.")
            return
        # create list with delete buttons
        keyboard = []
        for saved_name, md in METADATA.items():
            name = md["original_name"]
            # callback data include prefix + saved_name
            cb = f"owner_delete::{saved_name}"
            keyboard.append([InlineKeyboardButton(f"Delete — {name}", callback_data=cb)])
        await query.edit_message_text("Choose file to delete:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("owner_delete::"):
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return
        saved_name = data.split("::", 1)[1]
        meta = METADATA.get(saved_name)
        if not meta:
            await query.edit_message_text("File already removed or not found.")
            return
        # delete file physically
        path = UPLOAD_DIR / saved_name
        try:
            path.unlink(missing_ok=True)
        except Exception as e:
            logger.exception("delete error")
            await query.edit_message_text(f"Error deleting file: {e}")
            return
        del METADATA[saved_name]
        await query.edit_message_text(f"Deleted: {meta['original_name']}")
        return

    if data == "owner_shutdown":
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return
        await query.edit_message_text("Shutdown not implemented in this script.")
        return

    await query.edit_message_text("Unknown action.")


# Simple unknown handler
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Command samjha nahi. /start dekh lo.")


def main():
    # start flask server thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info(f"Started Flask file server on {WEB_HOST}:{WEB_PORT}")

    # build telegram app
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("files", list_files_cmd))
    app.add_handler(CommandHandler("myfiles", myfiles_cmd))
    app.add_handler(CommandHandler("owner", owner_cmd))

    # document handler (accept documents & audio & video & photos as files)
    app.add_handler(MessageHandler(filters.Document.ALL | filters.Audio.ALL | filters.Video.ALL | filters.PHOTO, handle_document))

    # callback queries
    app.add_handler(CallbackQueryHandler(callback_handler))

    # fallback
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot starting polling...")
    app.run_polling()


if __name__ == "__main__":
    if BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print("Edit the script: set BOT_TOKEN, OWNER_ID, OWNER_USERNAME and BASE_URL (public address).")
        raise SystemExit(1)
    main()
