# pip install python-telegram-bot==20.8 flask

import os
import threading
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, send_from_directory, abort
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
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

def main_keyboard():
    keyboard = [
        [KeyboardButton("/files"), KeyboardButton("/myfiles")],
        [KeyboardButton("/owner"), KeyboardButton("/start")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📁 *Telegram File Hosting Bot*\n\n"
        "यहाँ file भेजो और direct link पाओ।\n\n"
        "Commands:\n"
        "/files – सभी hosted files\n"
        "/myfiles – आपकी uploads\n"
        "/owner – Owner panel\n"
    )
    kb = [[InlineKeyboardButton("📞 Contact Owner", url=f"https://t.me/{OWNER_USERNAME}")]]
    await update.message.reply_markdown(text, reply_markup=InlineKeyboardMarkup(kb))
    await update.message.reply_text("👇 नीचे बटन से command चलाओ:", reply_markup=main_keyboard())

async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user
    # किसी भी document/photo/video/audio को पकड़ने के लिए generic attachment check
    doc = msg.document or msg.photo[-1] if msg.photo else None
    if not doc:
        await msg.reply_text("⚠️ कृपया कोई file भेजें (Document, Image, आदि)।")
        return

    orig_name = getattr(doc, "file_name", "uploaded_file")
    saved_name = make_saved_filename(orig_name)
    dest_path = UPLOAD_DIR / saved_name

    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(custom_path=str(dest_path))

    METADATA[saved_name] = {
        "uploader_id": user.id,
        "uploader_username": user.username or "",
        "original_name": orig_name,
        "saved_at": datetime.utcnow().isoformat(),
    }

    file_url = f"{BASE_URL}/files/{saved_name}"
    kb = [
        [InlineKeyboardButton("📂 Open link", url=file_url)],
        [InlineKeyboardButton("📞 Contact Owner", url=f"https://t.me/{OWNER_USERNAME}")],
    ]
    await msg.reply_markdown_v2(
        f"✅ File saved: `{orig_name}`\n🔗 [Download link]({file_url})",
        reply_markup=InlineKeyboardMarkup(kb),
    )

async def list_files_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not METADATA:
        await update.message.reply_text("📭 कोई file host नहीं है।", reply_markup=main_keyboard())
        return
    keyboard = []
    for fname, meta in METADATA.items():
        url = f"{BASE_URL}/files/{fname}"
        keyboard.append([InlineKeyboardButton(meta["original_name"], url=url)])
    if update.effective_user.id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("🛠 Owner Panel", callback_data="owner_panel")])
    await update.message.reply_text("📂 Hosted Files:", reply_markup=InlineKeyboardMarkup(keyboard))

async def myfiles_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_files = [(f, m) for f, m in METADATA.items() if m["uploader_id"] == uid]
    if not user_files:
        await update.message.reply_text("आपने अभी तक कुछ upload नहीं किया।", reply_markup=main_keyboard())
        return
    keyboard = []
    for fname, meta in user_files:
        url = f"{BASE_URL}/files/{fname}"
        keyboard.append([InlineKeyboardButton(meta["original_name"], url=url)])
    await update.message.reply_text("📁 आपकी Files:", reply_markup=InlineKeyboardMarkup(keyboard))

async def owner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ केवल owner के लिए।", reply_markup=main_keyboard())
        return
    keyboard = [[InlineKeyboardButton("🗑 Delete Files", callback_data="owner_manage")]]
    await update.message.reply_text("🛠 Owner Panel", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id

    if data == "owner_manage":
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return
        if not METADATA:
            await query.edit_message_text("No files to delete.")
            return
        keyboard = []
        for fname, meta in METADATA.items():
            cb = f"del::{fname}"
            keyboard.append([InlineKeyboardButton(f"❌ {meta['original_name']}", callback_data=cb)])
        await query.edit_message_text("Select file to delete:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("del::"):
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return
        fname = data.split("::", 1)[1]
        meta = METADATA.pop(fname, None)
        if not meta:
            await query.edit_message_text("Already deleted.")
            return
        try:
            (UPLOAD_DIR / fname).unlink(missing_ok=True)
        except Exception as e:
            await query.edit_message_text(f"Error deleting: {e}")
            return
        await query.edit_message_text(f"✅ Deleted {meta['original_name']}")
        return

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. /start भेजो।", reply_markup=main_keyboard())

def main():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info(f"Flask running on {WEB_HOST}:{WEB_PORT}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("files", list_files_cmd))
    app.add_handler(CommandHandler("myfiles", myfiles_cmd))
    app.add_handler(CommandHandler("owner", owner_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_upload))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot polling started...")
    app.run_polling()

if __name__ == "__main__":
    main()
