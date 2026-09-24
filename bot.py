"""
Bot Telegram Video Downloader — Tanpa Watermark
Mendukung: TikTok, Douyin, RedNote, Instagram, YouTube, Facebook

Cara pakai:
1. Isi BOT_TOKEN di file .env
2. pip install -r requirements.txt
3. python bot.py
"""
import os
import logging
import json
from datetime import datetime

from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode, ChatAction

from config import (
    BOT_TOKEN,
    ADMIN_ID,
    MAX_FILE_SIZE_MB,
    SUPPORTED_PLATFORMS,
    WELCOME_MESSAGE,
    PROCESSING_MESSAGE,
    SUCCESS_MESSAGE,
    ERROR_MESSAGE,
    UNSUPPORTED_MESSAGE,
    HELP_MESSAGE,
)
from downloader import (
    download_video,
    detect_platform,
    extract_urls,
    format_duration,
    format_file_size,
    cleanup_file,
)

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Statistik Sederhana ──────────────────────────────────
STATS_FILE = os.path.join(os.path.dirname(__file__), "stats.json")


def load_stats() -> dict:
    """Muat statistik dari file."""
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "total_downloads": 0,
        "total_users": [],
        "per_platform": {},
        "errors": 0,
        "start_date": datetime.now().isoformat(),
    }


def save_stats(stats: dict):
    """Simpan statistik ke file."""
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=2)
    except Exception as e:
        logger.warning(f"Gagal menyimpan statistik: {e}")


def update_stats(user_id: int, platform: str, success: bool):
    """Update statistik download."""
    stats = load_stats()
    if success:
        stats["total_downloads"] += 1
        stats["per_platform"][platform] = stats["per_platform"].get(platform, 0) + 1
    else:
        stats["errors"] += 1
    if user_id not in stats["total_users"]:
        stats["total_users"].append(user_id)
    save_stats(stats)


# ── Command Handlers ─────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start."""
    keyboard = [
        [
            InlineKeyboardButton("📖 Bantuan", callback_data="help"),
            InlineKeyboardButton("📊 Platform", callback_data="platforms"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        WELCOME_MESSAGE,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /help."""
    await update.message.reply_text(
        HELP_MESSAGE.format(max_size=MAX_FILE_SIZE_MB),
        parse_mode=ParseMode.HTML,
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /stats (admin only)."""
    user_id = update.effective_user.id

    if ADMIN_ID and user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Hanya admin yang bisa melihat statistik.")
        return

    stats = load_stats()
    platform_stats = "\n".join(
        f"  {SUPPORTED_PLATFORMS.get(p, {}).get('emoji', '•')} {p}: {count}"
        for p, count in sorted(
            stats.get("per_platform", {}).items(),
            key=lambda x: x[1],
            reverse=True,
        )
    ) or "  Belum ada data"

    text = f"""
📊 <b>Statistik Bot</b>

📅 <b>Aktif sejak:</b> {stats.get('start_date', 'N/A')[:10]}
📥 <b>Total Download:</b> {stats.get('total_downloads', 0)}
👥 <b>Total User:</b> {len(stats.get('total_users', []))}
❌ <b>Total Error:</b> {stats.get('errors', 0)}

📋 <b>Per Platform:</b>
{platform_stats}
"""
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ── Callback Query Handler ───────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk inline keyboard callbacks."""
    query = update.callback_query
    await query.answer()

    if query.data == "help":
        await query.edit_message_text(
            HELP_MESSAGE.format(max_size=MAX_FILE_SIZE_MB),
            parse_mode=ParseMode.HTML,
        )
    elif query.data == "platforms":
        platform_text = "🌐 <b>Platform yang Didukung:</b>\n\n"
        for key, info in SUPPORTED_PLATFORMS.items():
            domains = ", ".join(info["domains"][:2])
            platform_text += f"{info['emoji']} <b>{info['name']}</b>\n   └ {domains}\n\n"
        platform_text += "📌 Kirim link video dari platform di atas!"

        keyboard = [[InlineKeyboardButton("⬅️ Kembali", callback_data="back_start")]]
        await query.edit_message_text(
            platform_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    elif query.data == "back_start":
        keyboard = [
            [
                InlineKeyboardButton("📖 Bantuan", callback_data="help"),
                InlineKeyboardButton("📊 Platform", callback_data="platforms"),
            ]
        ]
        await query.edit_message_text(
            WELCOME_MESSAGE,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


# ── URL / Message Handler ───────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler utama — mendeteksi URL dalam pesan dan mendownload video.
    """
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    urls = extract_urls(text)

    if not urls:
        # Bukan URL, abaikan atau beri pesan ringan
        return

    user = update.effective_user
    chat_id = update.effective_chat.id

    for url in urls[:3]:  # Batasi 3 URL per pesan
        platform = detect_platform(url)

        if platform is None:
            await update.message.reply_text(
                UNSUPPORTED_MESSAGE,
                parse_mode=ParseMode.HTML,
            )
            continue

        platform_info = SUPPORTED_PLATFORMS[platform]

        # Kirim pesan "sedang memproses"
        processing_msg = await update.message.reply_text(
            PROCESSING_MESSAGE.format(
                emoji=platform_info["emoji"],
                platform=platform_info["name"],
            ),
            parse_mode=ParseMode.HTML,
        )

        # Kirim typing action
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        try:
            # Download video
            result = await download_video(url, platform)

            if result.success and result.file_path:
                # Kirim upload action
                await context.bot.send_chat_action(
                    chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO
                )

                # Edit pesan processing
                await processing_msg.edit_text(
                    "📤 <b>Mengirim video...</b>",
                    parse_mode=ParseMode.HTML,
                )

                # Kirim video
                caption = (
                    f"{platform_info['emoji']} <b>{platform_info['name']}</b>\n"
                    f"📹 {result.title}\n"
                    f"⏱ {format_duration(result.duration)} • "
                    f"📏 {format_file_size(result.file_size)}"
                )

                with open(result.file_path, "rb") as video_file:
                    try:
                        await context.bot.send_video(
                            chat_id=chat_id,
                            video=InputFile(video_file),
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            supports_streaming=True,
                            read_timeout=120,
                            write_timeout=120,
                        )
                    except Exception:
                        # Jika gagal kirim sebagai video, coba sebagai document
                        video_file.seek(0)
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=InputFile(video_file),
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                            read_timeout=120,
                            write_timeout=120,
                        )

                # Hapus pesan processing
                await processing_msg.delete()

                # Cleanup file
                cleanup_file(result.file_path)

                # Update stats
                update_stats(user.id, platform, True)
                logger.info(
                    f"✅ Download berhasil: {platform} oleh user {user.id} "
                    f"({user.first_name})"
                )

            else:
                # Download gagal
                error_text = result.error or "Unknown error"
                await processing_msg.edit_text(
                    ERROR_MESSAGE.format(error=error_text),
                    parse_mode=ParseMode.HTML,
                )
                update_stats(user.id, platform, False)
                logger.warning(
                    f"❌ Download gagal: {platform} - {error_text}"
                )

        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            await processing_msg.edit_text(
                ERROR_MESSAGE.format(error=f"Error: {str(e)[:150]}"),
                parse_mode=ParseMode.HTML,
            )
            update_stats(user.id, platform, False)


# ── Error Handler ────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk error global."""
    logger.error(f"Exception while handling an update: {context.error}", exc_info=True)


# ── Main ─────────────────────────────────────────────────

def main():
    """Jalankan bot."""
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        print("=" * 50)
        print("❌ ERROR: BOT_TOKEN belum di-set!")
        print()
        print("Langkah-langkah:")
        print("1. Buka @BotFather di Telegram")
        print("2. Kirim /newbot dan ikuti instruksi")
        print("3. Salin token yang diberikan")
        print("4. Buat file .env dan isi:")
        print("   BOT_TOKEN=token_kamu_disini")
        print()
        print("Atau salin .env.example ke .env lalu edit.")
        print("=" * 50)
        return

    print("=" * 50)
    print("🎬 Video Downloader Bot — Starting...")
    print(f"📊 Admin ID: {ADMIN_ID or 'Not set'}")
    print(f"📏 Max file size: {MAX_FILE_SIZE_MB}MB")
    print("=" * 50)

    # Buat application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(60)
        .write_timeout(120)
        .build()
    )

    # Register handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("stats", cmd_stats))
    application.add_handler(CallbackQueryHandler(callback_handler))

    # Handler untuk pesan berisi URL
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    # Error handler
    application.add_error_handler(error_handler)

    # Start polling
    print("🚀 Bot is running! Press Ctrl+C to stop.")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
