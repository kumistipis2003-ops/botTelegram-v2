"""
Modul downloader — menggunakan yt-dlp untuk mendownload video
dari berbagai platform tanpa watermark.
"""
import os
import re
import time
import asyncio
import logging
from urllib.parse import urlparse
from dataclasses import dataclass, field
from typing import Optional

import json
import urllib.parse
import urllib.request
import requests
import yt_dlp

from config import DOWNLOAD_DIR, MAX_FILE_SIZE_BYTES, SUPPORTED_PLATFORMS

logger = logging.getLogger(__name__)


# ── Data Classes ──────────────────────────────────────────

@dataclass
class DownloadResult:
    """Hasil download video."""
    success: bool
    file_path: Optional[str] = None
    title: str = "Untitled"
    duration: int = 0          # dalam detik
    file_size: int = 0         # dalam bytes
    platform: str = "unknown"
    thumbnail_url: Optional[str] = None
    error: Optional[str] = None
    is_image: bool = False
    image_paths: list = field(default_factory=list)


# ── Utilitas ──────────────────────────────────────────────

def detect_platform(url: str) -> Optional[str]:
    """Deteksi platform dari URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")

        for platform_key, platform_info in SUPPORTED_PLATFORMS.items():
            for d in platform_info["domains"]:
                if domain == d or domain.endswith("." + d):
                    return platform_key
    except Exception:
        pass
    return None


def extract_urls(text: str) -> list[str]:
    """Ekstrak semua URL dari teks."""
    url_pattern = re.compile(
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\-.~:/?#\[\]@!$&\'()*+,;=%]*'
    )
    return url_pattern.findall(text)


def format_duration(seconds: int) -> str:
    """Format durasi dari detik ke HH:MM:SS atau MM:SS."""
    if seconds <= 0:
        return "N/A"
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_file_size(size_bytes: int) -> str:
    """Format ukuran file ke human-readable."""
    if size_bytes <= 0:
        return "N/A"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _clean_old_downloads(max_age_seconds: int = 3600):
    """Bersihkan file download yang sudah lama (default: 1 jam)."""
    now = time.time()
    try:
        for filename in os.listdir(DOWNLOAD_DIR):
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            if os.path.isfile(filepath):
                file_age = now - os.path.getmtime(filepath)
                if file_age > max_age_seconds:
                    os.remove(filepath)
                    logger.debug(f"Cleaned up old file: {filename}")
    except Exception as e:
        logger.warning(f"Cleanup error: {e}")


# ── YT-DLP Options per Platform ──────────────────────────

def _get_ydl_opts(platform: str, output_path: str) -> dict:
    """
    Mendapatkan opsi yt-dlp yang disesuaikan per platform.
    Setiap platform memiliki konfigurasi optimal yang berbeda.
    """

    # Opsi dasar yang berlaku untuk semua platform
    base_opts = {
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "noplaylist": True,             # Hanya download 1 video, bukan playlist
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        },
    }

    # Konfigurasi spesifik per platform
    platform_opts = {
        "tiktok": {
            "format": "best",
            # yt-dlp otomatis cari versi non-watermark untuk TikTok
        },
        "douyin": {
            "format": "best",
        },
        "rednote": {
            "format": "best",
        },
        "instagram": {
            "format": "best",
            # Mungkin butuh cookies untuk beberapa konten
        },
        "youtube": {
            # Download kualitas terbaik ≤1080p agar ukuran tidak terlalu besar
            "format": (
                "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo[height<=1080]+bestaudio/"
                "best[height<=1080]/"
                "best"
            ),
            "merge_output_format": "mp4",
        },
        "facebook": {
            "format": "best",
        },
    }

    opts = {**base_opts, **platform_opts.get(platform, {})}
    return opts


# ── Core Downloader ──────────────────────────────────────

async def download_video(url: str, platform: str) -> DownloadResult:
    """
    Download video dari URL yang diberikan.
    Menjalankan yt-dlp secara asynchronous di thread pool.
    """
    # Bersihkan file lama
    _clean_old_downloads()

    # Buat nama file unik
    timestamp = int(time.time() * 1000)
    output_template = os.path.join(DOWNLOAD_DIR, f"{platform}_{timestamp}")
    output_path = output_template + ".%(ext)s"

    logger.info(f"Downloading from {platform}: {url}")

    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None, _sync_download, url, platform, output_path, output_template
        )
        return result
    except Exception as e:
        logger.error(f"Download error for {url}: {e}")
        return DownloadResult(
            success=False,
            platform=platform,
            error=str(e),
        )


def _extract_rednote(url: str) -> dict:
    """Ekstrak video/foto RedNote tanpa watermark via mobile headers."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        opener = urllib.request.build_opener()
        resp = opener.open(req, timeout=12)
        final_url = resp.geturl()
        html = resp.read().decode("utf-8", errors="ignore")

        if "login?redirectPath=" in final_url or "login?redirectPath=" in html:
            m_redirect = re.search(r'redirectPath=([^"\'&]+)', final_url) or re.search(r'redirectPath=([^"\'&]+)', html)
            if m_redirect:
                target = urllib.parse.unquote(m_redirect.group(1))
                req2 = urllib.request.Request(target, headers=headers)
                resp2 = opener.open(req2, timeout=12)
                html = resp2.read().decode("utf-8", errors="ignore")

        m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});?</script>', html)
        if not m:
            return {"success": False, "error": "Tidak dapat membaca halaman RedNote."}

        clean_json = m.group(1).replace(":undefined", ":null")
        data = json.loads(clean_json)
        note = data.get("noteData", {}).get("data", {}).get("noteData", {})
        if not note and "note" in data:
            detail = data.get("note", {}).get("noteDetailMap", {})
            if detail:
                note = list(detail.values())[0].get("note", {})

        if not note:
            return {"success": False, "error": "Data note tidak ditemukan."}

        title = note.get("title") or (note.get("desc", "").strip()[:80] if note.get("desc") else "RedNote Video")
        video = note.get("video", {})
        media = video.get("media", {})
        stream = media.get("stream", {})

        formats = stream.get("h264") or stream.get("h265") or []
        if not formats:
            return {"success": False, "error": "Video tidak ditemukan (kemungkinan postingan foto)."}

        best_fmt = max(formats, key=lambda f: (f.get("height", 0), f.get("videoBitrate", 0)))
        direct_url = best_fmt.get("masterUrl") or (best_fmt.get("backupUrls", [None])[0])

        return {
            "success": True,
            "title": title,
            "url": direct_url,
            "duration": int(best_fmt.get("duration", 0) / 1000) if best_fmt.get("duration") else 0,
            "size": best_fmt.get("size", 0),
        }
    except Exception as e:
        logger.error(f"RedNote extraction error: {e}")
        return {"success": False, "error": str(e)}


def _sync_download(
    url: str, platform: str, output_path: str, output_template: str
) -> DownloadResult:
    """Operasi download sinkron (dijalankan di thread pool)."""

    # Khusus RedNote: coba direct download dari custom extractor
    if platform == "rednote" or "xhs" in url or "xiaohongshu" in url:
        try:
            rn_info = _extract_rednote(url)
            if rn_info.get("success") and rn_info.get("url"):
                direct_url = rn_info["url"]
                target_file = output_path.replace("%(ext)s", "mp4")
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.xiaohongshu.com/",
                }
                resp = requests.get(direct_url, headers=headers, stream=True, timeout=30)
                if resp.status_code in (200, 206):
                    with open(target_file, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                    if os.path.exists(target_file) and os.path.getsize(target_file) > 0:
                        return DownloadResult(
                            success=True,
                            platform=platform,
                            file_path=target_file,
                            title=rn_info.get("title", "RedNote Video"),
                            duration=rn_info.get("duration", 0),
                            file_size=os.path.getsize(target_file),
                        )
        except Exception as e:
            logger.warning(f"RedNote custom download failed, trying yt-dlp: {e}")

    ydl_opts = _get_ydl_opts(platform, output_path)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Pertama, extract info tanpa download
            info = ydl.extract_info(url, download=False)
            if info is None:
                return DownloadResult(
                    success=False, platform=platform,
                    error="Tidak bisa mengekstrak info video."
                )

            title = info.get("title", "Untitled")
            duration = info.get("duration", 0) or 0
            thumbnail = info.get("thumbnail", None)

            # Cek estimasi ukuran file
            filesize_approx = info.get("filesize_approx") or info.get("filesize") or 0

            # Jika terlalu besar, coba format yang lebih kecil
            if filesize_approx > MAX_FILE_SIZE_BYTES and platform == "youtube":
                ydl_opts["format"] = (
                    "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
                    "bestvideo[height<=720]+bestaudio/"
                    "best[height<=720]/"
                    "best"
                )

            # Download
            with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
                ydl2.download([url])

            # Cari file yang didownload
            downloaded_file = _find_downloaded_file(output_template)

            if downloaded_file is None:
                return DownloadResult(
                    success=False, platform=platform,
                    error="File download tidak ditemukan."
                )

            file_size = os.path.getsize(downloaded_file)

            # Cek ukuran final
            if file_size > MAX_FILE_SIZE_BYTES:
                os.remove(downloaded_file)
                return DownloadResult(
                    success=False, platform=platform,
                    title=title, duration=duration,
                    error=f"File terlalu besar ({format_file_size(file_size)}). "
                          f"Batas Telegram: {MAX_FILE_SIZE_BYTES // (1024*1024)}MB.",
                )

            return DownloadResult(
                success=True,
                file_path=downloaded_file,
                title=title[:100],  # Potong judul agar tidak terlalu panjang
                duration=duration,
                file_size=file_size,
                platform=platform,
                thumbnail_url=thumbnail,
            )

    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        # Buat pesan error lebih user-friendly
        if "Private" in error_msg or "private" in error_msg:
            error_msg = "Video ini bersifat private dan tidak bisa didownload."
        elif "unavailable" in error_msg.lower():
            error_msg = "Video tidak tersedia atau sudah dihapus."
        elif "login" in error_msg.lower() or "sign in" in error_msg.lower():
            error_msg = "Video memerlukan login untuk diakses."
        elif "geo" in error_msg.lower() or "country" in error_msg.lower():
            error_msg = "Video tidak tersedia di region server bot."
        else:
            # Singkatkan pesan error
            error_msg = error_msg[:200]

        return DownloadResult(
            success=False, platform=platform, error=error_msg
        )
    except Exception as e:
        return DownloadResult(
            success=False, platform=platform,
            error=f"Error tidak terduga: {str(e)[:150]}"
        )


def _find_downloaded_file(output_template: str) -> Optional[str]:
    """Cari file yang sudah didownload berdasarkan template nama."""
    directory = os.path.dirname(output_template)
    basename = os.path.basename(output_template)

    try:
        for filename in os.listdir(directory):
            if filename.startswith(basename):
                filepath = os.path.join(directory, filename)
                if os.path.isfile(filepath) and os.path.getsize(filepath) > 0:
                    return filepath
    except Exception:
        pass
    return None


def cleanup_file(file_path: str):
    """Hapus file setelah berhasil dikirim."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"Cleaned up: {file_path}")
    except Exception as e:
        logger.warning(f"Failed to clean up {file_path}: {e}")
