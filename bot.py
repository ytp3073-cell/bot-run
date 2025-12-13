import os
import time
import zipfile
import logging
import threading
import shlex
import subprocess
from flask import Flask, send_from_directory, abort, Response, render_template_string
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =============== CONFIG ===============
BOT_TOKEN = "8419880200:AAG5OpgB0BG7FOpN-XrUu_7y3hGJKmWimI4"
SERVER_IP_OR_DOMAIN = "3.111.168.104"  # e.g. "13.232.215.220" or domain
HOST_PORT = 8080

BASE_URL = f"http://{SERVER_IP_OR_DOMAIN}:{HOST_PORT}"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITES_DIR = os.path.join(BASE_DIR, "sites")
os.makedirs(SITES_DIR, exist_ok=True)

# Docker resource limits (tweak as needed)
DOCKER_MEMORY = "256m"
DOCKER_CPUS = "0.5"
DOCKER_TIMEOUT = 25  # seconds max runtime for container

# Allowed executable extensions to attempt running inside sandbox
RUN_EXTS = {".py", ".sh"}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =============== FLASK ROUTES ===============

@app.route("/<site_id>/")
@app.route("/<site_id>/<path:path>")
def serve_site(site_id, path="index.html"):
    site_path = os.path.join(SITES_DIR, site_id)
    if not os.path.isdir(site_path):
        abort(404)
    if not path:
        path = "index.html"
    return send_from_directory(site_path, path)


# Terminal view: simple auto-refresh HTML that shows locks.txt tail
TERMINAL_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta http-equiv="refresh" content="2">
  <title>Terminal - {{site_id}}</title>
  <style>
    body { background:#0b0b0b; color:#e6e6e6; font-family: monospace; padding:10px; }
    pre { white-space: pre-wrap; word-wrap:break-word; }
    .timestamp { color:#9aa; font-size:0.9em; }
  </style>
</head>
<body>
  <div class="timestamp">Site: {{site_id}} — Last updated: {{ts}}</div>
  <pre>{{content}}</pre>
</body>
</html>
"""

@app.route("/terminal/<site_id>")
def terminal(site_id):
    site_path = os.path.join(SITES_DIR, site_id)
    if not os.path.isdir(site_path):
        abort(404)
    lock_path = os.path.join(site_path, "locks.txt")
    if not os.path.exists(lock_path):
        content = "(no logs yet)"
    else:
        with open(lock_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    return render_template_string(
        TERMINAL_HTML,
        site_id=site_id,
        ts=time.strftime("%Y-%m-%d %H:%M:%S"),
        content=content
    )

# =============== HELPERS ===============

def append_lock(site_path: str, text: str):
    lock_path = os.path.join(site_path, "locks.txt")
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(lock_path, "a", encoding="utf-8", errors="replace") as f:
        f.write(f"[{ts}] {text}\n")
    logger.info(f"Appended to {lock_path}: {text}")

def is_docker_available():
    try:
        subprocess.run(["docker", "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception:
        return False

def run_in_docker(site_path: str, filename: str, site_id: str):
    """
    Run given filename from site_path inside a docker python image (or bash for .sh).
    Writes stdout/stderr into locks.txt. Enforces --network none and resource limits.
    Returns True if execution started (not necessarily success).
    """
    filepath_in_container = f"/site/{filename}"
    lock_path = os.path.join(site_path, "locks.txt")
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".py":
        image_cmd = ["python", filepath_in_container]
        image = "python:3.11-slim"
    elif ext == ".sh":
        image_cmd = ["bash", filepath_in_container]
        image = "bash:5"  # fallback; if not available, use debian and bash -c
    else:
        append_lock(site_path, f"Not an executable extension for sandboxed run: {filename}")
        return False

    # Build docker run command
    docker_cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--memory", DOCKER_MEMORY,
        "--cpus", DOCKER_CPUS,
        "-v", f"{site_path}:/site:ro",  # read-only bind inside container
        "--workdir", "/site",
        image
    ] + image_cmd

    append_lock(site_path, f"STARTING: docker run for {filename} (site: {site_id})")
    logger.info("Running docker command: %s", " ".join(shlex.quote(p) for p in docker_cmd))

    try:
        # Launch container and capture output with timeout
        proc = subprocess.run(docker_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=DOCKER_TIMEOUT)
        out = proc.stdout.decode("utf-8", errors="replace")
        append_lock(site_path, f"EXIT_CODE: {proc.returncode}")
        for line in out.splitlines():
            append_lock(site_path, line)
        append_lock(site_path, "FINISHED")
    except subprocess.TimeoutExpired:
        append_lock(site_path, f"TIMEOUT: exceeded {DOCKER_TIMEOUT}s; container killed.")
    except Exception as e:
        append_lock(site_path, f"ERROR running docker: {e}")
        logger.exception("Docker run error")
    return True

def run_direct(site_path: str, filename: str, site_id: str):
    """
    Fallback direct execution WITHOUT docker. This is dangerous; we avoid doing this.
    Here we only log refusal.
    """
    append_lock(site_path, "Refusing to run directly on host because Docker is not available. Enable Docker.")
    return False

def start_runner_thread(site_path: str, filename: str, site_id: str):
    def target():
        if is_docker_available():
            run_in_docker(site_path, filename, site_id)
        else:
            run_direct(site_path, filename, site_id)
    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t

# =============== TELEGRAM HANDLERS ===============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Web Host + Python Runner (Docker sandbox required)\n\n"
        "• Kisi bhi file ko bhejo. Agar file .py hai to main Docker me run karunga (resource-limited).\n"
        "• Har site folder me 'locks.txt' hoga jahan stdout/stderr aur errors append honge.\n"
        "• Terminal view: {base}/terminal/<site_id>\n\n"
        "Use /mysites to list your sites."
    ).format(base=BASE_URL)
    await update.message.reply_text(text)

async def mysites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id_str = str(user.id)
    all_dirs = [
        d for d in os.listdir(SITES_DIR)
        if os.path.isdir(os.path.join(SITES_DIR, d)) and d.startswith(user_id_str + "_")
    ]
    if not all_dirs:
        await update.message.reply_text("Tumne koi site host nahi ki ab tak.")
        return
    lines = []
    for d in sorted(all_dirs):
        url = f"{BASE_URL}/{d}/"
        term = f"{BASE_URL}/terminal/{d}"
        lines.append(f"- {url}\n  terminal: {term}")
    await update.message.reply_text("Tumhari hosted sites:\n\n" + "\n".join(lines))

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        return
    doc = update.message.document
    user = update.effective_user
    user_id = user.id

    file_name = (doc.file_name or "uploaded_file").replace(" ", "_")
    file_size = doc.file_size or 0
    max_size = 100 * 1024 * 1024  # 100MB limit
    if file_size > max_size:
        await update.message.reply_text("❌ File bahut badi hai. Max 100 MB.")
        return

    await update.message.reply_text("⏳ File mil gayi, save kar raha hoon...")

    try:
        tg_file = await doc.get_file()
        site_id = f"{user_id}_{int(time.time())}"
        site_path = os.path.join(SITES_DIR, site_id)
        os.makedirs(site_path, exist_ok=True)

        save_path = os.path.join(site_path, file_name)
        await tg_file.download_to_drive(save_path)

        # If zip, extract
        if file_name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(save_path, "r") as z:
                    z.extractall(site_path)
                os.remove(save_path)
            except Exception as e:
                append_lock(site_path, f"ZIP extract error: {e}")
                await update.message.reply_text(f"ZIP extract error: {e}")
                return

        # Find candidate to run: prefer main.py, index.py, first .py in root
        candidate = None
        for p in ["main.py", "index.py", "app.py"]:
            if os.path.exists(os.path.join(site_path, p)):
                candidate = p
                break
        if not candidate:
            # pick first .py or .sh in root
            for f in os.listdir(site_path):
                if os.path.isfile(os.path.join(site_path, f)) and os.path.splitext(f)[1].lower() in RUN_EXTS:
                    candidate = f
                    break

        # Always create or touch locks.txt
        append_lock(site_path, f"Uploaded file: {file_name}")

        url = f"{BASE_URL}/{site_id}/"
        term = f"{BASE_URL}/terminal/{site_id}"

        if candidate:
            append_lock(site_path, f"Execution candidate found: {candidate}")
            start_runner_thread(site_path, candidate, site_id)
            await update.message.reply_text(
                "✅ File upload ho gayi.\n"
                f"Site URL: {url}\n"
                f"Terminal/logs: {term}\n\n"
                f"Note: Candidate to run: {candidate} — running inside Docker (if available)."
            )
        else:
            await update.message.reply_text(
                "✅ File upload ho gayi (no auto-executable found).\n"
                f"Site URL: {url}\n"
                f"Terminal/logs: {term}\n\n"
                "Agar tum chaho ki koi script auto-run ho to uska naam main.py / index.py honi chahiye ya root me .py/.sh hona chahiye."
            )
    except Exception as e:
        logger.exception("Error in handle_document")
        await update.message.reply_text(f"❌ Error while handling file: {e}")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Command samajh nahi aaya. /start try karo.")

async def main():
    if BOT_TOKEN == "YAHAN_APNA_BOT_TOKEN_DALO":
        raise RuntimeError("BOT_TOKEN set karo bot.py me.")
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=HOST_PORT), daemon=True)
    flask_thread.start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("mysites", mysites))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
