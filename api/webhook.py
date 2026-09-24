"""
Bot Telegram Video Downloader HD — Vercel Serverless (Webhook Mode)
Mendukung: TikTok, Douyin, RedNote, Instagram, YouTube, Facebook

Strategi HD untuk Vercel:
─────────────────────────
1. FAST MODE (utama): Ekstrak direct URL video HD via yt-dlp,
   lalu kirim URL ke Telegram → Telegram server yang download sendiri.
   Sangat cepat karena Vercel hanya perlu ekstrak info (~2-5 detik).

2. FALLBACK MODE: Jika URL-based gagal, download file ke /tmp
   lalu upload ke Telegram. Lebih lambat tapi lebih reliable.

Deploy ke Vercel:
1. Push ke GitHub
2. Connect repo di vercel.com
3. Set environment variable BOT_TOKEN
4. Deploy & set webhook via /api/set_webhook
"""
import os
import re
import time
import logging
import tempfile
from urllib.parse import urlparse

import telebot
import yt_dlp
import requests
from flask import Flask, request, jsonify

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# Batas ukuran file Telegram Bot API (50MB)
TELEGRAM_FILE_LIMIT = 49 * 1024 * 1024

# ── Platform yang Didukung ────────────────────────────────
PLATFORMS = {
    "tiktok": {
        "name": "TikTok",
        "emoji": "🎵",
        "domains": [
            "tiktok.com", "vm.tiktok.com", "vt.tiktok.com",
        ],
    },
    "douyin": {
        "name": "Douyin",
        "emoji": "🎶",
        "domains": [
            "douyin.com", "v.douyin.com", "iesdouyin.com",
        ],
    },
    "rednote": {
        "name": "RedNote (小红书)",
        "emoji": "📕",
        "domains": [
            "xiaohongshu.com", "xhslink.com", "xhs.link",
        ],
    },
    "instagram": {
        "name": "Instagram",
        "emoji": "📸",
        "domains": [
            "instagram.com", "instagr.am",
        ],
    },
    "youtube": {
        "name": "YouTube",
        "emoji": "▶️",
        "domains": [
            "youtube.com", "youtu.be", "youtube-nocookie.com",
            "m.youtube.com",
        ],
    },
    "facebook": {
        "name": "Facebook",
        "emoji": "📘",
        "domains": [
            "facebook.com", "fb.watch", "fb.com", "m.facebook.com",
        ],
    },
}


# ── Format HD per Platform ────────────────────────────────
# Konfigurasi format yt-dlp yang dioptimalkan untuk kualitas HD

FORMAT_OPTIONS = {
    "tiktok": {
        # TikTok: ambil kualitas terbaik (biasanya 1080p tanpa watermark)
        "format": "best",
    },
    "douyin": {
        "format": "best",
    },
    "rednote": {
        "format": "best",
    },
    "instagram": {
        # Instagram: kualitas terbaik (biasanya 1080p)
        "format": "best",
    },
    "youtube": {
        # YouTube: prioritas single-file MP4 HD agar tidak perlu FFmpeg merge
        # Urutan: 1080p mp4 → 720p mp4 → best mp4 → best apapun
        "format": (
            "best[height<=1080][ext=mp4]/"
            "best[height<=720][ext=mp4]/"
            "best[ext=mp4]/"
            "best"
        ),
    },
    "facebook": {
        "format": "best",
    },
}


# ── Utilitas ──────────────────────────────────────────────

def detect_platform(url: str):
    """Deteksi platform dari URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        for key, info in PLATFORMS.items():
            for d in info["domains"]:
                if domain == d or domain.endswith("." + d):
                    return key
    except Exception:
        pass
    return None


def extract_urls(text: str) -> list:
    """Ekstrak URL dari teks."""
    pattern = re.compile(
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\-.~:/?#\[\]@!$&\'()*+,;=%]*'
    )
    return pattern.findall(text)


def format_duration(seconds):
    """Format durasi ke HH:MM:SS."""
    if not seconds or seconds <= 0:
        return "N/A"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_size(size_bytes):
    """Format ukuran file."""
    if not size_bytes or size_bytes <= 0:
        return "N/A"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def get_resolution_label(height):
    """Dapatkan label resolusi dari tinggi video."""
    if not height:
        return ""
    if height >= 2160:
        return "4K"
    elif height >= 1440:
        return "2K"
    elif height >= 1080:
        return "1080p HD"
    elif height >= 720:
        return "720p HD"
    elif height >= 480:
        return "480p"
    elif height >= 360:
        return "360p"
    return f"{height}p"


# ── Core: Ekstrak Info & Direct URL ──────────────────────

def extract_video_info(url: str, platform: str):
    """
    Ekstrak informasi video dan direct URL menggunakan yt-dlp.
    TIDAK mendownload file — hanya ambil metadata & URL langsung.
    Ini sangat cepat (~2-5 detik).
    """
    fmt = FORMAT_OPTIONS.get(platform, {"format": "best"})

    ydl_opts = {
        "format": fmt["format"],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 15,
        "retries": 2,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info is None:
                return {"success": False, "error": "Tidak bisa mengekstrak info video."}

            title = info.get("title", "Untitled")
            duration = info.get("duration", 0) or 0
            thumbnail = info.get("thumbnail")
            uploader = info.get("uploader", "")

            # Dapatkan direct URL video
            direct_url = info.get("url")
            height = info.get("height", 0) or 0
            width = info.get("width", 0) or 0
            filesize = info.get("filesize") or info.get("filesize_approx") or 0
            ext = info.get("ext", "mp4")

            # Jika tidak ada direct URL di top-level, cari di requested_formats
            if not direct_url and info.get("requested_formats"):
                # Ambil format video pertama
                for fmt_info in info["requested_formats"]:
                    if fmt_info.get("vcodec", "none") != "none":
                        direct_url = fmt_info.get("url")
                        height = fmt_info.get("height", height)
                        width = fmt_info.get("width", width)
                        filesize = fmt_info.get("filesize") or filesize
                        ext = fmt_info.get("ext", ext)
                        break

            # Jika masih tidak ada, cari di formats list
            if not direct_url and info.get("formats"):
                # Cari format terbaik dengan video
                best_format = None
                for fmt_info in reversed(info["formats"]):
                    fmt_url = fmt_info.get("url")
                    if fmt_url and fmt_info.get("vcodec", "none") != "none":
                        # Preferensi: mp4, height tinggi
                        if best_format is None:
                            best_format = fmt_info
                        elif (fmt_info.get("height", 0) or 0) > (best_format.get("height", 0) or 0):
                            best_format = fmt_info
                if best_format:
                    direct_url = best_format.get("url")
                    height = best_format.get("height", height)
                    width = best_format.get("width", width)
                    filesize = best_format.get("filesize") or filesize
                    ext = best_format.get("ext", ext)

            resolution = get_resolution_label(height)

            return {
                "success": True,
                "title": title[:100],
                "duration": duration,
                "thumbnail": thumbnail,
                "uploader": uploader[:50] if uploader else "",
                "direct_url": direct_url,
                "height": height,
                "width": width,
                "resolution": resolution,
                "filesize": filesize,
                "ext": ext,
                "original_url": url,
            }

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        if "private" in error_msg.lower():
            error_msg = "Video bersifat private."
        elif "unavailable" in error_msg.lower():
            error_msg = "Video tidak tersedia / sudah dihapus."
        elif "login" in error_msg.lower():
            error_msg = "Video memerlukan login."
        elif "geo" in error_msg.lower():
            error_msg = "Video tidak tersedia di region ini."
        else:
            error_msg = error_msg[:200]
        return {"success": False, "error": error_msg}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


# ── Fallback: Download File ke /tmp ──────────────────────

def download_to_file(url: str, platform: str):
    """
    Fallback: download video ke file temporary.
    Digunakan jika kirim via URL gagal.
    """
    tmp_dir = tempfile.mkdtemp()
    timestamp = int(time.time() * 1000)
    output_path = os.path.join(tmp_dir, f"{platform}_{timestamp}.%(ext)s")

    fmt = FORMAT_OPTIONS.get(platform, {"format": "best"})

    ydl_opts = {
        "outtmpl": output_path,
        "format": fmt["format"],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 2,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        },
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            if info is None:
                return {"success": False, "error": "Download gagal."}

            # Cari file yang didownload
            downloaded = None
            for f in os.listdir(tmp_dir):
                fp = os.path.join(tmp_dir, f)
                if os.path.isfile(fp) and os.path.getsize(fp) > 0:
                    downloaded = fp
                    break

            if not downloaded:
                return {"success": False, "error": "File tidak ditemukan."}

            file_size = os.path.getsize(downloaded)
            if file_size > TELEGRAM_FILE_LIMIT:
                os.remove(downloaded)
                return {
                    "success": False,
                    "error": f"File terlalu besar ({format_size(file_size)}). Batas: 50MB.",
                }

            return {
                "success": True,
                "file_path": downloaded,
                "title": (info.get("title") or "Video")[:80],
                "duration": info.get("duration", 0) or 0,
                "file_size": file_size,
                "height": info.get("height", 0) or 0,
            }

    except Exception as e:
        return {"success": False, "error": str(e)[:150]}


def cleanup_file(path):
    """Hapus file & parent dir temporary."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
            parent = os.path.dirname(path)
            if parent and os.path.isdir(parent):
                os.rmdir(parent)
    except Exception:
        pass


# ── Kirim Video ke User ─────────────────────────────────

def send_video_to_user(chat_id, video_info, platform_info):
    """
    Kirim video ke user dengan strategi 2 tahap:
    1. Coba kirim via direct URL (cepat, HD)
    2. Fallback: download & upload file
    """
    title = video_info.get("title", "Video")
    duration = video_info.get("duration", 0)
    resolution = video_info.get("resolution", "")
    direct_url = video_info.get("direct_url")
    thumbnail = video_info.get("thumbnail")
    filesize = video_info.get("filesize", 0)
    uploader = video_info.get("uploader", "")

    # Bangun caption
    res_text = f" • 🎞 {resolution}" if resolution else ""
    size_text = f" • 📏 {format_size(filesize)}" if filesize else ""
    uploader_text = f"\n👤 {uploader}" if uploader else ""
    caption = (
        f"{platform_info['emoji']} <b>{platform_info['name']}</b>\n"
        f"📹 {title}{uploader_text}\n"
        f"⏱ {format_duration(duration)}{res_text}{size_text}"
    )

    # ━━━━━━ TAHAP 1: Kirim via Direct URL (cepat!) ━━━━━━
    if direct_url:
        try:
            logger.info(f"Trying URL-based send: {resolution}")
            bot.send_video(
                chat_id,
                video=direct_url,
                caption=caption,
                parse_mode="HTML",
                supports_streaming=True,
                timeout=55,
            )
            logger.info("✅ URL-based send success!")
            return True
        except Exception as e:
            logger.warning(f"URL-based send failed: {e}")
            # Lanjut ke fallback

    # ━━━━━━ TAHAP 2: Fallback — Download & Upload ━━━━━━
    try:
        logger.info("Trying fallback: download to file...")
        result = download_to_file(
            video_info["original_url"],
            detect_platform(video_info["original_url"]) or "unknown",
        )

        if result["success"] and result.get("file_path"):
            height = result.get("height", 0)
            res_label = get_resolution_label(height) if height else resolution
            file_size = result.get("file_size", 0)

            caption_fb = (
                f"{platform_info['emoji']} <b>{platform_info['name']}</b>\n"
                f"📹 {result.get('title', title)}\n"
                f"⏱ {format_duration(result.get('duration', duration))}"
                f" • 🎞 {res_label}"
                f" • 📏 {format_size(file_size)}"
            )

            with open(result["file_path"], "rb") as video_file:
                try:
                    bot.send_video(
                        chat_id,
                        video_file,
                        caption=caption_fb,
                        parse_mode="HTML",
                        supports_streaming=True,
                        timeout=55,
                    )
                except Exception:
                    video_file.seek(0)
                    bot.send_document(
                        chat_id,
                        video_file,
                        caption=caption_fb,
                        parse_mode="HTML",
                        timeout=55,
                    )

            cleanup_file(result["file_path"])
            logger.info("✅ Fallback download+upload success!")
            return True
        else:
            error = result.get("error", "Download gagal")
            logger.warning(f"Fallback failed: {error}")
            bot.send_message(
                chat_id,
                f"❌ <b>Download Gagal</b>\n\n<code>{error}</code>\n\n"
                f"💡 Pastikan link valid dan video tidak private.",
                parse_mode="HTML",
            )
            return False

    except Exception as e:
        logger.error(f"Fallback error: {e}", exc_info=True)
        bot.send_message(
            chat_id,
            f"❌ <b>Error:</b> <code>{str(e)[:120]}</code>",
            parse_mode="HTML",
        )
        return False


# ── Pesan Bot ─────────────────────────────────────────────

WELCOME_MSG = """
🎬 <b>Video Downloader Bot HD</b> — <i>Tanpa Watermark!</i>

Kirim link video dari platform berikut dan saya akan mendownloadnya dalam <b>kualitas HD</b> 🔥

🎵 <b>TikTok</b> — Video HD tanpa watermark
🎶 <b>Douyin</b> — Video HD tanpa watermark
📕 <b>RedNote (小红书)</b> — Video & gambar HD
📸 <b>Instagram</b> — Reels & Post HD
▶️ <b>YouTube</b> — Video & Shorts HD (1080p)
📘 <b>Facebook</b> — Video & Reels HD

━━━━━━━━━━━━━━━━━━━━━━
📌 <b>Cara Pakai:</b> Cukup kirim/paste link video!
⚡ Proses otomatis, kualitas HD, tanpa watermark.
━━━━━━━━━━━━━━━━━━━━━━
"""

HELP_MSG = """
📖 <b>Bantuan Video Downloader Bot HD</b>

<b>Cara Menggunakan:</b>
1️⃣ Salin link video dari aplikasi/browser
2️⃣ Paste link tersebut di chat ini
3️⃣ Tunggu bot memproses dan mengirim video HD

<b>Command:</b>
/start — Mulai bot
/help — Bantuan ini
/quality — Info kualitas per platform

<b>🎞 Kualitas Download:</b>
• TikTok / Douyin — Full HD (1080p)
• Instagram — Full HD (1080p)
• YouTube — HD (720p-1080p, single file)
• Facebook — HD (tergantung upload asli)
• RedNote — Best quality available

<b>⚠️ Catatan:</b>
• Max ukuran file: 50MB (batas Telegram)
• Video private tidak bisa didownload
• Jika HD gagal, otomatis fallback ke SD
"""

QUALITY_MSG = """
🎞 <b>Info Kualitas Download per Platform</b>

🎵 <b>TikTok</b>
└ Resolusi: <b>1080p Full HD</b> (tanpa watermark)
└ Format: MP4

🎶 <b>Douyin</b>
└ Resolusi: <b>1080p Full HD</b> (tanpa watermark)
└ Format: MP4

📕 <b>RedNote (小红书)</b>
└ Resolusi: <b>Best available</b>
└ Format: MP4

📸 <b>Instagram</b>
└ Resolusi: <b>1080p Full HD</b>
└ Format: MP4

▶️ <b>YouTube</b>
└ Resolusi: <b>720p-1080p HD</b> (single file MP4)
└ Format: MP4 (tanpa perlu FFmpeg merge)

📘 <b>Facebook</b>
└ Resolusi: <b>HD</b> (tergantung upload asli)
└ Format: MP4

━━━━━━━━━━━━━━━━━━━━━━
💡 Bot akan selalu mencoba kualitas tertinggi yang tersedia.
Jika gagal, otomatis turun ke kualitas lebih rendah.
"""


# ── Telegram Handlers ─────────────────────────────────────

@bot.message_handler(commands=["start"])
def handle_start(message):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        telebot.types.InlineKeyboardButton("📖 Bantuan", callback_data="help"),
        telebot.types.InlineKeyboardButton("🎞 Kualitas", callback_data="quality"),
    )
    bot.send_message(
        message.chat.id,
        WELCOME_MSG,
        parse_mode="HTML",
        reply_markup=markup,
    )


@bot.message_handler(commands=["help"])
def handle_help(message):
    bot.send_message(message.chat.id, HELP_MSG, parse_mode="HTML")


@bot.message_handler(commands=["quality"])
def handle_quality(message):
    bot.send_message(message.chat.id, QUALITY_MSG, parse_mode="HTML")


# Callback untuk inline keyboard
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        bot.answer_callback_query(call.id)
        if call.data == "help":
            bot.edit_message_text(
                HELP_MSG,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML",
            )
        elif call.data == "quality":
            bot.edit_message_text(
                QUALITY_MSG,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML",
            )
        elif call.data == "back_start":
            markup = telebot.types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                telebot.types.InlineKeyboardButton("📖 Bantuan", callback_data="help"),
                telebot.types.InlineKeyboardButton("🎞 Kualitas", callback_data="quality"),
            )
            bot.edit_message_text(
                WELCOME_MSG,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML",
                reply_markup=markup,
            )
    except Exception as e:
        logger.warning(f"Callback error: {e}")


# ── Handler Utama: URL ───────────────────────────────────

@bot.message_handler(func=lambda m: m.text and extract_urls(m.text or ""))
def handle_url(message):
    """Handler utama — mendeteksi URL dan download video HD."""
    urls = extract_urls(message.text)
    chat_id = message.chat.id

    for url in urls[:2]:  # Maks 2 URL per pesan
        platform = detect_platform(url)

        if platform is None:
            bot.send_message(
                chat_id,
                "⚠️ <b>Platform tidak didukung.</b>\n\n"
                "Kirim link dari: TikTok, Douyin, RedNote, Instagram, "
                "YouTube, atau Facebook.",
                parse_mode="HTML",
            )
            continue

        info = PLATFORMS[platform]

        # Kirim pesan "sedang memproses"
        processing = bot.send_message(
            chat_id,
            f"⏳ <b>Sedang memproses...</b>\n\n"
            f"{info['emoji']} Mengekstrak video HD dari <b>{info['name']}</b>...\n"
            f"⏱ Mohon tunggu sebentar.",
            parse_mode="HTML",
        )

        try:
            # ── STEP 1: Ekstrak info & direct URL (cepat!) ──
            video_info = extract_video_info(url, platform)

            if not video_info["success"]:
                bot.edit_message_text(
                    f"❌ <b>Gagal mengekstrak video</b>\n\n"
                    f"<code>{video_info.get('error', 'Unknown')}</code>\n\n"
                    f"💡 Pastikan link valid dan video tidak private.",
                    chat_id=chat_id,
                    message_id=processing.message_id,
                    parse_mode="HTML",
                )
                continue

            # Update pesan dengan info resolusi
            resolution = video_info.get("resolution", "")
            res_text = f" ({resolution})" if resolution else ""

            bot.edit_message_text(
                f"📤 <b>Mengirim video HD{res_text}...</b>\n\n"
                f"{info['emoji']} {video_info.get('title', 'Video')}\n"
                f"⏱ {format_duration(video_info.get('duration', 0))}",
                chat_id=chat_id,
                message_id=processing.message_id,
                parse_mode="HTML",
            )

            # ── STEP 2: Kirim video ke user ──
            success = send_video_to_user(chat_id, video_info, info)

            # Hapus pesan processing
            try:
                bot.delete_message(chat_id, processing.message_id)
            except Exception:
                pass

            if success:
                logger.info(
                    f"✅ HD Download OK: {platform} {resolution} → user {chat_id}"
                )
            else:
                logger.warning(f"❌ Download gagal: {platform} → user {chat_id}")

        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            try:
                bot.edit_message_text(
                    f"❌ <b>Error:</b> <code>{str(e)[:120]}</code>\n\n"
                    f"💡 Coba lagi atau kirim link yang berbeda.",
                    chat_id=chat_id,
                    message_id=processing.message_id,
                    parse_mode="HTML",
                )
            except Exception:
                pass


# ── Flask Routes (Vercel Endpoints) ──────────────────────

@app.route("/", methods=["GET"])
def index():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "bot": "Video Downloader Bot HD",
        "version": "2.0",
        "features": ["HD quality", "No watermark", "6 platforms"],
        "platforms": list(PLATFORMS.keys()),
    })


@app.route("/api/webhook", methods=["POST"])
def webhook():
    """Endpoint webhook yang dipanggil Telegram."""
    if request.headers.get("content-type") == "application/json":
        json_data = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])
        return "OK", 200
    return "Bad Request", 400


@app.route("/api/set_webhook", methods=["GET"])
def set_webhook():
    """
    Endpoint untuk mendaftarkan webhook ke Telegram.
    Akses URL ini 1x setelah deploy:
    https://your-app.vercel.app/api/set_webhook
    """
    vercel_url = request.host_url.rstrip("/")
    webhook_url = f"{vercel_url}/api/webhook"

    # Hapus webhook lama & set yang baru
    bot.remove_webhook()
    success = bot.set_webhook(url=webhook_url)

    if success:
        return jsonify({
            "status": "success",
            "message": f"Webhook berhasil di-set ke: {webhook_url}",
            "webhook_url": webhook_url,
            "quality": "HD (up to 1080p)",
        })
    else:
        return jsonify({
            "status": "error",
            "message": "Gagal set webhook. Cek BOT_TOKEN.",
        }), 500


# ── Untuk Development Lokal ──────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("🎬 Video Downloader Bot HD — Local Mode")
    print("🎞 Quality: HD (up to 1080p)")
    print("📌 Mode: Polling (local development)")
    print("=" * 50)
    bot.remove_webhook()
    bot.infinity_polling()
