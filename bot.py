
import os
import re
import asyncio
import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

TOKEN = os.getenv("BOT_TOKEN")
MAX_SIZE = 45 * 1024 * 1024  # 45 MB
MAX_DURATION = 15 * 60       # 15 minutes

ALLOWED_SCHEMES = {"http", "https"}


def valid_url(text):
    try:
        parsed = urlparse(text.strip())
        return (
            parsed.scheme in ALLOWED_SCHEMES
            and bool(parsed.hostname)
            and "." in parsed.hostname
            and not any(c.isspace() for c in text)
        )
    except Exception:
        return False


def download_video(url, folder):
    output = str(Path(folder) / "video.%(ext)s")

    options = {
        "outtmpl": output,
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
        "max_filesize": MAX_SIZE,
        "socket_timeout": 25,
        "retries": 2,
        "fragment_retries": 2,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

        if info.get("is_live"):
            raise ValueError("پخش زنده پشتیبانی نمی‌شود.")

        duration = info.get("duration")
        if duration and duration > MAX_DURATION:
            raise ValueError("مدت ویدیو بیشتر از ۱۵ دقیقه است.")

        size = info.get("filesize") or info.get("filesize_approx")
        if size and size > MAX_SIZE:
            raise ValueError("حجم ویدیو از حد مجاز بیشتر است.")

        ydl.download([url])

    files = [
        p for p in Path(folder).iterdir()
        if p.is_file() and p.name.startswith("video.")
    ]
    if not files:
        raise ValueError("فایل دانلودشده پیدا نشد.")

    file_path = max(files, key=lambda p: p.stat().st_size)

    if file_path.stat().st_size > MAX_SIZE:
        raise ValueError("حجم فایل بیشتر از حد مجاز است.")

    return str(file_path), info.get("title", "Video")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! 🎬 به ربات دانلود ویدیو خوش آمدی.\n\n"
        "لینک مستقیم یا لینک عمومی ویدیو را بفرست.\n"
        "حداکثر مدت: ۱۵ دقیقه\n"
        "حداکثر حجم فایل: ۴۵ مگابایت\n\n"
        "فقط محتوایی را دانلود کن که اجازهٔ دریافت آن را داری."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "راهنما:\n"
        "۱. لینک ویدیو را ارسال کن.\n"
        "۲. منتظر بمان تا دانلود انجام شود.\n"
        "۳. فایل در همین گفت‌وگو ارسال می‌شود.\n\n"
        "لینک‌های خصوصی یا محافظت‌شده ممکن است کار نکنند."
    )


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    url = message.text.strip()

    if len(url) > 2048 or not valid_url(url):
        await message.reply_text("لطفاً یک لینک معتبر http یا https بفرست.")
        return

    status = await message.reply_text(
        "⏳ لینک دریافت شد؛ در حال بررسی و دانلود..."
    )

    try:
        with tempfile.TemporaryDirectory(prefix="tgvideo_") as folder:
            path, title = await asyncio.to_thread(
                download_video, url, folder
            )

            await status.edit_text("📤 دانلود انجام شد؛ در حال ارسال فایل...")

            with open(path, "rb") as video:
                await message.reply_document(
                    document=video,
                    filename=Path(path).name,
                    caption=title[:900],
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                    pool_timeout=30,
                )

        await status.delete()

    except yt_dlp.utils.DownloadError:
        await status.edit_text(
            "❌ دانلود ناموفق بود. ممکن است سایت پشتیبانی نشود، "
            "لینک خصوصی باشد یا دسترسی محدود شده باشد."
        )
    except ValueError as exc:
        await status.edit_text(f"⚠️ {exc}")
    except Exception:
        logging.exception("Video processing failed")
        try:
            await status.edit_text(
                "❌ خطایی رخ داد. لطفاً لینک دیگری امتحان کن."
            )
        except Exception:
            pass


def main():
    if not TOKEN:
        raise RuntimeError(
            "متغیر محیطی BOT_TOKEN تنظیم نشده است."
        )

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)
    )

    logging.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
