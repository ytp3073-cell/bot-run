# pip install --force-reinstall python-telegram-bot==20.8 flask

import threading
import logging
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
import html

from flask import Flask, send_from_directory, abort, Response
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
BASE_URL = "http://3.111.168.104:8178"   # Lightsail IP + port

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

WEB_HOST = "0.0.0.0"
WEB_PORT = 8178
# ----------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# key = id (saved file name OR site_id)
METADATA = {}

flask_app = Flask(__name__)

# ---------- Pretty 3D index page ----------
def build_index_html() -> str:
    cards = []
    if not METADATA:
        cards_html = """
        <div class="empty">
            <h2>No files hosted yet</h2>
            <p>Upload from Telegram bot to see your sites and files here.</p>
        </div>
        """
    else:
        for key, md in METADATA.items():
            if md["type"] == "site":
                url = md["main_url"]
                badge = "🌐 Website"
                color_class = "site"
            else:
                url = f"/files/{key}"
                badge = "📄 File"
                color_class = "file"

            name = html.escape(md["original_name"])
            user = html.escape(md.get("uploader_username") or str(md["uploader_id"]))
            time = html.escape(md["saved_at"].split("T")[0])

            cards.append(f"""
            <a href="{url}" class="card {color_class}">
                <div class="badge">{badge}</div>
                <h2>{name}</h2>
                <p>by @{user}</p>
                <span class="time">{time}</span>
            </a>
            """)

        cards_html = "\n".join(cards)

    page = f"""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8"/>
        <title>Telegram File Hosting</title>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <style>
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            }}
            body {{
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                background: radial-gradient(circle at top, #1e293b 0, #020617 45%, #000000 100%);
                color: #e5e7eb;
                padding: 40px 16px;
            }}
            .container {{
                width: 100%;
                max-width: 1100px;
            }}
            h1 {{
                font-size: 2.4rem;
                margin-bottom: 0.25rem;
                color: #f9fafb;
                text-shadow: 0 10px 40px rgba(0,0,0,0.8);
            }}
            .subtitle {{
                margin-bottom: 24px;
                color: #9ca3af;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
                gap: 18px;
            }}
            .card {{
                position: relative;
                padding: 18px 18px 20px 18px;
                border-radius: 18px;
                background: linear-gradient(135deg, rgba(15,23,42,0.95), rgba(30,64,175,0.9));
                box-shadow:
                    0 18px 40px rgba(0,0,0,0.7),
                    0 0 0 1px rgba(148,163,184,0.2);
                text-decoration: none;
                color: inherit;
                transform: translateY(0) translateZ(0);
                transition:
                    transform 0.2s ease,
                    box-shadow 0.2s ease,
                    background 0.2s ease,
                    border-color 0.2s ease;
                border: 1px solid rgba(148,163,184,0.3);
                overflow: hidden;
            }}
            .card::before {{
                content: "";
                position: absolute;
                inset: -40%;
                background:
                    radial-gradient(circle at 0 0, rgba(96,165,250,0.22), transparent 60%),
                    radial-gradient(circle at 100% 100%, rgba(244,114,182,0.18), transparent 60%);
                opacity: 0;
                transition: opacity 0.25s ease;
                pointer-events: none;
            }}
            .card:hover {{
                transform: translateY(-6px) translateZ(8px);
                box-shadow:
                    0 26px 60px rgba(0,0,0,0.85),
                    0 0 0 1px rgba(191,219,254,0.45);
                border-color: rgba(191,219,254,0.8);
                background: radial-gradient(circle at top left, rgba(59,130,246,0.35), rgba(15,23,42,0.98));
            }}
            .card:hover::before {{
                opacity: 1;
            }}
            .badge {{
                display: inline-flex;
                align-items: center;
                font-size: 0.7rem;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                padding: 4px 9px;
                border-radius: 999px;
                background: rgba(15,23,42,0.9);
                border: 1px solid rgba(148,163,184,0.7);
                color: #e5e7eb;
                margin-bottom: 10px;
            }}
            .card.site .badge {{
                border-color: rgba(96,165,250,0.8);
            }}
            .card.file .badge {{
                border-color: rgba(52,211,153,0.8);
            }}
            .card h2 {{
                font-size: 1.05rem;
                margin-bottom: 5px;
                color: #f9fafb;
                word-break: break-word;
            }}
            .card p {{
                font-size: 0.85rem;
                color: #9ca3af;
                margin-bottom: 6px;
            }}
            .card .time {{
                font-size: 0.75rem;
                color: #6b7280;
            }}
            .empty {{
                padding: 40px 28px;
                border-radius: 22px;
                background: linear-gradient(145deg, rgba(15,23,42,0.95), rgba(30,64,175,0.9));
                box-shadow:
                    0 18px 40px rgba(0,0,0,0.8),
                    0 0 0 1px rgba(148,163,184,0.3);
                text-align: center;
            }}
            .empty h2 {{
                font-size: 1.4rem;
                margin-bottom: 8px;
            }}
            .empty p {{
                color: #9ca3af;
                font-size: 0.95rem;
            }}
            .top-bar {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 18px;
                gap: 12px;
            }}
            .pill {{
                padding: 6px 12px;
                border-radius: 999px;
                border: 1px solid rgba(148,163,184,0.5);
                font-size: 0.8rem;
                color: #9ca3af;
                background: rgba(15,23,42,0.9);
            }}
            @media (max-width: 600px) {{
                h1 {{ font-size: 1.8rem; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="top-bar">
                <div>
                    <h1>Telegram File Hosting</h1>
                    <p class="subtitle">Files & websites uploaded via your bot are listed here.</p>
                </div>
                <div class="pill">Bot: @{html.escape(OWNER_USERNAME)}</div>
            </div>
            <div class="grid">
                {cards_html}
            </div>
        </div>
    </body>
    </html>
    """
    return page


@flask_app.route("/", methods=["GET"])
def index_page():
    return Response(build_index_html(), mimetype="text/html")


@flask_app.route("/files/<path:filename>", methods=["GET"])
def serve_file(filename):
    safe_path = (UPLOAD_DIR / filename).resolve()
    try:
        safe_path.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        abort(403)
    if not safe_path.exists():
        abort(404)
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)


def run_flask():
    flask_app.run(host=WEB_HOST, port=WEB_PORT, threaded=True)


# ------------ HELPERS -------------
def make_saved_filename(original_name: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    safe = original_name.replace(" ", "_")
    return f"{ts}__{safe}"

def make_site_id() -> str:
    return datetime.utcnow().strftime("site_%Y%m%d%H%M%S%f")

def main_keyboard():
    keyboard = [
        [KeyboardButton("/files"), KeyboardButton("/myfiles")],
        [KeyboardButton("/owner"), KeyboardButton("/start")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# ------------ BOT HANDLERS -------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🧊 *3D File / Website Hosting Bot*\n\n"
        "• HTML / PHP / TXT / JS / CSS / CPP जैसी files सीधे host होंगी.\n"
        "• ZIP भेजो (website) → unzip होकर अलग folder में host होगा.\n"
        "• Website का direct link भी मिलेगा (index.html मिलते ही).\n\n"
        "Commands:\n"
        "• /files – सब hosted items\n"
        "• /myfiles – तुम्हारी uploads\n"
        "• /owner – Owner panel\n\n"
        "👉 Files को हमेशा *Document* की तरह भेजना."
    )
    kb = [[InlineKeyboardButton("📞 Contact Owner", url=f"https://t.me/{OWNER_USERNAME}")]]
    await update.message.reply_markdown(text, reply_markup=InlineKeyboardMarkup(kb))
    await update.message.reply_text("👇 नीचे वाले buttons से भी use कर सकते हो:", reply_markup=main_keyboard())


async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user
    doc = msg.document

    if not doc:
        await msg.reply_text("⚠️ Website/file के लिए ZIP या code file *Document* की तरह भेजो.")
        return

    orig_name = doc.file_name or "uploaded_file"
    lower_name = orig_name.lower()
    ext = lower_name.rsplit(".", 1)[-1] if "." in lower_name else ""

    # ---------- ZIP → WEBSITE ----------
    if ext == "zip":
        site_id = make_site_id()
        site_dir = UPLOAD_DIR / site_id
        site_dir.mkdir(parents=True, exist_ok=True)

        zip_path = site_dir / orig_name.replace(" ", "_")
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(custom_path=str(zip_path))

        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(site_dir)
        except zipfile.BadZipFile:
            await msg.reply_text("❌ ZIP corrupt है, unzip नहीं हो पाया.")
            shutil.rmtree(site_dir, ignore_errors=True)
            return
        finally:
            zip_path.unlink(missing_ok=True)

        main_rel = "index.html" if (site_dir / "index.html").exists() else ""
        if main_rel:
            main_url = f"{BASE_URL}/files/{site_id}/{main_rel}"
        else:
            main_url = f"{BASE_URL}/files/{site_id}"

        METADATA[site_id] = {
            "type": "site",
            "uploader_id": user.id,
            "uploader_username": user.username or "",
            "original_name": orig_name,
            "saved_at": datetime.utcnow().isoformat(),
            "main_url": main_url,
        }

        kb = [
            [InlineKeyboardButton("🌐 Open Website", url=main_url)],
            [InlineKeyboardButton("📞 Contact Owner", url=f"https://t.me/{OWNER_USERNAME}")],
        ]
        await msg.reply_text(
            f"✅ Website ZIP host हो गया.\n🔗 URL: {main_url}",
            reply_markup=InlineKeyboardMarkup(kb),
        )
        return

    # ---------- NORMAL SINGLE FILE ----------
    saved_name = make_saved_filename(orig_name)
    dest_path = UPLOAD_DIR / saved_name

    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(custom_path=str(dest_path))

    METADATA[saved_name] = {
        "type": "file",
        "uploader_id": user.id,
        "uploader_username": user.username or "",
        "original_name": orig_name,
        "saved_at": datetime.utcnow().isoformat(),
    }

    file_url = f"{BASE_URL}/files/{saved_name}"
    kb = [
        [InlineKeyboardButton("📂 Open File", url=file_url)],
        [InlineKeyboardButton("📞 Contact Owner", url=f"https://t.me/{OWNER_USERNAME}")],
    ]
    await msg.reply_text(
        f"✅ File host हो गया: {orig_name}\n🔗 URL: {file_url}",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def list_files_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not METADATA:
        await update.message.reply_text("📭 अभी कुछ भी host नहीं है.", reply_markup=main_keyboard())
        return

    keyboard = []
    for key, md in METADATA.items():
        if md["type"] == "site":
            url = md["main_url"]
            label = f"🌐 {md['original_name']} (site)"
        else:
            url = f"{BASE_URL}/files/{key}"
            label = f"📄 {md['original_name']}"
        keyboard.append([InlineKeyboardButton(label, url=url)])

    if update.effective_user.id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("🛠 Owner Panel", callback_data="owner_panel")])

    await update.message.reply_text("Hosted items:", reply_markup=InlineKeyboardMarkup(keyboard))


async def myfiles_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_items = [(k, m) for k, m in METADATA.items() if m["uploader_id"] == uid]

    if not user_items:
        await update.message.reply_text("आपने अभी तक कुछ upload नहीं किया.", reply_markup=main_keyboard())
        return

    keyboard = []
    for key, md in user_items:
        if md["type"] == "site":
            url = md["main_url"]
            label = f"🌐 {md['original_name']} (site)"
        else:
            url = f"{BASE_URL}/files/{key}"
            label = f"📄 {md['original_name']}"
        keyboard.append([InlineKeyboardButton(label, url=url)])

    await update.message.reply_text("📁 आपकी hosted चीज़ें:", reply_markup=InlineKeyboardMarkup(keyboard))


async def owner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ सिर्फ owner के लिए.", reply_markup=main_keyboard())
        return
    keyboard = [[InlineKeyboardButton("🗑 Manage / Delete", callback_data="owner_manage")]]
    await update.message.reply_text("🛠 Owner Panel", reply_markup=InlineKeyboardMarkup(keyboard))


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

    if data == "owner_manage":
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return
        if not METADATA:
            await query.edit_message_text("कुछ भी host नहीं है.")
            return

        keyboard = []
        for key, md in METADATA.items():
            prefix = "🌐" if md["type"] == "site" else "📄"
            cb = f"del::{key}"
            keyboard.append([
                InlineKeyboardButton(f"❌ {prefix} {md['original_name']}", callback_data=cb)
            ])
        await query.edit_message_text("Delete करने के लिए चुनो:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("del::"):
        if uid != OWNER_ID:
            await query.edit_message_text("Unauthorized.")
            return

        key = data.split("::", 1)[1]
        md = METADATA.pop(key, None)
        if not md:
            await query.edit_message_text("Already deleted.")
            return

        path = UPLOAD_DIR / key
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        except Exception as e:
            await query.edit_message_text(f"Error deleting: {e}")
            return

        await query.edit_message_text(f"✅ Deleted {md['original_name']}")
        return


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. /start भेजो.", reply_markup=main_keyboard())


def main():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    logger.info(f"Flask server running on {WEB_HOST}:{WEB_PORT}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("files", list_files_cmd))
    app.add_handler(CommandHandler("myfiles", myfiles_cmd))
    app.add_handler(CommandHandler("owner", owner_cmd))

    # केवल documents handle कर रहे हैं (code / zip / html सब इसी में आएँगे)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_upload))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot polling started...")
    app.run_polling()


if __name__ == "__main__":
    main()
