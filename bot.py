# pip install --force-reinstall python-telegram-bot==20.8 flask

import threading, logging, shutil, zipfile, html
from pathlib import Path
from datetime import datetime
from flask import Flask, send_from_directory, abort, Response
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ============= CONFIG =============
BOT_TOKEN = "8419880200:AAG5OpgB0BG7FOpN-XrUu_7y3hGJKmWimI4"
OWNER_ID = 7652176329
OWNER_USERNAME = "ducy"
BASE_URL = "http://3.111.168.104:8178"

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
WEB_HOST = "0.0.0.0"
WEB_PORT = 8178
# =================================

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# key = file_id or site_id
METADATA = {}
flask_app = Flask(__name__)

# ============= FLASK FRONT (3D STYLE) =============

def build_index_html() -> str:
    if not METADATA:
        cards_html = """
        <div class="empty">
            <h2>🚀 No sites or files yet</h2>
            <p>Upload from your Telegram hosting bot to see them here.</p>
        </div>
        """
    else:
        cards = []
        for key, md in METADATA.items():
            if md["type"] == "site":
                url = md["main_url"]
                badge = "Website"
                icon = "🌐"
                cls = "site"
            else:
                url = f"/files/{key}"
                badge = "File"
                icon = "📄"
                cls = "file"
            title = html.escape(md["original_name"])
            user = html.escape(md.get("uploader_username") or str(md["uploader_id"]))
            date = html.escape(md["saved_at"].split("T")[0])

            cards.append(f"""
            <a href="{url}" class="card {cls}">
                <div class="glow"></div>
                <div class="badge">{badge}</div>
                <h2>{icon} {title}</h2>
                <p>@{user}</p>
                <span class="time">{date}</span>
            </a>
            """)

        cards_html = "\n".join(cards)

    return f"""
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8"/>
        <title>Telegram Website Hosting</title>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                background: radial-gradient(circle at top, #1d263b 0, #020617 40%, #000 100%);
                color: #e5e7eb;
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                padding: 32px 16px;
                overflow-x: hidden;
            }}
            .bg-orbit {{
                position: fixed;
                inset: 0;
                background:
                    radial-gradient(circle at 10% 0%, rgba(56,189,248,0.28), transparent 55%),
                    radial-gradient(circle at 90% 100%, rgba(244,114,182,0.22), transparent 55%);
                opacity: 0.9;
                mix-blend-mode: screen;
                pointer-events: none;
                z-index: 0;
            }}
            .container {{
                position: relative;
                z-index: 1;
                width: 100%;
                max-width: 1120px;
            }}
            .top {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 12px;
                margin-bottom: 22px;
            }}
            h1 {{
                font-size: 2.4rem;
                letter-spacing: 0.03em;
                color: #f9fafb;
                text-shadow: 0 18px 55px rgba(0,0,0,0.8);
            }}
            .subtitle {{
                color: #9ca3af;
                font-size: 0.9rem;
                margin-top: 4px;
            }}
            .pill {{
                padding: 8px 14px;
                border-radius: 999px;
                border: 1px solid rgba(148,163,184,0.5);
                background: rgba(15,23,42,0.92);
                font-size: 0.8rem;
                color: #cbd5f5;
                box-shadow: 0 10px 30px rgba(0,0,0,0.6);
                display: flex;
                align-items: center;
                gap: 6px;
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
                background: radial-gradient(circle at top left, rgba(37,99,235,0.22), rgba(15,23,42,0.98));
                border: 1px solid rgba(148,163,184,0.45);
                text-decoration: none;
                color: inherit;
                overflow: hidden;
                transform: perspective(900px) translateZ(0) rotateX(0deg) rotateY(0deg) translateY(0);
                transition:
                    transform 0.22s ease-out,
                    box-shadow 0.22s ease-out,
                    border-color 0.22s ease-out,
                    background 0.22s ease-out;
                box-shadow:
                    0 18px 40px rgba(0,0,0,0.7),
                    0 0 0 1px rgba(15,23,42,0.8);
            }}
            .card .glow {{
                position: absolute;
                inset: -40%;
                background:
                    radial-gradient(circle at 0 0, rgba(129,230,217,0.32), transparent 60%),
                    radial-gradient(circle at 100% 100%, rgba(251,113,133,0.22), transparent 60%);
                opacity: 0;
                transition: opacity 0.22s ease-out;
                pointer-events: none;
            }}
            .card.site {{
                border-color: rgba(96,165,250,0.75);
            }}
            .card.file {{
                border-color: rgba(52,211,153,0.75);
            }}
            .card:hover {{
                transform: perspective(900px) translateZ(18px) translateY(-6px) rotateX(6deg);
                box-shadow:
                    0 28px 70px rgba(0,0,0,0.9),
                    0 0 0 1px rgba(191,219,254,0.7);
                background: radial-gradient(circle at top left, rgba(59,130,246,0.35), rgba(15,23,42,0.98));
            }}
            .card:hover .glow {{
                opacity: 1;
            }}
            .badge {{
                display: inline-flex;
                align-items: center;
                padding: 4px 10px;
                border-radius: 999px;
                font-size: 0.7rem;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                border: 1px solid rgba(148,163,184,0.8);
                background: rgba(15,23,42,0.95);
                color: #e5e7eb;
                margin-bottom: 12px;
            }}
            .card.site .badge {{
                border-color: rgba(96,165,250,0.9);
            }}
            .card.file .badge {{
                border-color: rgba(52,211,153,0.9);
            }}
            .card h2 {{
                font-size: 1.05rem;
                margin-bottom: 6px;
                color: #f9fafb;
                word-break: break-word;
            }}
            .card p {{
                font-size: 0.85rem;
                color: #cbd5f5;
                margin-bottom: 6px;
            }}
            .card .time {{
                font-size: 0.75rem;
                color: #9ca3af;
            }}
            .empty {{
                margin-top: 50px;
                padding: 40px 28px;
                border-radius: 24px;
                background: radial-gradient(circle at top, rgba(37,99,235,0.25), rgba(15,23,42,0.95));
                border: 1px solid rgba(148,163,184,0.6);
                box-shadow:
                    0 22px 50px rgba(0,0,0,0.85),
                    0 0 0 1px rgba(15,23,42,0.9);
            }}
            .empty h2 {{
                font-size: 1.5rem;
                margin-bottom: 6px;
            }}
            .empty p {{
                font-size: 0.95rem;
                color: #cbd5f5;
            }}
            @media (max-width: 640px) {{
                h1 {{ font-size: 1.9rem; }}
                .top {{ flex-direction: column; align-items: flex-start; }}
            }}
        </style>
    </head>
    <body>
        <div class="bg-orbit"></div>
        <div class="container">
            <div class="top">
                <div>
                    <h1>Telegram Website Hosting</h1>
                    <p class="subtitle">
                        Upload ZIP or files via your Telegram bot – hosted instantly with 3D cards.
                    </p>
                </div>
                <div class="pill">
                    <span>Bot owner</span>
                    <strong>@{html.escape(OWNER_USERNAME)}</strong>
                </div>
            </div>
            <div class="grid">
                {cards_html}
            </div>
        </div>
    </body>
    </html>
    """

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


# ============= HELPERS =============

def make_saved_filename(name: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    return f"{ts}__{name.replace(' ','_')}"

def make_site_id() -> str:
    return f"site_{datetime.utcnow():%Y%m%d%H%M%S%f}"

def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📤 Upload File")],
            [KeyboardButton("/files"), KeyboardButton("/myfiles")],
            [KeyboardButton("/owner"), KeyboardButton("/start")],
        ],
        resize_keyboard=True
    )


# ============= TELEGRAM HANDLERS =============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "✨ *Website Hosting Bot*\n\n"
        "📤 नीचे वाला *Upload File* button दबाओ और कोई भी HTML / PHP / TXT / JS / CSS / CPP "
        "या फिर पूरा website ZIP *Document* की तरह भेजो.\n\n"
        "🧩 Features:\n"
        "• ZIP → auto unzip → site host → link\n"
        "• Single file host (HTML, code, etc.)\n"
        "• /files – सारे hosted items\n"
        "• /myfiles – सिर्फ आपकी uploads\n"
        "• /owner – owner panel (delete, control)\n"
    )
    await update.message.reply_markdown(text, reply_markup=main_keyboard())


async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "📤 Upload File":
        await update.message.reply_text(
            "📎 अब कोई file *Document* की तरह भेजो (ZIP या code file).",
            reply_markup=main_keyboard()
        )


async def handle_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    user = msg.from_user
    doc = msg.document

    if not doc:
        await msg.reply_text("⚠️ File को हमेशा *Document* की तरह भेजो (ZIP, HTML, PHP, TXT, आदि).")
        return

    name = doc.file_name or "uploaded"
    lower = name.lower()
    ext = lower.rsplit(".", 1)[-1] if "." in lower else ""

    # ---------- ZIP → WEBSITE ----------
    if ext == "zip":
        site_id = make_site_id()
        site_dir = UPLOAD_DIR / site_id
        site_dir.mkdir(parents=True, exist_ok=True)

        zip_path = site_dir / name.replace(" ", "_")
        file = await context.bot.get_file(doc.file_id)
        await file.download_to_drive(str(zip_path))

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
            "original_name": name,
            "saved_at": datetime.utcnow().isoformat(),
            "main_url": main_url,
        }

        kb = [[InlineKeyboardButton("🌐 Open Website", url=main_url)]]
        await msg.reply_text(
            f"✅ Website hosted successfully!\n\n🔗 {main_url}",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # ---------- NORMAL FILE HOST ----------
    saved_name = make_saved_filename(name)
    dest = UPLOAD_DIR / saved_name

    file = await context.bot.get_file(doc.file_id)
    await file.download_to_drive(str(dest))

    file_url = f"{BASE_URL}/files/{saved_name}"
    METADATA[saved_name] = {
        "type": "file",
        "uploader_id": user.id,
        "uploader_username": user.username or "",
        "original_name": name,
        "saved_at": datetime.utcnow().isoformat(),
    }

    kb = [[InlineKeyboardButton("📂 Open File", url=file_url)]]
    await msg.reply_text(
        f"✅ File hosted successfully!\n\n🔗 {file_url}",
        reply_markup=InlineKeyboardMarkup(kb)
    )


async def list_files_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not METADATA:
        await update.message.reply_text("📭 अभी कुछ भी host नहीं है.", reply_markup=main_keyboard())
        return

    kb = []
    for key, md in METADATA.items():
        if md["type"] == "site":
            label = f"🌐 {md['original_name']}"
            url = md["main_url"]
        else:
            label = f"📄 {md['original_name']}"
            url = f"{BASE_URL}/files/{key}"
        kb.append([InlineKeyboardButton(label, url=url)])

    if update.effective_user.id == OWNER_ID:
        kb.append([InlineKeyboardButton("⚙️ Owner Panel", callback_data="owner_manage")])

    await update.message.reply_text("📂 Hosted items:", reply_markup=InlineKeyboardMarkup(kb))


async def myfiles_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_items = [(k, m) for k, m in METADATA.items() if m["uploader_id"] == uid]

    if not user_items:
        await update.message.reply_text("🗃️ आपने अभी तक कुछ upload नहीं किया.", reply_markup=main_keyboard())
        return

    kb = []
    for key, md in user_items:
        if md["type"] == "site":
            label = f"🌐 {md['original_name']}"
            url = md["main_url"]
        else:
            label = f"📄 {md['original_name']}"
            url = f"{BASE_URL}/files/{key}"
        kb.append([InlineKeyboardButton(label, url=url)])

    await update.message.reply_text("📁 आपकी uploads:", reply_markup=InlineKeyboardMarkup(kb))


async def owner_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 ये सिर्फ owner के लिए है.", reply_markup=main_keyboard())
        return
    kb = [[InlineKeyboardButton("🗑 Delete / Manage", callback_data="owner_manage")]]
    await update.message.reply_text("⚙️ Owner Panel:", reply_markup=InlineKeyboardMarkup(kb))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    await q.answer()
    data = q.data

    if data == "owner_manage":
        if uid != OWNER_ID:
            await q.edit_message_text("Unauthorized.")
            return

        if not METADATA:
            await q.edit_message_text("❕ अभी कुछ भी host नहीं है.")
            return

        kb = []
        for key, md in METADATA.items():
            prefix = "🌐" if md["type"] == "site" else "📄"
            label = f"❌ {prefix} {md['original_name']}"
            kb.append([InlineKeyboardButton(label, callback_data=f"del::{key}")])

        await q.edit_message_text("Delete करने के लिए चुनो:", reply_markup=InlineKeyboardMarkup(kb))
        return

    if data.startswith("del::"):
        if uid != OWNER_ID:
            await q.edit_message_text("Unauthorized.")
            return

        key = data.split("::", 1)[1]
        md = METADATA.pop(key, None)
        if not md:
            await q.edit_message_text("Already deleted.")
            return

        path = UPLOAD_DIR / key
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        except Exception as e:
            await q.edit_message_text(f"Error deleting: {e}")
            return

        await q.edit_message_text(f"✅ Deleted {md['original_name']}")


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. /start भेजो.", reply_markup=main_keyboard())


# ============= MAIN =============

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info(f"Flask running on {WEB_HOST}:{WEB_PORT}")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("files", list_files_cmd))
    app.add_handler(CommandHandler("myfiles", myfiles_cmd))
    app.add_handler(CommandHandler("owner", owner_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_upload))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Bot polling started...")
    app.run_polling()


if __name__ == "__main__":
    main()
