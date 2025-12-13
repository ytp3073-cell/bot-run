# filename: bot.py
# pip install python-telegram-bot==20.8 flask

import os
import threading
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, send_from_directory, abort
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------- CONFIG ----------------
BOT_TOKEN = "8419880200:AAG5OpgB0BG7FOpN-XrUu_7y3hGJKmWimI4"
OWNER_ID = 7652176329
OWNER_USERNAME = "ducy"
BASE_URL = "http://3.111.168.104:8178"

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

WEB_HOST = "0.0.0.0"
WEB_PORT = 8178

# ----------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

METADATA = {}

flask_app = Flask(__name__)

@flask_app.route("/files/<path:filename>", methods=["GET"])
def serve_file(filename):
    safe_path = UPLOAD_DIR.joinpath(filename)
    try:
        safe_path.resolve(strict=True)
    except FileNotFoundError:
        abort(404)
    if UPLOAD_DIR not in safe_path.parents and safe_path != UPLOAD_DIR:
        abort(403)
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


def run_flask():
    flask_app.run(host=WEB_HOST, port=WEB_PORT, threaded=True)


def make_saved_filename(original_name: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    safe = original_name.replace(" ", "_")
    return f"{ts}__{safe}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📁 *File Hosting Bot*\n\n"
        "Upload files directly here.\n"
        "Commands:\n"
        "/files - All hosted files\n"
        "/myfiles - Your uploads\n"
        "/owner - Owner panel (owner only)"
    )
    kb = [[InlineKeyboardButton("Contact Owner", url=f"https://t.me/{OWNER_USERNAME}")]]
    await update.message.reply_markdown(text, reply_markup=InlineKeyboardMarkup(kb))


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user
    doc = msg.document or msg.effective_attachment
    if doc is None:
        await msg.reply_text("⚠️ कोई document detect नहीं हुआ। कृपया फाइल भेजें।")
        return

    orig_name = doc.file_name or "unknown"
    saved_name = make_saved_filename(orig_name)
    dest_path = UPLOAD_DIR / saved_name

    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(custom_path=str(dest_path))

    METADATA[saved_name] = {
        "uploader_id": user.id,
        "uploader_username": user.username or "",
        "original_name": orig_name,
        "saved_at": datetime.utcnow().isoformat(),
        "size": doc.file_size or 0,
    }

    file_url = f"{BASE_URL}/files/{saved_name}"
    kb = [
        [InlineKeyboardButton("📂 Open link", url=file_url)],
        [InlineKeyboardButton("📞 Contact Owner", url=f"https://t.me/{OWNER_USERNAME}")],
    ]
    await msg.reply_markdown_v2(f"✅ File saved: `{orig_name}`\n🔗 [Open link]({file_url})", reply_markup=InlineKeyboardMarkup(kb))


async def list_files_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not METADATA:
        await update.message.reply_text("कोई file host नहीं है अभी।")
        return
    keyboard = []
    for saved_name, md in METADATA.items():
        name = md["original_name"]
        uploader = md["uploader_username"] or str(md["uploader_id"])
        file_url = f"{BASE_URL}/files/{saved_name}"
        keyboard.append([InlineKeyboardButton(f"{name} ({uploader})", url=file_url)])
    if update.effective_user.id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("Owner Panel", callback_data="owner_panel")])
    await update.message.reply_text("📂 Hosted Files:", reply_markup=InlineKeyboardMarkup(keyboard))


async def myfiles_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_files = [(s, m) for s, m in METADATA.items() if m["uploader_id"] == uid]
    if not user_files:
        await update.message.reply_text("आपने अभी तक कोई file upload नहीं की।")
        return
    keyboard = []
    for saved_name, md in user_files:
        name = md["original_name"]
        file_url = f"{BASE_URL}/files/{saved_name}"
        keyboard.append([InlineKeyboardButton(name, url=file_url)])
    await update.message.reply_text("आपकी Files:", reply_markup=InlineKeyboardMarkup(keyboard))


async def owner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != OWNER_ID:
        await update.message.reply_text("❌ यह command सिर्फ owner के लिए है।")
        return
    keyboard = [
        [InlineKeyboardButton("Manage Files", callback_data="owner_manage_files")],
    ]
    await update.message.reply_text("🛠 Owner Panel:", reply_markup=InlineKeyboardMarkup(keyboard))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "owner_panel":
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return
        await owner_cmd(update, context)
        return

    if data == "owner_manage_files":
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return
        if not METADATA:
            await query.edit_message_text("No files.")
            return
        keyboard = []
        for saved_name, md in METADATA.items():
            name = md["original_name"]
            cb = f"owner_delete::{saved_name}"
            keyboard.append([InlineKeyboardButton(f"❌ Delete {name}", callback_data=cb)])
        await query.edit_message_text("Choose file to delete:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("owner_delete::"):
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return
        saved_name = data.split("::", 1)[1]
        meta = METADATA.get(saved_name)
        if not meta:
            await query.edit_message_text("File already removed.")
            return
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


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Command नहीं मिला। /start भेजें।")


def main():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info(f"Started Flask file server on {WEB_HOST}:{WEB_PORT}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("files", list_files_cmd))
    app.add_handler(CommandHandler("myfiles", myfiles_cmd))
    app.add_handler(CommandHandler("owner", owner_cmd))

    # ✅ fixed line below
    app.add_handler(
        MessageHandler(
            filters.Document.ALL | filters.AUDIO.ALL | filters.VIDEO.ALL | filters.PHOTO,
            handle_document,
        )
    )

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot starting polling...")
    app.run_polling()


if __name__ == "__main__":
    if BOT_TOKEN == "":
        print("Edit BOT_TOKEN before running.")
        raise SystemExit(1)
    main()
