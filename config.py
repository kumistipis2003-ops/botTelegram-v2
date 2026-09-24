"""
Konfigurasi bot dan konstanta.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Bot Token ──────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# ── Direktori Download Sementara ──────────────────────────
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ── Platform yang Didukung ────────────────────────────────
SUPPORTED_PLATFORMS = {
    "tiktok": {
        "name": "TikTok",
        "emoji": "🎵",
        "domains": ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com"],
    },
    "douyin": {
        "name": "Douyin",
        "emoji": "🎶",
        "domains": ["douyin.com", "v.douyin.com", "iesdouyin.com"],
    },
    "rednote": {
        "name": "RedNote (小红书)",
        "emoji": "📕",
        "domains": ["xiaohongshu.com", "xhslink.com", "xhs.link"],
    },
    "instagram": {
        "name": "Instagram",
        "emoji": "📸",
        "domains": ["instagram.com", "instagr.am"],
    },
    "youtube": {
        "name": "YouTube",
        "emoji": "▶️",
        "domains": ["youtube.com", "youtu.be", "youtube-nocookie.com", "m.youtube.com"],
    },
    "facebook": {
        "name": "Facebook",
        "emoji": "📘",
        "domains": ["facebook.com", "fb.watch", "fb.com", "m.facebook.com"],
    },
}

# ── Pesan-pesan Bot ───────────────────────────────────────
WELCOME_MESSAGE = """
🎬 <b>Video Downloader Bot HD</b> — <i>Tanpa Watermark!</i>

Kirim link video dari platform berikut dan saya akan mendownloadnya dalam <b>kualitas HD</b> 🔥

🎵 <b>TikTok</b> — Video HD tanpa watermark
🎶 <b>Douyin</b> — Video HD tanpa watermark
📕 <b>RedNote (小红书)</b> — Video & gambar HD
📸 <b>Instagram</b> — Reels, Post & Stories HD
▶️ <b>YouTube</b> — Video & Shorts HD (1080p)
📘 <b>Facebook</b> — Video & Reels HD

━━━━━━━━━━━━━━━━━━━━━━
📌 <b>Cara Pakai:</b> Cukup kirim/paste link video
⚡ Proses otomatis, kualitas HD, tanpa watermark!
━━━━━━━━━━━━━━━━━━━━━━
"""

PROCESSING_MESSAGE = "⏳ <b>Sedang memproses...</b>\n\n{emoji} Mendownload dari <b>{platform}</b>...\n⏱ Mohon tunggu sebentar."

SUCCESS_MESSAGE = """
✅ <b>Download Berhasil!</b>

{emoji} <b>Platform:</b> {platform}
📹 <b>Judul:</b> {title}
⏱ <b>Durasi:</b> {duration}
📏 <b>Ukuran:</b> {size}

<i>— Downloaded by @YourBotUsername</i>
"""

ERROR_MESSAGE = """
❌ <b>Download Gagal</b>

Maaf, terjadi masalah saat mendownload video:
<code>{error}</code>

💡 <b>Tips:</b>
• Pastikan link valid dan video masih tersedia
• Coba lagi dalam beberapa saat
• Pastikan video tidak di-private
"""

UNSUPPORTED_MESSAGE = """
⚠️ <b>Platform Tidak Didukung</b>

Link yang kamu kirim tidak dikenali. Platform yang didukung:

🎵 TikTok  •  🎶 Douyin  •  📕 RedNote
📸 Instagram  •  ▶️ YouTube  •  📘 Facebook

📌 Kirim link video dari platform di atas.
"""

FILE_TOO_LARGE_MESSAGE = """
⚠️ <b>File Terlalu Besar</b>

Ukuran video melebihi batas Telegram ({max_size}MB).
Saya akan mengirim link download sebagai gantinya.
"""

HELP_MESSAGE = """
📖 <b>Bantuan Video Downloader Bot</b>

<b>Cara Menggunakan:</b>
1️⃣ Salin link video dari aplikasi/browser
2️⃣ Paste link tersebut di chat ini
3️⃣ Tunggu bot memproses dan mengirim video

<b>Command:</b>
/start — Mulai bot
/help — Tampilkan bantuan ini
/stats — Lihat statistik (admin only)

<b>Platform yang Didukung:</b>
🎵 TikTok — tiktok.com, vm.tiktok.com
🎶 Douyin — douyin.com, v.douyin.com
📕 RedNote — xiaohongshu.com, xhslink.com
📸 Instagram — instagram.com
▶️ YouTube — youtube.com, youtu.be
📘 Facebook — facebook.com, fb.watch

<b>Catatan:</b>
• Maksimal ukuran file: {max_size}MB
• Video private mungkin tidak bisa didownload
• Pastikan link lengkap dan valid
"""
